# GivEnergy Modbus

[![pypi](https://img.shields.io/pypi/v/givenergy-modbus.svg)](https://pypi.org/project/givenergy-modbus/)
[![python](https://img.shields.io/pypi/pyversions/givenergy-modbus.svg)](https://pypi.org/project/givenergy-modbus/)
[![Build Status](https://github.com/dewet22/givenergy-modbus/actions/workflows/dev.yml/badge.svg)](https://github.com/dewet22/givenergy-modbus/actions/workflows/dev.yml)
[![codecov](https://codecov.io/gh/dewet22/givenergy-modbus/branch/main/graphs/badge.svg)](https://codecov.io/github/dewet22/givenergy-modbus)

A python library to access GivEnergy inverters via Modbus TCP on a local network, with no dependency on the GivEnergy
Cloud. This extends [pymodbus](https://pymodbus.readthedocs.io/) by providing a custom framer, decoder and PDUs that are
specific to the GivEnergy implementation.

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

Use the provided client to interact with the device over the network, and register caches to build combined state of a
device:

```python
import datetime
from givenergy_modbus.client import GivEnergyClient
from givenergy_modbus.model.battery import Battery
from givenergy_modbus.model.inverter import Inverter, Model
from givenergy_modbus.model.register_cache import RegisterCache

client = GivEnergyClient(host="192.168.99.99")

# change configuration on the device:
client.enable_charge_target(80)
# set a charging slot from 00:30 to 04:30
client.set_charge_slot_1((datetime.time(hour=0, minute=30), datetime.time(hour=4, minute=30)))
# set the inverter to charge when there's excess, and discharge otherwise. it will also respect charging slots.
client.set_mode_dynamic()

rc = RegisterCache()
client.update_inverter_registers(rc)
inverter = Inverter.from_orm(rc)
assert inverter.inverter_serial_number == 'SA1234G567'
assert inverter.inverter_model == Model.Hybrid
assert inverter.v_pv1 == 1.4  # V
assert inverter.e_battery_discharge_day == 8.1  # kWh
assert inverter.enable_charge_target
assert inverter.dict() == {
    'inverter_serial_number': 'SA1234G567',
    'device_type_code': '3001',
    'charge_slot_1': (datetime.time(0, 30), datetime.time(7, 30)),
    'f_ac1': 49.98,
    ...
}
assert inverter.json() == '{"inverter_serial_number": "SA1234G567", "device_type_code": "3001", ...'

# it is _probably_ a good idea to not share register caches across devices
rc = RegisterCache()
client.update_battery_registers(rc, battery_number=0)
battery = Battery.from_orm(rc)

assert battery.serial_number == 'BG1234G567'
assert battery.v_battery_cell_01 == 3.117
assert battery.dict() == {
    'bms_firmware_version': 3005,
    'design_capacity': 160.0,
    ...
}
assert battery.json() == '{"battery_serial_number": "BG1234G567", "v_battery_cell_01": 3.117, ...'
```

## Credits

This package was created with [Cookiecutter](https://github.com/audreyr/cookiecutter) and
the [waynerv/cookiecutter-pypackage](https://github.com/waynerv/cookiecutter-pypackage) project template.
