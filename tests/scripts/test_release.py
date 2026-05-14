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


def test_trailer_accepts_emoji_prefixed_section_name():
    msg = "refactor: rename API\n\nChangelog: ✨ Added"
    assert release._parse_commit(msg)[0] == "✨ Added"


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


def test_push_removed_changelog_is_also_detected():
    # If a branch deletes CHANGELOG.md, skip too — otherwise the bot's next
    # read_text() would raise FileNotFoundError.
    assert release._push_touched_changelog([{"removed": ["CHANGELOG.md"]}]) is True


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
    cl_path.write_text(_MINIMAL_CHANGELOG, encoding="utf-8")
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
    text = tmp_changelog.read_text(encoding="utf-8")
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
    assert tmp_changelog.read_text(encoding="utf-8") == _MINIMAL_CHANGELOG


def test_append_many_honours_changelog_section_trailer(tmp_changelog, monkeypatch):
    commits = [
        {
            "id": "abc1234",
            "message": "refactor: rename API\n\nChangelog: Changed",
            "modified": ["src/foo.py"],
        },
    ]
    _drive_append_many(commits, monkeypatch)
    text = tmp_changelog.read_text(encoding="utf-8")
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
    text = tmp_changelog.read_text(encoding="utf-8")
    assert "add widget" in text
    assert "fixup review feedback" not in text


def test_append_many_with_empty_stdin_is_noop(tmp_changelog, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    release.cmd_append_many(None)
    assert tmp_changelog.read_text(encoding="utf-8") == _MINIMAL_CHANGELOG


# ---------------------------------------------------------------------------
# cmd_append (single-commit path) — must apply the same skip rules
# ---------------------------------------------------------------------------


def test_append_writes_entry_for_normal_commit(tmp_changelog, monkeypatch):
    monkeypatch.setenv("COMMIT_MSG", "feat: add widget")
    release.cmd_append(None)
    text = tmp_changelog.read_text(encoding="utf-8")
    assert "✨ Added" in text
    assert "add widget" in text


def test_append_honours_changelog_skip_trailer(tmp_changelog, monkeypatch):
    monkeypatch.setenv("COMMIT_MSG", "fix: tiny follow-up\n\nChangelog: skip")
    release.cmd_append(None)
    assert tmp_changelog.read_text(encoding="utf-8") == _MINIMAL_CHANGELOG


def test_append_skips_merge_commits(tmp_changelog, monkeypatch):
    monkeypatch.setenv("COMMIT_MSG", "Merge pull request #99 from foo/bar")
    release.cmd_append(None)
    assert tmp_changelog.read_text(encoding="utf-8") == _MINIMAL_CHANGELOG


# ---------------------------------------------------------------------------
# cmd_bump — version bumping (release + prerelease semantics)
# ---------------------------------------------------------------------------


class _BumpArgs:
    """Minimal stand-in for argparse Namespace passed to cmd_bump."""

    def __init__(self, current: str, bump: str, prerelease: str | None = None) -> None:
        self.current = current
        self.bump = bump
        self.prerelease = prerelease


def _bump(capsys, current: str, bump: str, prerelease: str | None = None) -> str:
    release.cmd_bump(_BumpArgs(current, bump, prerelease))
    return capsys.readouterr().out.strip()


def test_bump_major_minor_patch(capsys):
    assert _bump(capsys, "1.3.0", "major") == "2.0.0"
    assert _bump(capsys, "1.3.0", "minor") == "1.4.0"
    assert _bump(capsys, "1.3.0", "patch") == "1.3.1"


def test_bump_major_with_alpha_starts_prerelease(capsys):
    assert _bump(capsys, "1.3.0", "major", "alpha") == "2.0.0a1"
    assert _bump(capsys, "1.3.0", "minor", "beta") == "1.4.0b1"
    assert _bump(capsys, "1.3.0", "patch", "rc") == "1.3.1rc1"


def test_bump_prerelease_increments_counter(capsys):
    assert _bump(capsys, "2.0.0a1", "prerelease") == "2.0.0a2"
    assert _bump(capsys, "2.0.0b5", "prerelease") == "2.0.0b6"
    assert _bump(capsys, "1.4.0rc1", "prerelease") == "1.4.0rc2"


def test_bump_prerelease_requires_existing_prerelease():
    with pytest.raises(SystemExit):
        release.cmd_bump(_BumpArgs("2.0.0", "prerelease"))


def test_bump_finalize_drops_prerelease_suffix(capsys):
    assert _bump(capsys, "2.0.0a3", "finalize") == "2.0.0"
    assert _bump(capsys, "1.4.0rc2", "finalize") == "1.4.0"


def test_bump_finalize_requires_existing_prerelease():
    with pytest.raises(SystemExit):
        release.cmd_bump(_BumpArgs("2.0.0", "finalize"))


def test_bump_release_drops_prerelease_from_current(capsys):
    # Bumping major/minor/patch from a prerelease ignores the suffix on `current`.
    assert _bump(capsys, "2.0.0a3", "major") == "3.0.0"
    assert _bump(capsys, "2.0.0a3", "minor") == "2.1.0"
    assert _bump(capsys, "2.0.0a3", "patch") == "2.0.1"


def test_bump_rejects_unparseable_version():
    with pytest.raises(SystemExit):
        release.cmd_bump(_BumpArgs("not-a-version", "patch"))


def test_bump_prerelease_flag_invalid_with_prerelease_bump():
    with pytest.raises(SystemExit):
        release.cmd_bump(_BumpArgs("2.0.0a1", "prerelease", "alpha"))
