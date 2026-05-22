# Usage

The client is async — all network operations must run inside an `asyncio` event loop.
Commands are plain functions in `givenergy_modbus.client.commands` that return lists of
requests, which you send via `one_shot_command` or `execute`.

## Basic example

```python
import asyncio
from givenergy_modbus.client.client import Client
from givenergy_modbus.client import commands
from givenergy_modbus.model import TimeSlot
from givenergy_modbus.model.inverter import Model

async def main():
    client = Client(host="192.168.99.99", port=8899)
    await client.connect()

    # Read current state first (needed for slot_map)
    await client.refresh_plant(full_refresh=True)
    plant = client.plant

    # Write configuration to the device
    await client.one_shot_command(commands.set_charge_target(80))
    await client.one_shot_command(
        commands.set_charge_slot(1, TimeSlot.from_components(0, 30, 4, 30), plant.inverter.slot_map)
    )
    await client.one_shot_command(commands.set_mode_dynamic())

    print(plant.inverter_serial_number)
    print(plant.inverter.model)                 # e.g. Model.HYBRID
    print(plant.inverter.enable_charge_target)
    print(plant.inverter.charge_slot_1)         # TimeSlot instance
    print(plant.inverter.slot_map)              # SlotMap for this model

    if plant.batteries:
        print(plant.batteries[0].serial_number)
        print(plant.batteries[0].soc)

    await client.close()

asyncio.run(main())
```

## Watching for updates

Use `watch_plant` to keep the plant state refreshed in the background:

```python
async def main():
    client = Client(host="192.168.99.99", port=8899)

    def on_update():
        print(f"SOC: {client.plant.batteries[0].soc}%")

    await client.watch_plant(handler=on_update, refresh_period=15.0)
```

## Tuning timeouts and retries

`refresh_plant`, `refresh`, `load_config`, `one_shot_command` and `watch_plant` all accept
the same three knobs:

- `timeout` (default 1.0s for refresh, 1.5s for `one_shot_command`) — how long to wait for
  each response.
- `retries` (default 0) — number of additional attempts after a timeout.
- `retry_delay` (default 0.5s) — seconds to wait between a timed-out attempt and the next.

The retry delay exists because some inverters exhibit multi-second silent windows where
they stop responding to anything; firing the retry immediately tends to land it inside
the same window, accomplishing nothing. The 0.5s default matches what GivTCP independently
arrived at and works for most hardware. If you observe sustained timeout clusters longer
than ~1s in your logs, try increasing it; if you need fail-fast behaviour for an
interactive command, pass `retry_delay=0`.

## Charge and discharge slots

The number of available slots depends on the inverter model. The inverter command API (see below) reads `slot_map` from the instance so you don't have to thread it through:

```python
inverter = plant.inverter

# Set slot 1 (available on all models)
await client.one_shot_command(
    inverter.set_charge_slot(1, TimeSlot.from_components(0, 30, 4, 30))
)

# Set slot 5 (only available on extended-slot models)
await client.one_shot_command(
    inverter.set_charge_slot(5, TimeSlot.from_components(12, 0, 14, 0))
)

# Clear slot 3
await client.one_shot_command(inverter.reset_charge_slot(3))
```

If you call the underlying primitives directly (`commands.set_charge_slot(...)`), you must pass `inverter.slot_map` explicitly — see the [Available commands](#available-commands) reference further down.

Models and their slot counts:

| Models | Charge slots | Discharge slots |
|---|---|---|
| HYBRID_GEN1, HYBRID_GEN2, AC, POLAR | 2 | 2 |
| HYBRID_GEN3 (ARM fw ≤ 302) | 2 | 2 |
| HYBRID_GEN3 (ARM fw > 302), ALL_IN_ONE, HYBRID_GEN4, HYBRID_HV_GEN3 | 10 | 10 |
| Three-phase (HYBRID_3PH, AC_3PH) | 10 | 10 |

## Inverter command API

The recommended entry point is the inverter instance itself:

```python
inverter = plant.inverter

await client.one_shot_command(inverter.set_charge_target(80))
await client.one_shot_command(inverter.set_enable_discharge(True))
await client.one_shot_command(inverter.set_charge_slot(1, my_timeslot))
```

The inverter knows its own `slot_map`, so slot setters don't need it threaded through. The mixin is composed onto both `SinglePhaseInverter` and `ThreePhaseInverter`; the methods listed below ("Available commands") are universally available.

Three-phase-only and EMS-only commands (`set_ac_charge`, `set_force_charge`/`_discharge`, `set_battery_*_limit_ac`, `set_battery_pause_mode`, `set_pause_slot_*`, `set_ems_plant`, `set_export_slot_*`) are not yet exposed via the inverter API — call them on `commands.*` directly while their model-vs-firmware applicability is resolved (see [#75](https://github.com/dewet22/givenergy-modbus/issues/75)). They will appear on model-specific mixins in later 2.x minors.

## Available commands

All commands live in `givenergy_modbus.client.commands` and return
`list[TransparentRequest]` for passing to `one_shot_command` or `execute`. The
inverter API above delegates to these; using them directly remains supported
for tests and lower-level integration.

### Stability

Both surfaces are supported within the 2.x line. `inverter.set_*` is the
recommended high-level API; `commands.*` is the primitive layer that the
mixin delegates to. There is no plan to deprecate `commands.*` within 2.x —
the two are not duplicate paths but two layers of the same stack. If
individual primitives turn out to be persistent footguns when used without an
inverter (e.g. routing the wrong `slot_map`), they may be `@deprecated`
case-by-case as model-specific mixins land in later 2.x minors.

### Charging

| Function | Description |
|---|---|
| `set_charge_target(soc)` | Stop charging when SOC reaches `soc`% (4–100) |
| `disable_charge_target()` | Remove SOC limit, target 100% |
| `set_enable_charge(enabled)` | Enable or disable charging |
| `set_battery_charge_limit(val)` | Charge power limit (0–50%) |
| `set_battery_charge_limit_ac(val)` | AC charge power limit (1–100%) |
| `set_shallow_charge(val)` | Set shallow charge threshold |

### Discharging

| Function | Description |
|---|---|
| `set_enable_discharge(enabled)` | Enable or disable discharging |
| `set_battery_discharge_limit(val)` | Discharge power limit (0–50%) |
| `set_battery_discharge_limit_ac(val)` | AC discharge power limit (1–100%) |
| `set_battery_soc_reserve(val)` | Minimum SOC to maintain (4–100%) |
| `set_battery_power_reserve(val)` | Battery power reserve (4–100%) |

### Time slots

| Function | Description |
|---|---|
| `set_charge_slot(idx, timeslot, slot_map)` | Set charge slot `idx` (1-based) |
| `set_charge_slot_start(idx, t, slot_map)` | Set just the start of charge slot `idx` (or `None` to clear that end) |
| `set_charge_slot_end(idx, t, slot_map)` | Set just the end of charge slot `idx` (or `None` to clear that end) |
| `reset_charge_slot(idx, slot_map)` | Clear charge slot `idx` |
| `set_discharge_slot(idx, timeslot, slot_map)` | Set discharge slot `idx` (1-based) |
| `set_discharge_slot_start(idx, t, slot_map)` | Set just the start of discharge slot `idx` (or `None` to clear that end) |
| `set_discharge_slot_end(idx, t, slot_map)` | Set just the end of discharge slot `idx` (or `None` to clear that end) |
| `reset_discharge_slot(idx, slot_map)` | Clear discharge slot `idx` |
| `set_export_slot(idx, slot)` | Set export slot `idx` (1–3), or clear if `None` |
| `set_export_slot_start(idx, t)` | Set just the start of export slot `idx` |
| `set_export_slot_end(idx, t)` | Set just the end of export slot `idx` |
| `set_battery_pause_mode(val)` | Set pause mode (`BatteryPauseMode`: DISABLED, PAUSE_CHARGE, PAUSE_DISCHARGE, PAUSE_BOTH) |
| `set_pause_slot(slot)` | Set battery pause time slot (or `None` to clear) |
| `set_pause_slot_start(t)` | Set just the start of the battery pause slot |
| `set_pause_slot_end(t)` | Set just the end of the battery pause slot |

The whole-slot setters (`set_charge_slot`, `set_discharge_slot`, `set_pause_slot`,
`set_export_slot`) write both endpoints in one call. The `_start` / `_end` variants
each write a single register and exist for callers (notably Home Assistant) whose UI
models start and end as independent entities. Either form is fine — they produce the
same wire frames when used in sequence.

The charge and discharge variants require `slot_map` as a non-default argument —
always pass `plant.inverter.slot_map` so the call routes to the right registers for
the inverter type. Defaulting it would mean a slot index that's valid on one inverter
family silently targeting wrong registers on another.

### Operating modes

| Function | Description |
|---|---|
| `set_mode_dynamic()` | Dynamic/Eco mode — maximise self-consumption |
| `set_mode_storage(discharge_slot_1, discharge_slot_2, discharge_for_export)` | Storage/timed discharge mode |
| `set_discharge_mode_max_power()` | Set battery to discharge at max power |
| `set_discharge_mode_to_match_demand()` | Set battery to match load demand |
| `set_ac_charge(enabled)` | Enable or disable AC charging (three-phase) |
| `set_force_charge(enabled)` | Force battery charge (three-phase) |
| `set_force_discharge(enabled)` | Force battery discharge (three-phase) |

### Battery calibration

| Function | Description |
|---|---|
| `set_calibrate_battery_soc(val)` | Recalibrate SOC estimation: `0` = Stop, `1` = Start (default), `3` = Charge Only |

### System

| Function | Description |
|---|---|
| `set_active_power_rate(target)` | Max inverter output as % of rated capacity |
| `set_system_date_time(dt)` | Set inverter clock |
| `set_enable_rtc(enabled)` | Enable Real Time Clock (persists settings to EEPROM) |
| `set_inverter_reboot()` | Restart the inverter |
| `set_ems_plant(enabled)` | Enable EMS plant control |

## Serialisation

All model objects are pydantic v2 models:

```python
plant.inverter.model_dump()       # dict
plant.inverter.model_dump_json()  # JSON string
```

## Capturing frames for bug reports

`Client.capture_frames(sink, duration=60.0)` tees raw TX/RX bytes to a caller-supplied sink callable while the normal refresh loop continues — useful when a bug report needs to include the actual wire bytes. Inverter and dongle serial numbers are redacted by the library before the sink is invoked: only the digits are zeroed; the prefix and model letter survive because they carry diagnostic signal.

The library does the redaction; persistence and format are the caller's choice. A minimal file-based capture looks like:

```python
from datetime import UTC, datetime

with open("capture.txt", "w") as f:
    def write_line(direction, frame):
        ts = datetime.now(UTC).isoformat(timespec="microseconds")
        f.write(f"{ts} {direction} {frame.hex()}\n")
        f.flush()
    async with Client("inverter.local", 8899) as client:
        await client.refresh_plant(full_refresh=True)
        await asyncio.gather(
            client.watch_plant(refresh_period=5),
            client.capture_frames(write_line, duration=60),
        )
```

Only one capture may run on a Client at a time — starting a second raises `RuntimeError`.

## Persisting detection state across restarts

`Client.detect()` is the slow part of a cold start — it probes for BCUs, meters and
battery devices across address ranges where most slots are empty, each probe waiting
for its own timeout. The returned `PlantCapabilities` describes the topology that
was actually found, and can be persisted by the calling application to skip the
empty-slot scan on next start.

```python
import json
from pathlib import Path

caps = await client.detect()
Path("~/.givenergy-caps.json").expanduser().write_text(json.dumps(caps.to_dict()))
```

On next start, hand the previously-captured caps back via `prior=`:

```python
import json
from pathlib import Path

from givenergy_modbus.exceptions import PlantTopologyMismatch
from givenergy_modbus.model.plant import PlantCapabilities

stored = json.loads(Path("~/.givenergy-caps.json").expanduser().read_text())
prior = PlantCapabilities.from_dict(stored)

try:
    caps = await client.detect(prior=prior)
except PlantTopologyMismatch as exc:
    # Hardware changed since `prior` was captured. Either fall back to a cold
    # detect, prompt the user, or accept the new layout explicitly.
    caps = await client.detect()  # cold rescan
```

Hinted mode is **strict**: each address listed in `prior` is still probed, but the
empty-slot sweep is skipped. If anything in `prior` fails to confirm — or the
inverter's device_type has changed — `detect()` raises `PlantTopologyMismatch`
(carrying both `prior` and `actual`) and leaves `client.plant.capabilities` as
`None`. The application chooses the recovery policy. Library does no file I/O
itself; storage location and lifecycle are entirely the caller's responsibility.

The serialised form is stable and includes a `schema_version` field:

```json
{
  "schema_version": 1,
  "device_type": "HYBRID",
  "inverter_address": "0x32",
  "meter_addresses": ["0x01"],
  "lv_battery_addresses": ["0x32", "0x33"],
  "bcu_stacks": []
}
```
