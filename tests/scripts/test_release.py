"""Tests for the release-helper logic in scripts/release.py."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# scripts/ isn't a package; make release.py importable by filename.
_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import release  # type: ignore[import-not-found]  # noqa: E402

# ---------------------------------------------------------------------------
# _parse_commit: section classification from conventional prefixes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "subject,expected_section,expected_description",
    [
        ("feat: add fancy thing", "Added", "add fancy thing"),
        ("fix: stop the crash", "Fixed", "stop the crash"),
        ("fix(client): scope to client", "Fixed", "scope to client"),
        ("perf: faster", "Changed", "faster"),
        ("refactor: tidy up", "Changed", "tidy up"),
        ("revert: undo the thing", "Fixed", "undo the thing"),
        ("security: patch the hole", "Security", "patch the hole"),
        ("docs: explain better", "Changed", "explain better"),
        ("chore: bump dep", "Maintenance", "bump dep"),
        ("ci: tweak workflow", "Maintenance", "tweak workflow"),
        ("test: add coverage", "Maintenance", "add coverage"),
        ("Just a normal subject", "Changed", "Just a normal subject"),
    ],
)
def test_parse_commit_routes_by_prefix(subject, expected_section, expected_description):
    section, description = release._parse_commit(subject)
    assert section == expected_section
    assert description == expected_description


def test_parse_commit_breaking_marker_routes_to_changed():
    section, description = release._parse_commit("feat!: rewrite the world")
    assert section == "Changed"
    assert description == "⚠️ Breaking: rewrite the world"


def test_parse_commit_breaking_with_scope():
    section, description = release._parse_commit("feat(api)!: drop legacy endpoint")
    assert section == "Changed"
    assert description == "⚠️ Breaking: drop legacy endpoint"


# ---------------------------------------------------------------------------
# Changelog: trailer overrides
# ---------------------------------------------------------------------------


def test_changelog_trailer_skip_returns_skip_section():
    message = "fix: tiny tweak\n\nbody text\n\nChangelog: skip"
    section, description = release._parse_commit(message)
    assert section == "skip"
    assert description == "tiny tweak"


def test_changelog_trailer_overrides_section():
    message = "refactor: rename slave_address → device_address\n\nChangelog: Changed"
    section, _ = release._parse_commit(message)
    assert section == "Changed"


def test_changelog_trailer_is_case_insensitive():
    message = "chore: noise\n\nchangelog: fixed"
    section, _ = release._parse_commit(message)
    assert section == "Fixed"


def test_last_changelog_trailer_wins():
    message = "fix: something\n\nbody\n\nChangelog: Added\nChangelog: Removed"
    section, _ = release._parse_commit(message)
    assert section == "Removed"


def test_changelog_trailer_unknown_section_falls_back_to_prefix():
    """Unrecognised override drops back to the conventional-prefix-derived section."""
    message = "fix: real bug\n\nChangelog: NotARealSection"
    section, _ = release._parse_commit(message)
    assert section == "Fixed"


def test_changelog_trailer_not_in_final_paragraph_is_ignored():
    """Trailers live in the last paragraph only — earlier mentions don't count."""
    message = "fix: a thing\n\nChangelog: Added\n\nsome trailing prose"
    section, _ = release._parse_commit(message)
    assert section == "Fixed"


# ---------------------------------------------------------------------------
# Skippable commits
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "subject",
    [
        "Merge pull request #42 from foo/bar",
        "Merge branch 'feature/x' into main",
        "chore: release 2.0.0a1",
        "chore: release 1.3.0",
        "chore: update [Unreleased] changelog",
    ],
)
def test_skippable_commits(subject):
    assert release._is_skippable_commit(subject) is True


def test_non_skippable_commits():
    assert release._is_skippable_commit("fix: a real bug") is False
    assert release._is_skippable_commit("chore: not a release") is False


# ---------------------------------------------------------------------------
# Classification and rendering
# ---------------------------------------------------------------------------


def test_classify_and_render_groups_by_section(monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    commits = [
        ("aaaaaaa", "feat: new thing"),
        ("bbbbbbb", "fix: a bug"),
        ("ccccccc", "chore: bump dep"),
        ("ddddddd", "fix: another bug"),
    ]
    sections = release._classify_commits(commits)
    body = release._render_body(sections)
    expected = "### Added\n\n- new thing\n\n### Fixed\n\n- a bug\n- another bug\n\n### Maintenance\n\n- bump dep\n"
    assert body == expected


def test_classify_drops_skip_trailer_and_skippable(monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    commits = [
        ("aaaaaaa", "fix: keeper"),
        ("bbbbbbb", "fix: dropped\n\nChangelog: skip"),
        ("ccccccc", "chore: release 1.2.3"),
        ("ddddddd", "Merge pull request #99 from foo/bar"),
    ]
    sections = release._classify_commits(commits)
    body = release._render_body(sections)
    assert body == "### Fixed\n\n- keeper\n"


def test_render_body_empty_when_no_entries():
    assert release._render_body({k: [] for k in release._SECTION_ORDER}) == ""


def test_render_body_section_order(monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    commits = [
        ("h1", "chore: maint"),
        ("h2", "security: lockdown"),
        ("h3", "feat: new"),
        ("h4", "fix: bug"),
    ]
    body = release._render_body(release._classify_commits(commits))
    # Verify sections appear in canonical order: Added → Fixed → Security → Maintenance
    assert (
        body.index("### Added") < body.index("### Fixed") < body.index("### Security") < body.index("### Maintenance")
    )


# ---------------------------------------------------------------------------
# Entry formatting with attribution
# ---------------------------------------------------------------------------


def test_format_entry_with_repo(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.delenv("GITHUB_SERVER_URL", raising=False)
    entry = release._format_entry("abcdef1234567", "fix something")
    assert entry == "- fix something ([abcdef1](https://github.com/owner/repo/commit/abcdef1234567))"


def test_format_entry_respects_custom_server(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://ghe.example.com/")
    entry = release._format_entry("abcdef1234567", "x")
    assert "https://ghe.example.com/owner/repo/commit/abcdef1234567" in entry


def test_format_entry_without_repo_omits_attribution(monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    assert release._format_entry("abcdef1234567", "y") == "- y"


# ---------------------------------------------------------------------------
# cmd_bump
# ---------------------------------------------------------------------------


def _bump_args(current, bump):
    class _Ns:
        pass

    a = _Ns()
    a.current = current
    a.bump = bump
    return a


def test_cmd_bump_patch(capsys):
    release.cmd_bump(_bump_args("1.2.3", "patch"))
    assert capsys.readouterr().out.strip() == "1.2.4"


def test_cmd_bump_minor_resets_patch(capsys):
    release.cmd_bump(_bump_args("1.2.5", "minor"))
    assert capsys.readouterr().out.strip() == "1.3.0"


def test_cmd_bump_major_resets_minor_and_patch(capsys):
    release.cmd_bump(_bump_args("1.9.9", "major"))
    assert capsys.readouterr().out.strip() == "2.0.0"


# ---------------------------------------------------------------------------
# cmd_generate end-to-end
# ---------------------------------------------------------------------------


def _generate_args(version, preview=False):
    class _Ns:
        pass

    a = _Ns()
    a.version = version
    a.preview = preview
    return a


def test_cmd_generate_writes_section_to_changelog(tmp_path, monkeypatch, capsys):
    cl_path = tmp_path / "CHANGELOG.md"
    cl_path.write_text("# Changelog\n\nHistorical preamble.\n\n## [1.0.0] - 2026-01-01\n\n### Added\n\n- initial\n")
    monkeypatch.setattr(release, "CHANGELOG", cl_path)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

    fake_commits = [
        ("aaaaaaa", "feat: shiny"),
        ("bbbbbbb", "fix: oops"),
    ]
    with patch.object(release, "_git_commits_since_last_tag", return_value=fake_commits):
        release.cmd_generate(_generate_args("1.1.0"))

    written = cl_path.read_text()
    assert "## [1.1.0]" in written
    # New section sits ABOVE the existing 1.0.0 section
    assert written.index("## [1.1.0]") < written.index("## [1.0.0]")
    assert "- shiny" in written
    assert "- oops" in written
    # stdout carries the body for the GitHub Release description
    out = capsys.readouterr().out
    assert "### Added" in out
    assert "### Fixed" in out
    assert "## [" not in out  # body only, no version header


def test_cmd_generate_preview_does_not_modify_file(tmp_path, monkeypatch, capsys):
    cl_path = tmp_path / "CHANGELOG.md"
    original = "# Changelog\n\n## [1.0.0] - 2026-01-01\n\n### Added\n\n- initial\n"
    cl_path.write_text(original)
    monkeypatch.setattr(release, "CHANGELOG", cl_path)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

    with patch.object(release, "_git_commits_since_last_tag", return_value=[("aaaa", "feat: shiny")]):
        release.cmd_generate(_generate_args("1.1.0", preview=True))

    assert cl_path.read_text() == original
    out = capsys.readouterr().out
    assert "## [1.1.0]" in out
    assert "- shiny" in out


def test_cmd_generate_empty_commit_list_warns_but_writes(tmp_path, monkeypatch, capsys):
    cl_path = tmp_path / "CHANGELOG.md"
    cl_path.write_text("# Changelog\n\n## [1.0.0] - 2026-01-01\n\n### Added\n\n- initial\n")
    monkeypatch.setattr(release, "CHANGELOG", cl_path)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

    with patch.object(release, "_git_commits_since_last_tag", return_value=[]):
        release.cmd_generate(_generate_args("1.0.1"))

    captured = capsys.readouterr()
    assert "no changelog-worthy commits" in captured.err
    assert "## [1.0.1]" in cl_path.read_text()
