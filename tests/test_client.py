import datetime
from typing import Tuple
from unittest.mock import MagicMock as Mock
from unittest.mock import call

import pytest

from givenergy_modbus.client import GivEnergyClient
from givenergy_modbus.model.battery import Battery
from givenergy_modbus.model.inverter import Inverter, Model  # type: ignore  # shut up mypy
from givenergy_modbus.model.plant import Plant
from givenergy_modbus.model.register import HoldingRegister, InputRegister  # type: ignore  # shut up mypy
from tests.model.test_battery import EXPECTED_BATTERY_DICT
from tests.model.test_inverter import EXPECTED_INVERTER_DICT
from tests.model.test_register import HOLDING_REGISTERS, INPUT_REGISTERS  # type: ignore  # shut up mypy
from tests.model.test_register_cache import register_cache  # noqa: F401


@pytest.fixture()
def client() -> GivEnergyClient:
    """Supply a client with a mocked modbus client."""
    # side_effects = [{1: 2, 3: 4}, {5: 6, 7: 8}, {9: 10, 11: 12}, {13: 14, 15: 16}, {17: 18, 19: 20}]
    return GivEnergyClient(host='foo')  # , modbus_client=Mock(name='modbus_client', side_effect=side_effects))


@pytest.fixture()
def client_with_mocked_write_holding_register() -> Tuple[GivEnergyClient, Mock]:
    """Supply a client with a mocked write_holding_register() function."""
    c = GivEnergyClient(host='foo')
    mock = Mock()
    c.modbus_client.write_holding_register = mock  # type: ignore  # shut up mypy
    return c, mock


def test_refresh_plant_without_batteries(client):  # noqa: F811
    """Ensure we can refresh data and obtain an Inverter DTO."""
    p = Plant(number_batteries=0)
    client.modbus_client.read_registers = Mock(
        name='read_registers',
        side_effect=[
            # full refresh
            {k: v for k, v in INPUT_REGISTERS.items() if 0 <= k < 60},
            {k: v for k, v in INPUT_REGISTERS.items() if 180 <= k < 240},
            {k: v for k, v in HOLDING_REGISTERS.items() if 0 <= k < 60},
            {k: v for k, v in HOLDING_REGISTERS.items() if 60 <= k < 120},
            {k: v for k, v in HOLDING_REGISTERS.items() if 120 <= k < 180},
            # quick refresh
            {k: v for k, v in INPUT_REGISTERS.items() if 0 <= k < 60},
            {k: v for k, v in INPUT_REGISTERS.items() if 180 <= k < 240},
        ],
    )

    assert p.inverter_rc == {}
    assert p.batteries_rcs == []

    client.refresh_plant(p, full_refresh=True, sleep_between_queries=0)

    assert client.modbus_client.read_registers.call_args_list == [
        call(InputRegister, 0, 60, slave_address=50),
        call(InputRegister, 180, 60, slave_address=50),
        call(HoldingRegister, 0, 60, slave_address=50),
        call(HoldingRegister, 60, 60, slave_address=50),
        call(HoldingRegister, 120, 60, slave_address=50),
    ]

    assert p.inverter == Inverter(
        inverter_serial_number='SA1234G567',
        device_type_code='2001',
        inverter_module=198706,
        dsp_firmware_version=449,
        arm_firmware_version=449,
        usb_device_inserted=2,
        select_arm_chip=False,
        meter_type=1,
        reverse_115_meter_direct=False,
        reverse_418_meter_direct=False,
        enable_drm_rj45_port=True,
        ct_adjust=2,
        enable_buzzer=False,
        num_mppt=2,
        num_phases=1,
        enable_ammeter=True,
        p_grid_port_max_output=6000,
        enable_60hz_freq_mode=False,
        inverter_modbus_address=17,
        modbus_version=1.4,
        pv1_voltage_adjust=0,
        pv2_voltage_adjust=0,
        grid_r_voltage_adjust=0,
        grid_s_voltage_adjust=0,
        grid_t_voltage_adjust=0,
        grid_power_adjust=0,
        battery_voltage_adjust=0,
        pv1_power_adjust=0,
        pv2_power_adjust=0,
        system_time=datetime.datetime(2022, 1, 1, 23, 57, 19),
        active_power_rate=100,
        reactive_power_rate=0,
        power_factor=-1,
        inverter_state=(0, 1),
        inverter_start_time=30,
        inverter_restart_delay_time=30,
        dci_1_i=0.0,
        dci_1_time=0,
        dci_2_i=0.0,
        dci_2_time=0,
        f_ac_high_c=52.0,
        f_ac_high_in=52.0,
        f_ac_high_in_time=28,
        f_ac_high_out=51.98,
        f_ac_high_out_time=28,
        f_ac_low_c=47.0,
        f_ac_low_in=47.45,
        f_ac_low_in_time=1,
        f_ac_low_out=47.0,
        f_ac_low_out_time=24,
        gfci_1_i=0.0,
        gfci_1_time=0,
        gfci_2_i=0.0,
        gfci_2_time=0,
        v_ac_high_c=283.7,
        v_ac_high_in=262.0,
        v_ac_high_in_time=52,
        v_ac_high_out=274.0,
        v_ac_high_out_time=27,
        v_ac_low_c=175.5,
        v_ac_low_in=184.0,
        v_ac_low_in_time=126,
        v_ac_low_out=184.0,
        v_ac_low_out_time=126,
        first_battery_serial_number='BG1234G567',
        first_battery_bms_firmware_version=3005,
        enable_bms_read=True,
        battery_type=1,
        battery_nominal_capacity=160.0,
        enable_auto_judge_battery_type=True,
        v_pv_input_start=150.0,
        v_battery_under_protection_limit=43.2,
        v_battery_over_protection_limit=58.5,
        enable_discharge=False,
        enable_charge=True,
        enable_charge_target=True,
        battery_power_mode=1,
        soc_force_adjust=0,
        charge_slot_1=(datetime.time(0, 30), datetime.time(4, 30)),
        charge_slot_2=(datetime.time(0, 0), datetime.time(0, 4)),
        discharge_slot_1=(datetime.time(0, 0), datetime.time(0, 0)),
        discharge_slot_2=(datetime.time(0, 0), datetime.time(0, 0)),
        charge_and_discharge_soc=(0, 0),
        battery_low_force_charge_time=6,
        battery_soc_reserve=4,
        battery_charge_limit=50,
        battery_discharge_limit=50,
        island_check_continue=0,
        battery_discharge_min_power_reserve=4,
        charge_target_soc=100,
        charge_soc_stop_2=0,
        discharge_soc_stop_2=0,
        charge_soc_stop_1=0,
        discharge_soc_stop_1=0,
        inverter_status=0,
        system_mode=1,
        inverter_countdown=30,
        charge_status=0,
        battery_percent=4,
        charger_warning_code=0,
        work_time_total=213,
        fault_code=0,
        e_battery_charge_day=9.0,
        e_battery_charge_day_2=9.0,
        e_battery_charge_total=174.4,
        e_battery_discharge_day=8.9,
        e_battery_discharge_day_2=8.9,
        e_battery_discharge_total=169.6,
        e_battery_throughput_total=183.2,
        e_discharge_year=0.0,
        e_inverter_out_day=8.1,
        e_inverter_out_total=93.0,
        e_grid_out_day=0.0,
        e_grid_in_day=20.9,
        e_grid_in_total=365.3,
        e_grid_out_total=0.6,
        e_inverter_in_day=9.3,
        e_inverter_in_total=94.6,
        e_pv1_day=0.4,
        e_pv2_day=0.5,
        e_solar_diverter=0.0,
        f_ac1=49.9,
        f_eps_backup=49.86,
        i_ac1=0.0,
        i_battery=0.0,
        i_grid_port=2.92,
        i_pv1=0.0,
        i_pv2=0.0,
        p_battery=0,
        p_eps_backup=0,
        p_grid_apparent=680,
        p_grid_out=-342,
        p_inverter_out=0,
        p_load_demand=342,
        p_pv1=0,
        p_pv2=0,
        e_pv_total=15.9,
        pf_inverter_out=-0.521,
        temp_battery=17.0,
        temp_charger=22.3,
        temp_inverter_heatsink=22.2,
        v_ac1=236.7,
        v_battery=49.91,
        v_eps_backup=235.6,
        v_highbrigh_bus=12,
        v_n_bus=0.0,
        v_p_bus=7.0,
        v_pv1=1.4,
        v_pv2=1.0,
        inverter_model=Model.Hybrid,
        firmware_version='D0.449-A0.449',
    )

    assert p.inverter.dict() == EXPECTED_INVERTER_DICT
    assert p.inverter.inverter_serial_number == 'SA1234G567'
    assert p.inverter.inverter_model == Model.Hybrid
    assert p.inverter.v_pv1 == 1.4
    assert p.inverter.e_inverter_out_day == 8.1
    assert p.inverter.enable_charge_target

    assert p.batteries == []

    client.refresh_plant(p, full_refresh=False, sleep_between_queries=0)

    assert client.modbus_client.read_registers.call_args_list == [
        call(InputRegister, 0, 60, slave_address=50),
        call(InputRegister, 180, 60, slave_address=50),
        call(HoldingRegister, 0, 60, slave_address=50),
        call(HoldingRegister, 60, 60, slave_address=50),
        call(HoldingRegister, 120, 60, slave_address=50),
        call(InputRegister, 0, 60, slave_address=50),
        call(InputRegister, 180, 60, slave_address=50),
    ]
    assert p.batteries == []


def test_refresh_plant_with_batteries(client):  # noqa: F811
    """Ensure we can refresh data and instantiate a Battery DTO."""
    p = Plant(number_batteries=3)
    client.modbus_client.read_registers = Mock(
        name='read_registers',
        side_effect=[
            # full refresh
            {k: v for k, v in INPUT_REGISTERS.items() if 0 <= k < 60},
            {k: v for k, v in INPUT_REGISTERS.items() if 180 <= k < 240},
            {k: v for k, v in HOLDING_REGISTERS.items() if 0 <= k < 60},
            {k: v for k, v in HOLDING_REGISTERS.items() if 60 <= k < 120},
            {k: v for k, v in HOLDING_REGISTERS.items() if 120 <= k < 180},
            {k: v for k, v in INPUT_REGISTERS.items() if 60 <= k < 120},
            {k: v for k, v in INPUT_REGISTERS.items() if 60 <= k < 120},
            {k: v for k, v in INPUT_REGISTERS.items() if 60 <= k < 120},
            # quick refresh
            {k: v for k, v in INPUT_REGISTERS.items() if 0 <= k < 60},
            {k: v for k, v in INPUT_REGISTERS.items() if 180 <= k < 240},
            {k: v for k, v in INPUT_REGISTERS.items() if 60 <= k < 120},
            {k: v for k, v in INPUT_REGISTERS.items() if 60 <= k < 120},
            {k: v for k, v in INPUT_REGISTERS.items() if 60 <= k < 120},
        ],
    )

    assert p.inverter_rc == {}
    assert p.batteries_rcs == [{}, {}, {}]

    client.refresh_plant(p, full_refresh=True, sleep_between_queries=0)

    assert client.modbus_client.read_registers.call_args_list == [
        call(InputRegister, 0, 60, slave_address=50),
        call(InputRegister, 180, 60, slave_address=50),
        call(HoldingRegister, 0, 60, slave_address=50),
        call(HoldingRegister, 60, 60, slave_address=50),
        call(HoldingRegister, 120, 60, slave_address=50),
        call(InputRegister, 60, 60, slave_address=0x32),
        call(InputRegister, 60, 60, slave_address=0x33),
        call(InputRegister, 60, 60, slave_address=0x34),
    ]

    assert len(p.batteries) == 3
    assert p.batteries[0] == Battery(
        battery_serial_number='BG1234G567',
        v_battery_cell_01=3.117,
        v_battery_cell_02=3.124,
        v_battery_cell_03=3.129,
        v_battery_cell_04=3.129,
        v_battery_cell_05=3.125,
        v_battery_cell_06=3.13,
        v_battery_cell_07=3.122,
        v_battery_cell_08=3.116,
        v_battery_cell_09=3.111,
        v_battery_cell_10=3.105,
        v_battery_cell_11=3.119,
        v_battery_cell_12=3.134,
        v_battery_cell_13=3.146,
        v_battery_cell_14=3.116,
        v_battery_cell_15=3.135,
        v_battery_cell_16=3.119,
        temp_battery_cells_1=17.5,
        temp_battery_cells_2=16.7,
        temp_battery_cells_3=17.1,
        temp_battery_cells_4=16.1,
        v_battery_cells_sum=49.97,
        temp_bms_mos=17.2,
        v_battery_out=50.029,
        battery_full_capacity=190.97,
        battery_design_capacity=160.0,
        battery_remaining_capacity=18.04,
        battery_status_1_2=(0, 0),
        battery_status_3_4=(6, 16),
        battery_status_5_6=(1, 0),
        battery_status_7=(0, 0),
        battery_warning_1_2=(0, 0),
        battery_num_cycles=12,
        battery_num_cells=16,
        bms_firmware_version=3005,
        battery_soc=9,
        battery_design_capacity_2=160.0,
        temp_battery_max=17.4,
        temp_battery_min=16.7,
        usb_inserted=True,
        e_battery_charge_total_2=174.4,
        e_battery_discharge_total_2=169.6,
    )

    assert p.batteries[0].dict() == EXPECTED_BATTERY_DICT
    assert p.batteries[0].battery_serial_number == 'BG1234G567'
    assert p.batteries[0].v_battery_cell_01 == 3.117

    client.refresh_plant(p, full_refresh=False, sleep_between_queries=0)

    assert client.modbus_client.read_registers.call_args_list == [
        call(InputRegister, 0, 60, slave_address=50),
        call(InputRegister, 180, 60, slave_address=50),
        call(HoldingRegister, 0, 60, slave_address=50),
        call(HoldingRegister, 60, 60, slave_address=50),
        call(HoldingRegister, 120, 60, slave_address=50),
        call(InputRegister, 60, 60, slave_address=0x32),
        call(InputRegister, 60, 60, slave_address=0x33),
        call(InputRegister, 60, 60, slave_address=0x34),
        # quick refresh
        call(InputRegister, 0, 60, slave_address=50),
        call(InputRegister, 180, 60, slave_address=50),
        call(InputRegister, 60, 60, slave_address=0x32),
        call(InputRegister, 60, 60, slave_address=0x33),
        call(InputRegister, 60, 60, slave_address=0x34),
    ]
    assert len(p.batteries) == 3


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
    assert e.value.args[0] == 'Specified Charge Target SOC (1) is not in [4-100]'


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
    getattr(c, f'set_{action}_slot_{slot}')((datetime.time(hour1, min1), datetime.time(hour2, min2)))
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

    c.set_mode_storage((datetime.time(1, 2), datetime.time(3, 4)))
    c.set_mode_storage((datetime.time(5, 6), datetime.time(7, 8)), (datetime.time(9, 10), datetime.time(11, 12)))
    c.set_mode_storage((datetime.time(13, 14), datetime.time(15, 16)), export=True)

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

    c.set_datetime(datetime.datetime(year=2022, month=11, day=23, hour=4, minute=34, second=59))

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
    assert e.value.args[0] == 'Specified Charge Limit (51%) is not in [0-50]%'


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
    assert e.value.args[0] == 'Specified Discharge Limit (51%) is not in [0-50]%'


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
    data: Tuple[str, HoldingRegister], client_with_mocked_write_holding_register: Tuple[GivEnergyClient, Mock]
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


@pytest.mark.skip('FIXME return to this some day')
def test_timeout(client):
    """Try to simulate a socket timeout."""
    import socket

    client.modbus_client.socket = Mock(side_effect=socket.timeout)

    client.set_battery_discharge_limit(1)

    assert client.modbus_client.socket.call_args_list == []
