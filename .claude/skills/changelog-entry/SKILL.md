---
name: changelog-entry
description: Preview or apply CHANGELOG.md entries for local commits not yet pushed to origin/main
disable-model-invocation: true
---

# changelog-entry

Use `scripts/release.py` to generate and optionally apply CHANGELOG.md entries for commits that exist locally but have not yet been pushed to origin/main.

## Steps

1. Find unpushed commits:
   ```
   git log origin/main..HEAD --format="%H %s" --no-merges
   ```
   If there are none, report "No unpushed commits — nothing to add." and stop.

2. For each commit (oldest first), determine what entry it would produce:
   - Show the commit hash (short), message, and the section it maps to using the logic in `_COMMIT_TYPE_TO_SECTION` in `scripts/release.py` (feat→Added, fix→Fixed, perf/refactor/docs→Changed, ci/chore/test/style/build/wip→Maintenance, security→Security; unknown types default to Changed)
   - Skip commits where `_is_skippable_commit` would return True (merge commits, "chore: update [Unreleased] changelog")

3. Print a preview table like:
   ```
   Section      | Entry
   -------------|------
   Fixed        | - prevent crash on reconnect
   Maintenance  | - update CI workflow
   ```

4. Ask the user: "Apply these entries to CHANGELOG.md now? (y/n)"

5. If yes: for each non-skippable commit, run:
   ```bash
   COMMIT_MSG="<full commit message>" \
   COMMIT_SHA="<full sha>" \
   COMMIT_AUTHOR_LOGIN="<git config user.name or empty>" \
   GITHUB_REPOSITORY="dewet22/givenergy-modbus" \
   GITHUB_SERVER_URL="https://github.com" \
   uv run python scripts/release.py append
   ```
   Run commits in chronological order (oldest first).

6. Confirm how many entries were written and show the updated `## [Unreleased]` section from CHANGELOG.md.

## Notes
- The CI (`changelog.yml`) runs this automatically on push — this skill is for previewing or applying entries locally before pushing.
- Never edit CHANGELOG.md by hand; always go through `scripts/release.py` to preserve consistent formatting.
- Commits with `chore: update [Unreleased] changelog` are always skipped — they are the bot's own changelog commits.
