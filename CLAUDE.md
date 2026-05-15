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

`CHANGELOG.md` is generated at release time by `scripts/release.py generate`, which walks `git log <last-v-tag>..HEAD` on the current branch and writes a new versioned section. There is no `[Unreleased]` section maintained between releases — release sections appear only at release time. The conventional-commit prefix determines the section:

| Prefix | Section |
|---|---|
| `feat:` | ✨ Added |
| `fix:` / `revert:` | 🐛 Fixed |
| `perf:` / `<type>!:` (breaking) | 🔄 Changed |
| `security:` | 🔒 Security |
| `refactor:` / `docs:` / `chore:` / `ci:` / `test:` / `style:` / `build:` / `wip:` | 🔧 Maintenance |

**Default rule: don't edit `CHANGELOG.md` directly.** Let `release.py generate` build it from commits at release time. Editing by hand is reserved for fixing past mistakes in already-released sections; the most-recent section will be rewritten on the next release if you do touch it.

### Per-commit overrides (`Changelog:` trailer)

When the conventional-commit prefix doesn't reflect the user impact, add a `Changelog:` git trailer to the commit body:

```text
refactor: rename slave_address → device_address

Changelog: Changed
```

- `Changelog: <section>` redirects the entry to that section (case-insensitive; matches `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`, `Maintenance`).
- `Changelog: skip` suppresses the entry entirely. Useful for fixup commits whose narrative is already captured by their parent.

Trailer must live in the final paragraph of the commit body (standard git trailer semantics). Last `Changelog:` trailer in the final paragraph wins.

### Previewing the upcoming section

`CHANGELOG.md` doesn't reflect upcoming changes between releases. To see what would land in the next release:

```bash
python3 scripts/release.py generate <next-version> --preview
```

Walks the same commits and prints the rendered section without modifying the file. `git log <last-v-tag>..HEAD --oneline` is the lighter-weight alternative.
