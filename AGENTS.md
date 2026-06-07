# givenergy-modbus

Python library for local Modbus TCP communication with GivEnergy inverters,
with no dependency on the GivEnergy Cloud. Implements a custom framer,
decoder, and PDUs specific to GivEnergy's Modbus variant from scratch.
Async client, pydantic v2 data models, conventional-commit changelog.

## Scope and sister repos

This agent owns `givenergy-modbus` only. Two sibling repositories exist, each with their own dedicated agent:

- **`givenergy-hass`** — the Home Assistant custom component to control a local plant
- **`givenergy-cli`** — a command-line interface to perform common interactive tasks

When a change in this component requires corresponding work in a sister repo, communicate via the **shared coordination inbox** at `/tmp/givenergy-coordination/`.

### Coordination inbox protocol

- **Shared directory:** `/tmp/givenergy-coordination`
- **Filename format:** `<unix-epoch>-<recipient>-<description>.md`
  - `recipient` is one of `cli`, `modbus`, or `hass`
  - `description` is a brief slug, optionally referencing an issue (e.g. `mock-pdu-logging-#42`)
  - Example: `1780409632-modbus-mock-pdu-logging.md`
- **Writing a message:** create a new file; never mutate an existing one
- **Replying:** create a new file with the current epoch, the original sender as addressee, and a description prefixed with `re-`. Only reply if actionable, save on pleasantries.
- **Content:** describe the expected outcome at the API boundary — not how to implement it; include enough context to act without this conversation's history. It does not need to be overly verbose since agents share a lot of common knowledge across  these repos.
- **Scanning:** after every turn, scan the inbox for new files through the stop hook and script defined in `.claude/settings.json`; make a decision whether to immediately act on the message, park it for when the current work winds up, or handing off to a subagent. Check with the user if any uncertainty.

The old `.claude/handoffs/` and bare `/tmp` locations are superseded by this inbox.

## GitHub identity — bot vs your voice

GitHub interactions split into two identities. The rule of thumb: **anything that
publishes prose as the user goes out under their keyring auth; mechanical, structural,
and read-only actions go out under the automation bot.**

- **Git pushes are unaffected** — git uses SSH, so commits/pushes always go under the
  user's key regardless of token. This split only governs `gh` / `gh api` calls.
- `gh` token precedence is `GH_TOKEN` > `GITHUB_TOKEN` > keyring.
- Bot identity is `dewet22-claude`; the user's keyring identity is `dewet22`.

**Bot identity (autonomous)** — prefix the command with `ghbot` (a shell function that
loads the bot `GH_TOKEN` in a subshell), e.g. `ghbot pr merge 35`. Covers:
- All reads: `gh pr checks/view/list/diff`, `gh run list/view/watch`, `gh api` GETs,
  `gh issue/release/repo view/list`, `gh search`
- `gh workflow run` (release trigger)
- `gh pr merge`
- Resolving review threads (GraphQL `resolveReviewThread`)
- Labels (`gh label`, `gh pr edit --add-label`)

**Your voice (the user)** — just plain `gh …`. Since `GH_TOKEN` is never ambient, bare
`gh` already pins to the user's keyring identity — the default, no prefix needed.
(Belt-and-braces: `env -u GH_TOKEN -u GITHUB_TOKEN gh …` forces keyring even if a token
leaked into the environment.) Covers anything that authors prose as the user:
- Review-thread replies (`gh api …/comments/…/replies`)
- `gh pr comment` / `gh issue comment`
- PR review submissions (`gh pr review`)
- `gh pr create` (title/body are prose authored as the user)
- `gh issue create`, closing with a comment
- Editing PR/issue descriptions

The bot token lives at `$CLAUDE_CONFIG_DIR/gh-env` (`export GH_TOKEN=…`), wrapped by the
`ghbot` shell function (defined in `~/.zshenv` so non-interactive login shells pick it up).
It needs `repo` (read, merge, labels) and `workflow` (trigger releases) scopes. This is a
shared cross-agent convention — the modbus and hass agents follow the same split.

## Architecture
- `givenergy_modbus/client/client.py` — `Client`: primary public interface
- `givenergy_modbus/client/commands.py` — `RegisterMap` and high-level command methods (all `set_*` controls / write commands)
- `givenergy_modbus/model/` — inverter/battery data models and register definitions
  - `inverter.py` — `SinglePhaseInverter`, `SlotMap`, `SINGLE_PHASE_SLOTS`, `EXTENDED_SLOTS`
  - `inverter_threephase.py` — `ThreePhaseInverter`, `THREE_PHASE_SLOTS`
- `givenergy_modbus/pdu/` — Protocol Data Units (custom GivEnergy framing)
  - `write_registers.py` — `WRITE_SAFE_REGISTERS` allowlist (see Critical Caution)
- `givenergy_modbus/framer.py` — custom Modbus framer (GivEnergy wire format)
- `givenergy_modbus/codec.py` — decoder for PDU payloads
- `docs/usage.md` — user-facing command reference (keep in sync with commands.py)

## Critical Caution — register writes
⚠️ Writing to registers can cause real hardware damage. Be extremely conservative
with any changes that touch register writes, PDU construction, or the LUT.
Never speculatively change register addresses or values. When in doubt, read only.

Prefer real evidence (wire captures, GivTCP cross-reference) before adding a writable
register. A new writable register must be added in **two** places or it fails at
send time:

1. the command-mixin `WRITE_SAFE_REGISTERS` in `client/commands.py`, and
2. the canonical `WRITE_SAFE_REGISTERS` in `pdu/write_registers.py` — enforced by
   `WriteHoldingRegisterRequest.ensure_valid_state()` at `encode()` time. A register
   missing here builds a request fine but raises `InvalidPduState` on the wire.

Add a regression test that calls `.encode()` on the new command (not just constructs
it) — constructing alone won't catch a missing PDU-allowlist entry.

## Slot maps
Slot availability is model-dependent. `SinglePhaseInverter.slot_map` returns either
`SINGLE_PHASE_SLOTS` (2 slots) or `EXTENDED_SLOTS` (10 slots) based on DTC + ARM
firmware version. Always pass `inverter.slot_map` to slot commands; never hardcode
register addresses.

## Commands and docs
When adding, removing, or changing any function in `client/commands.py`, update
`docs/usage.md` in the same commit. That commands table is the primary reference for
downstream consumers.

## Conventions
- Inclusive terminology only: `device_address`, never `slave_address`; no master/slave
  in code, comments, commit messages, or docs (quote legacy protocol terms verbatim,
  in a quote block, if unavoidable).
- Conventional commits: `feat:`, `fix:`, `refactor:`, etc.

## Testing
**Run `tox` before every commit, not just before a PR.** The CI matrix runs the same
envs; `pytest` alone misses things CI catches in ~20s of local tox:

- `lint` runs mypy, which spots mixin-pattern cross-class invariants (e.g. a mixin
  reading `self.slot_map` when the attribute lives on the composed inverter class)
  that pytest can't see.
- `format` runs `ruff format --check`, which catches preferred-syntax drift — notably
  PEP 758 unparenthesised `except` clauses on the py314 target.
- `build` runs `mkdocs build`, `twine check`, and the wheel build, where docstring
  problems, broken nav links, and packaging regressions surface before a release.

```bash
uv run --group test tox        # full check — pytest + ruff + mypy + bandit + build + docs
uv run --group test pytest     # faster: tests only
uv run ruff check --fix && uv run ruff format  # faster: format + lint only
```

## Public API & downstream consumers
- `Client` is the primary public interface — backwards compatibility matters.
- `set_*` methods in `commands.py` expose inverter control; treat with extra care.
- This library is consumed by **givenergy-hass** (Home Assistant integration) and
  **givenergy-cli**, each maintained separately. Keep public API changes conservative
  and backwards-compatible where possible. Cross-repo changes are coordinated via
  self-contained handoff specs that state the expected outcomes at the API boundary
  without prescribing the consumer's implementation.
- Public API changes require a CHANGELOG entry (see below).

## Changelog
`CHANGELOG.md` is generated at release time by `scripts/release.py generate`, which
walks `git log <last-v-tag>..HEAD` on the current branch and writes a new versioned
section. There is no `[Unreleased]` section between releases. The conventional-commit
prefix determines the section:

| Prefix | Section |
|---|---|
| `feat:` | ✨ Added |
| `fix:` / `revert:` | 🐛 Fixed |
| `perf:` / `<type>!:` (breaking) | 🔄 Changed |
| `security:` | 🔒 Security |
| `refactor:` / `docs:` / `chore:` / `ci:` / `test:` / `style:` / `build:` / `wip:` | 🔧 Maintenance |

**Default rule: don't edit `CHANGELOG.md` directly.** Let `release.py generate` build
it from commits at release time. Editing by hand is reserved for fixing past mistakes
in already-released sections; the most-recent section is rewritten on the next release
if you touch it.

### Per-commit overrides (`Changelog:` trailer)
When the conventional-commit prefix doesn't reflect the user impact, add a `Changelog:`
git trailer to the commit body:

```text
refactor: rename a public model field for clarity

Changelog: Changed
```

- `Changelog: <section>` redirects the entry to that section (case-insensitive; matches
  `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`, `Maintenance`).
- `Changelog: skip` suppresses the entry entirely. Useful for fixup commits whose
  narrative is already captured by their parent.

Trailer must live in the final paragraph of the commit body (standard git trailer
semantics). Last `Changelog:` trailer in the final paragraph wins.

### Previewing the upcoming section
```bash
python3 scripts/release.py generate <next-version> --preview
```
Walks the same commits and prints the rendered section without modifying the file.
`git log <last-v-tag>..HEAD --oneline` is the lighter-weight alternative.

## Key Dependencies
- `pydantic` — data models and validation
- `crccheck` — CRC computation for frame integrity
- Apache-2.0 licensed, published to PyPI
