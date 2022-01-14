"""Console script for interacting with GivEnergy inverters."""
import logging

import click

from givenergy_modbus.client import GivEnergyClient
from givenergy_modbus.model.register_cache import RegisterCache
from givenergy_modbus.util import InterceptHandler

_logger = logging.getLogger(__package__)


def is_documented_by(original):
    """Copies the docstring from the original source to the decorated target."""

    def wrapper(target):
        target.__doc__ = original.__doc__
        return target

    return wrapper


@click.group()
@click.option('-h', '--host', type=str, required=True, envvar='GIVENERGY_HOST')
@click.option(
    '--log-level',
    default='INFO',
    type=click.Choice(['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'NOTSET'], case_sensitive=False),
)
@click.pass_context
def main(ctx, host, log_level):
    """A python library to access GivEnergy inverters via Modbus TCP, with no dependency on the GivEnergy Cloud."""
    ctx.ensure_object(dict)

    # Install our improved logging handler.
    logging.basicConfig(handlers=[InterceptHandler()], level=getattr(logging, log_level))
    ctx.obj['CLIENT'] = GivEnergyClient(host=host)


@main.command()
@click.pass_context
@click.option('-b', '--batteries', type=int, default=1)
def dump_registers(ctx, batteries):
    """Dump out raw register data for use in debugging."""
    rc = RegisterCache()
    ctx.obj['CLIENT'].update_inverter_registers(register_cache=rc)
    inverter_json = rc.to_json()

    batteries_json = {}
    for i in range(batteries):
        rc = RegisterCache()
        ctx.obj['CLIENT'].update_battery_registers(register_cache=rc, battery_number=i)
        batteries_json[i] = rc.to_json()

    click.echo('Inverter registers:')
    click.echo(inverter_json)
    click.echo('Batteries registers:')
    click.echo(batteries_json)


@main.command()
@click.pass_context
@click.argument('target_soc', type=int)
@is_documented_by(GivEnergyClient.enable_charge_target)
def enable_charge_target(ctx, target_soc):  # noqa: D103
    ctx.obj['CLIENT'].enable_charge_target(target_soc)


@main.command()
@click.pass_context
@is_documented_by(GivEnergyClient.disable_charge_target)
def disable_charge_target(ctx):  # noqa: D103
    ctx.obj['CLIENT'].disable_charge_target()


@main.command()
@click.pass_context
@is_documented_by(GivEnergyClient.enable_charge)
def enable_charge(ctx):  # noqa: D103
    ctx.obj['CLIENT'].enable_charge()


@main.command()
@click.pass_context
@is_documented_by(GivEnergyClient.disable_charge)
def disable_charge(ctx):  # noqa: D103
    ctx.obj['CLIENT'].disable_charge()


@main.command()
@click.pass_context
@is_documented_by(GivEnergyClient.enable_discharge)
def enable_discharge(ctx):  # noqa: D103
    ctx.obj['CLIENT'].enable_discharge()


@main.command()
@click.pass_context
@is_documented_by(GivEnergyClient.disable_discharge)
def disable_discharge(ctx):  # noqa: D103
    ctx.obj['CLIENT'].disable_discharge()


if __name__ == "__main__":
    main(obj={})  # pragma: no cover
