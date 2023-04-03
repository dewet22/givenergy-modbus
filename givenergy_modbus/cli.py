"""Console script for interacting with GivEnergy inverters."""
import asyncio
import datetime
import logging
import pprint
import sys

import click
from loguru import logger

from givenergy_modbus.client.coordinator import Coordinator


class InterceptHandler(logging.Handler):
    """Install loguru by intercepting logging."""

    def emit(self, record):
        """Redirect logging emissions to loguru instead."""
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where the logged message originated, skipping frames from plumbing/infrastructure
        frame, depth = sys._getframe(6), 6
        while frame and (
            frame.f_code.co_filename == logging.__file__ or 'sentry_sdk/integrations' in frame.f_code.co_filename
        ):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def is_documented_by(original):
    """Copies the docstring from the original source to the decorated target."""

    def wrapper(target):
        target.__doc__ = original.__doc__
        return target

    return wrapper


@click.group()
@click.option(
    '-h',
    '--host',
    help='Host to connect to, can also be set via the GIVENERGY_HOST environment variable',
    type=str,
    required=True,
    envvar='GIVENERGY_HOST',
)
@click.option(
    '-p',
    '--port',
    help='Port to connect to, can also be set via the GIVENERGY_PORT environment variable',
    type=int,
    required=False,
    default=8899,
    envvar='GIVENERGY_PORT',
)
@click.option(
    '--log-level',
    default='INFO',
    type=click.Choice(['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'NOTSET'], case_sensitive=False),
)
@click.pass_context
def main(ctx, host, port, log_level):
    """A python CLI to access GivEnergy inverters via Modbus TCP, with no dependency on the GivEnergy Cloud."""
    ctx.ensure_object(dict)
    logging.basicConfig(handlers=[InterceptHandler()], force=True, level=getattr(logging, log_level))
    ctx.obj['CLIENT'] = Coordinator(host=host, port=port)


@main.command()
@click.pass_context
# @click.option('-b', '--batteries', type=int, default=1)
def show_plant(ctx):
    """Show interpretation of the current plant state."""
    p = asyncio.run(ctx.obj['CLIENT'].refresh_plant())
    click.echo('Inverter data:')
    click.echo(pprint.pformat(p.inverter.dict(), indent=4))
    for i, b in enumerate(p.batteries):
        click.echo(f'Battery #{i} data:')
        click.echo(pprint.pformat(b.dict(), indent=4))
    # logger.info(json.dumps(p.register_caches))


@main.command()
@click.pass_context
# @click.option('-b', '--batteries', type=int, default=1)
def dump_registers(ctx):
    """Dump out raw register data for use in debugging."""
    p = asyncio.run(ctx.obj['CLIENT'].refresh_plant())
    for i, rc in p.register_caches.items():
        click.echo(f'{i}: {rc.json()}')


@main.command()
@click.pass_context
@click.argument('target_soc', type=int)
# @is_documented_by(Coordinator.set_charge_target)
def set_charge_target(ctx, target_soc):  # noqa: D103
    ctx.obj['CLIENT'].set_charge_target(target_soc)


@main.command()
@click.pass_context
# @is_documented_by(Coordinator.disable_charge_target)
def disable_charge_target(ctx):  # noqa: D103
    ctx.obj['CLIENT'].disable_charge_target()


@main.command()
@click.pass_context
# @is_documented_by(Coordinator.enable_charge)
def enable_charge(ctx):  # noqa: D103
    ctx.obj['CLIENT'].enable_charge()


@main.command()
@click.pass_context
# @is_documented_by(Coordinator.disable_charge)
def disable_charge(ctx):  # noqa: D103
    ctx.obj['CLIENT'].disable_charge()


@main.command()
@click.pass_context
# @is_documented_by(Coordinator.enable_discharge)
def enable_discharge(ctx):  # noqa: D103
    ctx.obj['CLIENT'].enable_discharge()


@main.command()
@click.pass_context
# @is_documented_by(Coordinator.disable_discharge)
def disable_discharge(ctx):  # noqa: D103
    ctx.obj['CLIENT'].disable_discharge()


@main.command()
@click.pass_context
# @is_documented_by(Coordinator.set_battery_discharge_mode_max_power)
def set_battery_discharge_mode_max_power(ctx):  # noqa: D103
    ctx.obj['CLIENT'].set_battery_discharge_mode_max_power()


@main.command()
@click.pass_context
# @is_documented_by(Coordinator.set_battery_discharge_mode_demand)
def set_battery_discharge_mode_demand(ctx):  # noqa: D103
    ctx.obj['CLIENT'].set_battery_discharge_mode_demand()


@main.command()
@click.option('-s', '--start', type=click.DateTime(formats=['%H:%m']), required=True)
@click.option('-e', '--end', type=click.DateTime(formats=['%H:%m']), required=True)
@click.pass_context
# @is_documented_by(Coordinator.set_charge_slot_1)
def set_charge_slot_1(ctx, start, end):  # noqa: D103
    click.echo(start)
    click.echo(end)
    ctx.obj['CLIENT'].set_charge_slot_1((start, end))


@main.command()
@click.option('-s', '--start', type=click.DateTime(formats=['%H:%M', '%H%M']), required=True)
@click.option('-e', '--end', type=click.DateTime(formats=['%H:%M', '%H%M']), required=True)
@click.pass_context
# @is_documented_by(Coordinator.set_charge_slot_2)
def set_charge_slot_2(ctx, start: datetime.datetime, end: datetime.datetime):  # noqa: D103
    click.echo(start.time())
    click.echo(end.time())
    ctx.obj['CLIENT'].set_charge_slot_2((start, end))


@main.command()
@click.argument('charge_limit', type=int)
@click.pass_context
# @is_documented_by(Coordinator.set_battery_charge_limit)
def set_battery_charge_limit(ctx, charge_limit: int):  # noqa: D103
    ctx.obj['CLIENT'].set_battery_charge_limit(charge_limit)


@main.command()
@click.argument('discharge_limit', type=int)
@click.pass_context
# @is_documented_by(Coordinator.set_battery_discharge_limit)
def set_battery_discharge_limit(ctx, discharge_limit: int):  # noqa: D103
    ctx.obj['CLIENT'].set_battery_discharge_limit(discharge_limit)


if __name__ == '__main__':
    main(obj={})  # pragma: no cover
