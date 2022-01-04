#!/usr/bin/env python
"""Console script for interacting with GivEnergy inverters."""

import logging

import click

from .client import GivEnergyModbusClient

# from .model.inverter import Inverter
# from .model.register_banks import HoldingRegister, InputRegister
# from .pdu import ReadInputRegistersRequest
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

    with GivEnergyModbusClient(host="192.168.0.241") as client:
        # print(client.execute(ReadInputRegistersRequest(slave_address=0x37, base_register=60, register_count=16)))
        i = client.get_inverter()
        i.debug()
        # print(client.refresh())


if __name__ == "__main__":
    main()  # pragma: no cover
