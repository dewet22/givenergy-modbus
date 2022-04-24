import pytest

from givenergy_modbus.model.battery import Battery
from givenergy_modbus.model.register import InputRegister  # type: ignore
from tests.model.test_register_cache import (  # noqa: F401
    register_cache,
    register_cache_battery_daytime_discharging,
    register_cache_battery_missing,
    register_cache_battery_unsure,
)

EXPECTED_BATTERY_DICT = {
    'bms_firmware_version': 3005,
    'design_capacity': 160.0,
    'design_capacity_2': 160.0,
    'full_capacity': 190.97,
    'num_cells': 16,
    'num_cycles': 12,
    'remaining_capacity': 18.04,
    'battery_serial_number': 'BG1234G567',
    'soc': 9,
    'status_1_2': (0, 0),
    'status_3_4': (6, 16),
    'status_5_6': (1, 0),
    'status_7': (0, 0),
    'temp_bms_mos': 17.2,
    'temp_cells_1': 17.5,
    'temp_cells_2': 16.7,
    'temp_cells_3': 17.1,
    'temp_cells_4': 16.1,
    'temp_max': 17.4,
    'temp_min': 16.7,
    'usb_inserted': 8,
    'v_cell_01': 3.117,
    'v_cell_02': 3.124,
    'v_cell_03': 3.129,
    'v_cell_04': 3.129,
    'v_cell_05': 3.125,
    'v_cell_06': 3.13,
    'v_cell_07': 3.122,
    'v_cell_08': 3.116,
    'v_cell_09': 3.111,
    'v_cell_10': 3.105,
    'v_cell_11': 3.119,
    'v_cell_12': 3.134,
    'v_cell_13': 3.146,
    'v_cell_14': 3.116,
    'v_cell_15': 3.135,
    'v_cell_16': 3.119,
    'v_cells_sum': 49.97,
    'v_battery_out': 50.029,
    'warning_1_2': (0, 0),
    'e_charge_total': 174.4,
    'e_discharge_total': 169.6,
}


def test_has_expected_attributes():
    """Ensure registers mapped to Batteries/BMS are represented in the model."""
    expected_attributes = set()
    for i in range(60):
        name = InputRegister(i + 60).name.lower()
        if name.endswith('_h'):
            continue
        elif name.endswith('_l'):
            name = name[:-2]
        elif name.startswith('status_') or name.startswith('warning_'):
            pass
        elif name.endswith('_1_2'):
            name = name[:-4]
        elif name.endswith('_3_4') or name.endswith('_5_6') or name.endswith('_7_8') or name.endswith('_9_10'):
            continue
        elif name.startswith('input_reg'):
            continue
        expected_attributes.add(name)
    assert expected_attributes == set(Battery.__fields__.keys())


def test_from_orm(register_cache):  # noqa: F811
    """Ensure we can return a dict view of battery data."""
    assert Battery.from_orm(register_cache).dict() == EXPECTED_BATTERY_DICT


def test_from_orm_actual_data(register_cache_battery_daytime_discharging):  # noqa: F811
    """Ensure we can instantiate an instance of battery data from actual registers."""
    assert Battery.from_orm(register_cache_battery_daytime_discharging).dict() == {
        'battery_serial_number': 'BG1234G567',
        'bms_firmware_version': 3005,
        'design_capacity': 160.0,
        'design_capacity_2': 160.0,
        'e_charge_total': 174.4,
        'e_discharge_total': 169.6,
        'full_capacity': 195.13,
        'num_cells': 16,
        'num_cycles': 23,
        'remaining_capacity': 131.42,
        'soc': 67,
        'status_1_2': (0, 0),
        'status_3_4': (14, 16),
        'status_5_6': (1, 0),
        'status_7': (0, 0),
        'temp_bms_mos': 17.2,
        'temp_cells_1': 16.8,
        'temp_cells_2': 15.7,
        'temp_cells_3': 16.5,
        'temp_cells_4': 14.6,
        'temp_max': 16.8,
        'temp_min': 15.7,
        'usb_inserted': 8,
        'v_battery_out': 51.816,
        'v_cell_01': 3.232,
        'v_cell_02': 3.237,
        'v_cell_03': 3.235,
        'v_cell_04': 3.232,
        'v_cell_05': 3.235,
        'v_cell_06': 3.229,
        'v_cell_07': 3.237,
        'v_cell_08': 3.233,
        'v_cell_09': 3.238,
        'v_cell_10': 3.237,
        'v_cell_11': 3.235,
        'v_cell_12': 3.235,
        'v_cell_13': 3.235,
        'v_cell_14': 3.235,
        'v_cell_15': 3.24,
        'v_cell_16': 3.238,
        'v_cells_sum': 51.832,
        'warning_1_2': (0, 0),
    }


def test_from_orm_unsure_data(register_cache_battery_unsure, register_cache_battery_missing):  # noqa: F811
    """Ensure we cannot instantiate an instance of battery data from registers returned for non-existent slave."""
    b = Battery.from_orm(register_cache_battery_unsure)
    assert b.battery_serial_number == '\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
    assert b.is_valid() is False


def test_empty():
    """Ensure we cannot instantiate from empty data."""
    with pytest.raises(ValueError, match=r'\d validation errors for Battery'):
        Battery()
    with pytest.raises(ValueError, match=r'\d validation errors for Battery'):
        Battery.from_orm({})
