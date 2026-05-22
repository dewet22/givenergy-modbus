# GivEnergy Modbus

<p align="center"><img src="logo.png" alt="GivEnergy" width="320"></p>

[![pypi](https://img.shields.io/pypi/v/givenergy-modbus)](https://pypi.org/project/givenergy-modbus/)
[![python](https://img.shields.io/pypi/pyversions/givenergy-modbus)](https://pypi.org/project/givenergy-modbus/)
[![CI](https://img.shields.io/github/checks-status/dewet22/givenergy-modbus/main)](https://github.com/dewet22/givenergy-modbus/actions?query=branch%3Amain)
[![codecov](https://img.shields.io/codecov/c/github/dewet22/givenergy-modbus)](https://codecov.io/github/dewet22/givenergy-modbus)
[![license](https://img.shields.io/github/license/dewet22/givenergy-modbus)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

A Python library for communicating with GivEnergy inverters via Modbus TCP on a local network, with no dependency on the GivEnergy Cloud. Inspired by and originally built on [pymodbus](https://pymodbus.readthedocs.io/), it now provides its own asyncio-based framer, decoder and PDUs specific to the GivEnergy implementation.

> ⚠️ This project makes no representations as to its completeness or correctness. You use it at your own risk — if your
> inverter mysteriously explodes because you accidentally set the `BOOMTIME` register or you consume a MWh of
> electricity doing SOC calibration: you **really** are on your own. We make every effort to prevent you from shooting
> yourself in the foot, so as long as you use the client and its exposed methods, you should be perfectly safe.

* Documentation: <https://dewet22.github.io/givenergy-modbus>
* GitHub: <https://github.com/dewet22/givenergy-modbus>
* PyPI: <https://pypi.org/project/givenergy-modbus/>
* Free software: Apache-2.0

## Features

* Reading all registers and decoding them into their representative datatypes
* Writing data to holding registers that are deemed to be safe to set configuration on the inverter

## How to use

The client is async. Use it inside an `asyncio` event loop; commands are plain functions that return request lists
which you send via `one_shot_command` or `execute`:

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
    # set a charging slot from 00:30 to 04:30; slot_map selects correct registers for this model
    await client.one_shot_command(
        commands.set_charge_slot(1, TimeSlot.from_components(0, 30, 4, 30), plant.inverter.slot_map)
    )
    # set the inverter to charge from excess solar and discharge to meet demand
    await client.one_shot_command(commands.set_mode_dynamic())

    assert plant.inverter_serial_number == 'SA1234G567'
    assert plant.inverter.model == Model.HYBRID
    assert plant.inverter.enable_charge_target
    assert plant.inverter.charge_slot_1 == TimeSlot.from_components(0, 30, 4, 30)
    assert plant.inverter.model_dump() == {
        'serial_number': 'SA1234G567',
        'device_type_code': '3001',
        'charge_slot_1': TimeSlot.from_components(0, 30, 4, 30),
        ...
    }
    assert plant.inverter.model_dump_json() == '{"serial_number": "SA1234G567", "device_type_code": "3001", ...'

    assert plant.batteries[0].serial_number == 'BG1234G567'
    assert plant.batteries[0].v_cell_01 == 3.117
    assert plant.batteries[0].model_dump() == {
        'bms_firmware_version': 3005,
        'cap_design': 160.0,
        ...
    }
    assert plant.batteries[0].model_dump_json() == '{"serial_number": "BG1234G567", "v_cell_01": 3.117, ...'

    await client.close()

asyncio.run(main())
```

## Credits

This package was created with [Cookiecutter](https://github.com/audreyr/cookiecutter) and
the [waynerv/cookiecutter-pypackage](https://github.com/waynerv/cookiecutter-pypackage) project template.
