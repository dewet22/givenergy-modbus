import datetime
import json
from unittest import skip

import pytest

from givenergy_modbus.model import TimeSlot
from givenergy_modbus.model.inverter import (
    BatteryCalibrationStage,
    BatteryPowerMode,
    Inverter,
    MeterType,
    Model,
    UsbDevice,
)
from givenergy_modbus.model.register import HoldingRegister, InputRegister
from givenergy_modbus.model.register_cache import RegisterCache


@skip('might not be needed any more')
def test_has_expected_attributes():
    """Ensure registers mapped to Batteries/BMS are represented in the model."""
    keys_to_ignore = {
        'reboot',
    }
    suffixes_to_strip = {'_l', '_start', '_1_2', '_month'}
    suffixes_to_ignore = {'_h', '_end', '_3_4', '_5_6', '_7_8', '_9_10'}
    prefixes_to_leave_untouched = {'status_', 'warning_', 'v_pv_input_start'}
    prefixes_to_ignore = {'input_reg', 'holding_reg', 'cei021_', 'auto_test_', 'system_time_'}

    def add_name(values: set, val: str):
        val = val.lower()
        for key in keys_to_ignore:
            if val == key:
                return
        for pfx in prefixes_to_leave_untouched:
            if val.startswith(pfx):
                values.add(val)
                return
        for pfx in prefixes_to_ignore:
            if val.startswith(pfx):
                return
        for sfx in suffixes_to_strip:
            if val.endswith(sfx):
                values.add(val[: -len(sfx)])
                return
        for sfx in suffixes_to_ignore:
            if val.endswith(sfx):
                return
        if val == 'num_mppt_and_num_phases':
            values.add('num_mppt')
            values.add('num_phases')
            return
        values.add(val)

    expected_attributes = {  # computed fields
        'firmware_version',
        'system_time',
        'e_pv_day',
        'p_pv',
    }
    for i in range(60):
        add_name(expected_attributes, HoldingRegister(i).name)
        add_name(expected_attributes, HoldingRegister(i + 60).name)
        add_name(expected_attributes, HoldingRegister(i + 120).name)
        add_name(expected_attributes, InputRegister(i).name)
        add_name(expected_attributes, InputRegister(i + 120).name)
        add_name(expected_attributes, InputRegister(i + 180).name)
        # add_name(expected_attributes, InputRegister(i+240).name)
    assert expected_attributes == set(Inverter.schema()['properties'].keys()).difference(
        set(Inverter.__exclude_fields__.keys())
    )


def fix_complex_json_fields(d: dict) -> None:
    d['system_time'] = d['system_time'].isoformat()
    d['charge_slot_2'] = {
        'start': d['charge_slot_2'].start.isoformat(),
        'end': d['charge_slot_2'].end.isoformat(),
    }


def test_from_registers_empty():
    """Ensure an empty object cannot be instantiated/validated because of missing data for virtual attributes."""
    i = Inverter.from_registers(RegisterCache())
    expected_dict = {
        'arm_firmware_version': 0,
        'battery_calibration_stage': BatteryCalibrationStage.OFF,
        'battery_power_mode': BatteryPowerMode.EXPORT,
        'charge_slot_2': TimeSlot(start=datetime.time(0, 0), end=datetime.time(0, 0)),
        'device_type_code': '0000',
        'dsp_firmware_version': 0,
        'enable_60hz_freq_mode': False,
        'enable_ammeter': False,
        'enable_buzzer': False,
        'enable_charge_target': False,
        'enable_drm_rj45_port': False,
        'enable_inverter': False,
        'enable_inverter_auto_restart': False,
        'firmware_version': 'D0.0-A0.0',
        'first_battery_bms_firmware_version': 0,
        'first_battery_serial_number': '',
        'grid_port_max_power_output': 0,
        'meter_type': MeterType.CT_OR_EM418,
        'modbus_address': 0,
        'modbus_version': '0.00',
        'model': Model.UNKNOWN,
        'module': '00000000',
        'num_mppt': 0,
        'num_phases': 0,
        'reverse_115_meter': False,
        'reverse_418_meter': False,
        'reverse_ct': False,
        'select_arm_chip': False,
        'serial_number': '',
        'system_time': datetime.datetime(2000, 1, 1, 0, 0, 0),
        'usb_device_inserted': UsbDevice.NONE,
    }

    assert i.dict() == expected_dict
    json_dict = json.loads(i.json())
    assert json_dict.keys() == expected_dict.keys()
    fix_complex_json_fields(expected_dict)
    assert json_dict == expected_dict


def test_from_registers(register_cache):
    """Ensure we can return a dict view of inverter data."""
    i = Inverter.from_registers(register_cache)
    expected_dict = {
        # 'active_power_rate': 100,
        # 'battery_charge_limit': 50,
        # 'battery_discharge_limit': 50,
        # 'battery_discharge_min_power_reserve': 4,
        # 'battery_low_force_charge_time': 6,
        # 'battery_nominal_capacity': 160.0,
        # 'battery_percent': 4,
        # 'battery_soc_reserve': 4,
        # 'battery_type': 1,
        # 'battery_voltage_adjust': 0,
        # 'bms_chip_version': 101,
        # 'charge_and_discharge_soc': (0, 0),
        # 'charge_slot_1': (datetime.time(0, 30), datetime.time(4, 30)),
        # 'charge_soc_stop_1': 0,
        # 'charge_soc_stop_2': 0,
        # 'charge_status': 0,
        # 'charge_target_soc': 100,
        # 'charger_warning_code': 0,
        # 'dci_1_i': 0.0,
        # 'dci_1_time': 0,
        # 'dci_2_i': 0.0,
        # 'dci_2_time': 0,
        # 'dci_fault_value': 0.0,
        # 'discharge_slot_1': (datetime.time(0, 0), datetime.time(0, 0)),
        # 'discharge_slot_2': (datetime.time(0, 0), datetime.time(0, 0)),
        # 'discharge_soc_stop_1': 0,
        # 'discharge_soc_stop_2': 0,
        # 'e_battery_charge_day': 9.0,
        # 'e_battery_charge_day_2': 9.0,
        # 'e_battery_charge_total': 174.4,
        # 'e_battery_discharge_day': 8.9,
        # 'e_battery_discharge_day_2': 8.9,
        # 'e_battery_discharge_total': 169.6,
        # 'e_battery_throughput_total': 183.2,
        # 'e_discharge_year': 0.0,
        # 'e_grid_in_day': 20.9,
        # 'e_grid_in_total': 365.3,
        # 'e_grid_out_day': 0.0,
        # 'e_grid_out_total': 0.6,
        # 'e_inverter_in_day': 9.3,
        # 'e_inverter_in_total': 94.6,
        # 'e_inverter_out_day': 8.1,
        # 'e_inverter_out_total': 93.0,
        # 'e_pv1_day': 0.4,
        # 'e_pv2_day': 0.5,
        # 'e_pv_day': 0.9,
        # 'e_pv_total': 15.9,
        # 'e_solar_diverter': 0.0,
        # 'enable_above_6kw_system': False,
        # 'enable_auto_judge_battery_type': True,
        # 'enable_bms_read': True,
        # 'enable_charge': True,
        # 'enable_discharge': False,
        # 'enable_frequency_derating': False,
        # 'enable_low_voltage_fault_ride_through': False,
        # 'enable_spi': False,
        # 'f_ac1': 49.9,
        # 'f_ac_fault_value': 0.0,
        # 'f_ac_high_c': 52.0,
        # 'f_ac_high_in': 52.0,
        # 'f_ac_high_in_time': 28,
        # 'f_ac_high_out': 51.98,
        # 'f_ac_high_out_time': 28,
        # 'f_ac_low_c': 47.0,
        # 'f_ac_low_in': 47.45,
        # 'f_ac_low_in_time': 1,
        # 'f_ac_low_out': 47.0,
        # 'f_ac_low_out_time': 24,
        # 'f_eps_backup': 49.86,
        # 'fault_code': 0,
        # 'frequency_load_limit_rate': 0,
        # 'gfci_1_i': 0.0,
        # 'gfci_1_time': 0,
        # 'gfci_2_i': 0.0,
        # 'gfci_2_time': 0,
        # 'gfci_fault_value': 0.0,
        # 'grid_power_adjust': 0,
        # 'grid_r_voltage_adjust': 0,
        # 'grid_s_voltage_adjust': 0,
        # 'grid_t_voltage_adjust': 0,
        # 'i_ac1': 0.0,
        # 'i_battery': 0.0,
        # 'i_grid_port': 2.92,
        # 'i_pv1': 0.0,
        # 'i_pv2': 0.0,
        # 'inverter_countdown': 30,
        # 'inverter_reboot': 0,
        # 'inverter_restart_delay_time': 30,
        # 'inverter_start_time': 30,
        # 'inverter_status': 0,
        # 'island_check_continue': 0,
        # 'iso1': 0,
        # 'iso2': 0,
        # 'iso_fault_value': 0.0,
        # 'local_command_test': False,
        # 'p_battery': 0,
        # 'p_eps_backup': 0,
        # 'p_grid_apparent': 680,
        # 'p_grid_out': -342,
        # 'p_inverter_out': 0,
        # 'p_load_demand': 342,
        # 'p_pv': 13,
        # 'p_pv1': 4,
        # 'p_pv2': 9,
        # 'pf_cmd_memory_state': False,
        # 'pf_inverter_out': -0.521,
        # 'pf_limit_lp1_lp': 0,
        # 'pf_limit_lp1_pf': -1.0,
        # 'pf_limit_lp2_lp': 0,
        # 'pf_limit_lp2_pf': -1.0,
        # 'pf_limit_lp3_lp': 0,
        # 'pf_limit_lp3_pf': -1.0,
        # 'pf_limit_lp4_lp': 0,
        # 'pf_limit_lp4_pf': -1.0,
        # 'power_factor': -1,
        # 'power_factor_function_model': 0,
        # 'pv1_power_adjust': 0,
        # 'pv1_voltage_adjust': 0,
        # 'pv2_power_adjust': 0,
        # 'pv2_voltage_adjust': 0,
        # 'reactive_power_rate': 0,
        # 'real_v_f_value': 0.0,
        # 'remote_bms_restart': False,
        # 'safety_time_limit': 0.0,
        # 'safety_v_f_limit': 0.0,
        # 'start_system_auto_test': False,
        # 'system_mode': 1,
        # 'temp_battery': 17.0,
        # 'temp_charger': 22.3,
        # 'temp_fault_value': 0.0,
        # 'temp_inverter_heatsink': 22.2,
        # 'test_treat_time': 0,
        # 'test_treat_value': 0.0,
        # 'test_value': 0.0,
        # 'usb_device_inserted': 2,
        # 'user_code': 7,
        # 'v_10_min_protection': 274.0,
        # 'v_ac1': 236.7,
        # 'v_ac_fault_value': 0.0,
        # 'v_ac_high_c': 283.7,
        # 'v_ac_high_in': 262.0,
        # 'v_ac_high_in_time': 52,
        # 'v_ac_high_out': 274.0,
        # 'v_ac_high_out_time': 27,
        # 'v_ac_low_c': 175.5,
        # 'v_ac_low_in': 184.0,
        # 'v_ac_low_in_time': 126,
        # 'v_ac_low_out': 184.0,
        # 'v_ac_low_out_time': 126,
        # 'v_battery': 49.91,
        # 'v_battery_over_protection_limit': 58.50,
        # 'v_battery_under_protection_limit': 43.20,
        # 'v_eps_backup': 235.6,
        # 'v_highbrigh_bus': 12,
        # 'v_n_bus': 0.0,
        # 'v_p_bus': 7.0,
        # 'v_pv1': 1.4,
        # 'v_pv2': 1.0,
        # 'v_pv_fault_value': 0.0,
        # 'v_pv_input_start': 150.0,
        # 'variable_address': 32768,
        # 'variable_value': 30235,
        # 'work_time_total': 213,
        'arm_firmware_version': 449,
        'battery_calibration_stage': BatteryCalibrationStage.OFF,
        'battery_power_mode': BatteryPowerMode.SELF_CONSUMPTION,
        'charge_slot_2': TimeSlot(datetime.time(0, 0), datetime.time(0, 4)),
        'device_type_code': '2001',
        'dsp_firmware_version': 449,
        'enable_60hz_freq_mode': False,
        'enable_ammeter': True,
        'enable_buzzer': False,
        'enable_charge_target': True,
        'enable_drm_rj45_port': True,
        'enable_inverter': True,
        'enable_inverter_auto_restart': False,
        'firmware_version': 'D0.449-A0.449',
        'first_battery_bms_firmware_version': 3005,
        'first_battery_serial_number': 'BG1234G567',
        'grid_port_max_power_output': 6000,
        'meter_type': MeterType.EM115,
        'modbus_address': 0x11,
        'modbus_version': '1.40',
        'model': Model.HYBRID,
        'module': '00030832',
        'num_mppt': 2,
        'num_phases': 1,
        'reverse_115_meter': False,
        'reverse_418_meter': False,
        'reverse_ct': True,
        'select_arm_chip': False,
        'serial_number': 'SA1234G567',
        'system_time': datetime.datetime(2022, 1, 1, 23, 57, 19),
        'usb_device_inserted': UsbDevice.DISK,
    }
    assert i.serial_number == 'SA1234G567'
    assert i.model == Model.HYBRID
    assert getattr(i, 'serial_number') == 'SA1234G567'
    with pytest.raises(TypeError, match="'Inverter' object is not subscriptable"):
        i['serial_number']

    assert i.dict() == expected_dict
    json_dict = json.loads(i.json())
    assert json_dict.keys() == expected_dict.keys()
    fix_complex_json_fields(expected_dict)
    assert json_dict == expected_dict


def test_from_registers_actual_data(register_cache_inverter_daytime_discharging_with_solar_generation):
    """Ensure we can instantiate an Inverter from actual register data."""
    i = Inverter.from_registers(register_cache_inverter_daytime_discharging_with_solar_generation)
    assert i.serial_number == 'SA1234G567'
    assert i.model == Model.HYBRID
    expected_dict = {
        # 'active_power_rate': 100,
        # 'battery_charge_limit': 50,
        # 'battery_discharge_limit': 50,
        # 'battery_discharge_min_power_reserve': 4,
        # 'battery_low_force_charge_time': 6,
        # 'battery_nominal_capacity': 160.0,
        # 'battery_percent': 68,
        # 'battery_soc_reserve': 4,
        # 'battery_type': 1,
        # 'battery_voltage_adjust': 0,
        # 'bms_chip_version': 101,
        # 'charge_and_discharge_soc': (0, 0),
        # 'charge_slot_1': (datetime.time(0, 30), datetime.time(4, 30)),
        # 'charge_soc_stop_1': 0,
        # 'charge_soc_stop_2': 0,
        # 'charge_status': 5,
        # 'charge_target_soc': 100,
        # 'charger_warning_code': 0,
        # 'dci_1_i': 0.0,
        # 'dci_1_time': 0,
        # 'dci_2_i': 0.0,
        # 'dci_2_time': 0,
        # 'dci_fault_value': 0.0,
        # 'discharge_slot_1': (datetime.time(0, 0), datetime.time(0, 0)),
        # 'discharge_slot_2': (datetime.time(0, 0), datetime.time(0, 0)),
        # 'discharge_soc_stop_1': 0,
        # 'discharge_soc_stop_2': 0,
        # 'e_battery_charge_day': 9.1,
        # 'e_battery_charge_day_2': 9.1,
        # 'e_battery_charge_total': 183.5,
        # 'e_battery_discharge_day': 3.4,
        # 'e_battery_discharge_day_2': 3.4,
        # 'e_battery_discharge_total': 173.0,
        # 'e_battery_throughput_total': 356.5,
        # 'e_discharge_year': 0.0,
        # 'e_grid_in_day': 19.8,
        # 'e_grid_in_total': 624.2,
        # 'e_grid_out_day': 0.0,
        # 'e_grid_out_total': 0.9,
        # 'e_inverter_in_day': 9.3,
        # 'e_inverter_in_total': 188.1,
        # 'e_inverter_out_day': 3.8,
        # 'e_inverter_out_total': 172.5,
        # 'e_pv1_day': 0.4,
        # 'e_pv2_day': 0.6,
        # 'e_pv_day': 1.0,
        # 'e_pv_total': 26.3,
        # 'e_solar_diverter': 0.0,
        # 'enable_above_6kw_system': False,
        # 'enable_auto_judge_battery_type': True,
        # 'enable_bms_read': True,
        # 'enable_charge': True,
        # 'enable_discharge': False,
        # 'enable_frequency_derating': True,
        # 'enable_low_voltage_fault_ride_through': False,
        # 'enable_spi': True,
        # 'f_ac1': 49.96,
        # 'f_ac_fault_value': 0.0,
        # 'f_ac_high_c': 52.0,
        # 'f_ac_high_in': 52.0,
        # 'f_ac_high_in_time': 28,
        # 'f_ac_high_out': 51.98,
        # 'f_ac_high_out_time': 28,
        # 'f_ac_low_c': 47.0,
        # 'f_ac_low_in': 47.45,
        # 'f_ac_low_in_time': 1,
        # 'f_ac_low_out': 47.0,
        # 'f_ac_low_out_time': 24,
        # 'f_eps_backup': 49.92,
        # 'fault_code': 0,
        # 'frequency_load_limit_rate': 24,
        # 'gfci_1_i': 0.0,
        # 'gfci_1_time': 0,
        # 'gfci_2_i': 0.0,
        # 'gfci_2_time': 0,
        # 'gfci_fault_value': 0.0,
        # 'grid_power_adjust': 0,
        # 'grid_r_voltage_adjust': 0,
        # 'grid_s_voltage_adjust': 0,
        # 'grid_t_voltage_adjust': 0,
        # 'i_ac1': 0.27,
        # 'i_battery': 6.47,
        # 'i_grid_port': 2.57,
        # 'i_pv1': 0.3,
        # 'i_pv2': 0.3,
        # 'inverter_countdown': 0,
        # 'inverter_restart_delay_time': 30,
        # 'inverter_start_time': 30,
        # 'inverter_status': 1,
        # 'island_check_continue': 0,
        # 'iso1': 0,
        # 'iso2': 0,
        # 'iso_fault_value': 0.0,
        # 'local_command_test': False,
        # 'p_battery': 360,
        # 'p_eps_backup': 0,
        # 'p_grid_apparent': 554,
        # 'p_grid_out': 21,
        # 'p_inverter_out': 536,
        # 'p_load_demand': 515,
        # 'p_pv': 245,
        # 'p_pv1': 117,
        # 'p_pv2': 128,
        # 'pf_cmd_memory_state': True,
        # 'pf_inverter_out': -0.0469,
        # 'pf_limit_lp1_lp': 255,
        # 'pf_limit_lp1_pf': 1.0,
        # 'pf_limit_lp2_lp': 255,
        # 'pf_limit_lp2_pf': 1.0,
        # 'pf_limit_lp3_lp': 255,
        # 'pf_limit_lp3_pf': 1.0,
        # 'pf_limit_lp4_lp': 255,
        # 'pf_limit_lp4_pf': 1.0,
        # 'power_factor': -1,
        # 'power_factor_function_model': 0,
        # 'pv1_power_adjust': 0,
        # 'pv1_voltage_adjust': 0,
        # 'pv2_power_adjust': 0,
        # 'pv2_voltage_adjust': 0,
        # 'reactive_power_rate': 0,
        # 'real_v_f_value': 0.0,
        # 'reboot': 0,
        # 'remote_bms_restart': False,
        # 'safety_time_limit': 0.0,
        # 'safety_v_f_limit': 0.0,
        # 'start_system_auto_test': False,
        # 'system_mode': 1,
        # 'temp_battery': 16.0,
        # 'temp_charger': 24.1,
        # 'temp_fault_value': 0.0,
        # 'temp_inverter_heatsink': 24.4,
        # 'test_treat_time': 0,
        # 'test_treat_value': 0.0,
        # 'test_value': 0.0,
        # 'usb_device_inserted': 2,
        # 'user_code': 7,
        # 'v_10_min_protection': 274.0,
        # 'v_ac1': 236.3,
        # 'v_ac_fault_value': 0.0,
        # 'v_ac_high_c': 283.7,
        # 'v_ac_high_in': 262.0,
        # 'v_ac_high_in_time': 52,
        # 'v_ac_high_out': 274.0,
        # 'v_ac_high_out_time': 27,
        # 'v_ac_low_c': 175.5,
        # 'v_ac_low_in': 184.0,
        # 'v_ac_low_in_time': 126,
        # 'v_ac_low_out': 184.0,
        # 'v_ac_low_out_time': 126,
        # 'v_battery': 51.73,
        # 'v_battery_over_protection_limit': 58.5,
        # 'v_battery_under_protection_limit': 43.2,
        # 'v_eps_backup': 235.10,
        # 'v_highbrigh_bus': 2829,
        # 'v_n_bus': 0.0,
        # 'v_p_bus': 383.0,
        # 'v_pv1': 357.0,
        # 'v_pv2': 369.70,
        # 'v_pv_fault_value': 0.0,
        # 'v_pv_input_start': 150.0,
        # 'variable_address': 32768,
        # 'variable_value': 30235,
        # 'work_time_total': 385,
        'arm_firmware_version': 449,
        'battery_calibration_stage': BatteryCalibrationStage.OFF,
        'battery_power_mode': BatteryPowerMode.SELF_CONSUMPTION,
        'charge_slot_2': TimeSlot(datetime.time(0, 0), datetime.time(0, 4)),
        'device_type_code': '2001',
        'dsp_firmware_version': 449,
        'enable_60hz_freq_mode': False,
        'enable_ammeter': True,
        'enable_buzzer': False,
        'enable_charge_target': False,
        'enable_drm_rj45_port': True,
        'enable_inverter': True,
        'enable_inverter_auto_restart': False,
        'firmware_version': 'D0.449-A0.449',
        'first_battery_bms_firmware_version': 3005,
        'first_battery_serial_number': 'BG1234G567',
        'grid_port_max_power_output': 6000,
        'meter_type': MeterType.EM115,
        'modbus_address': 0x11,
        'modbus_version': '1.40',
        'model': Model.HYBRID,
        'module': '00030832',
        'num_mppt': 2,
        'num_phases': 1,
        'reverse_115_meter': False,
        'reverse_418_meter': False,
        'reverse_ct': True,
        'select_arm_chip': False,
        'serial_number': 'SA1234G567',
        'system_time': datetime.datetime(2022, 1, 11, 11, 51, 46),
        'usb_device_inserted': UsbDevice.DISK,
    }
    assert i.dict() == expected_dict
    json_dict = json.loads(i.json())
    assert json_dict.keys() == expected_dict.keys()
    fix_complex_json_fields(expected_dict)
    assert json_dict == expected_dict
