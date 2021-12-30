"""Console script for givenergy_modbus."""

import logging

import click

from .client import GivEnergyClient
from .pdu import ReadInputRegistersRequest

_logger = logging.getLogger(__package__)


@click.command()
def main():
    """Main entrypoint."""
    click.echo("givenergy-modbus")
    click.echo("=" * len("givenergy-modbus"))
    click.echo(
        "A python library to access GivEnergy inverters via Modbus TCP, with no dependency on the GivEnergy Cloud."
    )

    with GivEnergyClient(host="192.168.0.241") as client:
        _logger.debug(f"client {client}: {vars(client)}")
        _logger.debug(f"framer {client.framer}: {vars(client.framer)}")
        # client.register(GivEnergyModbusResponse)
        request = ReadInputRegistersRequest(base_register=0x0, register_count=6)
        _logger.info(f"request: {request}")
        result = client.execute(request)
        _logger.info(f"result: {result}")
        # print(result.values)


if __name__ == "__main__":
    main()  # pragma: no cover
