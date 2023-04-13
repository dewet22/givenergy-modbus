from unittest import skip

import pytest

from givenergy_modbus.model import RegisterCache
from givenergy_modbus.model.battery import Battery
from givenergy_modbus.model.register import InputRegister

EXPECTED_BATTERY_DICT = {
    'bms_firmware_version': 3005,
    'design_capacity': 160.0,
    'design_capacity_2': 160.0,
    'e_charge_total': 174.4,
    'e_discharge_total': 169.6,
    'full_capacity': 190.97,
    'num_cells': 16,
    'num_cycles': 12,
    'remaining_capacity': 18.04,
    'serial_number': 'BG1234G567',
    'state_of_charge': 9,
    'status': (0, 0, 6, 16, 1, 0, 0, 0),
    'temp_bms_mosfet': 17.2,
    'temp_cells_13_16': 16.1,
    'temp_cells_1_4': 17.5,
    'temp_cells_5_8': 16.7,
    'temp_cells_9_12': 17.1,
    'temp_max': 17.4,
    'temp_min': 16.7,
    'usb_inserted': True,
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
    'v_out': 50.029,
    'warning': (0, 0),
}


@skip('might not be needed any more')
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


def test_from_registers(register_cache):
    """Ensure we can return a dict view of battery data."""
    assert Battery.from_registers(register_cache).dict() == EXPECTED_BATTERY_DICT


def test_from_registers_actual_data(register_cache_battery_daytime_discharging):
    """Ensure we can instantiate an instance of battery data from actual registers."""
    assert Battery.from_registers(register_cache_battery_daytime_discharging).dict() == {
        'bms_firmware_version': 3005,
        'design_capacity_2': 160.0,
        'e_charge_total': 174.4,
        'e_discharge_total': 169.6,
        'num_cells': 16,
        'num_cycles': 23,
        'state_of_charge': 67,
        'temp_max': 16.8,
        'temp_min': 15.7,
        'usb_inserted': True,
        'design_capacity': 160.0,
        'full_capacity': 195.13,
        'remaining_capacity': 131.42,
        'serial_number': 'BG1234G567',
        'status': (0, 0, 14, 16, 1, 0, 0, 0),
        'temp_bms_mosfet': 17.2,
        'temp_cells_13_16': 14.6,
        'temp_cells_1_4': 16.8,
        'temp_cells_5_8': 15.7,
        'temp_cells_9_12': 16.5,
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
        'v_out': 51.816,
        'warning': (0, 0),
    }


def test_from_registers_unsure_data(register_cache_battery_unsure):
    """Ensure we cannot instantiate an instance of battery data from registers returned for non-existent slave."""
    b = Battery.from_registers(register_cache_battery_unsure)
    assert b.serial_number == ''
    assert b.is_valid() is False


def test_empty():
    """Ensure we cannot instantiate from empty data."""
    with pytest.raises(ValueError, match=r'\d validation error[s]? for Battery'):
        Battery()
    # with pytest.raises(ValueError, match=r'\d validation error[s]? for Battery'):
    b = Battery.from_registers(RegisterCache({}))
    assert b.serial_number == ''
