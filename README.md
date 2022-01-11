# GivEnergy Modbus

[![pypi](https://img.shields.io/pypi/v/givenergy-modbus.svg)](https://pypi.org/project/givenergy-modbus/)
[![python](https://img.shields.io/pypi/pyversions/givenergy-modbus.svg)](https://pypi.org/project/givenergy-modbus/)
[![Build Status](https://github.com/dewet22/givenergy-modbus/actions/workflows/dev.yml/badge.svg)](https://github.com/dewet22/givenergy-modbus/actions/workflows/dev.yml)
[![codecov](https://codecov.io/gh/dewet22/givenergy-modbus/branch/main/graphs/badge.svg)](https://codecov.io/github/dewet22/givenergy-modbus)

A python library to access GivEnergy inverters via Modbus TCP on a local network, with no dependency on the GivEnergy Cloud.
This extends [pymodbus](https://pymodbus.readthedocs.io/) by providing a custom framer, decoder and PDUs
that are specific to the GivEnergy implementation.

> ⚠️ This project makes no representations as to its completeness or correctness. You use it at your own risk — if your inverter
> mysteriously explodes because you accidentally set the `BOOMTIME` register, or you consume a MWh of electricity doing SOC calibration,
> you really are on your own.

* Documentation: <https://dewet22.github.io/givenergy-modbus>
* GitHub: <https://github.com/dewet22/givenergy-modbus>
* PyPI: <https://pypi.org/project/givenergy-modbus/>
* Free software: Apache-2.0

## Features

* Reading all registers and decoding them into their representative datatypes
* Writing data to individual holding registers that are deemed to be safe

## How to use

Use the provided client to interact with the device over the network:

```python
from datetime import time
from givenergy_modbus.client import GivEnergyClient
from givenergy_modbus.model.inverter import Model

client = GivEnergyClient(host="192.168.99.99")
client.enable_charge_target(80)
# set a charging slot from 00:30 to 04:30
client.set_charge_slot_1((time(hour=0, minute=30), time(hour=4, minute=30)))

inverter = client.fetch_inverter()
assert inverter.serial_number == 'SA1234G567'
assert inverter.model == Model.Hybrid
assert inverter.v_pv1 == 1.4000000000000001
assert inverter.e_generated_day == 8.1
assert inverter.enable_charge_target
assert inverter.dict() == {
    'active_power_rate': 100,
    'arm_firmware_version': 449,
    'battery_charge_limit': 50,
    ...
}

battery = client.fetch_battery(battery_number=0)

assert battery.serial_number == 'BG1234G567'
assert battery.v_cell_01 == 3.117
assert battery.dict() == {
    'bms_firmware_version': 3005,
    'design_capacity': 160.0,
    ...
}
```

## Credits

This package was created with [Cookiecutter](https://github.com/audreyr/cookiecutter) and the [waynerv/cookiecutter-pypackage](https://github.com/waynerv/cookiecutter-pypackage) project template.
