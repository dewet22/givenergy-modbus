#!/usr/bin/env python
"""Console script for interacting with GivEnergy inverters."""

import logging

import click

from .client import GivEnergyClient
from .util import InterceptHandler

_logger = logging.getLogger(__package__)


@click.command()
def main():
    """Main entrypoint for the CLI."""
    # Install our improved logging handler.
    logging.basicConfig(handlers=[InterceptHandler()], level=logging.INFO)

    click.echo("givenergy-modbus")
    click.echo("=" * len("givenergy-modbus"))
    click.echo(
        "A python library to access GivEnergy inverters via Modbus TCP, with no dependency on the GivEnergy Cloud."
    )

    client = GivEnergyClient(host="192.168.0.241")
    # client.load_inverter_registers().debug()
    # client.load_battery_registers(0).debug()
    # client.load_battery_registers(1).debug()
    print(client.fetch_inverter())
    print(client.fetch_battery())


if __name__ == "__main__":
    main()  # pragma: no cover
