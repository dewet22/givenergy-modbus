from givenergy_modbus.model.battery import Battery
from givenergy_modbus.model.register_cache import RegisterCache

EXPECTED_BATTERY_DICT = {
    # 'bms_firmware_version': 3005,
    # 'design_capacity': 160.0,
    # 'design_capacity_2': 160.0,
    # 'e_charge_total': 174.4,
    # 'e_discharge_total': 169.6,
    # 'full_capacity': 190.97,
    # 'num_cells': 16,
    # 'num_cycles': 12,
    # 'remaining_capacity': 18.04,
    'serial_number': 'BG1234G567',
    # 'state_of_charge': 9,
    # 'status': (0, 0, 6, 16, 1, 0, 0, 0),
    # 'temp_bms_mosfet': 17.2,
    # 'temp_cells_13_16': 16.1,
    # 'temp_cells_1_4': 17.5,
    # 'temp_cells_5_8': 16.7,
    # 'temp_cells_9_12': 17.1,
    # 'temp_max': 17.4,
    # 'temp_min': 16.7,
    # 'usb_inserted': True,
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
    # 'v_cells_sum': 49.97,
    # 'v_out': 50.029,
    # 'warning': (0, 0),
}


def test_from_registers(register_cache):
    """Ensure we can return a dict view of battery data."""
    assert Battery.from_orm(register_cache).dict() == EXPECTED_BATTERY_DICT


def test_from_registers_actual_data(register_cache_battery_daytime_discharging):
    """Ensure we can instantiate an instance of battery data from actual registers."""
    assert Battery.from_orm(register_cache_battery_daytime_discharging).dict() == {
        # 'bms_firmware_version': 3005,
        # 'design_capacity': 160.0,
        # 'design_capacity_2': 160.0,
        # 'e_charge_total': 174.4,
        # 'e_discharge_total': 169.6,
        # 'full_capacity': 195.13,
        # 'num_cells': 16,
        # 'num_cycles': 23,
        # 'remaining_capacity': 131.42,
        'serial_number': 'BG1234G567',
        # 'state_of_charge': 67,
        # 'status': (0, 0, 14, 16, 1, 0, 0, 0),
        # 'temp_bms_mosfet': 17.2,
        # 'temp_cells_13_16': 14.6,
        # 'temp_cells_1_4': 16.8,
        # 'temp_cells_5_8': 15.7,
        # 'temp_cells_9_12': 16.5,
        # 'temp_max': 16.8,
        # 'temp_min': 15.7,
        # 'usb_inserted': True,
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
        # 'v_cells_sum': 51.832,
        # 'v_out': 51.816,
        # 'warning': (0, 0),
    }


def test_from_registers_unsure_data(register_cache_battery_unsure):
    """Ensure we cannot instantiate an instance of battery data from registers returned for non-existent slave."""
    b = Battery.from_orm(register_cache_battery_unsure)
    assert b.serial_number == ''
    assert b.is_valid() is False


def test_empty():
    """Ensure we cannot instantiate from empty data."""
    assert Battery().dict() == {
        'serial_number': None,
        'v_cell_01': None,
        'v_cell_02': None,
        'v_cell_03': None,
        'v_cell_04': None,
        'v_cell_05': None,
        'v_cell_06': None,
        'v_cell_07': None,
        'v_cell_08': None,
        'v_cell_09': None,
        'v_cell_10': None,
        'v_cell_11': None,
        'v_cell_12': None,
        'v_cell_13': None,
        'v_cell_14': None,
        'v_cell_15': None,
        'v_cell_16': None,
    }

    assert Battery.from_orm(RegisterCache({})).dict() == {
        'serial_number': None,
        'v_cell_01': None,
        'v_cell_02': None,
        'v_cell_03': None,
        'v_cell_04': None,
        'v_cell_05': None,
        'v_cell_06': None,
        'v_cell_07': None,
        'v_cell_08': None,
        'v_cell_09': None,
        'v_cell_10': None,
        'v_cell_11': None,
        'v_cell_12': None,
        'v_cell_13': None,
        'v_cell_14': None,
        'v_cell_15': None,
        'v_cell_16': None,
    }
