#!/usr/bin/env python3
"""Release helper: version bumping and CHANGELOG management."""

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

CHANGELOG = Path(__file__).parent.parent / "CHANGELOG.md"

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
    # Non-functional but recorded for completeness
    "ci": "🔧 Maintenance",
    "chore": "🔧 Maintenance",
    "test": "🔧 Maintenance",
    "style": "🔧 Maintenance",
    "build": "🔧 Maintenance",
    "wip": "🔧 Maintenance",
}


class Changelog:
    """Line-by-line reader/editor for Keep a Changelog files."""

    def __init__(self, path: Path = CHANGELOG) -> None:
        self.path = path
        self.lines = path.read_text().splitlines(keepends=True)

    def save(self) -> None:
        """Write the current line buffer back to disk."""
        self.path.write_text("".join(self.lines))

    def unreleased_has_content(self) -> bool:
        """Return True if [Unreleased] contains any non-blank, non-header lines."""
        in_section = False
        for line in self.lines:
            if line.startswith("## [Unreleased]"):
                in_section = True
                continue
            if in_section:
                if line.startswith("## ["):
                    break
                if line.strip():
                    return True
        return False

    def insert_version_header(self, version: str, today: str) -> None:
        """Insert a new versioned header immediately after [Unreleased].

        The existing [Unreleased] content naturally becomes the body of the new version,
        leaving [Unreleased] empty and ready for the next cycle.
        """
        for i, line in enumerate(self.lines):
            if line.startswith("## [Unreleased]"):
                self.lines[i + 1 : i + 1] = ["\n", f"## [{version}] - {today}\n"]
                return

    def extract_version_entry(self, version: str) -> str:
        """Return the body of a versioned section as a stripped string."""
        in_section = False
        body_lines: list[str] = []
        for line in self.lines:
            if line.startswith(f"## [{version}]"):
                in_section = True
                continue
            if in_section:
                if line.startswith("## ["):
                    break
                body_lines.append(line)
        return "".join(body_lines).strip()

    def append_to_unreleased(self, section: str, entry: str) -> None:
        """Append a bullet to a ### section under [Unreleased], creating it if needed."""
        block_start = block_end = -1
        for i, line in enumerate(self.lines):
            if line.startswith("## [Unreleased]"):
                block_start = i + 1
            elif block_start != -1 and line.startswith("## ["):
                block_end = i
                break
        if block_start == -1:
            return
        if block_end == -1:
            block_end = len(self.lines)

        block = self.lines[block_start:block_end]
        section_header = f"### {section}\n"

        try:
            idx = block.index(section_header)
        except ValueError:
            # Section doesn't exist — insert before the first existing section that
            # comes after this one in _SECTION_ORDER, or at the end of the block.
            new_rank = _SECTION_ORDER.index(section) if section in _SECTION_ORDER else len(_SECTION_ORDER)
            insert_at = block_end
            for j, line in enumerate(block):
                if line.startswith("### "):
                    name = line[4:].strip()
                    rank = _SECTION_ORDER.index(name) if name in _SECTION_ORDER else len(_SECTION_ORDER)
                    if rank > new_rank:
                        abs_pos = block_start + j
                        while abs_pos > block_start and not self.lines[abs_pos - 1].strip():
                            abs_pos -= 1
                        insert_at = abs_pos
                        break
            else:
                while insert_at > block_start and not self.lines[insert_at - 1].strip():
                    insert_at -= 1
            self.lines[insert_at:insert_at] = ["\n", section_header, "\n", f"{entry}\n"]
            return

        # Section exists — insert before its trailing blank lines
        abs_header = block_start + idx
        next_section_offset = next(
            (j for j, line in enumerate(block[idx + 1 :], start=idx + 1) if line.startswith("### ")),
            len(block),
        )
        abs_section_end = block_start + next_section_offset
        insert_at = abs_section_end
        while insert_at > abs_header and not self.lines[insert_at - 1].strip():
            insert_at -= 1
        self.lines.insert(insert_at, f"{entry}\n")


def _parse_commit(message: str) -> tuple[str, str]:
    """Return (changelog_section, description) for a conventional commit message."""
    subject = message.splitlines()[0].strip()
    m = re.match(r"^(\w+)(?:\([^)]*\))?(!)?\s*:\s*(.+)", subject)
    if not m:
        return "🔄 Changed", subject
    commit_type, breaking, description = m.group(1).lower(), m.group(2), m.group(3).strip()
    if breaking:
        return "🔄 Changed", f"⚠️ Breaking: {description}"
    return _COMMIT_TYPE_TO_SECTION.get(commit_type, "🔄 Changed"), description


def cmd_check(_args) -> None:
    """Fail if [Unreleased] has no entries."""
    if not Changelog().unreleased_has_content():
        print("ERROR: [Unreleased] section is empty — add changelog entries before releasing.", file=sys.stderr)
        sys.exit(1)


def cmd_bump(args) -> None:
    """Print the next version given a current version and bump type."""
    major, minor, patch = map(int, args.current.split("."))
    if args.bump == "major":
        major += 1
        minor = 0
        patch = 0  # noqa: E702
    elif args.bump == "minor":
        minor += 1
        patch = 0  # noqa: E702
    else:
        patch += 1
    print(f"{major}.{minor}.{patch}")


def cmd_update(args) -> None:
    """Move [Unreleased] entries under a new versioned header and print the entry body."""
    cl = Changelog()
    cl.insert_version_header(args.version, date.today().isoformat())
    cl.save()
    print(cl.extract_version_entry(args.version))


def _commit_attribution(changelog_text: str) -> str:
    """Return an attribution suffix like ' ([abc1234](url) by @login 🎉)' if env vars are set."""
    sha = os.environ.get("COMMIT_SHA", "").strip()
    login = os.environ.get("COMMIT_AUTHOR_LOGIN", "").strip()
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()

    if not sha:
        return ""

    parts: list[str] = []
    if repo:
        short_sha = sha[:7]
        parts.append(f"[{short_sha}]({server}/{repo}/commit/{sha})")
    if login:
        is_first = f"@{login}" not in changelog_text
        parts.append(f"@{login}" + (" 🎉" if is_first else ""))

    return f" ({', '.join(parts)})" if parts else ""


def cmd_append(_args) -> None:
    """Append a conventional commit (from $COMMIT_MSG) to [Unreleased]."""
    message = os.environ.get("COMMIT_MSG", "").strip()
    if not message:
        return
    section, description = _parse_commit(message)
    cl = Changelog()
    attribution = _commit_attribution(cl.path.read_text())
    cl.append_to_unreleased(section, f"- {description}{attribution}")
    cl.save()


def _is_skippable_commit(message: str) -> bool:
    """Return True for commits that shouldn't produce changelog entries.

    Skips:
    - Merge commits ("Merge pull request" / "Merge branch") — the feature commits
      they wrap are already in the push's `commits` list separately.
    - The bot's own changelog-update commits — would otherwise recurse.
    - Any chore: commit whose subject mentions "changelog" — these are housekeeping
      edits to CHANGELOG.md itself and don't belong as entries within it.
    """
    subject = message.splitlines()[0].strip()
    if subject.startswith(("Merge pull request", "Merge branch")):
        return True
    if subject == "chore: update [Unreleased] changelog":
        return True
    if subject.startswith("chore:") and "changelog" in subject.lower():
        return True
    return False


def cmd_append_many(_args) -> None:
    """Append every commit from a JSON push-event `commits` array (read from stdin).

    Each commit object must have `id`, `message`, and optionally `author.username`.
    Commits where _is_skippable_commit returns True are dropped silently.
    """
    raw = sys.stdin.read().strip()
    if not raw:
        return
    commits = json.loads(raw)
    cl = Changelog()
    for c in commits:
        message = (c.get("message") or "").strip()
        if not message or _is_skippable_commit(message):
            continue
        sha = c.get("id", "")
        login = (c.get("author") or {}).get("username", "")
        # _commit_attribution reads from env vars; set them per-commit so the
        # attribution string reflects this commit (not a stale value from $COMMIT_SHA).
        os.environ["COMMIT_SHA"] = sha
        os.environ["COMMIT_AUTHOR_LOGIN"] = login
        section, description = _parse_commit(message)
        attribution = _commit_attribution("".join(cl.lines))
        cl.append_to_unreleased(section, f"- {description}{attribution}")
    cl.save()


def main() -> None:
    """CLI entry point: parse argv and dispatch to the chosen subcommand."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Fail if [Unreleased] section is empty")

    bump_p = sub.add_parser("bump", help="Print next version number")
    bump_p.add_argument("current", help="Current version (e.g. 1.2.3)")
    bump_p.add_argument("bump", choices=["major", "minor", "patch"])

    update_p = sub.add_parser("update", help="Move [Unreleased] to a versioned section and print the entry")
    update_p.add_argument("version", help="New version (e.g. 1.2.3)")

    sub.add_parser("append", help="Append $COMMIT_MSG to [Unreleased] (conventional commits)")
    sub.add_parser(
        "append-many",
        help="Append every commit from a JSON push-event `commits` array (read from stdin)",
    )

    args = parser.parse_args()
    {
        "check": cmd_check,
        "bump": cmd_bump,
        "update": cmd_update,
        "append": cmd_append,
        "append-many": cmd_append_many,
    }[args.command](args)


if __name__ == "__main__":
    main()
