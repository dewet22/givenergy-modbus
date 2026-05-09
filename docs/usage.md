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

    # Write configuration to the device
    await client.one_shot_command(commands.set_charge_target(80))
    await client.one_shot_command(commands.set_charge_slot_1(TimeSlot.from_components(0, 30, 4, 30)))
    await client.one_shot_command(commands.set_mode_dynamic())

    # Read current state
    await client.refresh_plant(full_refresh=True)
    plant = client.plant

    print(plant.inverter_serial_number)
    print(plant.inverter.model)           # e.g. Model.HYBRID
    print(plant.inverter.enable_charge_target)
    print(plant.inverter.charge_slot_1)   # TimeSlot instance

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

## Available commands

All commands live in `givenergy_modbus.client.commands` and return
`list[TransparentRequest]` for passing to `one_shot_command` or `execute`:

| Function | Description |
|---|---|
| `set_charge_target(soc)` | Stop charging when SOC reaches `soc`% |
| `disable_charge_target()` | Remove SOC limit, target 100% |
| `set_enable_charge(enabled)` | Enable or disable charging |
| `set_enable_discharge(enabled)` | Enable or disable discharging |
| `set_charge_slot_1(timeslot)` | Set charge slot 1 start/end times |
| `set_charge_slot_2(timeslot)` | Set charge slot 2 start/end times |
| `set_discharge_slot_1(timeslot)` | Set discharge slot 1 start/end times |
| `set_discharge_slot_2(timeslot)` | Set discharge slot 2 start/end times |
| `set_mode_dynamic()` | Dynamic/Eco mode — maximise self-consumption |
| `set_mode_storage(...)` | Storage mode with configurable discharge slots |
| `set_battery_soc_reserve(val)` | Minimum SOC to maintain |
| `set_battery_charge_limit(val)` | Charge power limit (0–50%) |
| `set_battery_discharge_limit(val)` | Discharge power limit (0–50%) |
| `set_system_date_time(dt)` | Set inverter clock |
| `set_inverter_reboot()` | Restart the inverter |

## Serialisation

All model objects are pydantic v2 models:

```python
plant.inverter.model_dump()       # dict
plant.inverter.model_dump_json()  # JSON string
```
