"""Console script for givenergy_modbus."""

import logging

import click

from .client import GivEnergyClient
from .pdu import ReadHoldingRegistersRequest, ReadInputRegistersRequest
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

    with GivEnergyClient(host="192.168.0.241") as client:
        ir = client.execute(ReadInputRegistersRequest(base_register=0x0, register_count=60)).register_values
        hr1 = client.execute(ReadHoldingRegistersRequest(base_register=0x0, register_count=60)).register_values
        hr2 = client.execute(ReadHoldingRegistersRequest(base_register=60, register_count=60)).register_values

    _logger.info({1: ir, 2: hr1, 3: hr2})


if __name__ == "__main__":
    main()  # pragma: no cover
