---
name: run-checks
description: Run the full tox quality gate (format, lint, mypy, bandit, tests) and summarise failures
disable-model-invocation: true
---

# run-checks

Run every tox environment in sequence and report a clear pass/fail summary.

## Steps

1. Run each environment in order, capturing output:
   ```bash
   uv run --group test tox -e format
   uv run --group test tox -e lint
   uv run --group test tox -e py313
   ```

2. For each environment, report one line:
   - `✓ format` — passed
   - `✗ lint — ruff: 3 errors, mypy: 1 error, bandit: 0 issues` — failed, with a brief summary of what failed

3. If any environment failed, print the relevant error lines (not the full tox output — just the actionable lines: ruff errors, mypy errors, bandit findings, or pytest failures).

4. End with an overall verdict:
   - All passed: "All checks passed."
   - Any failed: "X/3 checks failed. Fix the issues above before committing."

## Notes
- Run environments sequentially, not in parallel — tox shares the venv lock.
- `tox -e build` (docs + twine check) is intentionally excluded here; run it separately before a release.
- If tox itself is not installed, run: `uv run --group test tox --version` to verify, and if missing instruct the user to run `uv sync --group test`.
