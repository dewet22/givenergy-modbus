from givenergy_modbus.model.battery import Battery

from .test_register_cache import register_cache  # noqa: F401

EXPECTED_BATTERY_DICT = {
    'bms_firmware_version': 3005,
    'design_capacity': 190.97,
    'design_capacity_2': 160.0,
    'full_capacity': 190.97,
    'num_cells': 16,
    'num_cycles': 12,
    'remaining_capacity': 190.97,
    'serial_number': 'BG1234G567',
    'soc': 9,
    'status_1_2': (0, 0),
    'status_3_4': (6, 16),
    'status_5_6': (1, 0),
    'status_7': (0, 0),
    'temp_bms_mos': 17.2,
    'temp_cell_block_1': 17.5,
    'temp_cell_block_2': 16.7,
    'temp_cell_block_3': 17.1,
    'temp_cell_block_4': 16.1,
    'temp_max_now': 17.400000000000002,
    'temp_min_now': 16.7,
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
    'v_cell_15': 3.1350000000000002,
    'v_cell_16': 3.119,
    'v_cells_sum': 49.97,
    'v_out': 50.029,
    'warning_1_2': (0, 0),
}


def test_from_orm(register_cache):  # noqa: F811
    """Ensure we can return a dict view of inverter data."""
    assert Battery.from_orm(register_cache).dict() == EXPECTED_BATTERY_DICT
