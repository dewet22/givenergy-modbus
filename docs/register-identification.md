# Register identification via sentinel cross-correlation

The GivEnergy Android app's **Read Only** tab displays telemetry labels (e.g.
"Grid voltage 242.7 V", "Battery temperature 25.0 °C") but does not show register
numbers.  This document describes how to identify the register address backing each
label using the `MockPlant` sentinel approach.

## Principle

Seed a `MockPlant` with *sentinel* values — raw register value = register address.
When the app reads a register and applies its converter (e.g. divide by 10 for "deci"
scale), it displays a value that encodes the address.  Reading that value off the
screen and inverting the converter recovers the address.

For a linear converter with scale `s`:

```
raw = address
displayed = address × s
```

**Single-pass ambiguity:** the same displayed value can match multiple `(address, scale)` pairs.
For example `24.2` matches both address 242 at scale 0.1 *and* address 2420 at scale 0.01.

**Two-pass resolution:** run a second pass with `offset=K` (e.g. 1000):

```
pass 1:  d1 = address × s
pass 2:  d2 = (address + K) × s

s = (d2 − d1) / K          ← scale, uniquely determined
address = d1 / s            ← address, uniquely determined
```

## Step-by-step procedure

### 1. Choose the register banks to probe

Decide which device address and register type to seed.  For inverter telemetry:

| Bank | Device | Type |
|---|---|---|
| Standard inverter IR | 0x31 | IR |
| Holding registers | 0x11 | HR |
| Battery | 0x32–0x37 | IR |

Seed ranges densely (e.g. `range(0, 240)`) so the app's read requests always find
populated registers and don't time out.

### 2. Run pass 1 (offset = 0)

```bash
# Using givenergy-cli (once the identify commands are implemented):
givenergy-cli mock-plant \
    --capture path/to/plant.log \
    --sentinels \
    --device 0x31 --type ir --base 0 --count 240 \
    --offset 0 \
    --host 0.0.0.0 --port 8899

# Or directly in Python:
from givenergy_modbus.testing import MockPlant
from givenergy_modbus.model.register import IR

mock = MockPlant.from_sentinels(
    "path/to/plant.log",
    spec=[(0x31, IR, range(0, 240))],
    offset=0,
)
import asyncio
asyncio.run(mock.serve_forever())
```

Connect the GivEnergy app to the mock's IP and port.  Navigate to
**Direct Control → Read Only**.  For each displayed label, record the value as `d1`.

### 3. Run pass 2 (offset = 1000)

Stop the mock; re-start with `--offset 1000`.  Record each value as `d2`.

> **Choosing K:** use K = 1000.  This is safe for all known GivEnergy register
> addresses (max address ≈ 5014; 5014 + 1000 = 6014 ≪ 65535 uint16 max).

### 4. Identify each register

```bash
# CLI:
givenergy-cli identify 242.7 --second 342.7 --k 1000
# → address=2427, scale=0.1 (deci), confidence=two-pass

# Python:
from givenergy_modbus.testing import identify
candidates = identify(242.7, 342.7, k=1000)
print(candidates)
# → [Candidate(address=2427, scale=0.1, confidence='two-pass')]
```

### 5. Cross-check against the existing model

Compare each `(address, scale)` against the existing register LUT
(`SinglePhaseInverterRegisterGetter.REGISTER_LUT` in `model/inverter.py`).

- **Address matches an existing Def** → confirm the app label is the human-readable
  name for that field.  Update the field's comment/docstring if it differs.
- **Address unknown** → record it as a new Def candidate for the #48 register audit.
  Note the app label and inferred scale; submit a PR adding `Def(C.deci, None, IR(address))`
  (or the appropriate converter) under the right field name.

### 6. Handle clamping and non-linear registers

Some fields are problematic for auto-identification:

| Case | Symptom | Workaround |
|---|---|---|
| **Clamped field** (e.g. SOC %) | App shows 100.0 % even with sentinel=2427 | Use a sentinel value in the valid range; probe with a third pass using a smaller offset |
| **Boolean/enum** | App shows only 0 or 1 | Use a non-zero in-range sentinel and check which field toggles |
| **uint32 pair** | Two registers combine into one displayed value | Seed the two adjacent addresses and note which label changes when each changes |
| **timeslot** | Two registers encode start/end time | Similar to uint32 |

Non-linear registers cannot be uniquely identified by `identify()` — handle them manually.

## Example mapping table

After completing both passes, build a table like:

| App label | address | type | scale | Existing field | Action |
|---|---|---|---|---|---|
| Grid voltage | 2427 | IR | 0.1 (deci) | `v_ac1` at IR(8) | **Mismatch** — re-probe, likely IR(8) not 2427 |
| Battery temperature | 250 | IR | 0.1 (deci) | `t_battery` at IR(56) | — |
| AC charge today | ? | IR | 0.1 (deci) | unmapped | Add `Def(C.deci, None, IR(?))` |

> Note: the sentinel value is the *address*, not necessarily a realistic reading.
> "Grid voltage 242.7 V" from a sentinel means address 2427, but the real v_ac1 at
> address 8 would display 0.8 V in sentinel mode.  Use cross-referencing, not
> absolute values, to confirm names.

## Reference

- `givenergy_modbus/testing/identify.py` — `sentinel_devices`, `identify`, `Candidate`
- `givenergy_modbus/testing/mock_plant.py` — `MockPlant.from_sentinels`
- `givenergy_modbus/model/inverter.py` — `SinglePhaseInverterRegisterGetter.REGISTER_LUT`
- Issue #48 — register audit tracking confirmed and candidate fields
