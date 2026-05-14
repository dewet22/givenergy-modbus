"""Tests for the changelog-bot helper in scripts/release.py.

Covers the auto-bucketing of conventional commits and the three opt-in
overrides:

- `Changelog: <section>` trailer to redirect a commit's entry
- `Changelog: skip` trailer to suppress an entry
- Branch-managed CHANGELOG.md: any push that touches the file skips the bot
"""

import io
import json
import sys
from pathlib import Path

import pytest

# scripts/ isn't a package, so make release.py importable by name.
_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import release  # noqa: E402, I001


# ---------------------------------------------------------------------------
# _parse_commit — automatic bucketing
# ---------------------------------------------------------------------------


def test_feat_lands_in_added():
    assert release._parse_commit("feat: add foo")[0] == "✨ Added"


def test_fix_lands_in_fixed():
    assert release._parse_commit("fix: correct bar")[0] == "🐛 Fixed"


def test_refactor_lands_in_maintenance_by_default():
    assert release._parse_commit("refactor: extract helper")[0] == "🔧 Maintenance"


def test_breaking_change_lands_in_changed_with_prefix():
    section, description = release._parse_commit("feat!: redesign API")
    assert section == "🔄 Changed"
    assert description.startswith("⚠️ Breaking: ")


def test_unknown_type_falls_back_to_changed():
    assert release._parse_commit("flarble: something odd")[0] == "🔄 Changed"


def test_non_conventional_subject_falls_back_to_changed():
    section, description = release._parse_commit("just a plain sentence")
    assert section == "🔄 Changed"
    assert description == "just a plain sentence"


def test_scoped_type_still_parses():
    assert release._parse_commit("feat(api): add endpoint")[0] == "✨ Added"


# ---------------------------------------------------------------------------
# Changelog: <section> trailer override
# ---------------------------------------------------------------------------


def test_trailer_overrides_section():
    msg = "refactor: rename slave→device\n\nLonger body\n\nChangelog: Changed"
    assert release._parse_commit(msg)[0] == "🔄 Changed"


def test_trailer_is_case_insensitive():
    msg = "refactor: rename slave→device\n\nchangelog: changed"
    assert release._parse_commit(msg)[0] == "🔄 Changed"


def test_trailer_with_unknown_section_is_ignored():
    msg = "feat: add foo\n\nChangelog: Whatever"
    # Falls back to the conventional-commit default, not silently picking something else.
    assert release._parse_commit(msg)[0] == "✨ Added"


def test_trailer_skip_does_not_override_section_in_parse():
    # _parse_commit shouldn't crash on skip; skipping is _is_skippable_commit's job.
    msg = "fix: process noise\n\nChangelog: skip"
    section, _ = release._parse_commit(msg)
    assert section == "🐛 Fixed"


def test_last_trailer_wins_when_multiple_present():
    # Standard git-trailer semantics: the final occurrence is authoritative.
    msg = "refactor: foo\n\nChangelog: Maintenance\nChangelog: Changed"
    assert release._parse_commit(msg)[0] == "🔄 Changed"


def test_trailer_inside_body_text_still_matches():
    # The trailer detector uses MULTILINE rather than strict end-of-message position,
    # so a `Changelog:` line anywhere in the body counts.
    msg = "refactor: foo\n\nSome context here.\nChangelog: Added\n\nMore narrative."
    assert release._parse_commit(msg)[0] == "✨ Added"


# ---------------------------------------------------------------------------
# _is_skippable_commit
# ---------------------------------------------------------------------------


def test_merge_pr_commits_are_skipped():
    assert release._is_skippable_commit("Merge pull request #61 from foo/bar") is True


def test_merge_branch_commits_are_skipped():
    assert release._is_skippable_commit("Merge branch 'main' into feature") is True


def test_bot_changelog_commit_is_skipped():
    assert release._is_skippable_commit("chore: update [Unreleased] changelog") is True


def test_other_chore_changelog_commits_are_skipped():
    assert release._is_skippable_commit("chore: tidy changelog formatting") is True


def test_normal_commit_is_not_skipped():
    assert release._is_skippable_commit("feat: add new thing") is False


def test_changelog_skip_trailer_skips_commit():
    msg = "fix: fold in review feedback\n\nChangelog: skip"
    assert release._is_skippable_commit(msg) is True


def test_changelog_skip_trailer_is_case_insensitive():
    msg = "fix: fold in review feedback\n\nchangelog: SKIP"
    assert release._is_skippable_commit(msg) is True


# ---------------------------------------------------------------------------
# _push_touched_changelog
# ---------------------------------------------------------------------------


def test_push_touched_changelog_modified():
    assert release._push_touched_changelog([{"modified": ["CHANGELOG.md", "foo.py"]}]) is True


def test_push_touched_changelog_added():
    assert release._push_touched_changelog([{"added": ["CHANGELOG.md"]}]) is True


def test_push_did_not_touch_changelog():
    assert release._push_touched_changelog([{"modified": ["foo.py", "bar.py"]}]) is False


def test_push_with_no_file_info_does_not_touch():
    assert release._push_touched_changelog([{}, {"message": "x"}]) is False


def test_push_with_one_commit_touching_changelog_marks_whole_push():
    commits = [
        {"modified": ["foo.py"]},
        {"modified": ["CHANGELOG.md"]},
        {"modified": ["bar.py"]},
    ]
    assert release._push_touched_changelog(commits) is True


# ---------------------------------------------------------------------------
# cmd_append_many — integration via tmp CHANGELOG.md
# ---------------------------------------------------------------------------

_MINIMAL_CHANGELOG = """\
# Changelog

## [Unreleased]

## [1.0.0] - 2026-01-01
"""


@pytest.fixture
def tmp_changelog(tmp_path, monkeypatch):
    """Point the Changelog class at a temporary file populated with a minimal skeleton."""
    cl_path = tmp_path / "CHANGELOG.md"
    cl_path.write_text(_MINIMAL_CHANGELOG)
    monkeypatch.setattr(release, "CHANGELOG", cl_path)
    return cl_path


def _drive_append_many(commits: list[dict], monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(commits)))
    release.cmd_append_many(None)


def test_append_many_writes_entries(tmp_changelog, monkeypatch):
    commits = [
        {"id": "abc1234", "message": "feat: add widget", "author": {"username": "alice"}, "modified": ["src/foo.py"]},
        {"id": "def5678", "message": "fix: bar", "author": {"username": "alice"}, "modified": ["src/bar.py"]},
    ]
    _drive_append_many(commits, monkeypatch)
    text = tmp_changelog.read_text()
    assert "✨ Added" in text
    assert "add widget" in text
    assert "🐛 Fixed" in text
    assert "bar" in text


def test_append_many_skips_when_changelog_touched_in_push(tmp_changelog, monkeypatch):
    commits = [
        {"id": "abc1234", "message": "feat: add widget", "modified": ["src/foo.py"]},
        {"id": "def5678", "message": "docs: hand-write changelog entry", "modified": ["CHANGELOG.md"]},
    ]
    _drive_append_many(commits, monkeypatch)
    # File is untouched — no entries appended for either commit.
    assert tmp_changelog.read_text() == _MINIMAL_CHANGELOG


def test_append_many_honours_changelog_section_trailer(tmp_changelog, monkeypatch):
    commits = [
        {
            "id": "abc1234",
            "message": "refactor: rename API\n\nChangelog: Changed",
            "modified": ["src/foo.py"],
        },
    ]
    _drive_append_many(commits, monkeypatch)
    text = tmp_changelog.read_text()
    assert "🔄 Changed" in text
    # Should NOT land in Maintenance, the default for refactor:
    assert "🔧 Maintenance" not in text


def test_append_many_honours_changelog_skip_trailer(tmp_changelog, monkeypatch):
    commits = [
        {"id": "abc1234", "message": "feat: add widget", "modified": ["src/foo.py"]},
        {
            "id": "def5678",
            "message": "fix: fixup review feedback\n\nChangelog: skip",
            "modified": ["src/foo.py"],
        },
    ]
    _drive_append_many(commits, monkeypatch)
    text = tmp_changelog.read_text()
    assert "add widget" in text
    assert "fixup review feedback" not in text


def test_append_many_with_empty_stdin_is_noop(tmp_changelog, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    release.cmd_append_many(None)
    assert tmp_changelog.read_text() == _MINIMAL_CHANGELOG
