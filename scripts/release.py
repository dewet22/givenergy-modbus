#!/usr/bin/env python3
"""Release helper: version bumping and CHANGELOG generation."""

import argparse
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

CHANGELOG = Path(__file__).parent.parent / "CHANGELOG.md"

_COMMIT_TYPE_TO_SECTION: dict[str, str] = {
    "feat": "Added",
    "fix": "Fixed",
    "perf": "Changed",
    "refactor": "Changed",
    "revert": "Fixed",
    "security": "Security",
    "docs": "Changed",
    "ci": "Maintenance",
    "chore": "Maintenance",
    "test": "Maintenance",
    "style": "Maintenance",
    "build": "Maintenance",
    "wip": "Maintenance",
}

_SECTION_ORDER = ["Added", "Changed", "Deprecated", "Removed", "Fixed", "Security", "Maintenance"]

_SECTION_ALIASES = {s.lower(): s for s in _SECTION_ORDER}


class Changelog:
    """Line-by-line reader/writer for Keep a Changelog files."""

    def __init__(self, path: Path | None = None) -> None:
        # Resolve at call time so monkeypatching `release.CHANGELOG` in tests is honoured.
        self.path = path if path is not None else CHANGELOG
        self.lines = self.path.read_text().splitlines(keepends=True)

    def save(self) -> None:
        """Write the current line buffer back to disk."""
        self.path.write_text("".join(self.lines))

    def prepend_version_section(self, version: str, today: str, body: str) -> None:
        r"""Insert a new versioned section above the most recent existing one.

        `body` is the rendered section body (the lines under the `## [version] - date`
        header, e.g. `### Fixed\n\n- ...`). The header is added by this method.
        """
        new_header = f"## [{version}] - {today}\n"
        block = [new_header, "\n", *body.splitlines(keepends=True)]
        if not block[-1].endswith("\n"):
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
        section, description = "Changed", subject
    else:
        commit_type, breaking, description = m.group(1).lower(), m.group(2), m.group(3).strip()
        if breaking:
            section, description = "Changed", f"⚠️ Breaking: {description}"
        else:
            section = _COMMIT_TYPE_TO_SECTION.get(commit_type, "Changed")

    trailer = _find_changelog_trailer(message)
    if trailer is not None:
        if trailer.lower() == "skip":
            return "skip", description
        override = _SECTION_ALIASES.get(trailer.lower())
        if override:
            section = override

    return section, description


def _find_changelog_trailer(message: str) -> str | None:
    """Return the value of the last `Changelog:` git trailer in the message, or None.

    Standard git-trailer semantics: trailers live in the final paragraph of the body
    as `Key: value` pairs. Last `Changelog:` wins to match git's own behaviour.
    """
    paragraphs = re.split(r"\n\s*\n", message.strip())
    if len(paragraphs) < 2:
        return None
    last = paragraphs[-1]
    matches = re.findall(r"^Changelog:\s*(.+?)\s*$", last, flags=re.MULTILINE | re.IGNORECASE)
    return matches[-1] if matches else None


def _is_skippable_commit(message: str) -> bool:
    """Return True for commits that shouldn't produce changelog entries.

    Skips:
    - Merge commits (the underlying feature commits are present separately).
    - The release commit itself (`chore: release <version>`) — describes the act of
      releasing, not a user-visible change.
    - Bot-generated `chore: update [Unreleased] changelog` commits (historical: the
      bot is retired, but these commits remain in the history of every active branch).
    """
    subject = message.splitlines()[0].strip()
    if subject.startswith(("Merge pull request", "Merge branch")):
        return True
    if re.match(r"^chore: release \d", subject):
        return True
    if subject == "chore: update [Unreleased] changelog":
        return True
    return False


def _git_commits_since_last_tag() -> list[tuple[str, str]]:
    """Return [(sha, message), ...] for commits between the most recent v* tag and HEAD.

    If no tag is reachable from HEAD, walks all of history. Commits are returned
    oldest-first so the rendered section reads chronologically.
    """
    try:
        prev_tag = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0", "--match=v*", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        rev_range = f"{prev_tag}..HEAD"
    except subprocess.CalledProcessError:
        rev_range = "HEAD"

    raw = subprocess.check_output(
        ["git", "log", rev_range, "--format=%H%x00%B%x1e", "--reverse"],
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


def cmd_bump(args) -> None:
    """Print the next version given a current version and bump type."""
    major, minor, patch = map(int, args.current.split("."))
    if args.bump == "major":
        major += 1
        minor = 0
        patch = 0
    elif args.bump == "minor":
        minor += 1
        patch = 0
    else:
        patch += 1
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
    bump_p.add_argument("current", help="Current version (e.g. 1.2.3)")
    bump_p.add_argument("bump", choices=["major", "minor", "patch"])

    gen_p = sub.add_parser(
        "generate",
        help="Write a new versioned CHANGELOG section from commits since the last v* tag",
    )
    gen_p.add_argument("version", help="New version (e.g. 1.2.3)")
    gen_p.add_argument(
        "--preview",
        action="store_true",
        help="Print the rendered section without modifying CHANGELOG.md",
    )

    args = parser.parse_args()
    {"bump": cmd_bump, "generate": cmd_generate}[args.command](args)


if __name__ == "__main__":
    main()
