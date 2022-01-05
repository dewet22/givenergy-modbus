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

client = GivEnergyClient(host="192.168.99.99")
client.refresh()
client.set_winter_mode(True)
# set a charging slot from 00:30 to 04:30
client.set_charge_slot_1(time(hour=0, minute=30), time(hour=4, minute=30))

# Data is returned as an instance of `model.Inverter` which
# allows indexing and direct attribute access
client.refresh()
assert client.inverter.serial_number == 'SA1234G567'
assert client.inverter['model'] == 'Hybrid'
assert client.inverter.v_pv1 == 1.4000000000000001
assert client.inverter.v_battery_cell01 == 3.117
assert client.inverter.e_grid_out_total == 0.6000000000000001
assert client.inverter.winter_mode
```

## Credits

This package was created with [Cookiecutter](https://github.com/audreyr/cookiecutter) and the [waynerv/cookiecutter-pypackage](https://github.com/waynerv/cookiecutter-pypackage) project template.
