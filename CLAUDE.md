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
