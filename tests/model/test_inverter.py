import datetime
import warnings

import pytest

from givenergy_modbus.model import TimeSlot
from givenergy_modbus.model.inverter import (
    AC_COUPLED_MODELS,
    BatteryCalibrationStage,
    BatteryPowerMode,
    BatteryType,
    ChargeStatus,
    MeterType,
    Model,
    PowerFactorFunctionModel,
    SinglePhaseInverter,
    Status,
    UsbDevice,
    inverter_address_for,
    resolve_model,
)
from givenergy_modbus.model.register import HR
from givenergy_modbus.model.register_cache import RegisterCache


def test_first_battery_serial_number_removed():
    """first_battery_serial_number is gone from the model (#191).

    GivTCP-heritage, unused, and unverifiable: on AIO firmware it held the unit serial
    byte-swapped, not a battery serial. Removed outright — no field, no alias.
    """
    assert "first_battery_serial_number" not in SinglePhaseInverter().model_dump()
    cache = RegisterCache({HR(8): 0x4843, HR(9): 0x3234, HR(10): 0x3134, HR(11): 0x4731, HR(12): 0x3637})
    assert "first_battery_serial_number" not in SinglePhaseInverter.from_register_cache(cache).model_dump()


def test_inverter():
    i1 = SinglePhaseInverter()
    i2 = SinglePhaseInverter.from_register_cache(RegisterCache())

    assert (
        i1.model_dump()
        == i2.model_dump()
        == {
            "active_power_rate": None,
            "arm_firmware_version": None,
            "battery_max_power": None,
            "battery_calibration_stage": None,
            "battery_capacity_ah": None,
            "battery_capacity_kwh": None,
            "battery_power_mode": None,
            "battery_type": None,
            "bms_firmware_version": None,
            "charge_slot_2": None,
            "charge_soc": None,
            "device_type_code": None,
            "discharge_slot_1": None,
            "discharge_slot_2": None,
            "discharge_soc": None,
            "dsp_firmware_version": None,
            "enable_60hz_freq_mode": None,
            "enable_ammeter": None,
            "enable_auto_judge_battery_type": None,
            "enable_charge_target": None,
            "enable_discharge": None,
            "enable_drm_rj45_port": None,
            "enable_inverter": None,
            "enable_inverter_auto_restart": None,
            "enable_reversed_115_meter": None,
            "enable_reversed_418_meter": None,
            "firmware_version": None,
            "first_battery_bms_firmware_version": None,
            "grid_port_max_power_output": None,
            "meter_type": None,
            "modbus_address": None,
            "modbus_version": None,
            "model": None,
            "inverter_max_power": None,
            "is_ac_coupled": False,
            "module": None,
            "num_mppt": None,
            "num_phases": None,
            "power_factor": None,
            "reactive_power_rate": None,
            "enable_reversed_ct_clamp": None,
            "select_arm_chip": None,
            "serial_number": None,
            "status": None,
            "v_pv1": None,
            "v_pv2": None,
            "v_p_bus": None,
            "v_n_bus": None,
            "v_ac1": None,
            "e_battery_throughput": None,
            "i_pv1": None,
            "i_pv2": None,
            "i_ac1": None,
            "e_pv_total": None,
            "f_ac1": None,
            "charge_status": None,
            "charge_status_label": None,
            "v_highbrigh_bus": None,
            "pf_inverter_output_now": None,
            "e_pv1_day": None,
            "p_pv1": None,
            "e_pv2_day": None,
            "p_pv2": None,
            "e_grid_out_total": None,
            "e_solar_diverter": None,
            "p_grid_out_ph1": None,
            "e_grid_out_day": None,
            "e_grid_in_day": None,
            "e_inverter_in_total": None,
            "e_discharge_year": None,
            "p_grid_out": None,
            "p_backup": None,
            "e_grid_in_total": None,
            "e_ac_charge_today": None,
            "e_consumption_today": None,
            "e_battery_charge_today_alt1": None,
            "e_battery_discharge_today_alt1": None,
            "countdown": None,
            "fault_code": None,
            "t_inverter_heatsink": None,
            "p_load_demand": None,
            "p_grid_apparent": None,
            "e_pv_generation_today": None,
            "e_pv_generation_total": None,
            "work_time_total_hours": None,
            "system_mode": None,
            "v_battery": None,
            "i_battery": None,
            "p_battery": None,
            "v_ac1_output": None,
            "f_ac1_output": None,
            "t_charger": None,
            "t_battery": None,
            "charger_warning_code": None,
            "i_grid_port": None,
            "battery_soc": None,
            "system_time": None,
            "usb_device_inserted": None,
            "user_code": None,
            "variable_address": None,
            "variable_value": None,
            "v_pv_start": None,
            "restart_delay_time": None,
            "start_countdown_timer": None,
            "enable_charge": None,
            "charge_slot_1": None,
            "battery_high_voltage_protection_limit": None,
            "battery_low_voltage_protection_limit": None,
            # 'island_check_continue': None,
            "enable_buzzer": None,
            "enable_bms_read": None,
            "discharge_soc_stop_2": None,
            "charge_target_soc": None,
            "charge_soc_stop_2": None,
            "charge_soc_stop_1": None,
            "battery_soc_reserve": None,
            "battery_low_force_charge_time": None,
            "battery_discharge_min_power_reserve": None,
            "battery_discharge_limit": None,
            "battery_charge_limit": None,
            "debug_inverter": None,
            "discharge_soc_stop_1": None,
            "enable_above_6kw_system": None,
            "enable_battery_cable_impedance_alarm": None,
            "enable_battery_on_pv_or_grid": None,
            "enable_frequency_derating": None,
            "enable_g100_limit_switch": None,
            "enable_local_command_test": None,
            "enable_low_voltage_fault_ride_through": None,
            "enable_spi": None,
            "enable_ups_mode": None,
            "frequency_load_limit_rate": None,
            "power_factor_function_model": None,
            "start_system_auto_test": None,
            "threephase_abc": None,
            "threephase_balance_1": None,
            "threephase_balance_2": None,
            "threephase_balance_3": None,
            "threephase_balance_mode": None,
            "cmd_bms_flash_update": None,
            "enable_inverter_parallel_mode": None,
            "smart_load_slot_1": None,
            "smart_load_slot_2": None,
            "smart_load_slot_3": None,
            "smart_load_slot_4": None,
            "smart_load_slot_5": None,
            "smart_load_slot_6": None,
            "smart_load_slot_7": None,
            "smart_load_slot_8": None,
            "smart_load_slot_9": None,
            "smart_load_slot_10": None,
            "e_battery_charge_today": None,
            "e_battery_charge_today_alt3": None,
            "e_battery_charge_total": None,
            "e_battery_charge_total_alt2": None,
            "e_battery_discharge_today": None,
            "e_battery_discharge_today_alt3": None,
            "e_battery_discharge_total": None,
            "e_battery_discharge_total_alt2": None,
            "pv_power_setting": None,
            "e_inverter_export_total": None,
            "battery_voltage_adjust": None,
            "inverter_reboot": None,
            "enable_rtc": None,
            "inverter_errors": None,
            "inverter_fault_messages": None,
            "charge_target_soc_1": None,
            "charge_slot_2_x": None,
            "charge_target_soc_2": None,
            "charge_slot_3": None,
            "charge_target_soc_3": None,
            "charge_slot_4": None,
            "charge_target_soc_4": None,
            "charge_slot_5": None,
            "charge_target_soc_5": None,
            "charge_slot_6": None,
            "charge_target_soc_6": None,
            "charge_slot_7": None,
            "charge_target_soc_7": None,
            "charge_slot_8": None,
            "charge_target_soc_8": None,
            "charge_slot_9": None,
            "charge_target_soc_9": None,
            "charge_slot_10": None,
            "charge_target_soc_10": None,
            "discharge_target_soc_1": None,
            "discharge_target_soc_2": None,
            "discharge_slot_3": None,
            "discharge_target_soc_3": None,
            "discharge_slot_4": None,
            "discharge_target_soc_4": None,
            "discharge_slot_5": None,
            "discharge_target_soc_5": None,
            "discharge_slot_6": None,
            "discharge_target_soc_6": None,
            "discharge_slot_7": None,
            "discharge_target_soc_7": None,
            "discharge_slot_8": None,
            "discharge_target_soc_8": None,
            "discharge_slot_9": None,
            "discharge_target_soc_9": None,
            "discharge_slot_10": None,
            "discharge_target_soc_10": None,
            "export_priority": None,
            "battery_charge_limit_ac": None,
            "battery_discharge_limit_ac": None,
            "enable_eps": None,
            "battery_pause_mode": None,
            "battery_pause_slot_1": None,
            "e_battery_discharge_total_alt1": None,
            "e_battery_charge_total_alt1": None,
            "e_battery_discharge_today_alt2": None,
            "e_battery_charge_today_alt2": None,
            "p_combined_generation": None,
        }
    )


def test_from_registers(register_cache):
    """Ensure we can return a dict view of inverter data."""
    i = SinglePhaseInverter.from_register_cache(register_cache)
    assert i.serial_number == "SA1234G567"
    assert i.model == Model.HYBRID
    assert getattr(i, "serial_number") == "SA1234G567"
    with pytest.raises(TypeError, match="'SinglePhaseInverter' object is not subscriptable"):
        i["serial_number"]

    assert i.model_dump() == {
        "battery_charge_limit": 50,
        "battery_discharge_limit": 50,
        "battery_discharge_min_power_reserve": 4,
        "battery_high_voltage_protection_limit": 58.50,
        "battery_low_force_charge_time": 6,
        "battery_low_voltage_protection_limit": 43.20,
        # 'battery_percent': 4,
        "battery_soc_reserve": 4,
        # 'battery_voltage_adjust': 0,
        "charge_slot_1": TimeSlot.from_repr(30, 430),
        "charge_soc_stop_1": 0,
        "charge_soc_stop_2": 0,
        # 'charge_status': 0,
        "charge_target_soc": 100,
        # 'charger_warning_code': 0,
        "cmd_bms_flash_update": None,
        # 'dci_1_i': 0.0,
        # 'dci_1_time': 0,
        # 'dci_2_i': 0.0,
        # 'dci_2_time': 0,
        # 'dci_fault_value': 0.0,
        "debug_inverter": None,
        "discharge_soc_stop_1": None,
        "discharge_soc_stop_2": 0,
        # HYBRID_GEN1 (dtc 2001, arm 449): facade routes today→alt2, total→alt1 (#76).
        # Raw IR alt1/alt2 sources are asserted in the IR-block sections below.
        "e_battery_charge_today_alt3": None,  # HR(4114), dead/never polled
        "e_battery_charge_today": 9.0,  # canonical: GEN1 today→alt2 (IR183)
        "e_battery_charge_total_alt2": None,  # HR(4111-4112), dead/never polled
        "e_battery_charge_total": 174.4,  # canonical: GEN1 total→alt1 (IR181)
        "e_battery_discharge_today_alt3": None,  # HR(4113), dead/never polled
        "e_battery_discharge_today": 8.9,  # canonical: GEN1 today→alt2 (IR182)
        "e_battery_discharge_total_alt2": None,  # HR(4109-4110), dead/never polled
        "e_battery_discharge_total": 169.6,  # canonical: GEN1 total→alt1 (IR180)
        # 'e_battery_throughput_total': 183.2,
        # 'e_discharge_year': 0.0,
        # 'e_grid_in_day': 20.9,
        # 'e_grid_in_total': 365.3,
        # 'e_grid_out_day': 0.0,
        # 'e_grid_out_total': 0.6,
        "e_inverter_export_total": None,
        # 'e_inverter_in_day': 9.3,
        # 'e_inverter_in_total': 94.6,
        # 'e_inverter_out_day': 8.1,
        # 'e_inverter_out_total': 93.0,
        # 'e_pv1_day': 0.4,
        # 'e_pv2_day': 0.5,
        # 'e_pv_day': 0.9,
        # 'e_pv_total': 15.9,
        # 'e_solar_diverter': 0.0,
        "enable_above_6kw_system": None,
        "enable_battery_cable_impedance_alarm": None,
        "enable_battery_on_pv_or_grid": None,
        "enable_bms_read": True,
        "enable_buzzer": False,
        "enable_charge": True,
        "enable_frequency_derating": None,
        "enable_g100_limit_switch": None,
        "enable_inverter_parallel_mode": None,
        "enable_low_voltage_fault_ride_through": None,
        "enable_spi": None,
        "enable_ups_mode": None,
        "smart_load_slot_1": None,
        "smart_load_slot_2": None,
        "smart_load_slot_3": None,
        "smart_load_slot_4": None,
        "smart_load_slot_5": None,
        "smart_load_slot_6": None,
        "smart_load_slot_7": None,
        "smart_load_slot_8": None,
        "smart_load_slot_9": None,
        "smart_load_slot_10": None,
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
        "frequency_load_limit_rate": None,
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
        # 'inverter_status': 0,
        # 'island_check_continue': 0,
        # 'iso1': 0,
        # 'iso2': 0,
        # 'iso_fault_value': 0.0,
        "enable_local_command_test": None,
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
        "power_factor_function_model": None,
        # 'pv1_power_adjust': 0,
        # 'pv1_voltage_adjust': 0,
        # 'pv2_power_adjust': 0,
        # 'pv2_voltage_adjust': 0,
        "pv_power_setting": None,
        "v_pv_start": 150.0,
        # 'real_v_f_value': 0.0,
        # 'remote_bms_restart': False,
        "restart_delay_time": 30,
        # 'safety_time_limit': 0.0,
        # 'safety_v_f_limit': 0.0,
        "start_countdown_timer": 30,
        "start_system_auto_test": None,
        # 'system_mode': 1,
        # 'temp_battery': 17.0,
        # 'temp_charger': 22.3,
        # 'temp_fault_value': 0.0,
        # 'temp_inverter_heatsink': 22.2,
        # 'test_treat_time': 0,
        # 'test_treat_value': 0.0,
        # 'test_value': 0.0,
        "threephase_abc": None,
        "threephase_balance_1": None,
        "threephase_balance_2": None,
        "threephase_balance_3": None,
        "threephase_balance_mode": None,
        # 'usb_device_inserted': 2,
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
        # 'v_eps_backup': 235.6,
        # 'v_highbrigh_bus': 12,
        # 'v_n_bus': 0.0,
        # 'v_p_bus': 7.0,
        # 'v_pv1': 1.4,
        # 'v_pv2': 1.0,
        # 'v_pv_fault_value': 0.0,
        # 'work_time_total_hours': 213,
        "active_power_rate": 100,
        "arm_firmware_version": 449,
        "battery_max_power": 2600,
        "battery_calibration_stage": BatteryCalibrationStage.OFF,
        "battery_capacity_ah": 160,
        "battery_capacity_kwh": 8.192,
        "battery_power_mode": BatteryPowerMode.SELF_CONSUMPTION,
        "battery_type": BatteryType.LITHIUM,
        "bms_firmware_version": 101,
        "charge_slot_2": TimeSlot(datetime.time(0, 0), datetime.time(0, 4)),
        "charge_soc": 0,
        "device_type_code": "2001",
        "discharge_slot_1": TimeSlot.from_repr(0, 0),
        "discharge_slot_2": TimeSlot.from_repr(0, 0),
        "discharge_soc": 0,
        "dsp_firmware_version": 449,
        "enable_60hz_freq_mode": False,
        "enable_ammeter": True,
        "enable_auto_judge_battery_type": True,
        "enable_charge_target": True,
        "enable_discharge": False,
        "enable_drm_rj45_port": True,
        "enable_inverter": True,
        "enable_inverter_auto_restart": False,
        "enable_reversed_115_meter": False,
        "enable_reversed_418_meter": False,
        "enable_reversed_ct_clamp": True,
        "firmware_version": "D0.449-A0.449",
        "first_battery_bms_firmware_version": 3005,
        "grid_port_max_power_output": 6000,
        "meter_type": MeterType.EM115,
        "modbus_address": 0x11,
        "modbus_version": "1.40",
        "model": Model.HYBRID,
        "inverter_max_power": 5000,
        "is_ac_coupled": False,
        "module": "00030832",
        "num_mppt": 2,
        "num_phases": 1,
        "power_factor": -1.0,
        "reactive_power_rate": 0,
        "select_arm_chip": False,
        "serial_number": "SA1234G567",
        "status": Status.WAITING,
        "v_pv1": 1.4,
        "v_pv2": 1.0,
        "v_p_bus": 7.0,
        "v_n_bus": 0.0,
        "v_ac1": 236.7,
        "e_battery_throughput": 183.2,
        "i_pv1": 0.0,
        "i_pv2": 0.0,
        "i_ac1": 0.0,
        "e_pv_total": 15.9,
        "f_ac1": 49.9,
        "charge_status": 0,
        "charge_status_label": ChargeStatus.IDLE,
        "v_highbrigh_bus": 1.2,
        "pf_inverter_output_now": -0.521,
        "e_pv1_day": 0.4,
        "p_pv1": 4,
        "e_pv2_day": 0.5,
        "p_pv2": 9,
        "e_grid_out_total": 0.6,
        "e_solar_diverter": 0.0,
        "p_grid_out_ph1": 0,
        "e_grid_out_day": 0.0,
        "e_grid_in_day": 20.9,
        "e_inverter_in_total": 94.6,
        "e_discharge_year": 0.0,
        "p_grid_out": -342,
        "p_backup": 0,
        "e_grid_in_total": 365.3,
        "e_ac_charge_today": 9.3,  # IR(35) — was mislabelled e_load_day (#174)
        # computed: e_pv_generation_today + e_grid_in_day − e_grid_out_day − e_ac_charge_today
        #         = 8.1 + 20.9 − 0.0 − 9.3
        "e_consumption_today": 19.7,
        "e_battery_charge_today_alt1": 9.0,  # IR(36)
        "e_battery_discharge_today_alt1": 8.9,  # IR(37)
        "countdown": 30,
        "fault_code": "00000000",
        "t_inverter_heatsink": 22.2,
        "p_load_demand": 342,
        "p_grid_apparent": 680,
        "e_pv_generation_today": 8.1,  # IR(44) — was mislabelled e_inverter_out_day (#174)
        "e_pv_generation_total": 93.0,
        "work_time_total_hours": 213,
        "system_mode": 1,
        "v_battery": 49.91,
        "i_battery": 0.0,
        "p_battery": 0,
        "v_ac1_output": 235.6,
        "f_ac1_output": 49.86,
        "t_charger": 22.3,
        "t_battery": 17.0,
        "charger_warning_code": 0,
        "i_grid_port": 2.92,
        "battery_soc": 4,
        "system_time": datetime.datetime(2022, 1, 1, 23, 57, 19),
        "usb_device_inserted": UsbDevice.DISK,
        "user_code": 7,
        "variable_address": 32768,
        "variable_value": 30235,
        "battery_voltage_adjust": 0.0,
        "inverter_reboot": None,
        "enable_rtc": None,
        "inverter_errors": None,
        "inverter_fault_messages": None,
        "charge_target_soc_1": None,
        "charge_slot_2_x": None,
        "charge_target_soc_2": None,
        "charge_slot_3": None,
        "charge_target_soc_3": None,
        "charge_slot_4": None,
        "charge_target_soc_4": None,
        "charge_slot_5": None,
        "charge_target_soc_5": None,
        "charge_slot_6": None,
        "charge_target_soc_6": None,
        "charge_slot_7": None,
        "charge_target_soc_7": None,
        "charge_slot_8": None,
        "charge_target_soc_8": None,
        "charge_slot_9": None,
        "charge_target_soc_9": None,
        "charge_slot_10": None,
        "charge_target_soc_10": None,
        "discharge_target_soc_1": None,
        "discharge_target_soc_2": None,
        "discharge_slot_3": None,
        "discharge_target_soc_3": None,
        "discharge_slot_4": None,
        "discharge_target_soc_4": None,
        "discharge_slot_5": None,
        "discharge_target_soc_5": None,
        "discharge_slot_6": None,
        "discharge_target_soc_6": None,
        "discharge_slot_7": None,
        "discharge_target_soc_7": None,
        "discharge_slot_8": None,
        "discharge_target_soc_8": None,
        "discharge_slot_9": None,
        "discharge_target_soc_9": None,
        "discharge_slot_10": None,
        "discharge_target_soc_10": None,
        "export_priority": None,
        "battery_charge_limit_ac": None,
        "battery_discharge_limit_ac": None,
        "enable_eps": None,
        "battery_pause_mode": None,
        "battery_pause_slot_1": None,
        "e_battery_discharge_total_alt1": 169.6,  # IR(180)
        "e_battery_charge_total_alt1": 174.4,  # IR(181)
        "e_battery_discharge_today_alt2": 8.9,  # IR(182)
        "e_battery_charge_today_alt2": 9.0,  # IR(183)
        "p_combined_generation": None,
    }


def test_from_registers_actual_data(register_cache_inverter_daytime_discharging_with_solar_generation):
    """Ensure we can instantiate an SinglePhaseInverter from actual register data."""
    i = SinglePhaseInverter.from_register_cache(register_cache_inverter_daytime_discharging_with_solar_generation)
    assert i.serial_number == "SA1234G567"
    assert i.model == Model.HYBRID
    assert i.model_dump() == {
        "battery_charge_limit": 50,
        "battery_discharge_limit": 50,
        "battery_discharge_min_power_reserve": 4,
        "battery_high_voltage_protection_limit": 58.50,
        "battery_low_force_charge_time": 6,
        "battery_low_voltage_protection_limit": 43.20,
        # 'battery_percent': 68,
        "battery_soc_reserve": 4,
        # 'battery_voltage_adjust': 0,
        "charge_slot_1": TimeSlot.from_repr(30, 430),
        "charge_soc_stop_1": 0,
        "charge_soc_stop_2": 0,
        # 'charge_status': 5,
        "charge_target_soc": 100,
        # 'charger_warning_code': 0,
        "cmd_bms_flash_update": None,
        # 'dci_1_i': 0.0,
        # 'dci_1_time': 0,
        # 'dci_2_i': 0.0,
        # 'dci_2_time': 0,
        # 'dci_fault_value': 0.0,
        "debug_inverter": 0,
        "discharge_soc_stop_1": 0,
        "discharge_soc_stop_2": 0,
        # HYBRID_GEN1 (dtc 2001, arm 449): facade routes today→alt2, total→alt1 (#76).
        # Raw IR alt1/alt2 sources are asserted in the IR-block sections below.
        "e_battery_charge_today_alt3": None,  # HR(4114), dead/never polled
        "e_battery_charge_today": 9.1,  # canonical: GEN1 today→alt2 (IR183)
        "e_battery_charge_total_alt2": None,  # HR(4111-4112), dead/never polled
        "e_battery_charge_total": 183.5,  # canonical: GEN1 total→alt1 (IR181)
        "e_battery_discharge_today_alt3": None,  # HR(4113), dead/never polled
        "e_battery_discharge_today": 3.4,  # canonical: GEN1 today→alt2 (IR182)
        "e_battery_discharge_total_alt2": None,  # HR(4109-4110), dead/never polled
        "e_battery_discharge_total": 173.0,  # canonical: GEN1 total→alt1 (IR180)
        # 'e_battery_throughput_total': 356.5,
        # 'e_discharge_year': 0.0,
        # 'e_grid_in_day': 19.8,
        # 'e_grid_in_total': 624.2,
        # 'e_grid_out_day': 0.0,
        # 'e_grid_out_total': 0.9,
        "e_inverter_export_total": None,
        # 'e_inverter_in_day': 9.3,
        # 'e_inverter_in_total': 188.1,
        # 'e_inverter_out_day': 3.8,
        # 'e_inverter_out_total': 172.5,
        # 'e_pv1_day': 0.4,
        # 'e_pv2_day': 0.6,
        # 'e_pv_day': 1.0,
        # 'e_pv_total': 26.3,
        # 'e_solar_diverter': 0.0,
        "enable_above_6kw_system": False,
        "enable_battery_cable_impedance_alarm": False,
        "enable_battery_on_pv_or_grid": False,
        "enable_bms_read": True,
        "enable_buzzer": False,
        "enable_charge": True,
        "enable_frequency_derating": True,
        "enable_g100_limit_switch": False,
        "enable_inverter_parallel_mode": None,
        "enable_low_voltage_fault_ride_through": False,
        "enable_spi": True,
        "enable_ups_mode": False,
        "smart_load_slot_1": None,
        "smart_load_slot_2": None,
        "smart_load_slot_3": None,
        "smart_load_slot_4": None,
        "smart_load_slot_5": None,
        "smart_load_slot_6": None,
        "smart_load_slot_7": None,
        "smart_load_slot_8": None,
        "smart_load_slot_9": None,
        "smart_load_slot_10": None,
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
        "frequency_load_limit_rate": 24,
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
        # 'inverter_status': 1,
        # 'island_check_continue': 0,
        # 'iso1': 0,
        # 'iso2': 0,
        # 'iso_fault_value': 0.0,
        "enable_local_command_test": False,
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
        "power_factor_function_model": PowerFactorFunctionModel.PF_1,
        # 'pv1_power_adjust': 0,
        # 'pv1_voltage_adjust': 0,
        # 'pv2_power_adjust': 0,
        # 'pv2_voltage_adjust': 0,
        "pv_power_setting": None,
        "v_pv_start": 150.0,
        # 'real_v_f_value': 0.0,
        # 'reboot': 0,
        # 'remote_bms_restart': False,
        "restart_delay_time": 30,
        # 'safety_time_limit': 0.0,
        # 'safety_v_f_limit': 0.0,
        "start_countdown_timer": 30,
        "start_system_auto_test": False,
        # 'system_mode': 1,
        # 'temp_battery': 16.0,
        # 'temp_charger': 24.1,
        # 'temp_fault_value': 0.0,
        # 'temp_inverter_heatsink': 24.4,
        # 'test_treat_time': 0,
        # 'test_treat_value': 0.0,
        # 'test_value': 0.0,
        "threephase_abc": 0,
        "threephase_balance_1": 0,
        "threephase_balance_2": 0,
        "threephase_balance_3": 0,
        "threephase_balance_mode": 0,
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
        # 'v_eps_backup': 235.10,
        # 'v_highbrigh_bus': 2829,
        # 'v_n_bus': 0.0,
        # 'v_p_bus': 383.0,
        # 'v_pv1': 357.0,
        # 'v_pv2': 369.70,
        # 'v_pv_fault_value': 0.0,
        # 'work_time_total_hours': 385,
        "active_power_rate": 100,
        "arm_firmware_version": 449,
        "battery_max_power": 2600,
        "battery_calibration_stage": BatteryCalibrationStage.OFF,
        "battery_capacity_ah": 160,
        "battery_capacity_kwh": 8.192,
        "battery_power_mode": BatteryPowerMode.SELF_CONSUMPTION,
        "battery_type": BatteryType.LITHIUM,
        "bms_firmware_version": 101,
        "charge_slot_2": TimeSlot(datetime.time(0, 0), datetime.time(0, 4)),
        "charge_soc": 0,
        "device_type_code": "2001",
        "discharge_slot_1": TimeSlot.from_repr(0, 0),
        "discharge_slot_2": TimeSlot.from_repr(0, 0),
        "discharge_soc": 0,
        "dsp_firmware_version": 449,
        "enable_60hz_freq_mode": False,
        "enable_ammeter": True,
        "enable_auto_judge_battery_type": True,
        "enable_charge_target": False,
        "enable_discharge": False,
        "enable_drm_rj45_port": True,
        "enable_inverter": True,
        "enable_inverter_auto_restart": False,
        "enable_reversed_115_meter": False,
        "enable_reversed_418_meter": False,
        "enable_reversed_ct_clamp": True,
        "firmware_version": "D0.449-A0.449",
        "first_battery_bms_firmware_version": 3005,
        "grid_port_max_power_output": 6000,
        "meter_type": MeterType.EM115,
        "modbus_address": 0x11,
        "modbus_version": "1.40",
        "model": Model.HYBRID,
        "inverter_max_power": 5000,
        "is_ac_coupled": False,
        "module": "00030832",
        "num_mppt": 2,
        "num_phases": 1,
        "power_factor": -1.0,
        "reactive_power_rate": 0,
        "select_arm_chip": False,
        "serial_number": "SA1234G567",
        "status": Status.NORMAL,
        "v_pv1": 357.0,
        "v_pv2": 369.7,
        "v_p_bus": 383.0,
        "v_n_bus": 0.0,
        "v_ac1": 236.3,
        "e_battery_throughput": 356.5,
        "i_pv1": 0.3,
        "i_pv2": 0.3,
        "i_ac1": 2.7,
        "e_pv_total": 26.3,
        "f_ac1": 49.96,
        "charge_status": 5,
        "charge_status_label": ChargeStatus.DISCHARGING,
        "v_highbrigh_bus": 282.9,
        "pf_inverter_output_now": -0.0469,
        "e_pv1_day": 0.4,
        "p_pv1": 117,
        "e_pv2_day": 0.6,
        "p_pv2": 128,
        "e_grid_out_total": 0.9,
        "e_solar_diverter": 0.0,
        "p_grid_out_ph1": 536,
        "e_grid_out_day": 0.0,
        "e_grid_in_day": 19.8,
        "e_inverter_in_total": 188.1,
        "e_discharge_year": 0.0,
        "p_grid_out": 21,
        "p_backup": 0,
        "e_grid_in_total": 624.2,
        "e_ac_charge_today": 9.3,  # IR(35) — was mislabelled e_load_day (#174)
        # computed: e_pv_generation_today + e_grid_in_day − e_grid_out_day − e_ac_charge_today
        #         = 3.8 + 19.8 − 0.0 − 9.3
        "e_consumption_today": 14.3,
        "e_battery_charge_today_alt1": 9.1,  # IR(36)
        "e_battery_discharge_today_alt1": 3.4,  # IR(37)
        "countdown": 0,
        "fault_code": "00000000",
        "t_inverter_heatsink": 24.4,
        "p_load_demand": 515,
        "p_grid_apparent": 554,
        "e_pv_generation_today": 3.8,  # IR(44) — was mislabelled e_inverter_out_day (#174)
        "e_pv_generation_total": 172.5,
        "work_time_total_hours": 385,
        "system_mode": 1,
        "v_battery": 51.73,
        "i_battery": 6.47,
        "p_battery": 360,
        "v_ac1_output": 235.1,
        "f_ac1_output": 49.92,
        "t_charger": 24.1,
        "t_battery": 16.0,
        "charger_warning_code": 0,
        "i_grid_port": 2.57,
        "battery_soc": 68,
        "system_time": datetime.datetime(2022, 1, 11, 11, 51, 46),
        "usb_device_inserted": UsbDevice.DISK,
        "user_code": 7,
        "variable_address": 32768,
        "variable_value": 30235,
        "battery_voltage_adjust": 0.0,
        "inverter_reboot": 0,
        "enable_rtc": False,
        "inverter_errors": None,
        "inverter_fault_messages": None,
        "charge_target_soc_1": None,
        "charge_slot_2_x": None,
        "charge_target_soc_2": None,
        "charge_slot_3": None,
        "charge_target_soc_3": None,
        "charge_slot_4": None,
        "charge_target_soc_4": None,
        "charge_slot_5": None,
        "charge_target_soc_5": None,
        "charge_slot_6": None,
        "charge_target_soc_6": None,
        "charge_slot_7": None,
        "charge_target_soc_7": None,
        "charge_slot_8": None,
        "charge_target_soc_8": None,
        "charge_slot_9": None,
        "charge_target_soc_9": None,
        "charge_slot_10": None,
        "charge_target_soc_10": None,
        "discharge_target_soc_1": None,
        "discharge_target_soc_2": None,
        "discharge_slot_3": None,
        "discharge_target_soc_3": None,
        "discharge_slot_4": None,
        "discharge_target_soc_4": None,
        "discharge_slot_5": None,
        "discharge_target_soc_5": None,
        "discharge_slot_6": None,
        "discharge_target_soc_6": None,
        "discharge_slot_7": None,
        "discharge_target_soc_7": None,
        "discharge_slot_8": None,
        "discharge_target_soc_8": None,
        "discharge_slot_9": None,
        "discharge_target_soc_9": None,
        "discharge_slot_10": None,
        "discharge_target_soc_10": None,
        "export_priority": None,
        "battery_charge_limit_ac": None,
        "battery_discharge_limit_ac": None,
        "enable_eps": None,
        "battery_pause_mode": None,
        "battery_pause_slot_1": None,
        "e_battery_discharge_total_alt1": 173.0,  # IR(180)
        "e_battery_charge_total_alt1": 183.5,  # IR(181)
        "e_battery_discharge_today_alt2": 3.4,  # IR(182)
        "e_battery_charge_today_alt2": 9.1,  # IR(183)
        "p_combined_generation": None,
    }


def test_model_missing_guard():
    """Unknown single-char or non-string values raise ValueError rather than recursing."""
    import pytest

    with pytest.raises(ValueError):
        Model("9")  # single char, not a member
    with pytest.raises(ValueError):
        Model("9999")  # multi-char, first char also not a member


def test_model_coarse_lookup():
    """Model(dtc) returns the coarse family regardless of specific variant."""
    assert Model("2") is Model.HYBRID
    assert Model("2001") is Model.HYBRID
    assert Model("2101") is Model.HYBRID
    assert Model("4001") is Model.HYBRID_3PH
    assert Model("4101") is Model.HYBRID_3PH  # AIO_COMMERCIAL falls back to HYBRID_3PH family
    assert Model("5101") is Model.EMS  # EMS_COMMERCIAL falls back to EMS family
    assert Model("8101") is Model.ALL_IN_ONE  # HYBRID_HV_GEN3 falls back to ALL_IN_ONE family
    assert Model("8201") is Model.ALL_IN_ONE
    assert Model("8301") is Model.ALL_IN_ONE


def test_model_specific_variants():
    """Specific variants are reachable by direct construction."""
    assert Model("20g1") is Model.HYBRID_GEN1
    assert Model("20g2") is Model.HYBRID_GEN2
    assert Model("20g3") is Model.HYBRID_GEN3
    assert Model("21") is Model.POLAR
    assert Model("41") is Model.AIO_COMMERCIAL
    assert Model("51") is Model.EMS_COMMERCIAL
    assert Model("81") is Model.HYBRID_HV_GEN3
    assert Model("82") is Model.ALL_IN_ONE_HYBRID
    assert Model("83") is Model.HYBRID_GEN4


@pytest.mark.parametrize(
    "raw_dtc, arm_fw, expected",
    [
        # DTC "20xx" — generation depends on ARM firmware century
        (0x2001, 250, Model.HYBRID_GEN1),  # century 2 → GEN1
        (0x2001, 199, Model.HYBRID_GEN1),  # century 1 → GEN1
        (0x2001, 350, Model.HYBRID_GEN3),  # century 3 → GEN3
        (0x2001, 399, Model.HYBRID_GEN3),  # century 3 → GEN3
        (0x2001, 850, Model.HYBRID_GEN2),  # century 8 → GEN2
        (0x2001, 950, Model.HYBRID_GEN2),  # century 9 → GEN2
        (0x2003, 310, Model.HYBRID_GEN3),  # different power rating, same gen
        # Specific two-digit prefixes
        (0x2101, 100, Model.POLAR),
        (0x4001, 100, Model.HYBRID_3PH),
        (0x4101, 100, Model.AIO_COMMERCIAL),
        (0x5001, 100, Model.EMS),
        (0x5101, 100, Model.EMS_COMMERCIAL),
        (0x6001, 100, Model.AC_3PH),
        (0x7001, 100, Model.GATEWAY),
        (0x8001, 100, Model.ALL_IN_ONE),
        (0x8101, 100, Model.HYBRID_HV_GEN3),
        (0x8201, 100, Model.ALL_IN_ONE_HYBRID),
        (0x8301, 100, Model.HYBRID_GEN4),
    ],
)
def test_resolve_model(raw_dtc, arm_fw, expected):
    assert resolve_model(raw_dtc, arm_fw) is expected


@pytest.mark.parametrize(
    "model,expected",
    [
        # 0x11 for every model since the 0x31 read-alias retirement (#189);
        # AC and HYBRID_GEN1 hardware still answers at the 0x31 facade too
        (Model.AC, 0x11),
        (Model.HYBRID_GEN1, 0x11),
        (Model.HYBRID, 0x11),
        (Model.HYBRID_GEN2, 0x11),
        (Model.HYBRID_GEN3, 0x11),
        (Model.HYBRID_GEN4, 0x11),
        (Model.HYBRID_3PH, 0x11),
        (Model.AC_3PH, 0x11),
        (Model.EMS, 0x11),
        (Model.EMS_COMMERCIAL, 0x11),
        (Model.GATEWAY, 0x11),
        (Model.ALL_IN_ONE, 0x11),
        (Model.ALL_IN_ONE_HYBRID, 0x11),
        (Model.HYBRID_HV_GEN3, 0x11),
    ],
)
def test_inverter_address_for(model, expected):
    assert inverter_address_for(model) == expected


@pytest.mark.parametrize(
    "model,expected",
    [
        (Model.ALL_IN_ONE, 307.0),
        (Model.HYBRID_3PH, 76.8),
        (Model.AC_3PH, 76.8),
        (Model.HYBRID, 51.2),
    ],
)
def test_model_system_battery_voltage(model, expected):
    assert model.system_battery_voltage == expected


def test_single_phase_inverter_slot_map():
    from givenergy_modbus.model.inverter import EXTENDED_SLOTS, SINGLE_PHASE_SLOTS
    from givenergy_modbus.model.register import HR

    # Default (no DTC set) → legacy 2-slot map
    assert SinglePhaseInverter.from_register_cache(RegisterCache()).slot_map is SINGLE_PHASE_SLOTS

    # HYBRID_GEN1 / GEN2 → legacy
    for dtc_hex in (0x2001, 0x2002):
        cache = RegisterCache({HR(0): dtc_hex, HR(21): 100})
        assert SinglePhaseInverter.from_register_cache(cache).slot_map is SINGLE_PHASE_SLOTS

    # HYBRID_GEN3 with fw ≤ 302 → legacy
    cache = RegisterCache({HR(0): 0x2003, HR(21): 302})
    assert SinglePhaseInverter.from_register_cache(cache).slot_map is SINGLE_PHASE_SLOTS

    # HYBRID_GEN3 with fw > 302 → extended
    cache = RegisterCache({HR(0): 0x2003, HR(21): 303})
    assert SinglePhaseInverter.from_register_cache(cache).slot_map is EXTENDED_SLOTS

    # ALL_IN_ONE (80xx), HYBRID_GEN4 (83xx), HYBRID_HV_GEN3 (81xx) → extended
    for dtc_hex in (0x8001, 0x8301, 0x8101):
        cache = RegisterCache({HR(0): dtc_hex, HR(21): 100})
        assert SinglePhaseInverter.from_register_cache(cache).slot_map is EXTENDED_SLOTS


def test_single_phase_inverter_p_pv_and_e_pv_day():
    from givenergy_modbus.model.register import IR

    cache = RegisterCache({IR(18): 1000, IR(20): 500, IR(17): 12, IR(19): 8})
    inv = SinglePhaseInverter.from_register_cache(cache)
    assert inv.p_pv() == 1500  # type: ignore[attr-defined]
    assert inv.e_pv_day() == 2.0  # type: ignore[attr-defined]


def _cache(**entries):
    from givenergy_modbus.model.register import IR

    addr_lut = {"e_pv1_day": IR(17), "p_pv1": IR(18), "e_pv2_day": IR(19), "p_pv2": IR(20)}
    return RegisterCache({addr_lut[k]: v for k, v in entries.items()})


@pytest.mark.parametrize(
    "cache",
    [
        # p_pv2 missing
        _cache(p_pv1=1000, e_pv1_day=12, e_pv2_day=8),
        # p_pv1 missing
        _cache(p_pv2=500, e_pv1_day=12, e_pv2_day=8),
        # both missing
        _cache(e_pv1_day=12, e_pv2_day=8),
        # p_pv1 out of bounds → None after #82 bounds enforcement
        _cache(p_pv1=60000, p_pv2=500, e_pv1_day=12, e_pv2_day=8),
        # p_pv2 out of bounds → None
        _cache(p_pv1=1000, p_pv2=60000, e_pv1_day=12, e_pv2_day=8),
    ],
)
def test_p_pv_returns_none_when_either_input_unavailable(cache):
    inv = SinglePhaseInverter.from_register_cache(cache)
    assert inv.p_pv() is None  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "cache",
    [
        # e_pv2_day missing
        _cache(e_pv1_day=12, p_pv1=1000, p_pv2=500),
        # e_pv1_day missing
        _cache(e_pv2_day=8, p_pv1=1000, p_pv2=500),
        # both missing
        _cache(p_pv1=1000, p_pv2=500),
    ],
)
def test_e_pv_day_returns_none_when_either_input_unavailable(cache):
    inv = SinglePhaseInverter.from_register_cache(cache)
    assert inv.e_pv_day() is None  # type: ignore[attr-defined]


def test_inverter_max_power():
    from givenergy_modbus.model.inverter import _DTC_RATED_POWER
    from givenergy_modbus.model.register import HR

    # Known DTC → correct wattage via computed field
    cache = RegisterCache({HR(0): 0x2001})
    assert SinglePhaseInverter.from_register_cache(cache).inverter_max_power == 5000  # type: ignore[attr-defined]
    # DTC not in rated-power LUT → None
    cache = RegisterCache({HR(0): 0x2009})
    assert SinglePhaseInverter.from_register_cache(cache).inverter_max_power is None  # type: ignore[attr-defined]
    # No DTC at all → None
    cache = RegisterCache()
    assert SinglePhaseInverter.from_register_cache(cache).inverter_max_power is None  # type: ignore[attr-defined]
    # LUT covers 3-phase and AIO variants
    assert _DTC_RATED_POWER.get("4003") == 10000
    assert _DTC_RATED_POWER.get("8204") == 12000


def test_inverter_deprecation_alias():
    import givenergy_modbus.model.inverter as inv_module

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        cls = inv_module.Inverter  # type: ignore[attr-defined]
    assert cls is SinglePhaseInverter
    assert len(w) == 1
    assert issubclass(w[0].category, DeprecationWarning)
    assert "SinglePhaseInverter" in str(w[0].message)


def test_inverter_getattr_unknown():
    import givenergy_modbus.model.inverter as inv_module

    with pytest.raises(AttributeError, match="has no attribute"):
        _ = inv_module.NonExistentAttribute  # type: ignore[attr-defined]


def test_work_time_total_hours_rename_and_deprecated_alias():
    """The field is exposed as work_time_total_hours; work_time_total is a deprecated alias."""
    from givenergy_modbus.model.register import IR

    cache = RegisterCache({IR(47): 0, IR(48): 213})
    inv = SinglePhaseInverter.from_register_cache(cache)

    # New name returns the value cleanly with no warning.
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        assert inv.work_time_total_hours == 213  # type: ignore[attr-defined]
    assert [x for x in w if issubclass(x.category, DeprecationWarning)] == []

    # Deprecated alias still works, warns, and returns the same value.
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        assert inv.work_time_total == 213  # type: ignore[attr-defined]
    deprecations = [x for x in w if issubclass(x.category, DeprecationWarning)]
    assert len(deprecations) == 1
    assert "work_time_total_hours" in str(deprecations[0].message)

    # Dump output uses the new name only — the alias must not duplicate the field.
    dumped = inv.model_dump()
    assert "work_time_total_hours" in dumped
    assert "work_time_total" not in dumped


def test_enable_inverter_parallel_mode_rename_and_deprecated_alias():
    """HR(199) is now enable_inverter_parallel_mode; enable_standard_self_consumption_logic is a deprecated alias."""
    from givenergy_modbus.model.inverter_threephase import ThreePhaseInverter
    from givenergy_modbus.model.register import HR

    cache = RegisterCache({HR(199): 1})

    for cls in (SinglePhaseInverter, ThreePhaseInverter):
        inv = cls.from_register_cache(cache)

        # New name returns the value cleanly with no warning.
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            assert inv.enable_inverter_parallel_mode is True  # type: ignore[attr-defined]
        assert [x for x in w if issubclass(x.category, DeprecationWarning)] == []

        # Deprecated alias still works, warns, and returns the same value.
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            assert inv.enable_standard_self_consumption_logic is True  # type: ignore[attr-defined]
        deprecations = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(deprecations) == 1
        assert "enable_inverter_parallel_mode" in str(deprecations[0].message)

        # Dump output uses the new name only — the alias must not duplicate the field.
        dumped = inv.model_dump()
        assert "enable_inverter_parallel_mode" in dumped
        assert "enable_standard_self_consumption_logic" not in dumped


def test_e_ac_charge_today_rename_no_alias():
    """IR(35) is e_ac_charge_today (#174). The old e_load_day name was a mislabel.

    Unlike the other renames there is NO deprecated alias: e_load_day never held
    house-load, so keeping a back-compat alias would perpetuate the wrong meaning.
    """
    from givenergy_modbus.model.register import IR

    cache = RegisterCache({IR(35): 93})
    inv = SinglePhaseInverter.from_register_cache(cache)

    assert inv.e_ac_charge_today == 9.3  # type: ignore[attr-defined]
    dumped = inv.model_dump()
    assert "e_ac_charge_today" in dumped
    # The mislabel is gone entirely — no field, no alias.
    assert "e_load_day" not in dumped
    with pytest.raises(AttributeError):
        _ = inv.e_load_day  # type: ignore[attr-defined]


def test_e_pv_generation_today_rename_and_deprecated_alias():
    """IR(44) is e_pv_generation_today (#174); e_inverter_out_day is a deprecated alias.

    The two classes behave slightly differently:
    - SinglePhaseInverter: alias returns e_pv_generation_today (IR44, verified).
    - ThreePhaseInverter: alias returns e_pv_today (IR1412/3, the verified 3ph register),
      so warning and return value agree. IR44 still leaks as e_pv_generation_today via
      single-phase LUT inheritance, but the alias migration path is unambiguous.
    """
    from givenergy_modbus.model.inverter_threephase import ThreePhaseInverter
    from givenergy_modbus.model.register import IR

    # Single-phase: IR44 is the authoritative PV-generation register.
    sp_cache = RegisterCache({IR(44): 81})
    sp = SinglePhaseInverter.from_register_cache(sp_cache)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        assert sp.e_pv_generation_today == 8.1  # type: ignore[attr-defined]
    assert [x for x in w if issubclass(x.category, DeprecationWarning)] == []

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        assert sp.e_inverter_out_day == 8.1  # type: ignore[attr-defined]  # returns e_pv_generation_today
    sp_deprecations = [x for x in w if issubclass(x.category, DeprecationWarning)]
    assert len(sp_deprecations) == 1
    assert "e_pv_generation_today" in str(sp_deprecations[0].message)

    sp_dumped = sp.model_dump()
    assert "e_pv_generation_today" in sp_dumped
    assert "e_inverter_out_day" not in sp_dumped

    # Three-phase: IR44 leaks as e_pv_generation_today (unverified); the alias
    # returns e_pv_today (IR1412/3) so the migration path is unambiguous.
    # Seed both IR44 and IR1412/3 with the same decoded value (8.1) so the
    # alias-vs-field comparison is meaningful even on this synthetic cache.
    tp_cache = RegisterCache({IR(44): 81, IR(1412): 0, IR(1413): 81})
    tp = ThreePhaseInverter.from_register_cache(tp_cache)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        assert tp.e_pv_generation_today == 8.1  # type: ignore[attr-defined]  # inherited IR44
    assert [x for x in w if issubclass(x.category, DeprecationWarning)] == []

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        assert tp.e_inverter_out_day == 8.1  # type: ignore[attr-defined]  # returns e_pv_today
    tp_deprecations = [x for x in w if issubclass(x.category, DeprecationWarning)]
    assert len(tp_deprecations) == 1
    assert "e_pv_today" in str(tp_deprecations[0].message)

    tp_dumped = tp.model_dump()
    assert "e_pv_generation_today" in tp_dumped
    assert "e_inverter_out_day" not in tp_dumped


def test_e_pv_generation_total_rename_and_deprecated_alias():
    """IR(45/46) is e_pv_generation_total (#174); e_inverter_out_total is a deprecated alias.

    Unlike the day field, three-phase is NOT symmetric here:
    - SinglePhaseInverter: IR(45/46) renamed to e_pv_generation_total; e_inverter_out_total
      becomes a deprecated @property → e_pv_generation_total (not in model_dump()).
    - ThreePhaseInverter: keeps its OWN native e_inverter_out_total (IR1362/3), a genuine,
      distinct register from its PV total — so it stays a real field with no deprecation.
      The single-phase IR(45/46) also leaks in as e_pv_generation_total (unverified on 3ph),
      consistent with the e_pv_generation_today leak; left for #48.
    """
    from givenergy_modbus.model.inverter_threephase import ThreePhaseInverter
    from givenergy_modbus.model.register import IR

    # Single-phase: IR(45/46) is the authoritative PV-generation-total register (uint32, deci).
    sp_cache = RegisterCache({IR(45): 0, IR(46): 930})
    sp = SinglePhaseInverter.from_register_cache(sp_cache)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        assert sp.e_pv_generation_total == 93.0  # type: ignore[attr-defined]
    assert [x for x in w if issubclass(x.category, DeprecationWarning)] == []

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        assert sp.e_inverter_out_total == 93.0  # type: ignore[attr-defined]  # returns e_pv_generation_total
    sp_deprecations = [x for x in w if issubclass(x.category, DeprecationWarning)]
    assert len(sp_deprecations) == 1
    assert "e_pv_generation_total" in str(sp_deprecations[0].message)

    sp_dumped = sp.model_dump()
    assert "e_pv_generation_total" in sp_dumped
    assert "e_inverter_out_total" not in sp_dumped

    # Three-phase: e_inverter_out_total is a genuine native register (IR1362/3) — it stays
    # a real, non-deprecated field. The single-phase IR(45/46) leaks in as
    # e_pv_generation_total (unverified on 3ph).
    tp_cache = RegisterCache({IR(45): 0, IR(46): 930, IR(1362): 0, IR(1363): 1725})
    tp = ThreePhaseInverter.from_register_cache(tp_cache)

    # Native 3ph e_inverter_out_total reads IR1362/3 with no deprecation warning.
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        assert tp.e_inverter_out_total == 172.5  # type: ignore[attr-defined]
    assert [x for x in w if issubclass(x.category, DeprecationWarning)] == []

    tp_dumped = tp.model_dump()
    # Both keys are present on 3ph: the native total field and the leaked single-phase IR(45/46).
    assert tp_dumped["e_inverter_out_total"] == 172.5  # IR1362/3, native
    assert tp_dumped["e_pv_generation_total"] == 93.0  # IR45/46, leaked (unverified on 3ph)


def test_e_consumption_today_computed_formula():
    """Single-phase consumption is computed (#174), not a register.

    Formula recovered by sentinel cross-correlation against the GE app's
    Energy-today screen:
        consumption = pv_generation + grid_import − grid_export − ac_charge
    """
    from givenergy_modbus.model.register import IR

    # IR(44)=8.1 PV gen, IR(26)=20.9 grid import, IR(25)=0.0 grid export, IR(35)=9.3 AC charge
    cache = RegisterCache({IR(44): 81, IR(26): 209, IR(25): 0, IR(35): 93})
    inv = SinglePhaseInverter.from_register_cache(cache)

    assert inv.e_consumption_today == 8.1 + 20.9 - 0.0 - 9.3  # type: ignore[attr-defined]
    assert "e_consumption_today" in inv.model_dump()

    # Missing any input → None (no partial guess).
    partial = SinglePhaseInverter.from_register_cache(RegisterCache({IR(26): 209, IR(25): 0, IR(35): 93}))
    assert partial.e_consumption_today is None  # type: ignore[attr-defined]


def test_three_phase_has_no_computed_consumption_and_native_ac_charge():
    """Three-phase has a native e_ac_charge_today register and no computed consumption (#174).

    e_consumption_today is a SinglePhaseInverter computed_field, NOT in the register
    LUT, so it does not leak onto ThreePhaseInverter — which carries its own
    e_load_today register (IR1396/7). The native three-phase e_ac_charge_today
    (IR1376/7) overrides the single-phase IR(35) entry inherited via the LUT merge.
    """
    from givenergy_modbus.model.inverter_threephase import ThreePhaseInverter
    from givenergy_modbus.model.register import IR

    # Native three-phase e_ac_charge_today = IR(1376/1377) uint32 deci = 35.0;
    # the inherited single-phase IR(35) is seeded to a different value to prove the
    # native override wins (not the leaked single-phase register).
    cache = RegisterCache({IR(1376): 0, IR(1377): 350, IR(35): 99})
    tp = ThreePhaseInverter.from_register_cache(cache)

    assert tp.e_ac_charge_today == 35.0  # type: ignore[attr-defined]  # native IR1376/7, not 9.9
    dumped = tp.model_dump()
    assert "e_consumption_today" not in dumped  # computed field is single-phase only
    assert "e_load_day" not in dumped  # the single-phase mislabel does not leak


def test_battery_energy_facade_routes_by_model():
    """Battery-energy facade routes each metric to the model's declared altN (#76).

    Which register a firmware populates is a static property of the model, declared in
    _BATTERY_ENERGY_SOURCE — not inferred from live values (the #119 / #150-Codex
    lesson). The declared source is returned verbatim, including a legitimate 0.0; an
    undeclared model or metric returns None, with no value inspection and no
    cross-source fallback. The specific model is resolved via DTC+arm_fw like slot_map,
    so GEN1 is distinguished from the coarse HYBRID family.
    """
    from givenergy_modbus.model.register import HR, IR

    # HYBRID_GEN1 (dtc 0x2001, arm 449): today→alt2 (IR182/183), total→alt1 (IR180/181).
    # alt1 and alt2 daily are set to DIFFERENT values, so routing (not fallback) is what
    # selects alt2 — a value-based picker could not tell them apart.
    gen1 = SinglePhaseInverter.from_register_cache(
        RegisterCache(
            {
                HR(0): 0x2001,
                HR(21): 449,
                IR(36): 110,  # charge today alt1 — ignored on GEN1
                IR(183): 220,  # charge today alt2 — authoritative
                IR(37): 330,  # discharge today alt1 — ignored
                IR(182): 440,  # discharge today alt2 — authoritative
                IR(181): 1000,  # charge total alt1 — authoritative
                IR(180): 2000,  # discharge total alt1 — authoritative
            }
        )
    )
    assert gen1.e_battery_charge_today == 22.0  # alt2, not alt1's 11.0
    assert gen1.e_battery_discharge_today == 44.0  # alt2, not alt1's 33.0
    assert gen1.e_battery_charge_total == 100.0  # alt1
    assert gen1.e_battery_discharge_total == 200.0  # alt1

    # GEN1 declared source read as 0.0 is returned verbatim — NOT overridden by a
    # non-zero in a different source (the Codex stale-zero case, now structurally
    # impossible: alt2 is 0.0, alt1 is non-zero, the facade still returns 0.0).
    gen1_zero = SinglePhaseInverter.from_register_cache(
        RegisterCache({HR(0): 0x2001, HR(21): 449, IR(183): 0, IR(36): 910, IR(182): 0, IR(37): 870})
    )
    assert gen1_zero.e_battery_charge_today == 0.0
    assert gen1_zero.e_battery_discharge_today == 0.0

    # AC (dtc 0x3001): today→alt1 (IR36/37); total is undeclared → None even though
    # IR180/181 read non-zero (their IR totals are a real 0 on hardware; where the
    # lifetime total lives is unknown, so None beats a misleading value).
    ac = SinglePhaseInverter.from_register_cache(
        RegisterCache({HR(0): 0x3001, HR(21): 282, IR(36): 120, IR(37): 340, IR(181): 5000, IR(180): 6000})
    )
    assert ac.e_battery_charge_today == 12.0  # alt1
    assert ac.e_battery_discharge_today == 34.0  # alt1
    assert ac.e_battery_charge_total is None
    assert ac.e_battery_discharge_total is None

    # ALL_IN_ONE (dtc 0x8001): same routing as AC (today→alt1, total undeclared).
    aio = SinglePhaseInverter.from_register_cache(RegisterCache({HR(0): 0x8001, HR(21): 612, IR(36): 150, IR(37): 250}))
    assert aio.e_battery_charge_today == 15.0
    assert aio.e_battery_discharge_today == 25.0
    assert aio.e_battery_charge_total is None
    assert aio.e_battery_discharge_total is None

    # Undeclared model (HYBRID_GEN3, fw>302) → None for all four despite populated regs.
    gen3 = SinglePhaseInverter.from_register_cache(
        RegisterCache(
            {
                HR(0): 0x2003,
                HR(21): 303,
                IR(36): 111,
                IR(37): 222,
                IR(180): 333,
                IR(181): 444,
                IR(182): 555,
                IR(183): 666,
            }
        )
    )
    assert gen3.e_battery_charge_today is None
    assert gen3.e_battery_discharge_today is None
    assert gen3.e_battery_charge_total is None
    assert gen3.e_battery_discharge_total is None

    # No model at all (DTC/arm unset) → None: can't resolve a specific model to route by.
    bare = SinglePhaseInverter.from_register_cache(RegisterCache({IR(36): 110, IR(183): 220}))
    assert bare.e_battery_charge_today is None
    assert bare.e_battery_charge_total is None


def test_ac_coupled_models_constant():
    """AC_COUPLED_MODELS is exactly the two AC coarse families (no DC-coupled models)."""
    assert AC_COUPLED_MODELS == frozenset({Model.AC, Model.AC_3PH})


def test_single_phase_inverter_is_ac_coupled():
    """is_ac_coupled is True only for AC-coupled models, via coarse-family resolution.

    An AC DTC (0x3001) resolves to Model.AC, so the computed field reads True; DC-coupled
    families and an unread model read False.
    """
    from givenergy_modbus.model.register import HR

    # AC single-phase (dtc prefix 3) → True
    ac = SinglePhaseInverter.from_register_cache(RegisterCache({HR(0): 0x3001}))
    assert ac.model is Model.AC
    assert ac.is_ac_coupled is True

    # DC-coupled families → False
    for dtc in (0x2001, 0x2003, 0x8001, 0x5001):  # HYBRID, HYBRID(gen3), ALL_IN_ONE, EMS
        inv = SinglePhaseInverter.from_register_cache(RegisterCache({HR(0): dtc}))
        assert inv.is_ac_coupled is False, f"{inv.model} should not be AC-coupled"

    # Unknown model (DTC unread) → False, and the field is in the dump.
    bare = SinglePhaseInverter.from_register_cache(RegisterCache())
    assert bare.model is None
    assert bare.is_ac_coupled is False
    assert bare.model_dump()["is_ac_coupled"] is False


def test_pf_converter_inverter():
    """IR(16) and HR(52) decode with the offset-unsigned formula (raw/10,000 − 1) (#209).

    Verifies the three empirical clusters from the issue's 24h live data: the normal
    export cluster (~10,000), the heavy-charge dip (~1,700), and the reactive burst
    (~19,000). Under the simpler ÷10,000 formula the >10,000 readings would be
    impossible (>1.0), confirming the offset is necessary.
    """
    from givenergy_modbus.model.register import IR

    unity = SinglePhaseInverter.from_register_cache(RegisterCache({IR(16): 10_000}))
    assert unity.pf_inverter_output_now == 0.0

    charging_dip = SinglePhaseInverter.from_register_cache(RegisterCache({IR(16): 1_700}))
    assert charging_dip.pf_inverter_output_now == -0.83

    reactive_burst = SinglePhaseInverter.from_register_cache(RegisterCache({IR(16): 19_000}))
    assert reactive_burst.pf_inverter_output_now == 0.9

    # Fixture values from the issue
    assert round(4790 / 10_000 - 1, 4) == -0.521
    assert round(9531 / 10_000 - 1, 4) == -0.0469
    assert round(8160 / 10_000 - 1, 4) == -0.184


def test_charge_status_enum():
    """ChargeStatus decodes all known codes and returns None for unknowns (#222)."""
    from givenergy_modbus.model.register import IR

    idle = SinglePhaseInverter.from_register_cache(RegisterCache({IR(14): 0}))
    assert idle.charge_status == 0
    assert idle.charge_status_label is ChargeStatus.IDLE

    charging = SinglePhaseInverter.from_register_cache(RegisterCache({IR(14): 2}))
    assert charging.charge_status_label is ChargeStatus.CHARGING

    finishing = SinglePhaseInverter.from_register_cache(RegisterCache({IR(14): 3}))
    assert finishing.charge_status_label is ChargeStatus.FINISHING

    discharging = SinglePhaseInverter.from_register_cache(RegisterCache({IR(14): 5}))
    assert discharging.charge_status_label is ChargeStatus.DISCHARGING

    unknown = SinglePhaseInverter.from_register_cache(RegisterCache({IR(14): 99}))
    assert unknown.charge_status == 99
    assert unknown.charge_status_label is None
