"""Console script for interacting with GivEnergy inverters."""
import asyncio
import datetime
import logging
import sys
from statistics import mean, stdev, variance

import click
from loguru import logger
from tabulate import tabulate

from givenergy_modbus.client import Timeslot, commands
from givenergy_modbus.client.client import Client
from givenergy_modbus.model.plant import Plant


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
    ctx.obj['CLIENT'] = Client(host=host, port=port)


@main.command()
@click.pass_context
# @click.option('-b', '--batteries', type=int, default=1)
def show_plant(ctx):
    """Show interpretation of the current plant state."""
    reqs = commands.refresh_plant_data(complete=True)
    c: Client = ctx.obj['CLIENT']
    asyncio.run(c.one_shot_command(reqs))
    p = c.plant
    i = p.inverter
    click.echo(f'{i.inverter_model.name} Inverter, serial {i.inverter_serial_number}:')
    click.echo(f'    Firmware version {i.inverter_firmware_version}, type code {i.device_type_code}')
    click.echo(f'    Number of grid phases: {i.num_phases}')
    click.echo(f'    Meter type: {i.meter_type}')
    click.echo(f'    Status: {i.inverter_status} (fault code: {i.fault_code})')
    click.echo(f'    System mode: {i.system_mode}')
    click.echo(f'    System time: {i.system_time.isoformat(sep=" ")}')
    click.echo(f'    USB device inserted: {i.usb_device_inserted}')
    click.echo(f'    Total work time: {i.work_time_total}h')
    click.echo('    Temperatures:')
    click.echo(f'        Inverter heatsink: {i.temp_inverter_heatsink}℃')
    click.echo(f'        Charger: {i.temp_charger}℃')
    click.echo(f'        Battery: {i.temp_battery}℃')

    if i.battery_nominal_capacity > 0:
        click.echo('    Battery storage:')
        click.echo(f'        Batteries detected: {len(p.batteries)}')
        click.echo(f'        Nominal capacity: {i.battery_nominal_capacity}Ah')
        click.echo(f'        Total throughput: {i.e_battery_throughput_total}kWh')
        click.echo(f'        Current SOC: {i.battery_percent}%')
        click.echo(f'        SOC reserve: {i.battery_soc_reserve}%')
        if i.battery_power_mode == 0:
            click.echo('        Battery power mode: discharge at maximum power, allow export')
        elif i.battery_power_mode == 1:
            click.echo('        Battery power mode: discharge to match load, avoid export')
        else:
            click.echo(f'        Battery power mode: {i.battery_power_mode} (unknown)')
        click.echo(f'        Charge power limit: {52 * i.battery_charge_limit:4d}W / {i.battery_charge_limit}%')
        click.echo(
            f'        Discharge power limit: {52 * i.battery_discharge_limit:4d}W / {i.battery_discharge_limit}%'
        )

        if i.enable_charge:
            if i.enable_charge_target and i.charge_target_soc != 100:
                click.echo(
                    f'        Timed charge: enabled, '
                    f'target {i.charge_target_soc}% SOC '
                    f'from {i.charge_slot_1[0].strftime("%H:%M")} '
                    f'to {i.charge_slot_1[1].strftime("%H:%M")}'
                )
            else:
                click.echo(
                    f'        Timed charge: enabled, '
                    f'from {i.charge_slot_1[0].strftime("%H:%M")} '
                    f'to {i.charge_slot_1[1].strftime("%H:%M")}'
                )
        else:
            click.echo('        Timed charge: disabled')

        if i.enable_discharge:
            click.echo(
                f'        Timed discharge: enabled, '
                f'from {i.discharge_slot_1[0].strftime("%H:%M")} '
                f'to {i.discharge_slot_1[1].strftime("%H:%M")}'
            )
        else:
            click.echo('        Timed discharge: disabled')

    click.echo('    Long-term statistics:')
    click.echo('        Energy flows (kWh):')
    for line in tabulate(
        [
            ['Inverter', i.e_inverter_in_day, i.e_inverter_out_day, i.e_inverter_in_total, i.e_inverter_out_total],
            ['Grid', i.e_grid_in_day, i.e_grid_out_day, i.e_grid_in_total, i.e_grid_out_total],
            ['Solar', None, i.e_pv1_day + i.e_pv2_day, None, i.e_pv_total],
            [
                'Battery',
                i.e_battery_charge_day,
                i.e_battery_discharge_day,
                i.e_battery_charge_total,
                i.e_battery_discharge_total,
            ],
        ],
        headers=['', 'In today', 'Out today', 'In total', 'Out total'],
    ).splitlines():
        click.echo(f'            {line}')
    # click.echo(pprint.pformat(p.inverter.dict(), indent=4))

    for i, b in enumerate(p.batteries):
        click.echo()
        click.echo(f'Battery #{i} (serial # {b.battery_serial_number}):')
        click.echo(f'    BMS firmware: {b.bms_firmware_version}')
        click.echo(f'    Design capacity: {b.design_capacity}Ah')
        click.echo(f'    Actual capacity: {b.full_capacity}Ah')
        click.echo(f'    Remaining charge: {b.remaining_capacity}Ah')
        click.echo(f'    SOC: {b.soc}%')
        click.echo(f'    Total cycles: {b.num_cycles}')
        click.echo(f'    Total cells: {b.num_cells}')

        click.echo('    Temperatures:')
        click.echo(f'        Min/max: {b.temp_min}℃ / {b.temp_max}℃')
        click.echo(f'        BMS MOS: {b.temp_bms_mos}℃')
        click.echo(f'        Cell packs: {b.temp_cells_1}℃ {b.temp_cells_2}℃ {b.temp_cells_3}℃ {b.temp_cells_4}℃')

        click.echo('    Voltages:')
        voltages = (
            b.v_cell_01,
            b.v_cell_02,
            b.v_cell_03,
            b.v_cell_04,
            b.v_cell_05,
            b.v_cell_06,
            b.v_cell_07,
            b.v_cell_08,
            b.v_cell_09,
            b.v_cell_10,
            b.v_cell_11,
            b.v_cell_12,
            b.v_cell_13,
            b.v_cell_14,
            b.v_cell_15,
            b.v_cell_16,
        )
        click.echo(f'        Battery output: {b.v_battery_out}V')
        click.echo(f'        Cells total: {b.v_cells_sum}V')
        m = mean(voltages)
        click.echo(
            f'        Cells: {m:5.3f}V mean ('
            f'stdev: {stdev(voltages, xbar=m):6.4f}, '
            f'variance: {variance(voltages, xbar=m):6.4f})'
        )

        # click.echo(pprint.pformat(b.dict(), indent=4))
    # logger.info(json.dumps(p.register_caches))


@main.command()
@click.pass_context
# @click.option('-b', '--batteries', type=int, default=1)
def dump_registers(ctx):
    """Dump out raw register data for use in debugging."""
    reqs = commands.refresh_plant_data(complete=True)
    c = ctx.obj['CLIENT']
    asyncio.run(c.one_shot_command(reqs))
    for i, rc in c.plant.register_caches.items():
        click.echo(f'{i}: {rc.json()}')


@main.command()
@click.pass_context
# @click.option('-b', '--batteries', type=int, default=1)
@click.option(
    '-d',
    '--delay',
    help='Delay in seconds between refreshes. Refreshes typically take ~1s to complete.',
    type=float,
    default=9.0,
)
@click.option(
    '-p',
    '--passive',
    help='Besides doing a full refresh on startup, only monitor for other traffic.',
    is_flag=True,
    default=False,
)
def watch_plant(ctx, delay, passive):
    """Continuously refresh plant details and print energy flow summaries."""
    lines = 0

    def handler(plant: Plant):
        nonlocal lines
        i = plant.inverter
        if lines % 50 == 0:
            # fmt: off
            click.echo('Time      Grid (- is import)     Battery (- is charge)       Solar (2 strings)   '
                       'Load (EPS)')
            click.echo('--------  ---------------------  --------------------------  ------------------  '
                       '--------------')
            # fmt: on

        click.echo(
            f'{datetime.datetime.now().strftime("%H:%M:%S")}  '
            f'{i.v_ac1:5.1f}V {i.f_ac1:5.2f}Hz {i.p_grid_out:5d}W  '
            f'{i.v_battery:5.2f}V {i.i_battery:6.2f}A {i.p_battery:5d}W {i.battery_percent:3d}%  '
            f'{i.v_pv1:5.1f}/{i.v_pv2:5.1f}V {i.p_pv1 + i.p_pv2:4d}W  '
            f'{i.p_load_demand:5d}W ({i.p_eps_backup:4d}W) '
        )
        # {i.p_grid_out + i.p_load_demand - i.p_battery - i.p_pv1 - i.p_pv2}
        lines += 1

    asyncio.run(ctx.obj['CLIENT'].watch_plant(handler, refresh_period=delay, passive=passive))


@main.command()
@click.pass_context
@click.argument('target_soc', type=int)
@is_documented_by(commands.set_charge_target)
def set_charge_target(ctx, target_soc):  # noqa: D103
    asyncio.run(ctx.obj['CLIENT'].one_shot_command(commands.set_charge_target(target_soc)))


@main.command()
@click.pass_context
@is_documented_by(commands.disable_charge_target)
def disable_charge_target(ctx):  # noqa: D103
    asyncio.run(ctx.obj['CLIENT'].one_shot_command(commands.disable_charge_target()))


@main.command()
@click.pass_context
@is_documented_by(commands.enable_charge)
def enable_charge(ctx):  # noqa: D103
    asyncio.run(ctx.obj['CLIENT'].one_shot_command(commands.enable_charge()))


@main.command()
@click.pass_context
@is_documented_by(commands.disable_charge)
def disable_charge(ctx):  # noqa: D103
    asyncio.run(ctx.obj['CLIENT'].one_shot_command(commands.disable_charge()))


@main.command()
@click.pass_context
@is_documented_by(commands.enable_discharge)
def enable_discharge(ctx):  # noqa: D103
    asyncio.run(ctx.obj['CLIENT'].one_shot_command(commands.enable_discharge()))


@main.command()
@click.pass_context
@is_documented_by(commands.disable_discharge)
def disable_discharge(ctx):  # noqa: D103
    asyncio.run(ctx.obj['CLIENT'].one_shot_command(commands.disable_discharge()))


@main.command()
@click.pass_context
@is_documented_by(commands.set_discharge_mode_max_power)
def set_discharge_mode_max_power(ctx):  # noqa: D103
    asyncio.run(ctx.obj['CLIENT'].one_shot_command(commands.set_discharge_mode_max_power()))


@main.command()
@click.pass_context
@is_documented_by(commands.set_discharge_mode_to_match_demand)
def set_battery_discharge_mode_demand(ctx):  # noqa: D103
    asyncio.run(ctx.obj['CLIENT'].one_shot_command(commands.set_discharge_mode_to_match_demand()))


@main.command()
@click.option('-s', '--start', type=click.DateTime(formats=['%H:%M', '%H%M']), required=True)
@click.option('-e', '--end', type=click.DateTime(formats=['%H:%M', '%H%M']), required=True)
@click.pass_context
@is_documented_by(commands.set_charge_slot_1)
def set_charge_slot(ctx, start: datetime.datetime, end: datetime.datetime):  # noqa: D103
    asyncio.run(
        ctx.obj['CLIENT'].one_shot_command(commands.set_charge_slot_1(Timeslot(start=start.time(), end=end.time())))
    )


@main.command()
@click.option('-s', '--start', type=click.DateTime(formats=['%H:%M', '%H%M']), required=True)
@click.option('-e', '--end', type=click.DateTime(formats=['%H:%M', '%H%M']), required=True)
@click.pass_context
@is_documented_by(commands.set_discharge_slot_1)
def set_discharge_slot(ctx, start: datetime.datetime, end: datetime.datetime):  # noqa: D103
    asyncio.run(
        ctx.obj['CLIENT'].one_shot_command(commands.set_discharge_slot_1(Timeslot(start=start.time(), end=end.time())))
    )


@main.command()
@click.argument('charge_limit', type=int)
@click.pass_context
@is_documented_by(commands.set_battery_charge_limit)
def set_battery_charge_limit(ctx, charge_limit: int):  # noqa: D103
    asyncio.run(ctx.obj['CLIENT'].one_shot_command(commands.set_battery_charge_limit(charge_limit)))


@main.command()
@click.argument('discharge_limit', type=int)
@click.pass_context
@is_documented_by(commands.set_battery_discharge_limit)
def set_battery_discharge_limit(ctx, discharge_limit: int):  # noqa: D103
    asyncio.run(ctx.obj['CLIENT'].one_shot_command(commands.set_battery_discharge_limit(discharge_limit)))


if __name__ == '__main__':
    main(obj={})  # pragma: no cover
