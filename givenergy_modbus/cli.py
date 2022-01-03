"""Console script for givenergy_modbus."""

import logging
import time

import click

from .client import GivEnergyModbusClient
from .model.register_banks import HoldingRegister, InputRegister
from .util import InterceptHandler

_logger = logging.getLogger(__package__)


@click.command()
def main():
    """Main entrypoint for the CLI."""
    # Install our improved logging handler.
    logging.basicConfig(handlers=[InterceptHandler()], level=0)

    click.echo("givenergy-modbus")
    click.echo("=" * len("givenergy-modbus"))
    click.echo(
        "A python library to access GivEnergy inverters via Modbus TCP, with no dependency on the GivEnergy Cloud."
    )

    start = time.time()
    with GivEnergyModbusClient(host="192.168.0.241") as client:
        registers = {'i': client.read_all_input_registers(), 'h': client.read_all_holding_registers()}
    end = time.time()
    _logger.info(f'Reading all registers took {end-start:.3}s')

    for i, v in enumerate(registers['h']):
        r = HoldingRegister(i)
        print(
            f'{i:3} {r.name:40} {r.type.name:15} {r.scaling.name:5} '
            f'{r.scaling.value:5} 0x{v:04x} {v:10} {r.render(v):>20}'
        )

    print('#' * 100)
    for i, v in enumerate(registers['i']):
        r = InputRegister(i)
        print(
            f'{i:3} {r.name:40} {r.type.name:15} {r.scaling.name:5} '
            f'{r.scaling.value:5} 0x{v:04x} {v:10} {r.render(v):>20}'
        )
    print(registers)


if __name__ == "__main__":
    main()  # pragma: no cover
