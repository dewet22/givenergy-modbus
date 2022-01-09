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
    logging.basicConfig(handlers=[InterceptHandler()], level=0)

    click.echo("givenergy-modbus")
    click.echo("=" * len("givenergy-modbus"))
    click.echo(
        "A python library to access GivEnergy inverters via Modbus TCP, with no dependency on the GivEnergy Cloud."
    )

    client = GivEnergyClient(host="192.168.0.241")
    client.refresh()
    client.register_cache.debug()
    # print(client.inverter.to_dict())
    # print({k: v for k, v in client.inverter.to_dict().items() if k.find('charge') >= 0})


if __name__ == "__main__":
    main()  # pragma: no cover
