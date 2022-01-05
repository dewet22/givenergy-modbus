from datetime import datetime, time
from unittest.mock import MagicMock as Mock
from unittest.mock import call

import pytest

from givenergy_modbus.client import GivEnergyClient
from givenergy_modbus.model.register_banks import HoldingRegister

from .model.test_inverter import EXPECTED_INVERTER_DICT, HOLDING_REGISTERS, INPUT_REGISTERS


def test_refresh():
    """Ensure we can retrieve current data in a well-structured format."""
    c = GivEnergyClient(host='foo')
    c.modbus_client.read_all_holding_registers = Mock(return_value=HOLDING_REGISTERS)
    c.modbus_client.read_all_input_registers = Mock(return_value=INPUT_REGISTERS)
    c.refresh()
    assert c.modbus_client.read_all_holding_registers.call_count == 1
    assert c.modbus_client.read_all_input_registers.call_count == 1
    assert c.inverter.to_dict() == EXPECTED_INVERTER_DICT


@pytest.mark.parametrize(
    "data",
    (
        ('set_winter_mode', HoldingRegister.WINTER_MODE),
        ('set_battery_power_mode', HoldingRegister.BATTERY_POWER_MODE),
        ('set_discharge_enable', HoldingRegister.DISCHARGE_ENABLE),
        ('set_battery_smart_charge', HoldingRegister.BATTERY_SMART_CHARGE),
        ('set_shallow_charge', HoldingRegister.SHALLOW_CHARGE),
        ('set_battery_charge_limit', HoldingRegister.BATTERY_CHARGE_LIMIT),
        ('set_battery_discharge_limit', HoldingRegister.BATTERY_DISCHARGE_LIMIT),
        ('set_battery_power_reserve', HoldingRegister.BATTERY_POWER_RESERVE),
        ('set_battery_target_soc', HoldingRegister.BATTERY_TARGET_SOC),
    ),
)
def test_write_holding_register_helper_functions(data: tuple[str, HoldingRegister]):
    """Test wiring for the basic register writer functions is correct."""
    fn, register = data
    c = GivEnergyClient(host='foo')
    c.modbus_client.write_holding_register = Mock(return_value=True)  # type: ignore  # shut up mypy

    getattr(c, fn)(33)
    getattr(c, fn)(True)

    assert c.modbus_client.write_holding_register.call_args_list == [
        call(register, 33),
        call(register, 1),
    ]


@pytest.mark.parametrize("action", ("charge", "discharge"))
@pytest.mark.parametrize("slot", (1, 2))
@pytest.mark.parametrize("hour1", (0, 23))
@pytest.mark.parametrize("min1", (0, 59))
@pytest.mark.parametrize("hour2", (0, 23))
@pytest.mark.parametrize("min2", (0, 59))
def test_set_charge_slots(action, slot, hour1, min1, hour2, min2):
    """Ensure we can set charge time slots correctly."""
    c = GivEnergyClient(host='foo')
    mock = Mock(return_value=True)
    c.modbus_client.write_holding_register = mock

    getattr(c, f'set_{action}_slot_{slot}')(time(hour=hour1, minute=min1), time(hour=hour2, minute=min2))

    assert mock.call_args_list == [
        call(HoldingRegister[f'{action.upper()}_SLOT_{slot}_START'], hour1 * 100 + min1),
        call(HoldingRegister[f'{action.upper()}_SLOT_{slot}_END'], hour2 * 100 + min2),
    ]


def test_set_system_time():
    """Ensure we can set the system time correctly."""
    c = GivEnergyClient(host='foo')
    mock = Mock(return_value=True)
    c.modbus_client.write_holding_register = mock

    c.set_system_time(datetime(year=2022, month=11, day=23, hour=4, minute=34, second=59))

    assert mock.call_args_list == [
        call(HoldingRegister.SYSTEM_TIME_YEAR, 2022),
        call(HoldingRegister.SYSTEM_TIME_MONTH, 11),
        call(HoldingRegister.SYSTEM_TIME_DAY, 23),
        call(HoldingRegister.SYSTEM_TIME_HOUR, 4),
        call(HoldingRegister.SYSTEM_TIME_MINUTE, 34),
        call(HoldingRegister.SYSTEM_TIME_SECOND, 59),
    ]
