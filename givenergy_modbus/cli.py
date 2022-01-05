#!/usr/bin/env python
"""Console script for interacting with GivEnergy inverters."""

import logging

import click

from .client import GivEnergyClient

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

    client = GivEnergyClient(host="192.168.0.241")
    client.refresh()
    client.inverter.debug()


if __name__ == "__main__":
    main()  # pragma: no cover
