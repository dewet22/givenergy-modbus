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

    # Detect the topology once, then read the config banks (needed for slot_map).
    # load_config()/refresh() raise RefreshPartiallySucceeded / RefreshFailed on
    # read failures — see "Polling the plant" below for handling.
    await client.detect()
    await client.load_config()
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

## Polling the plant

Run `detect()` once after connecting, then drive your own poll loop over the
primitives: `load_config()` reads the HR configuration banks, `refresh()` reads
the IR measurement banks. Both return the populated `Plant` on full success, and
raise on read failures:

- `RefreshPartiallySucceeded` — some reads failed, some succeeded. The data that
  *did* arrive is on `exc.plant`; `exc.failures` lists the dropped reads (device
  address, request type, base register) and `exc.cause` is an `ExceptionGroup` of
  the raw errors. This is the one chance to use the partial data — cache it,
  surface it, count it — before deciding how to treat the gaps. How to treat them
  is the consumer's policy, not the library's.
- `RefreshFailed` — every read failed; the link is effectively dead and there is
  no partial data. Treat the device as unavailable.

Both share the base `RefreshError`, so a consumer that doesn't care to
distinguish can catch that.

```python
from givenergy_modbus.exceptions import RefreshFailed, RefreshPartiallySucceeded

async def main():
    client = Client(host="192.168.99.99", port=8899)
    await client.connect()
    await client.detect()

    while True:
        try:
            plant = await client.refresh()
        except RefreshPartiallySucceeded as exc:
            plant = exc.plant                  # use what we did collect
            # ...consumer policy: log exc.failures, bump a counter, etc.
        except RefreshFailed:
            plant = None                       # mark unavailable; maybe reconnect

        if plant is not None:                  # full or partial success
            print(f"SOC: {plant.batteries[0].soc}%")
        await asyncio.sleep(15)
```

> `Client.watch_plant()` and `Client.refresh_plant()` are deprecated and will be
> removed in 3.0 — own the loop as above. They now also propagate
> `RefreshPartiallySucceeded` / `RefreshFailed`.

## Power register measurement points

The instantaneous "grid" power registers on a single-phase Hybrid do **not** all
measure the same physical point — the shared `grid` prefix is misleading. There are
two distinct nodes: the inverter's own AC terminal (where it connects to the consumer
unit's busbar) and the external grid CT (the clamp at the meter boundary).

```
   PV ─DC─┐                       ┌─► house load            p_load_demand  (IR42)
          ├─[INVERTER]─AC─busbar──┤
   Bat ─DC┘   terminal            └─► grid CT ─► meter      p_grid_out     (IR30)
        p_grid_out_ph1 (IR24)          boundary
        p_grid_apparent (IR43)
        i_grid_port (IR58)
```

| Attribute | Node | Notes |
|---|---|---|
| `p_grid_out_ph1` (IR24) | **Inverter AC terminal** real power | onto the busbar; +ve = delivering. *Not* the grid CT despite the name |
| `p_grid_apparent` (IR43) | **Inverter AC terminal** apparent power (VA) | pairs with IR24 → sensible power factor |
| `i_grid_port` (IR58) | **Inverter AC terminal** current | pairs with IR24/IR43 |
| `p_grid_out` (IR30) | **External grid CT** net flow | +ve = export, −ve = import; the meter boundary |
| `p_load_demand` (IR42) | House load at the busbar | independently sensed, not derived from IR24−IR30 |
| `p_battery` (IR52) | Battery DC port | +ve = discharge, −ve = charge |

On a single-phase unit `p_grid_out_ph1` and `p_grid_out` are related but distinct
(per-phase inverter throughput vs net grid flow), so `inverter_terminal = load +
grid_export` (IR24 = IR42 + IR30) holds at the busbar. These node assignments were
established empirically against a single-phase Hybrid Gen 1; the three-phase layout
(whether `p_grid_out` aggregates the inverter phases or stays a separate CT register)
is not yet confirmed.

## Tuning timeouts and retries

`refresh`, `load_config` and `one_shot_command` all accept the same three knobs:

- `timeout` — how long to wait for each response. Defaults: `refresh` 2.0s, `load_config`
  2.0s, `one_shot_command` 1.5s.
- `retries` — number of additional attempts after a timeout. Defaults: `refresh` 1,
  `load_config` 3, `one_shot_command` 0.
- `retry_delay` (default 0.5s) — seconds to wait between a timed-out attempt and the next.

`refresh` defaults to `timeout=2.0, retries=1` because the inverter serialises requests:
when other clients (GivTCP, the vendor app, Predbat) poll the same unit, a tighter budget
loses the race and produces spurious "register read failed" timeouts even though the
device is responsive (#132). If you own the bus exclusively and want genuine failures
surfaced faster, pass a tighter `timeout`/`retries`.

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

The inverter knows its own `slot_map`, so slot setters don't need it threaded through. The base `_InverterCommands` mixin is composed onto both `SinglePhaseInverter` and `ThreePhaseInverter`; `_ThreePhaseCommands` (also composed onto `ThreePhaseInverter`) overrides the methods where single-phase and three-phase register addresses differ.

Three-phase inverters additionally carry the `_ThreePhaseCommands` mixin (marker: ✦ three-phase), so `set_ac_charge`, `set_force_charge`, `set_force_discharge`, and `set_battery_reserve_soc` are reachable as instance methods on `ThreePhaseInverter` only:

```python
if isinstance(inverter, ThreePhaseInverter):
    await client.one_shot_command(inverter.set_force_charge(True))
```

AC-limit commands (`set_battery_*_limit_ac`) and pause-mode commands (`set_battery_pause_mode`, `set_pause_slot_*`) remain on `commands.*` only — their model-vs-firmware applicability hasn't yet been confirmed against wire data (see [#75](https://github.com/dewet22/givenergy-modbus/issues/75)).

## EMS command API

EMS commands target the EMS plant controller — a peer device of the inverter, not the inverter itself — so they live on the `Ems` instance returned by `plant.ems` rather than on `plant.inverter`:

```python
ems = plant.ems
if ems is not None:  # None on non-EMS plants
    await client.one_shot_command(ems.set_ems_plant(True))
    await client.one_shot_command(ems.set_ems_charge_slot(1, my_timeslot))
    await client.one_shot_command(ems.set_export_slot(1, my_timeslot))
```

EMS slots use a fixed three-slot layout at HR(2044–2071) — there's no `slot_map` parameter. EMS commands are tagged ▣ ems in the tables below.

## Available commands

All commands live in `givenergy_modbus.client.commands` and return
`list[TransparentRequest]` for passing to `one_shot_command` or `execute`. The
inverter API above delegates to these; using them directly remains supported
for tests and lower-level integration.

### Stability

Both surfaces are supported within the 2.x line. The high-level mixin APIs
(`inverter.set_*` on `SinglePhaseInverter` / `ThreePhaseInverter`, `ems.set_*`
on `Ems`) are recommended; `commands.*` is the primitive layer that the
mixins delegate to. There is no plan to deprecate `commands.*` within 2.x —
the two are not duplicate paths but two layers of the same stack. If
individual primitives turn out to be persistent footguns when used without an
inverter (e.g. routing the wrong `slot_map`), they may be `@deprecated`
case-by-case.

### Where each command lives

| Surface | Composed onto | Marker in tables below |
|---|---|---|
| `_InverterCommands` | `SinglePhaseInverter`, `ThreePhaseInverter` | _(none — inherited base surface)_ |
| `_ThreePhaseCommands` | `ThreePhaseInverter` only | ✦ three-phase |
| `_EmsCommands` | `Ems` only | ▣ ems |
| `commands.*` only | _(not exposed as mixin method)_ | ⛔ commands-only |

An unmarked row means the method is available on both inverter types. On `ThreePhaseInverter`, `_ThreePhaseCommands` overrides `set_battery_soc_reserve`, `set_charge_target`, `disable_charge_target`, and the slot setters to use the correct three-phase registers (HR 1109, 1111, 1113–1121).

### Charging

| Function | Description | Surface |
|---|---|---|
| `set_charge_target(soc)` | Stop charging when SOC reaches `soc`% (4–100) | |
| `disable_charge_target()` | Remove SOC limit, target 100% | |
| `set_enable_charge(enabled)` | Enable or disable charging | |
| `set_battery_charge_limit(val)` | Charge power limit (0–50%) | |
| `set_battery_charge_limit_ac(val)` | AC charge power limit (1–100%) | ⛔ commands-only |
| `set_shallow_charge(val)` | Set shallow charge threshold (deprecated — use `set_battery_soc_reserve`) | ⛔ commands-only |

### Discharging

| Function | Description | Surface |
|---|---|---|
| `set_enable_discharge(enabled)` | Enable or disable discharging | |
| `set_battery_discharge_limit(val)` | Discharge power limit (0–50%) | |
| `set_battery_discharge_limit_ac(val)` | AC discharge power limit (1–100%) | ⛔ commands-only |
| `set_battery_soc_reserve(val)` | Minimum SOC to maintain (4–100%) | |
| `set_battery_power_reserve(val)` | Battery power reserve (4–100%) | |

### Time slots

| Function | Description | Surface |
|---|---|---|
| `set_charge_slot(idx, timeslot, slot_map)` | Set charge slot `idx` (1-based) | |
| `set_charge_slot_start(idx, t, slot_map)` | Set just the start of charge slot `idx` (or `None` to clear that end) | |
| `set_charge_slot_end(idx, t, slot_map)` | Set just the end of charge slot `idx` (or `None` to clear that end) | |
| `reset_charge_slot(idx, slot_map)` | Clear charge slot `idx` | |
| `set_discharge_slot(idx, timeslot, slot_map)` | Set discharge slot `idx` (1-based) | |
| `set_discharge_slot_start(idx, t, slot_map)` | Set just the start of discharge slot `idx` (or `None` to clear that end) | |
| `set_discharge_slot_end(idx, t, slot_map)` | Set just the end of discharge slot `idx` (or `None` to clear that end) | |
| `reset_discharge_slot(idx, slot_map)` | Clear discharge slot `idx` | |
| `set_export_slot(idx, slot)` | Set export slot `idx` (1–3), or clear if `None` | ▣ ems |
| `set_export_slot_start(idx, t)` | Set just the start of export slot `idx` | ▣ ems |
| `set_export_slot_end(idx, t)` | Set just the end of export slot `idx` | ▣ ems |
| `set_export_priority(priority)` | Set surplus-power dispatch priority (`ExportPriority`: BATTERY_FIRST, GRID_FIRST, LOAD_FIRST) — AC-coupled only | |
| `set_enable_eps(enabled)` | Enable or disable Emergency Power Supply (EPS) mode — AC-coupled only | |
| `set_battery_pause_mode(val)` | Set pause mode (`BatteryPauseMode`: DISABLED, PAUSE_CHARGE, PAUSE_DISCHARGE, PAUSE_BOTH) | ⛔ commands-only |
| `set_pause_slot(slot)` | Set battery pause time slot (or `None` to clear) | ⛔ commands-only |
| `set_pause_slot_start(t)` | Set just the start of the battery pause slot | ⛔ commands-only |
| `set_pause_slot_end(t)` | Set just the end of the battery pause slot | ⛔ commands-only |
| `set_ems_plant(enabled)` | Enable/disable EMS plant control | ▣ ems |
| `set_ems_charge_slot(idx, timeslot)` | Set EMS plant charge slot `idx` (1–3), or clear if `None` | ▣ ems |
| `set_ems_charge_slot_start(idx, t)` | Set just the start of EMS charge slot `idx` | ▣ ems |
| `set_ems_charge_slot_end(idx, t)` | Set just the end of EMS charge slot `idx` | ▣ ems |
| `set_ems_discharge_slot(idx, timeslot)` | Set EMS plant discharge slot `idx` (1–3), or clear if `None` | ▣ ems |
| `set_ems_discharge_slot_start(idx, t)` | Set just the start of EMS discharge slot `idx` | ▣ ems |
| `set_ems_discharge_slot_end(idx, t)` | Set just the end of EMS discharge slot `idx` | ▣ ems |
| `set_ems_charge_target_soc(idx, soc)` | EMS charge slot `idx` target SOC (0–100%) | ▣ ems |
| `set_ems_discharge_target_soc(idx, soc)` | EMS discharge slot `idx` target SOC (0–100%) | ▣ ems |
| `set_ems_export_slot(idx, timeslot)` | Set EMS plant export slot `idx` (1–3), or clear if `None` | ▣ ems |
| `set_ems_export_slot_start(idx, t)` | Set just the start of EMS export slot `idx` | ▣ ems |
| `set_ems_export_slot_end(idx, t)` | Set just the end of EMS export slot `idx` | ▣ ems |
| `set_ems_export_target_soc(idx, soc)` | EMS export slot `idx` target SOC (0–100%) | ▣ ems |
| `set_ems_export_power_limit(watts)` | EMS plant export power limit (watts) | ▣ ems |

EMS plant scheduling commands (`set_ems_*`) target the EMS controller's own
plant-config registers (HR 2040-2071) and use a fixed three-slot layout, so —
unlike the inverter charge/discharge setters — they take no `slot_map`. Use them
only against an EMS device (`plant.capabilities.is_ems`); they have no effect on a
standalone inverter. Export slots themselves (`set_export_slot`) are shared with the
EMS export schedule.

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

| Function | Description | Surface |
|---|---|---|
| `set_mode_dynamic()` | Dynamic/Eco mode — maximise self-consumption | |
| `set_mode_storage(discharge_slot_1, discharge_slot_2, discharge_for_export)` | Storage/timed discharge mode | |
| `set_discharge_mode_max_power()` | Set battery to discharge at max power | |
| `set_discharge_mode_to_match_demand()` | Set battery to match load demand | |
| `set_ac_charge(enabled)` | Enable or disable AC charging | ✦ three-phase |
| `set_force_charge(enabled)` | Force battery charge | ✦ three-phase |
| `set_force_discharge(enabled)` | Force battery discharge | ✦ three-phase |
| `set_battery_reserve_soc(val)` | Battery reserve SOC (HR 1078, "Battery Reserve %", 4–100%) | ✦ three-phase |

### Battery calibration

| Function | Description | Surface |
|---|---|---|
| `set_calibrate_battery_soc(val)` | Recalibrate SOC estimation: `0` = Stop, `1` = Start (default), `3` = Charge Only | |

### System

| Function | Description | Surface |
|---|---|---|
| `set_active_power_rate(target)` | Max inverter output as % of rated capacity | |
| `set_system_date_time(dt)` | Set inverter clock | |
| `set_enable_rtc(enabled)` | Enable Real Time Clock (persists settings to EEPROM) | |
| `set_inverter_reboot()` | Restart the inverter | |

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

from givenergy_modbus.exceptions import RefreshError

with open("capture.txt", "w") as f:
    def write_line(direction, frame):
        ts = datetime.now(UTC).isoformat(timespec="microseconds")
        f.write(f"{ts} {direction} {frame.hex()}\n")
        f.flush()
    async with Client("inverter.local", 8899) as client:
        await client.detect()

        async def poll():
            while True:
                try:
                    await client.refresh()
                except RefreshError:  # ignore partial/total failures for this capture demo
                    pass
                await asyncio.sleep(5)

        await asyncio.gather(
            poll(),
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
  "inverter_address": "0x11",
  "meter_addresses": ["0x01"],
  "lv_battery_addresses": ["0x32", "0x33"],
  "bcu_stacks": []
}
```

`inverter_address` is derived from the model: `0x11` for most inverters, `0x31`
for `AC` and `HYBRID_GEN1`. LV battery pack #1 lives at `0x32`, additional packs
at `0x33`–`0x37`. State persisted before this mapping (which used `0x32` as the
inverter address) reloads unchanged and self-heals on the next `detect()` via a
one-off `PlantTopologyMismatch`.
