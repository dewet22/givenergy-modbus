"""Console script for interacting with GivEnergy inverters."""

import logging

import click

from givenergy_modbus.client import GivEnergyClient
from givenergy_modbus.model.register_cache import RegisterCache
from givenergy_modbus.util import InterceptHandler

_logger = logging.getLogger(__package__)


@click.group()
@click.option(
    '--log-level',
    default='INFO',
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
    rc = RegisterCache()
    client.update_inverter_registers(register_cache=rc)
    inverter_json = rc.to_json()

    batteries_json = {}
    for i in range(batteries):
        rc = RegisterCache()
        client.update_battery_registers(register_cache=rc, battery_number=i)
        batteries_json[i] = rc.to_json()

    click.echo('Inverter registers:')
    click.echo(inverter_json)
    click.echo('Batteries registers:')
    click.echo(batteries_json)


if __name__ == "__main__":
    main()  # pragma: no cover
