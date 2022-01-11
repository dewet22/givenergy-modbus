from datetime import datetime, time
from unittest.mock import MagicMock as Mock
from unittest.mock import call

import pytest

from givenergy_modbus.client import GivEnergyClient
from givenergy_modbus.model.register import HoldingRegister, InputRegister  # type: ignore  # shut up mypy
from givenergy_modbus.pdu import ReadHoldingRegistersResponse, ReadInputRegistersResponse


@pytest.fixture()
def client_with_mocked_modbus_client() -> tuple[GivEnergyClient, Mock]:
    """Supply a client with a mocked modbus client."""
    c = GivEnergyClient(host='foo')
    mock = Mock()
    c.modbus_client = mock
    return c, mock


@pytest.fixture()
def client_with_mocked_write_holding_register() -> tuple[GivEnergyClient, Mock]:
    """Supply a client with a mocked write_holding_register() function."""
    c = GivEnergyClient(host='foo')
    mock = Mock()
    c.modbus_client.write_holding_register = mock  # type: ignore  # shut up mypy
    return c, mock


def test_load_inverter_registers():
    """Ensure we can retrieve current data in a well-structured format."""
    c = GivEnergyClient(host='foo', register_cache_class=Mock)
    c.modbus_client.read_holding_registers = Mock(return_value=ReadHoldingRegistersResponse())
    c.modbus_client.read_input_registers = Mock(return_value=ReadInputRegistersResponse())

    register_cache = c.load_inverter_registers()

    assert c.modbus_client.read_holding_registers.call_args_list == [call(0, 60), call(60, 60), call(120, 60)]
    assert c.modbus_client.read_input_registers.call_args_list == [call(0, 60), call(120, 60), call(180, 60)]
    # it really is a lot of work to test the detailed wiring of these deep method calls
    assert len(register_cache.set_registers.call_args_list) == 6
    assert register_cache.set_registers.call_args_list[0][0][0] is HoldingRegister
    assert register_cache.set_registers.call_args_list[0][1] == {}
    assert register_cache.set_registers.call_args_list[1][0][0] is HoldingRegister
    assert register_cache.set_registers.call_args_list[2][0][0] is HoldingRegister
    assert register_cache.set_registers.call_args_list[3][0][0] is InputRegister
    assert register_cache.set_registers.call_args_list[4][0][0] is InputRegister
    assert register_cache.set_registers.call_args_list[5][0][0] is InputRegister


def test_load_battery_registers():
    """Ensure we can retrieve current data in a well-structured format."""
    c = GivEnergyClient(host='foo', register_cache_class=Mock)
    c.modbus_client.read_holding_registers = Mock(return_value=ReadHoldingRegistersResponse())
    c.modbus_client.read_input_registers = Mock(return_value=ReadInputRegistersResponse())

    register_cache = c.load_battery_registers(33)

    assert c.modbus_client.read_holding_registers.call_args_list == []
    assert c.modbus_client.read_input_registers.call_args_list == [call(60, 60, slave_address=0x32 + 33)]
    # it really is a lot of work to test the detailed wiring of these deep method calls
    assert len(register_cache.set_registers.call_args_list) == 1
    assert register_cache.set_registers.call_args_list[0][0][0] is InputRegister
    assert register_cache.set_registers.call_args_list[0][1] == {}


def test_set_charge_target(client_with_mocked_write_holding_register):
    """Ensure we can set a charge target."""
    c, mock = client_with_mocked_write_holding_register

    c.enable_charge_target(45)
    c.enable_charge_target(100)

    assert mock.call_args_list == [
        call(HoldingRegister.ENABLE_CHARGE_TARGET, True),
        call(HoldingRegister.CHARGE_TARGET_SOC, 45),
        call(HoldingRegister.ENABLE_CHARGE_TARGET, False),
        call(HoldingRegister.CHARGE_TARGET_SOC, 100),
    ]
    with pytest.raises(ValueError) as e:
        c.enable_charge_target(1)
    assert e.value.args[0] == 'Specified Charge Target SOC (1) is not in [4-100].'


def test_disable_charge_target(client_with_mocked_write_holding_register):
    """Ensure we can remove a charge target."""
    c, mock = client_with_mocked_write_holding_register

    c.disable_charge_target()

    assert mock.call_args_list == [
        call(HoldingRegister.ENABLE_CHARGE_TARGET, False),
        call(HoldingRegister.CHARGE_TARGET_SOC, 100),
    ]


def test_set_charge(client_with_mocked_write_holding_register):
    """Ensure we can toggle charging."""
    c, mock = client_with_mocked_write_holding_register

    c.enable_charge()
    c.disable_charge()

    assert mock.call_args_list == [
        call(HoldingRegister.ENABLE_CHARGE, True),
        call(HoldingRegister.ENABLE_CHARGE, False),
    ]


def test_set_discharge(client_with_mocked_write_holding_register):
    """Ensure we can toggle discharging."""
    c, mock = client_with_mocked_write_holding_register

    c.enable_discharge()
    c.disable_discharge()

    assert mock.call_args_list == [
        call(HoldingRegister.ENABLE_DISCHARGE, True),
        call(HoldingRegister.ENABLE_DISCHARGE, False),
    ]


def test_set_battery_discharge_mode(client_with_mocked_write_holding_register):
    """Ensure we can set a discharge mode."""
    c, mock = client_with_mocked_write_holding_register

    c.set_battery_discharge_mode_max_power()
    c.set_battery_discharge_mode_demand()

    assert mock.call_args_list == [
        call(HoldingRegister.BATTERY_POWER_MODE, 0),
        call(HoldingRegister.BATTERY_POWER_MODE, 1),
    ]


@pytest.mark.parametrize("action", ("charge", "discharge"))
@pytest.mark.parametrize("slot", (1, 2))
@pytest.mark.parametrize("hour1", (0, 23))
@pytest.mark.parametrize("min1", (0, 59))
@pytest.mark.parametrize("hour2", (0, 23))
@pytest.mark.parametrize("min2", (0, 59))
def test_set_charge_slots(client_with_mocked_write_holding_register, action, slot, hour1, min1, hour2, min2):
    """Ensure we can set charge time slots correctly."""
    c, mock = client_with_mocked_write_holding_register

    # test set and reset functions for the relevant {action} and {slot}
    getattr(c, f'set_{action}_slot_{slot}')((time(hour1, min1), time(hour2, min2)))
    getattr(c, f'reset_{action}_slot_{slot}')()

    assert mock.call_args_list == [
        call(HoldingRegister[f'{action.upper()}_SLOT_{slot}_START'], hour1 * 100 + min1),
        call(HoldingRegister[f'{action.upper()}_SLOT_{slot}_END'], hour2 * 100 + min2),
        call(HoldingRegister[f'{action.upper()}_SLOT_{slot}_START'], 0),
        call(HoldingRegister[f'{action.upper()}_SLOT_{slot}_END'], 0),
    ]


def test_set_mode_dynamic(client_with_mocked_write_holding_register):
    """Ensure we can set the inverter to dynamic mode."""
    c, mock = client_with_mocked_write_holding_register

    c.set_mode_dynamic()

    assert mock.call_args_list == [
        call(HoldingRegister.BATTERY_POWER_MODE, 1),
        call(HoldingRegister.BATTERY_SOC_RESERVE, 4),
        call(HoldingRegister.ENABLE_DISCHARGE, False),
    ]


def test_set_mode_storage(client_with_mocked_write_holding_register):
    """Ensure we can set the inverter to a storage mode with discharge slots."""
    c, mock = client_with_mocked_write_holding_register

    c.set_mode_storage((time(1, 2), time(3, 4)))
    c.set_mode_storage((time(5, 6), time(7, 8)), (time(9, 10), time(11, 12)))
    c.set_mode_storage((time(13, 14), time(15, 16)), export=True)

    assert mock.call_args_list == [
        call(HoldingRegister.BATTERY_POWER_MODE, 1),
        call(HoldingRegister.BATTERY_SOC_RESERVE, 100),
        call(HoldingRegister.ENABLE_DISCHARGE, True),
        call(HoldingRegister.DISCHARGE_SLOT_1_START, 102),
        call(HoldingRegister.DISCHARGE_SLOT_1_END, 304),
        call(HoldingRegister.DISCHARGE_SLOT_2_START, 0),
        call(HoldingRegister.DISCHARGE_SLOT_2_END, 0),
        call(HoldingRegister.BATTERY_POWER_MODE, 1),
        call(HoldingRegister.BATTERY_SOC_RESERVE, 100),
        call(HoldingRegister.ENABLE_DISCHARGE, True),
        call(HoldingRegister.DISCHARGE_SLOT_1_START, 506),
        call(HoldingRegister.DISCHARGE_SLOT_1_END, 708),
        call(HoldingRegister.DISCHARGE_SLOT_1_START, 910),
        call(HoldingRegister.DISCHARGE_SLOT_1_END, 1112),
        call(HoldingRegister.BATTERY_POWER_MODE, 0),
        call(HoldingRegister.BATTERY_SOC_RESERVE, 100),
        call(HoldingRegister.ENABLE_DISCHARGE, True),
        call(HoldingRegister.DISCHARGE_SLOT_1_START, 1314),
        call(HoldingRegister.DISCHARGE_SLOT_1_END, 1516),
        call(HoldingRegister.DISCHARGE_SLOT_2_START, 0),
        call(HoldingRegister.DISCHARGE_SLOT_2_END, 0),
    ]


def test_set_system_time(client_with_mocked_write_holding_register):
    """Ensure we can set the system time correctly."""
    c, mock = client_with_mocked_write_holding_register

    c.set_datetime(datetime(year=2022, month=11, day=23, hour=4, minute=34, second=59))

    assert mock.call_args_list == [
        call(HoldingRegister.SYSTEM_TIME_YEAR, 2022),
        call(HoldingRegister.SYSTEM_TIME_MONTH, 11),
        call(HoldingRegister.SYSTEM_TIME_DAY, 23),
        call(HoldingRegister.SYSTEM_TIME_HOUR, 4),
        call(HoldingRegister.SYSTEM_TIME_MINUTE, 34),
        call(HoldingRegister.SYSTEM_TIME_SECOND, 59),
    ]


def test_set_charge_limit(client_with_mocked_write_holding_register):
    """Ensure we can set a charge limit."""
    c, mock = client_with_mocked_write_holding_register

    c.set_battery_charge_limit(1)
    c.set_battery_charge_limit(50)

    assert mock.call_args_list == [
        call(HoldingRegister.BATTERY_CHARGE_LIMIT, 1),
        call(HoldingRegister.BATTERY_CHARGE_LIMIT, 50),
    ]
    with pytest.raises(ValueError) as e:
        c.set_battery_charge_limit(51)
    assert e.value.args[0] == 'Specified Charge Limit (51%) is not in [0-50]%.'


def test_set_discharge_limit(client_with_mocked_write_holding_register):
    """Ensure we can set a discharge limit."""
    c, mock = client_with_mocked_write_holding_register

    c.set_battery_discharge_limit(1)
    c.set_battery_discharge_limit(50)

    assert mock.call_args_list == [
        call(HoldingRegister.BATTERY_DISCHARGE_LIMIT, 1),
        call(HoldingRegister.BATTERY_DISCHARGE_LIMIT, 50),
    ]
    with pytest.raises(ValueError) as e:
        c.set_battery_discharge_limit(51)
    assert e.value.args[0] == 'Specified Discharge Limit (51%) is not in [0-50]%.'


@pytest.mark.parametrize(
    "data",
    (
        ('set_discharge_enable', HoldingRegister.ENABLE_DISCHARGE),
        ('set_shallow_charge', HoldingRegister.BATTERY_SOC_RESERVE),
        ('set_battery_charge_limit', HoldingRegister.BATTERY_CHARGE_LIMIT),
        ('set_battery_discharge_limit', HoldingRegister.BATTERY_DISCHARGE_LIMIT),
        ('set_battery_power_reserve', HoldingRegister.BATTERY_DISCHARGE_MIN_POWER_RESERVE),
        ('set_battery_target_soc', HoldingRegister.CHARGE_TARGET_SOC),
    ),
)
def test_write_holding_register_helper_functions(
    data: tuple[str, HoldingRegister], client_with_mocked_write_holding_register: tuple[GivEnergyClient, Mock]
):
    """Test wiring for the basic register writer functions is correct."""
    fn, register = data
    c, mock = client_with_mocked_write_holding_register

    getattr(c, fn)(33)
    getattr(c, fn)(True)

    assert mock.call_args_list == [
        call(register, 33),
        call(register, 1),
    ]
