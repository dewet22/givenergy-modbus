import datetime

import pytest

from givenergy_modbus.model.register import RegisterCache

# fmt: off
INPUT_REGISTERS: dict[int, int] = dict(enumerate([
    0, 14, 10, 70, 0, 2367, 0, 1832, 0, 0,  # 00x
    0, 0, 159, 4990, 0, 12, 4790, 4, 0, 5,  # 01x
    0, 0, 6, 0, 0, 0, 209, 0, 946, 0,  # 02x
    65194, 0, 0, 3653, 0, 85, 84, 84, 30, 0,  # 03x
    0, 222, 342, 680, 81, 0, 930, 0, 213, 1,  # 04x
    4991, 0, 0, 2356, 4986, 223, 170, 0, 292, 4,  # 05x
    3117, 3124, 3129, 3129, 3125, 3130, 3122, 3116, 3111, 3105,  # 06x
    3119, 3134, 3146, 3116, 3135, 3119, 175, 167, 171, 161,  # 07x
    49970, 172, 0, 50029, 0, 19097, 0, 16000, 0, 1804,  # 08x
    0, 1552, 256, 0, 0, 0, 12, 16, 3005, 0,  # 09x
    9, 0, 16000, 174, 167, 0, 0, 0, 0, 0,  # 10x
    16967, 12594, 13108, 18229, 13879, 8, 0, 0, 0, 0,  # 11x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 12x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 13x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 14x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 15x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 16x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 17x
    906, 926,  # 18x
]))
HOLDING_REGISTERS: dict[int, int] = dict(enumerate([
    8193, 3, 2098, 513, 0, 50000, 3600, 1, 16967, 12594,  # 00x
    13108, 18229, 13879, 21313, 12594, 13108, 18229, 13879, 3005, 449,  # 01x
    1, 449, 2, 0, 32768, 30235, 6000, 1, 0, 0,  # 02x
    17, 0, 4, 7, 140, 22, 1, 1, 23, 57,  # 03x
    19, 1, 2, 0, 0, 0, 101, 1, 0, 0,  # 04x
    100, 0, 0, 1, 1, 160, 0, 0, 1, 0,  # 05x
    1500, 30, 30, 1840, 2740, 4700, 5198, 126, 27, 24,  # 06x
    28, 1840, 2620, 4745, 5200, 126, 52, 1, 28, 1755,  # 07x
    2837, 4700, 5200, 2740, 0, 0, 0, 0, 0, 0,  # 08x
    0, 0, 0, 0, 30, 430, 1, 4320, 5850, 0,  # 09x
    0, 0, 0, 0, 0, 0, 0, 0, 6, 1,  # 10x
    4, 50, 50, 0, 4, 0, 100, 0, 0, 0,  # 11x
    0,  # 12x
]))
# fmt: on

EXPECTED_INVERTER_DICT = {
    'inverter_serial_number': 'SA1234G567',
    'model': 'Hybrid',
    'device_type_code': 8193,
    'inverter_module': 198706,
    'input_tracker_num': 2,
    'output_phase_num': 1,
    'battery_serial_number': 'BG1234G567',
    'battery_firmware_version': 3005,
    'dsp_firmware_version': 449,
    'arm_firmware_version': 449,
    'winter_mode': True,
    'wifi_or_u_disk': 2,
    'select_dsp_or_arm': 0,
    'grid_port_max_output_power': 6000,
    'battery_power_mode': 1,
    'fre_mode': 0,
    'soc_force_adjust': 0,
    'communicate_address': 17,
    'charge_slot_1': (datetime.time(0, 30), datetime.time(4, 30)),
    'charge_slot_2': (datetime.time(0, 0), datetime.time(0, 4)),
    'discharge_slot_1': (datetime.time(0, 0), datetime.time(0, 0)),
    'discharge_slot_2': (datetime.time(0, 0), datetime.time(0, 0)),
    'modbus_version': '1.40',
    'system_time': datetime.datetime(2022, 1, 1, 23, 57, 19),
    'drm_enable': True,
    'ct_adjust': 2,
    'charge_and_discharge_soc': 0,
    'bms_version': 101,
    'b_meter_type': 1,
    'b_115_meter_direct': 0,
    'b_418_meter_direct': 0,
    'active_p_rate': 100,
    'reactive_p_rate': 0,
    'power_factor': 0,
    'inverter_state': 1,
    'battery_type': 1,
    'battery_nominal_capacity': 160,
    'auto_judge_battery_type_enable': 1,
    'discharge_enable': False,
    'input_start_voltage': 150.0,
    'start_time': datetime.time(0, 30),
    'restart_delay_time': 30,
    'v_ac_low_out': 184.0,
    'v_ac_high_out': 274.0,
    'f_ac_low_out': 47.0,
    'f_ac_high_out': 51.980000000000004,
    'v_ac_low_out_time': datetime.time(1, 26),
    'v_ac_high_out_time': datetime.time(0, 27),
    'f_ac_low_out_time': datetime.time(0, 24),
    'f_ac_high_out_time': datetime.time(0, 28),
    'v_ac_low_in': 184.0,
    'v_ac_high_in': 262.0,
    'f_ac_low_in': 47.45,
    'f_ac_high_in': 52.0,
    'v_ac_low_in_time': datetime.time(1, 26),
    'v_ac_high_in_time': datetime.time(0, 52),
    'f_ac_low_in_time': datetime.time(0, 1),
    'f_ac_high_in_time': datetime.time(0, 28),
    'v_ac_low_c': 175.5,
    'v_ac_high_c': 283.7,
    'f_ac_low_c': 47.0,
    'f_ac_high_c': 52.0,
    'gfci_1_i': 0.0,
    'gfci_1_time': datetime.time(0, 0),
    'gfci_2_i': 0.0,
    'gfci_2_time': datetime.time(0, 0),
    'dci_1_i': 0.0,
    'dci_1_time': datetime.time(0, 0),
    'dci_2_i': 0.0,
    'dci_2_time': datetime.time(0, 0),
    'battery_smart_charge': True,
    'discharge_low_limit': 4320,
    'charger_high_limit': 5850,
    'pv1_volt_adjust': 0,
    'pv2_volt_adjust': 0,
    'grid_r_volt_adjust': 0,
    'grid_s_volt_adjust': 0,
    'grid_t_volt_adjust': 0,
    'grid_power_adjust': 0,
    'battery_volt_adjust': 0,
    'pv1_power_adjust': 0,
    'pv2_power_adjust': 0,
    'battery_low_force_charge_time': 6,
    'bms_type': 1,
    'shallow_charge': 4,
    'battery_charge_limit': 50,
    'battery_discharge_limit': 50,
    'buzzer_sw': 0,
    'battery_power_reserve': 4,
    'island_check_continue': 0,
    'battery_target_soc': 100,
    'chg_soc_stop2': 0,
    'discharge_soc_stop2': 0,
    'chg_soc_stop': 0,
    'discharge_soc_stop': 0,
    'inverter_status': 0,
    'v_pv1': 1.4000000000000001,
    'v_pv2': 1.0,
    'v_p_bus_inside': 7.0,
    'v_n_bus_inside': 0.0,
    'v_single_phase_grid': 236.70000000000002,
    'e_battery_throughput': 183.20000000000002,
    'i_pv1': 0.0,
    'i_pv2': 0.0,
    'i_grid_output_single_phase': 0.0,
    'p_pv_total_generating_capacity': 15.9,
    'f_grid_three_single_phase': 49.9,
    'charge_status': 0,
    'v_highbrigh_bus': 12,
    'pf_inverter_output_now': 4790,
    'e_pv1_day': 0.4,
    'p_pv1': 0,
    'e_pv2_day': 0.5,
    'p_pv2': 0,
    'e_pv_day': 0.6000000000000001,
    'pv_mate': 0.0,
    'p_grid_output_three_single_phase': 0,
    'e_grid_out_day': 0.0,
    'e_grid_in_day': 20.900000000000002,
    'e_inverter_in_total': 94.60000000000001,
    'e_discharge_year': 0.0,
    'p_grid_output': -342,
    'p_backup': 0,
    'p_grid_in_total': 365.3,
    'e_total_load_day': 8.5,
    'e_battery_charge_day': 8.4,
    'e_battery_discharge_day': 8.4,
    'p_countdown': 30,
    'fault_code': 0,
    'temp_inverter': 22.200000000000003,
    'p_load_total': 342,
    'p_grid_apparent': 680,
    'e_generated_day': 8.1,
    'e_generated_total': 93.0,
    'work_time_total': 213,
    'system_mode': 1,
    'v_bat': 499.1,
    'i_bat': 0.0,
    'p_bat': 0,
    'v_output': 235.60000000000002,
    'f_output': 49.86,
    'temp_charger': 22.3,
    'temp_battery': 17.0,
    'charger_warning_code': 0,
    'p_grid_port': 2.92,
    'battery_percent': 4,
    'v_battery_cell01': 3.117,
    'v_battery_cell02': 3.124,
    'v_battery_cell03': 3.129,
    'v_battery_cell04': 3.129,
    'v_battery_cell05': 3.125,
    'v_battery_cell06': 3.13,
    'v_battery_cell07': 3.122,
    'v_battery_cell08': 3.116,
    'v_battery_cell09': 3.111,
    'v_battery_cell10': 3.105,
    'v_battery_cell11': 3.119,
    'v_battery_cell12': 3.134,
    'v_battery_cell13': 3.146,
    'v_battery_cell14': 3.116,
    'v_battery_cell15': 3.1350000000000002,
    'v_battery_cell16': 3.119,
    'temp_battery_cell1': 17.5,
    'temp_battery_cell2': 16.7,
    'temp_battery_cell3': 17.1,
    'temp_battery_cell4': 16.1,
    'v_battery_sum': 49.97,
    'temp_mos': 17.2,
    'v_battery_out': 50.029,
    'battery_full_capacity': 190.97,
    'battery_design_capacity': 160.0,
    'battery_remaining_capacity': 18.04,
    'battery_status_1_2': 0,
    'battery_status_3_4': 1552,
    'battery_status_5_6': 256,
    'battery_status_7': 0,
    'battery_warning_1_2': 0,
    'battery_cycles': 12,
    'battery_no_of_cells': 16,
    'bms_firmware_version': 3005,
    'battery_soc': 9,
    'battery_design_capacity_2': 160.0,
    'e_battery_discharge_ac_total': 0.0,
    'e_battery_charge_ac_total': 0.0,
    'battery_serial_number_2': 448662,
    'usb_inserted': True,
    'e_battery_discharge_total': 90.60000000000001,
    'e_battery_charge_total': 92.60000000000001,
}


def test_registers():
    """Ensure we can instantiate a Registers cache and derive correct attributes from it."""
    i = RegisterCache()
    i.update_holding_registers(HOLDING_REGISTERS)
    i.update_input_registers(INPUT_REGISTERS)
    assert i.holding_registers == HOLDING_REGISTERS
    assert i.input_registers == INPUT_REGISTERS

    # assert i.inverter_serial_number == 'SA1234G567'
    # assert i.model == 'Hybrid'
    # assert i.battery_serial_number == 'BG1234G567'
    assert i.bms_firmware_version == 3005
    assert i.dsp_firmware_version == 449
    assert i.arm_firmware_version == 449
    assert i.enable_charge_target
    # assert i.system_time == datetime.datetime(2022, 1, 1, 23, 57, 19)

    # time slots are BCD-encoded: 30 == 00:30, 430 == 04:30
    assert i.charge_slot_1_start == datetime.time(0, 30)
    assert i.charge_slot_1_end == datetime.time(4, 30)
    # assert i.charge_slot_1 == (datetime.time(0, 30), datetime.time(4, 30))
    assert i.charge_slot_2_start == datetime.time(0, 0)
    assert i.charge_slot_2_end == datetime.time(0, 4)
    # assert i.charge_slot_2 == (datetime.time(0, 0), datetime.time(0, 4))
    assert i.discharge_slot_1_start == datetime.time(0, 0)
    assert i.discharge_slot_1_end == datetime.time(0, 0)
    # assert i.discharge_slot_1 == (datetime.time(0, 0), datetime.time(0, 0))
    assert i.discharge_slot_2_start == datetime.time(0, 0)
    assert i.discharge_slot_2_end == datetime.time(0, 0)
    # assert i.discharge_slot_2 == (datetime.time(0, 0), datetime.time(0, 0))

    assert i.v_pv1 == 1.4000000000000001
    assert i.v_pv2 == 1.0
    assert i.v_p_bus == 7.0
    assert i.v_n_bus == 0.0
    assert i.v_ac1 == 236.70000000000002

    assert i.e_battery_throughput_h == 0
    assert i.e_battery_throughput_l == 183.20000000000002
    assert i.e_battery_throughput == 183.20000000000002

    assert i.e_pv1_day == 0.4
    assert i.e_pv2_day == 0.5
    assert i.e_grid_export_day_l == 0.6000000000000001

    assert i.battery_percent == 4
    assert i.e_battery_discharge_total == 90.60000000000001
    assert i.e_battery_charge_total == 92.60000000000001

    assert i.v_battery_cell_01 == 3.117
    assert i.v_battery_cell_16 == 3.119


@pytest.mark.skip("TODO fix")
def test_to_inverter():
    """Ensure we can return a dict view of inverter data."""
    i = RegisterCache()
    i.update_holding_registers(HOLDING_REGISTERS)
    i.update_input_registers(INPUT_REGISTERS)

    assert i.to_inverter() == EXPECTED_INVERTER_DICT
