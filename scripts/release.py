#!/usr/bin/env python3
"""Release helper: version bumping and CHANGELOG generation."""

import argparse
import os
import re

# Release tooling: invokes git with controlled arg lists only. PATH is controlled in CI.
import subprocess  # nosec B404
import sys
from datetime import date
from pathlib import Path

CHANGELOG = Path(__file__).parent.parent / "CHANGELOG.md"

# Optional hand-authored narrative per release: docs/release-notes/v<version>.md.
# When present, `generate` leads the section with it — finals after a long rc line
# otherwise ship a near-empty body (commits since the last rc only; the 2.1.0
# release description was a single bullet while all the substance sat in rc
# sections). The file carries the human story into both CHANGELOG.md and the
# GitHub Release description without making either hand-maintained.
RELEASE_NOTES_DIR = Path(__file__).parent.parent / "docs" / "release-notes"

_SECTION_ORDER: list[str] = [
    "✨ Added",
    "🔄 Changed",
    "⚠️ Deprecated",
    "🗑️ Removed",
    "🐛 Fixed",
    "🔒 Security",
    "🔧 Maintenance",
]

_COMMIT_TYPE_TO_SECTION: dict[str, str] = {
    "feat": "✨ Added",
    "fix": "🐛 Fixed",
    "perf": "🔄 Changed",
    "refactor": "🔧 Maintenance",
    "revert": "🐛 Fixed",
    "security": "🔒 Security",
    "docs": "🔧 Maintenance",
    "ci": "🔧 Maintenance",
    "chore": "🔧 Maintenance",
    "test": "🔧 Maintenance",
    "style": "🔧 Maintenance",
    "build": "🔧 Maintenance",
    "wip": "🔧 Maintenance",
}

# Trailer key that overrides automatic section bucketing on a per-commit basis.
# Values are either `skip` (suppress the entry) or any section name in _SECTION_ORDER
# (case-insensitive, emoji optional — `Changed` and `🔄 Changed` both resolve).
_CHANGELOG_TRAILER_RE = re.compile(r"^changelog\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)


def _resolve_section_alias(name: str) -> str | None:
    """Match a section name (e.g. 'Changed' or '✨ Added') to its emoji-prefixed form."""
    name = name.strip().lower()
    for section in _SECTION_ORDER:
        if section.lower() == name:
            return section
        textual = section.split(" ", 1)[-1].lower()
        if textual == name:
            return section
    return None


def _find_changelog_trailer(message: str) -> str | None:
    """Return the value of the last `Changelog:` trailer in the message, or None.

    Trailer must live in the final paragraph of the body to match git's own
    trailer semantics. Last `Changelog:` wins.
    """
    paragraphs = re.split(r"\n\s*\n", message.strip())
    if len(paragraphs) < 2:
        return None
    last = paragraphs[-1]
    matches = _CHANGELOG_TRAILER_RE.findall(last)
    return matches[-1].strip() if matches else None


class Changelog:
    """Line-by-line reader/writer for Keep a Changelog files."""

    def __init__(self, path: Path | None = None) -> None:
        # Resolve at call time so monkeypatching `release.CHANGELOG` in tests is honoured.
        self.path = path if path is not None else CHANGELOG
        # Section headers contain emoji; force UTF-8 to dodge Windows' cp1252 default.
        self.lines = self.path.read_text(encoding="utf-8").splitlines(keepends=True)

    def save(self) -> None:
        """Write the current line buffer back to disk."""
        self.path.write_text("".join(self.lines), encoding="utf-8")

    def prepend_version_section(self, version: str, today: str, body: str) -> None:
        r"""Insert a new versioned section above the most recent existing one.

        `body` is the rendered section body (the lines under the version header,
        e.g. `### 🐛 Fixed\n\n- ...`). The `## [version] - date` header is added here.
        """
        new_header = f"## [{version}] - {today}\n"
        block = [new_header, "\n", *body.splitlines(keepends=True)]
        if block and not block[-1].endswith("\n"):
            block[-1] += "\n"
        block.append("\n")

        for i, line in enumerate(self.lines):
            if line.startswith("## ["):
                self.lines[i:i] = block
                return
        # No existing version sections — append to the end of the preamble
        self.lines.extend(["\n", *block])


def _parse_commit(message: str) -> tuple[str, str]:
    """Return (changelog_section, description) for a conventional commit message.

    Honours the `Changelog:` trailer if present — `Changelog: skip` returns ("skip", "")
    so the caller can drop the commit, and `Changelog: <Section>` overrides the
    conventional-prefix-derived section.
    """
    subject = message.splitlines()[0].strip()
    m = re.match(r"^(\w+)(?:\([^)]*\))?(!)?\s*:\s*(.+)", subject)
    if not m:
        section, description = "🔄 Changed", subject
    else:
        commit_type, breaking, description = m.group(1).lower(), m.group(2), m.group(3).strip()
        section = "🔄 Changed" if breaking else _COMMIT_TYPE_TO_SECTION.get(commit_type, "🔄 Changed")
        if breaking:
            description = f"⚠️ Breaking: {description}"

    trailer = _find_changelog_trailer(message)
    if trailer is not None:
        if trailer.lower() == "skip":
            return "skip", description
        override = _resolve_section_alias(trailer)
        if override:
            section = override

    return section, description


def _is_skippable_commit(message: str) -> bool:
    """Return True for commits that shouldn't produce changelog entries.

    Skips:
    - Merge commits (the underlying feature commits are present separately).
    - The release commit itself (`chore: release <version>`).
    - Bot-generated `chore: update [Unreleased] changelog` commits (historical: the
      bot is retired, but these commits remain in the history of branches predating
      the changelog rework).
    - Any chore: commit whose subject mentions "changelog" — housekeeping edits to
      CHANGELOG.md itself, not user-visible changes.
    """
    subject = message.splitlines()[0].strip()
    if subject.startswith(("Merge pull request", "Merge branch")):
        return True
    if re.match(r"^chore: release \d", subject):
        return True
    if subject == "chore: update [Unreleased] changelog":
        return True
    if subject.startswith("chore:") and "changelog" in subject.lower():
        return True
    return False


def _git_commits_since_last_tag() -> list[tuple[str, str]]:
    """Return [(sha, message), ...] for commits between the most recent v* tag and HEAD.

    If no tag is reachable from HEAD, walks all of history. Commits are returned
    oldest-first so the rendered section reads chronologically.
    """
    try:
        # Fully literal arg list; PATH controlled in CI.
        prev_tag = subprocess.check_output(  # nosec B603 B607
            ["git", "describe", "--tags", "--abbrev=0", "--match=v*", "HEAD"],  # nosec B603 B607
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        rev_range = f"{prev_tag}..HEAD"
    except subprocess.CalledProcessError:
        rev_range = "HEAD"

    # `rev_range` is derived from `git describe` output (or "HEAD"), not user input.
    raw = subprocess.check_output(  # nosec B603 B607
        ["git", "log", rev_range, "--format=%H%x00%B%x1e", "--reverse"],  # nosec B603 B607
        text=True,
    )
    commits: list[tuple[str, str]] = []
    for record in raw.split("\x1e"):
        record = record.strip()
        if not record or "\x00" not in record:
            continue
        sha, message = record.split("\x00", 1)
        commits.append((sha.strip(), message.strip()))
    return commits


def _format_entry(sha: str, description: str) -> str:
    """Render a single changelog bullet with commit-hash attribution."""
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if repo:
        return f"- {description} ([{sha[:7]}]({server}/{repo}/commit/{sha}))"
    return f"- {description}"


def _render_body(sections: dict[str, list[str]]) -> str:
    """Render section dict to a CHANGELOG body string (no version header)."""
    parts: list[str] = []
    for name in _SECTION_ORDER:
        entries = sections.get(name)
        if not entries:
            continue
        if parts:
            parts.append("")
        parts.append(f"### {name}")
        parts.append("")
        parts.extend(entries)
    return "\n".join(parts) + "\n" if parts else ""


def _classify_commits(commits: list[tuple[str, str]]) -> dict[str, list[str]]:
    """Bucket commits into changelog sections, honouring skip-trailer and skippable rules."""
    sections: dict[str, list[str]] = {k: [] for k in _SECTION_ORDER}
    for sha, message in commits:
        if _is_skippable_commit(message):
            continue
        section, description = _parse_commit(message)
        if section == "skip":
            continue
        sections[section].append(_format_entry(sha, description))
    return sections


_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:(a|b|rc)(\d+))?$")
_PRERELEASE_STAGES = {"alpha": "a", "beta": "b", "rc": "rc"}

# PEP 440 prerelease ordering — `a` < `b` < `rc` < (release).
# Used by the prerelease-stage-switch path in cmd_bump to reject backwards moves.
_STAGE_ORDER: dict[str, int] = {"a": 0, "b": 1, "rc": 2}


def cmd_bump(args) -> None:
    """Print the next version given a current version and bump type.

    Bump types:
      major / minor / patch  — operate on the release tuple; any prerelease
                               suffix on `current` is dropped. Combine with
                               `--prerelease alpha|beta|rc` to start a new
                               prerelease line (e.g. 1.3.0 -> 2.0.0a1).
      prerelease             — increment the prerelease counter only
                               (2.0.0a1 -> 2.0.0a2). Requires current to
                               already have a prerelease suffix. Combine with
                               `--prerelease beta|rc` to advance the stage
                               (2.0.0a6 -> 2.0.0rc1); stage moves are
                               forward-only per PEP 440 ordering.
      finalize               — drop the prerelease suffix without changing
                               the release tuple (2.0.0a3 -> 2.0.0).
    """
    m = _VERSION_RE.match(args.current)
    if not m:
        print(f"ERROR: cannot parse version {args.current!r}", file=sys.stderr)
        sys.exit(1)
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    pre_stage, pre_n = m.group(4), m.group(5)

    if args.bump == "prerelease":
        if pre_stage is None:
            print(
                f"ERROR: prerelease bump requires current to have a prerelease suffix (got {args.current!r})",
                file=sys.stderr,
            )
            sys.exit(1)
        if args.prerelease:
            # Stage switch: a6 -> rc1, b2 -> rc1, etc. Counter resets to 1.
            new_stage = _PRERELEASE_STAGES[args.prerelease]
            if _STAGE_ORDER[new_stage] < _STAGE_ORDER[pre_stage]:
                print(
                    f"ERROR: cannot move backwards from {pre_stage!r} to {new_stage!r} (PEP 440 ordering: a < b < rc)",
                    file=sys.stderr,
                )
                sys.exit(1)
            if _STAGE_ORDER[new_stage] == _STAGE_ORDER[pre_stage]:
                print(
                    f"ERROR: already in stage {pre_stage!r}; omit --prerelease to increment the counter",
                    file=sys.stderr,
                )
                sys.exit(1)
            print(f"{major}.{minor}.{patch}{new_stage}1")
            return
        print(f"{major}.{minor}.{patch}{pre_stage}{int(pre_n) + 1}")
        return

    if args.bump == "finalize":
        if pre_stage is None:
            print(
                f"ERROR: finalize requires current to have a prerelease suffix (got {args.current!r})",
                file=sys.stderr,
            )
            sys.exit(1)
        if args.prerelease:
            print("ERROR: --prerelease cannot be combined with bump=finalize", file=sys.stderr)
            sys.exit(1)
        print(f"{major}.{minor}.{patch}")
        return

    if args.bump == "major":
        major, minor, patch = major + 1, 0, 0
    elif args.bump == "minor":
        minor, patch = minor + 1, 0
    else:  # patch
        patch += 1

    if args.prerelease:
        print(f"{major}.{minor}.{patch}{_PRERELEASE_STAGES[args.prerelease]}1")
    else:
        print(f"{major}.{minor}.{patch}")


def cmd_generate(args) -> None:
    """Generate a new versioned CHANGELOG section from commits since the last tag.

    Writes the section into CHANGELOG.md and prints the body (without the version
    header) to stdout — the release workflow captures stdout as the GitHub Release
    description. With `--preview`, only prints; does not modify the file.
    """
    commits = _git_commits_since_last_tag()
    sections = _classify_commits(commits)
    body = _render_body(sections)
    today = date.today().isoformat()

    notes_file = RELEASE_NOTES_DIR / f"v{args.version}.md"
    if notes_file.is_file():
        notes = notes_file.read_text(encoding="utf-8").strip()
        if notes:
            body = f"{notes}\n\n{body}" if body else f"{notes}\n"

    if args.preview:
        print(f"## [{args.version}] - {today}\n")
        print(body, end="")
        return

    if not body:
        print(
            f"WARNING: no changelog-worthy commits since the last tag — emitting an empty section for {args.version}",
            file=sys.stderr,
        )

    cl = Changelog()
    cl.prepend_version_section(args.version, today, body)
    cl.save()
    print(body, end="")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    bump_p = sub.add_parser("bump", help="Print next version number")
    bump_p.add_argument("current", help="Current version (e.g. 1.2.3 or 2.0.0a1)")
    bump_p.add_argument("bump", choices=["major", "minor", "patch", "prerelease", "finalize"])
    bump_p.add_argument(
        "--prerelease",
        choices=["alpha", "beta", "rc"],
        help="With major/minor/patch: start a prerelease line (e.g. 1.3.0 + major + alpha -> 2.0.0a1).",
    )

    gen_p = sub.add_parser(
        "generate",
        help="Write a new versioned CHANGELOG section from commits since the last v* tag",
    )
    gen_p.add_argument("version", help="New version (e.g. 1.2.3 or 2.0.0a2)")
    gen_p.add_argument(
        "--preview",
        action="store_true",
        help="Print the rendered section without modifying CHANGELOG.md",
    )

    args = parser.parse_args()
    {"bump": cmd_bump, "generate": cmd_generate}[args.command](args)


if __name__ == "__main__":
    main()
