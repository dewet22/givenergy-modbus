# givenergy-modbus

Python library for local Modbus TCP communication with GivEnergy inverters,
with no dependency on the GivEnergy Cloud. Implements a custom framer,
decoder, and PDUs specific to GivEnergy's Modbus variant from scratch.

## Architecture
- `givenergy_modbus/client/client.py` — `Client`: primary public interface
- `givenergy_modbus/client/commands.py` — `RegisterMap` and high-level command methods (including all `set_*` controls)
- `givenergy_modbus/model/` — inverter/battery data models and register definitions
- `givenergy_modbus/pdu/` — Protocol Data Units (custom GivEnergy framing)
- `givenergy_modbus/framer.py` — custom Modbus framer (GivEnergy wire format)
- `givenergy_modbus/codec.py` — decoder for PDU payloads

## Critical Caution
⚠️ Writing to registers can cause real hardware damage. Be extremely conservative
with any changes that touch register writes, PDU construction, or the LUT.
Never speculatively change register addresses or values. When in doubt, read only.

## Key Dependencies
- `pydantic` — data models and validation
- `crccheck` — CRC computation for frame integrity
- Apache-2.0 licensed, published to PyPI

## Public API
- `Client` is the primary public interface — backwards compatibility matters
- `set_*` methods in `commands.py` expose inverter control; treat these with extra care
- Changes to the public API require CHANGELOG.md updates

