# givenergy-modbus — Claude Code instructions

## Project overview

Python library for communicating with GivEnergy inverters over Modbus TCP.
Async client, pydantic v2 data models, conventional-commit changelog.

## Commands and docs

**When adding, removing, or changing any function in `givenergy_modbus/client/commands.py`,
update `docs/usage.md` in the same commit.** The commands table there is the primary
reference for downstream consumers (givenergy-hass, givenergy-cli).

## Key files

- `givenergy_modbus/client/commands.py` — all write commands
- `givenergy_modbus/pdu/write_registers.py` — `WRITE_SAFE_REGISTERS` allowlist; every writable register must be listed here
- `givenergy_modbus/model/inverter.py` — `SinglePhaseInverter`, `SlotMap`, `SINGLE_PHASE_SLOTS`, `EXTENDED_SLOTS`
- `givenergy_modbus/model/inverter_threephase.py` — `ThreePhaseInverter`, `THREE_PHASE_SLOTS`
- `docs/usage.md` — user-facing command reference (keep in sync with commands.py)

## Slot maps

Slot availability is model-dependent. `SinglePhaseInverter.slot_map` returns either
`SINGLE_PHASE_SLOTS` (2 slots) or `EXTENDED_SLOTS` (10 slots) based on DTC + ARM
firmware version. Always pass `inverter.slot_map` to slot commands; never hardcode
register addresses.

## Safe register writes

`WriteHoldingRegisterRequest.ensure_valid_state()` rejects writes to registers not in
`WRITE_SAFE_REGISTERS`. When adding a new write command, add its register(s) to that
set at the same time.

## Testing

```bash
uv run --group test pytest tests/
uv run --group test tox        # full matrix
uv run ruff check --fix && uv run ruff format
```

## Git

- Conventional commits: `feat:`, `fix:`, `refactor:`, etc.
- Don't push; prepare commits and let the user decide when to push/PR.

## Changelog

`CHANGELOG.md` is maintained automatically by `.github/workflows/changelog.yml` (driven by `scripts/release.py append-many`), which appends entries to `[Unreleased]` on every push to `main`. The conventional-commit prefix determines the section:

| Prefix | Section |
|---|---|
| `feat:` | ✨ Added |
| `fix:` / `revert:` | 🐛 Fixed |
| `perf:` / `<type>!:` (breaking) | 🔄 Changed |
| `security:` | 🔒 Security |
| `refactor:` / `docs:` / `chore:` / `ci:` / `test:` / `style:` / `build:` / `wip:` | 🔧 Maintenance |

**Default rule: don't touch `CHANGELOG.md` on a feature branch.** Let the bot handle it — touching `CHANGELOG.md` on a long-lived branch invites stale-`[Unreleased]`-section conflicts.

### Per-commit overrides (`Changelog:` trailer)

When the conventional-commit prefix doesn't reflect the user impact, add a `Changelog:` git trailer to the commit body:

```
refactor: rename slave_address → device_address

Changelog: Changed
```

- `Changelog: <section>` redirects the entry to that section (case-insensitive; matches `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`, `Maintenance`).
- `Changelog: skip` suppresses the entry entirely. Useful for fixup commits whose narrative is already captured by their parent.

The last `Changelog:` trailer in the message wins, matching standard git-trailer semantics.

### Branch-managed changelog (escape hatch)

If a PR's narrative is too complex for per-commit overrides, the branch can edit `CHANGELOG.md` directly. **If any commit in a push touches `CHANGELOG.md`, the bot skips that push entirely** — the assumption is the branch has authored its own fine-tuned entries. Be aware of the stale-`[Unreleased]` merge-conflict risk on long-lived branches.
