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
from givenergy_modbus.client import GivEnergyModbusClient
from givenergy_modbus.model.register_banks import HoldingRegister

with GivEnergyModbusClient(host="192.168.99.99") as client:
    data = client.refresh()
    client.write_holding_register(HoldingRegister.WINTER_MODE, 1)

# Data is returned as an instance of `model.Inverter` which allows indexing and attribute access
assert data.serial_number == 'SA1234G567'
assert data['model'] == 'Hybrid'
assert data.v_pv1 == 1.4000000000000001
assert data.v_battery_cell01 == 3.117
assert data.e_grid_out_total == 0.6000000000000001
assert data.winter_mode
```

## Credits

This package was created with [Cookiecutter](https://github.com/audreyr/cookiecutter) and the [waynerv/cookiecutter-pypackage](https://github.com/waynerv/cookiecutter-pypackage) project template.
