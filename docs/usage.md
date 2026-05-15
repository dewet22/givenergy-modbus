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

The number of available slots depends on the inverter model. Always pass
`inverter.slot_map` to slot commands so the correct register addresses are used:

```python
slot_map = plant.inverter.slot_map

# Set slot 1 (available on all models)
await client.one_shot_command(
    commands.set_charge_slot(1, TimeSlot.from_components(0, 30, 4, 30), slot_map)
)

# Set slot 5 (only available on extended-slot models)
await client.one_shot_command(
    commands.set_charge_slot(5, TimeSlot.from_components(12, 0, 14, 0), slot_map)
)

# Clear slot 3
await client.one_shot_command(commands.reset_charge_slot(3, slot_map))
```

Models and their slot counts:

| Models | Charge slots | Discharge slots |
|---|---|---|
| HYBRID_GEN1, HYBRID_GEN2, AC, POLAR | 2 | 2 |
| HYBRID_GEN3 (ARM fw ≤ 302) | 2 | 2 |
| HYBRID_GEN3 (ARM fw > 302), ALL_IN_ONE, HYBRID_GEN4, HYBRID_HV_GEN3 | 10 | 10 |
| Three-phase (HYBRID_3PH, AC_3PH) | 10 | 10 |

## Available commands

All commands live in `givenergy_modbus.client.commands` and return
`list[TransparentRequest]` for passing to `one_shot_command` or `execute`.

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
| `reset_charge_slot(idx, slot_map)` | Clear charge slot `idx` |
| `set_discharge_slot(idx, timeslot, slot_map)` | Set discharge slot `idx` (1-based) |
| `reset_discharge_slot(idx, slot_map)` | Clear discharge slot `idx` |
| `set_export_slot(idx, slot)` | Set export slot `idx` (1–3), or clear if `None` |
| `set_battery_pause_mode(val)` | Set pause mode (`BatteryPauseMode`: DISABLED, PAUSE_CHARGE, PAUSE_DISCHARGE, PAUSE_BOTH) |
| `set_pause_slot(slot)` | Set battery pause time slot (or `None` to clear) |

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
