#!/usr/bin/env python
"""Console script for interacting with GivEnergy inverters."""

import logging

import click

from .client import GivEnergyClient
from .util import InterceptHandler

_logger = logging.getLogger(__package__)


@click.group()
@click.option(
    '--log-level',
    default='DEBUG',
    type=click.Choice(['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'NOTSET'], case_sensitive=False),
)
def main(log_level):
    """A python library to access GivEnergy inverters via Modbus TCP, with no dependency on the GivEnergy Cloud."""
    # Install our improved logging handler.
    logging.basicConfig(handlers=[InterceptHandler()], level=getattr(logging, log_level))


@main.command()
@click.option('-h', '--host', type=str)
@click.option('-b', '--batteries', type=int, default=1)
def dump_registers(host, batteries):
    """Dump out raw register data for use in debugging."""
    _logger.info(f'Connecting to host {host}')
    client = GivEnergyClient(host=host)
    inverter_json = client.fetch_inverter_registers().to_json()
    batteries_json = {}
    for i in range(batteries):
        batteries_json[i] = client.fetch_battery_registers(i).to_json()

    click.echo('Inverter registers:')
    click.echo(inverter_json)
    click.echo('Batteries registers:')
    click.echo(batteries_json)


if __name__ == "__main__":
    main()  # pragma: no cover
