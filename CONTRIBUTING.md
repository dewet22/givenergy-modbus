# Contributing

Contributions are welcome, and they are greatly appreciated! Every little bit
helps, and credit will always be given.

You can contribute in many ways:

## Types of Contributions

### Report Bugs

Report bugs at https://github.com/dewet22/givenergy-modbus/issues.

If you are reporting a bug, please include:

* Your operating system name and version.
* Any details about your local setup that might be helpful in troubleshooting.
* Detailed steps to reproduce the bug.

### Fix Bugs

Look through the GitHub issues for bugs. Anything tagged with "bug" and "help
wanted" is open to whoever wants to implement it.

### Implement Features

Look through the GitHub issues for features. Anything tagged with "enhancement"
and "help wanted" is open to whoever wants to implement it.

### Write Documentation

GivEnergy Modbus could always use more documentation, whether as part of the
official GivEnergy Modbus docs, in docstrings, or even on the web in blog posts,
articles, and such.

### Submit Feedback

The best way to send feedback is to file an issue at https://github.com/dewet22/givenergy-modbus/issues.

If you are proposing a feature:

* Explain in detail how it would work.
* Keep the scope as narrow as possible, to make it easier to implement.
* Remember that this is a volunteer-driven project, and that contributions
  are welcome :)

## Get Started!

Ready to contribute? Here's how to set up `givenergy-modbus` for local development.

1. Fork the `givenergy-modbus` repo on GitHub.
2. Clone your fork locally:

    ```bash
    git clone git@github.com:your_name_here/givenergy-modbus.git
    ```

3. Ensure [uv](https://docs.astral.sh/uv/) is installed.
4. Install dependencies:

    ```bash
    uv sync --group test --group docs --group dev
    ```

5. Create a branch for local development:

    ```bash
    git checkout -b name-of-your-bugfix-or-feature
    ```

    Now you can make your changes locally.

6. When you're done making changes, check that your changes pass the
   tests, including testing other Python versions, with tox:

    ```bash
    uv run --group test tox
    ```

7. Commit your changes and push your branch to GitHub:

    ```bash
    git add .
    git commit -m "Your detailed description of your changes."
    git push origin name-of-your-bugfix-or-feature
    ```

9. Submit a pull request through the GitHub website.

## Pull Request Guidelines

Before you submit a pull request, check that it meets these guidelines:

1. The pull request should include tests.
2. If the pull request adds functionality, the docs should be updated. Put
   your new functionality into a function with a docstring, and add the
   feature to the list in README.md.
3. The pull request should work for Python 3.11 and above. Check
   https://github.com/dewet22/givenergy-modbus/actions
   and make sure that the tests pass for all supported Python versions.

## Tips

```bash
uv run --group test pytest tests/client/
```

To run a subset of tests.

## Deploying

Releases run via the `Release` workflow under GitHub Actions, triggered manually
through `workflow_dispatch`. The operator picks a `bump` (`patch` / `minor` /
`major` / `prerelease` / `finalize`) and an optional `prerelease_stage` to start
a new prerelease line (alpha / beta / rc). A `republish_tag` input is also
available for re-publishing an existing tag to PyPI without bumping the version.

The workflow generates the release's changelog section from conventional-commit
messages since the previous tag (via `scripts/release.py generate`), commits and
tags the new version, publishes to PyPI (OIDC), and notifies downstream
consumers. No manual tagging or `[Unreleased]` section editing is required.

### Dropping a Python version

Bumping `requires-python` in `pyproject.toml` (and the matching `target-version`
in the ruff config and tox/CI matrices) is technically a one-commit change here,
but the downstream blast radius is larger than it looks.

Both [givenergy-cli](https://github.com/dewet22/givenergy-cli) and
[givenergy-hass](https://github.com/dewet22/givenergy-hass) pin
`givenergy-modbus` on long-lived `v1.0` branches. Those branches carry their
own `requires-python` floor. When this library's floor moves up, the v1.0
branches keep their old floor and the resolver hits a Python-version split
the next time the downstream auto-bump workflow runs — e.g. with this project
at `>=3.14` and a downstream at `>=3.13`, `uv lock --upgrade-package
givenergy-modbus` fails with:

```
Because the requested Python version (>=3.13) does not satisfy Python>=3.14
and givenergy-modbus==X.Y.Z depends on Python>=3.14, we can conclude that
givenergy-modbus==X.Y.Z cannot be used.
```

When dropping a Python version, open companion PRs on the downstream `v1.0`
branches in the same session, bumping their `requires-python` to match. If the
new floor maps to a Home Assistant Core version, double-check HA's own floor
hasn't drifted away from where this project now sits — Home Assistant's
minimum-Python lives in its release notes, not in our pyproject.toml.
