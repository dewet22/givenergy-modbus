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
            "enable_plant_mode": None,
            "plant_role": None,
            "plant_meters": None,
            "overfrequency_load_drop_recovery_delay": None,
            "mppt_operating_mode": None,
            "connection_loading_slope": None,
            "eps_nominal_voltage": None,
            "underfrequency_add_load_delay": None,
            "en50549_zero_current_lower_voltage_limit": None,
            "en50549_zero_current_upper_voltage_limit": None,
            "overfrequency_derating_start_point": None,
            "enable_tariff_pricing_battery_logic": None,
            "import_price_battery_discharge_threshold": None,
            "import_price_battery_charge_threshold": None,
            "export_price_battery_discharge_threshold": None,
            "underfrequency_derating_start_point": None,
            "underfrequency_loading_slope": None,
            "overfrequency_derating_stop_point": None,
            "enable_bms_ocv_calibration": None,
            "gateway_power_off_setting": None,
            "force_off_grid": None,
            "enable_micro_grid": None,
            "enable_ev_charger": None,
            "ev_charger_import_limit": None,
            "ev_charger_reconnection_wait_time": None,
            "ev_charger_soc_limit": None,
            "enable_fan": None,
            "fan_speed": None,
            "enable_gateway": None,
            "bms_communication_mode": None,
            "n_pe_relay_toggle": None,
            "afci_setting": None,
            "enable_generator": None,
            "generator_start_soc": None,
            "generator_stop_soc": None,
            "generator_charge_power": None,
            "disable_leds": None,
            "lcd_screen_idle_timeout": None,
            "lead_acid_battery_calibration_upper_limit": None,
            "lead_acid_battery_calibration_lower_limit": None,
            "inverter_operating_mode": None,
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
            "e_self_consumption_today": None,
            "e_self_consumption_total": None,
            "e_pv_direct_today": None,
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
            "charger_warning_messages": None,
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
            "iso_protection_1": None,
            "iso_protection_2": None,
            "gfci_protection_value_1": None,
            "gfci_protection_time_1": None,
            "gfci_protection_value_2": None,
            "gfci_protection_time_2": None,
            "dci_protection_value_1": None,
            "dci_protection_time_1": None,
            "dci_protection_value_2": None,
            "dci_protection_time_2": None,
            "string_1_voltage_adjustment": None,
            "string_2_voltage_adjustment": None,
            "grid_import_limit": None,
            "grid_import_limit_enabled": None,
            "enable_lora": None,
            "enable_battery_self_heating": None,
            "string_1_power_adjustment": None,
            "string_2_power_adjustment": None,
            "power_factor_cmd_memory_state": None,
            "power_factor_point_1_load_percent": None,
            "power_factor_point_1_power_factor": None,
            "power_factor_point_2_load_percent": None,
            "power_factor_point_2_power_factor": None,
            "power_factor_point_3_load_percent": None,
            "power_factor_point_3_power_factor": None,
            "power_factor_point_4_load_percent": None,
            "power_factor_point_4_power_factor": None,
            "cei021_v1s_q": None,
            "cei021_v2s_q": None,
            "cei021_v1l_q": None,
            "cei021_v2l_q": None,
            "cei021_lock_in_active_power": None,
            "cei021_lock_out_active_power": None,
            "cei021_lock_in_grid_voltage": None,
            "cei021_lock_out_grid_voltage": None,
            "lvfrt_reactive_rate": None,
            "lvfrt_low_fault_value_1": None,
            "lvfrt_low_fault_time_1": None,
            "lvfrt_low_fault_value_2": None,
            "lvfrt_low_fault_time_2": None,
            "lvfrt_low_fault_value_3": None,
            "lvfrt_low_fault_time_3": None,
            "lvfrt_low_fault_value_4": None,
            "lvfrt_low_fault_time_4": None,
            "lvfrt_high_fault_value_1": None,
            "lvfrt_high_fault_time_1": None,
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
            "v_ac_low_limit_trip": None,
            "v_ac_high_limit_trip": None,
            "f_ac_low_limit_trip": None,
            "f_ac_high_limit_trip": None,
            "t_ac_low_voltage_trip": None,
            "t_ac_high_voltage_trip": None,
            "t_ac_low_freq_trip": None,
            "t_ac_high_freq_trip": None,
            "v_ac_low_limit_reconnect": None,
            "v_ac_high_limit_reconnect": None,
            "f_ac_low_limit_reconnect": None,
            "f_ac_high_limit_reconnect": None,
            "t_ac_low_voltage_reconnect": None,
            "t_ac_high_voltage_reconnect": None,
            "t_ac_low_freq_reconnect": None,
            "t_ac_high_freq_reconnect": None,
            "v_ac_low_limit_grid": None,
            "v_ac_high_limit_grid": None,
            "f_ac_low_limit_grid": None,
            "f_ac_high_limit_grid": None,
            "v_ac_10min_protect": None,
            "battery_nominal_power": None,
            "battery_nominal_current": None,
            "battery_max_charge_pct": None,
            "hv_cabinet_count": None,
            "hv_racks_per_cabinet": None,
            "hv_batteries_per_rack": None,
            "hv_cells_per_battery": None,
            "hv_total_cells": None,
            "hv_temp_sensors_per_battery": None,
            "hv_total_temp_sensors": None,
            "hv_max_pcs_power": None,
            "hv_max_charge_voltage": None,
            "hv_min_discharge_voltage": None,
            "hv_max_charge_current": None,
            "hv_parallel_count": None,
            "peak_shaving_export_limit_enabled": None,
            "peak_shaving_export_limit": None,
            "peak_shaving_enabled": None,
            "peak_shaving_threshold": None,
            "peak_shaving_import_limit_enabled": None,
            "peak_shaving_import_limit": None,
            "peak_shaving_power": None,
            "valley_filling_power": None,
            "p_combined_generation": None,
            "grid_import_power": None,
            "grid_export_power": None,
            "battery_charge_power": None,
            "battery_discharge_power": None,
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
        "enable_plant_mode": None,
        "plant_role": None,
        "plant_meters": None,
        "overfrequency_load_drop_recovery_delay": None,
        "mppt_operating_mode": None,
        "connection_loading_slope": None,
        "eps_nominal_voltage": None,
        "underfrequency_add_load_delay": None,
        "en50549_zero_current_lower_voltage_limit": None,
        "en50549_zero_current_upper_voltage_limit": None,
        "overfrequency_derating_start_point": None,
        "enable_tariff_pricing_battery_logic": None,
        "import_price_battery_discharge_threshold": None,
        "import_price_battery_charge_threshold": None,
        "export_price_battery_discharge_threshold": None,
        "underfrequency_derating_start_point": None,
        "underfrequency_loading_slope": None,
        "overfrequency_derating_stop_point": None,
        "enable_bms_ocv_calibration": None,
        "gateway_power_off_setting": None,
        "force_off_grid": None,
        "enable_micro_grid": None,
        "enable_ev_charger": None,
        "ev_charger_import_limit": None,
        "ev_charger_reconnection_wait_time": None,
        "ev_charger_soc_limit": None,
        "enable_fan": None,
        "fan_speed": None,
        "enable_gateway": None,
        "bms_communication_mode": None,
        "n_pe_relay_toggle": None,
        "afci_setting": None,
        "enable_generator": None,
        "generator_start_soc": None,
        "generator_stop_soc": None,
        "generator_charge_power": None,
        "disable_leds": None,
        "lcd_screen_idle_timeout": None,
        "lead_acid_battery_calibration_upper_limit": None,
        "lead_acid_battery_calibration_lower_limit": None,
        "inverter_operating_mode": None,
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
        # computed: max(0, e_pv_generation_today − e_grid_out_day) = max(0, 8.1 − 0.0)
        "e_self_consumption_today": 8.1,
        # computed: max(0, e_pv_generation_total − e_grid_out_total) = max(0, 93.0 − 0.6)
        "e_self_consumption_total": 92.4,
        # computed: max(0, (pv − grid_out) − max(0, battery_charge − ac_charge))
        #         = max(0, 8.1 − 0.0 − max(0, 9.0 − 9.3)) = 8.1 (all charge was AC → no PV-to-battery)
        "e_pv_direct_today": 8.1,
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
        "charger_warning_messages": [],
        "i_grid_port": 2.92,
        "battery_soc": 4,
        "system_time": datetime.datetime(2022, 1, 1, 23, 57, 19),
        "usb_device_inserted": UsbDevice.DISK,
        "user_code": 7,
        "variable_address": 32768,
        "variable_value": 30235,
        "iso_protection_1": 0,
        "iso_protection_2": 0,
        "gfci_protection_value_1": 0,
        "gfci_protection_time_1": 0,
        "gfci_protection_value_2": 0,
        "gfci_protection_time_2": 0,
        "dci_protection_value_1": 0,
        "dci_protection_time_1": 0,
        "dci_protection_value_2": 0,
        "dci_protection_time_2": 0,
        "string_1_voltage_adjustment": 0,
        "string_2_voltage_adjustment": 0,
        "grid_import_limit": 0,
        "grid_import_limit_enabled": False,
        "enable_lora": False,
        "enable_battery_self_heating": False,
        "string_1_power_adjustment": 0,
        "string_2_power_adjustment": 0,
        "power_factor_cmd_memory_state": None,
        "power_factor_point_1_load_percent": None,
        "power_factor_point_1_power_factor": None,
        "power_factor_point_2_load_percent": None,
        "power_factor_point_2_power_factor": None,
        "power_factor_point_3_load_percent": None,
        "power_factor_point_3_power_factor": None,
        "power_factor_point_4_load_percent": None,
        "power_factor_point_4_power_factor": None,
        "cei021_v1s_q": None,
        "cei021_v2s_q": None,
        "cei021_v1l_q": None,
        "cei021_v2l_q": None,
        "cei021_lock_in_active_power": None,
        "cei021_lock_out_active_power": None,
        "cei021_lock_in_grid_voltage": None,
        "cei021_lock_out_grid_voltage": None,
        "lvfrt_reactive_rate": None,
        "lvfrt_low_fault_value_1": None,
        "lvfrt_low_fault_time_1": None,
        "lvfrt_low_fault_value_2": None,
        "lvfrt_low_fault_time_2": None,
        "lvfrt_low_fault_value_3": None,
        "lvfrt_low_fault_time_3": None,
        "lvfrt_low_fault_value_4": None,
        "lvfrt_low_fault_time_4": None,
        "lvfrt_high_fault_value_1": None,
        "lvfrt_high_fault_time_1": None,
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
        "v_ac_low_limit_trip": 184.0,
        "v_ac_high_limit_trip": 274.0,
        "f_ac_low_limit_trip": 47.0,
        "f_ac_high_limit_trip": 51.98,
        "t_ac_low_voltage_trip": 1.26,
        "t_ac_high_voltage_trip": 0.27,
        "t_ac_low_freq_trip": 0.24,
        "t_ac_high_freq_trip": 0.28,
        "v_ac_low_limit_reconnect": 184.0,
        "v_ac_high_limit_reconnect": 262.0,
        "f_ac_low_limit_reconnect": 47.45,
        "f_ac_high_limit_reconnect": 52.0,
        "t_ac_low_voltage_reconnect": 1.26,
        "t_ac_high_voltage_reconnect": 0.52,
        "t_ac_low_freq_reconnect": 0.01,
        "t_ac_high_freq_reconnect": 0.28,
        "v_ac_low_limit_grid": 175.5,
        "v_ac_high_limit_grid": 283.7,
        "f_ac_low_limit_grid": 47.0,
        "f_ac_high_limit_grid": 52.0,
        "v_ac_10min_protect": 274.0,
        "battery_nominal_power": None,
        "battery_nominal_current": None,
        "battery_max_charge_pct": None,
        "hv_cabinet_count": None,
        "hv_racks_per_cabinet": None,
        "hv_batteries_per_rack": None,
        "hv_cells_per_battery": None,
        "hv_total_cells": None,
        "hv_temp_sensors_per_battery": None,
        "hv_total_temp_sensors": None,
        "hv_max_pcs_power": None,
        "hv_max_charge_voltage": None,
        "hv_min_discharge_voltage": None,
        "hv_max_charge_current": None,
        "hv_parallel_count": None,
        "peak_shaving_export_limit_enabled": None,
        "peak_shaving_export_limit": None,
        "peak_shaving_enabled": None,
        "peak_shaving_threshold": None,
        "peak_shaving_import_limit_enabled": None,
        "peak_shaving_import_limit": None,
        "peak_shaving_power": None,
        "valley_filling_power": None,
        "p_combined_generation": None,
        "grid_import_power": 342,  # p_grid_out=-342 → importing
        "grid_export_power": 0,
        "battery_charge_power": 0,
        "battery_discharge_power": 0,
    }


def test_from_registers_actual_data(register_cache_inverter_daytime_discharging_with_solar_generation):
    """Ensure we can instantiate an SinglePhaseInverter from actual register data."""
    i = SinglePhaseInverter.from_register_cache(register_cache_inverter_daytime_discharging_with_solar_generation)
    assert i.serial_number == "SA1234G567"
    assert i.model == Model.HYBRID
    assert i.model_dump() == {
        "enable_plant_mode": None,
        "plant_role": None,
        "plant_meters": None,
        "overfrequency_load_drop_recovery_delay": None,
        "mppt_operating_mode": None,
        "connection_loading_slope": None,
        "eps_nominal_voltage": None,
        "underfrequency_add_load_delay": None,
        "en50549_zero_current_lower_voltage_limit": None,
        "en50549_zero_current_upper_voltage_limit": None,
        "overfrequency_derating_start_point": None,
        "enable_tariff_pricing_battery_logic": None,
        "import_price_battery_discharge_threshold": None,
        "import_price_battery_charge_threshold": None,
        "export_price_battery_discharge_threshold": None,
        "underfrequency_derating_start_point": None,
        "underfrequency_loading_slope": None,
        "overfrequency_derating_stop_point": None,
        "enable_bms_ocv_calibration": None,
        "gateway_power_off_setting": None,
        "force_off_grid": None,
        "enable_micro_grid": None,
        "enable_ev_charger": None,
        "ev_charger_import_limit": None,
        "ev_charger_reconnection_wait_time": None,
        "ev_charger_soc_limit": None,
        "enable_fan": None,
        "fan_speed": None,
        "enable_gateway": None,
        "bms_communication_mode": None,
        "n_pe_relay_toggle": None,
        "afci_setting": None,
        "enable_generator": None,
        "generator_start_soc": None,
        "generator_stop_soc": None,
        "generator_charge_power": None,
        "disable_leds": None,
        "lcd_screen_idle_timeout": None,
        "lead_acid_battery_calibration_upper_limit": None,
        "lead_acid_battery_calibration_lower_limit": None,
        "inverter_operating_mode": None,
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
        # computed: max(0, e_pv_generation_today − e_grid_out_day) = max(0, 3.8 − 0.0)
        "e_self_consumption_today": 3.8,
        # computed: max(0, e_pv_generation_total − e_grid_out_total) = max(0, 172.5 − 0.9)
        "e_self_consumption_total": 171.6,
        # computed: max(0, (pv − grid_out) − max(0, battery_charge − ac_charge))
        #         = max(0, 3.8 − 0.0 − max(0, 9.1 − 9.3)) = 3.8 (all charge was AC → no PV-to-battery)
        "e_pv_direct_today": 3.8,
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
        "charger_warning_messages": [],
        "i_grid_port": 2.57,
        "battery_soc": 68,
        "system_time": datetime.datetime(2022, 1, 11, 11, 51, 46),
        "usb_device_inserted": UsbDevice.DISK,
        "user_code": 7,
        "variable_address": 32768,
        "variable_value": 30235,
        "iso_protection_1": 0,
        "iso_protection_2": 0,
        "gfci_protection_value_1": 0,
        "gfci_protection_time_1": 0,
        "gfci_protection_value_2": 0,
        "gfci_protection_time_2": 0,
        "dci_protection_value_1": 0,
        "dci_protection_time_1": 0,
        "dci_protection_value_2": 0,
        "dci_protection_time_2": 0,
        "string_1_voltage_adjustment": 0,
        "string_2_voltage_adjustment": 0,
        "grid_import_limit": 0,
        "grid_import_limit_enabled": False,
        "enable_lora": False,
        "enable_battery_self_heating": False,
        "string_1_power_adjustment": 0,
        "string_2_power_adjustment": 0,
        "power_factor_cmd_memory_state": 1,
        "power_factor_point_1_load_percent": 255,
        "power_factor_point_1_power_factor": 20000,
        "power_factor_point_2_load_percent": 255,
        "power_factor_point_2_power_factor": 20000,
        "power_factor_point_3_load_percent": 255,
        "power_factor_point_3_power_factor": 20000,
        "power_factor_point_4_load_percent": 255,
        "power_factor_point_4_power_factor": 20000,
        "cei021_v1s_q": 2484,
        "cei021_v2s_q": 2530,
        "cei021_v1l_q": 2116,
        "cei021_v2l_q": 2070,
        "cei021_lock_in_active_power": 20,
        "cei021_lock_out_active_power": 5,
        "cei021_lock_in_grid_voltage": 2415,
        "cei021_lock_out_grid_voltage": 2300,
        "lvfrt_reactive_rate": 0,
        "lvfrt_low_fault_value_1": 0,
        "lvfrt_low_fault_time_1": 0,
        "lvfrt_low_fault_value_2": 0,
        "lvfrt_low_fault_time_2": 0,
        "lvfrt_low_fault_value_3": 0,
        "lvfrt_low_fault_time_3": 0,
        "lvfrt_low_fault_value_4": 0,
        "lvfrt_low_fault_time_4": 0,
        "lvfrt_high_fault_value_1": 0,
        "lvfrt_high_fault_time_1": 0,
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
        "v_ac_low_limit_trip": 184.0,
        "v_ac_high_limit_trip": 274.0,
        "f_ac_low_limit_trip": 47.0,
        "f_ac_high_limit_trip": 51.98,
        "t_ac_low_voltage_trip": 1.26,
        "t_ac_high_voltage_trip": 0.27,
        "t_ac_low_freq_trip": 0.24,
        "t_ac_high_freq_trip": 0.28,
        "v_ac_low_limit_reconnect": 184.0,
        "v_ac_high_limit_reconnect": 262.0,
        "f_ac_low_limit_reconnect": 47.45,
        "f_ac_high_limit_reconnect": 52.0,
        "t_ac_low_voltage_reconnect": 1.26,
        "t_ac_high_voltage_reconnect": 0.52,
        "t_ac_low_freq_reconnect": 0.01,
        "t_ac_high_freq_reconnect": 0.28,
        "v_ac_low_limit_grid": 175.5,
        "v_ac_high_limit_grid": 283.7,
        "f_ac_low_limit_grid": 47.0,
        "f_ac_high_limit_grid": 52.0,
        "v_ac_10min_protect": 274.0,
        "battery_nominal_power": None,
        "battery_nominal_current": None,
        "battery_max_charge_pct": None,
        "hv_cabinet_count": None,
        "hv_racks_per_cabinet": None,
        "hv_batteries_per_rack": None,
        "hv_cells_per_battery": None,
        "hv_total_cells": None,
        "hv_temp_sensors_per_battery": None,
        "hv_total_temp_sensors": None,
        "hv_max_pcs_power": None,
        "hv_max_charge_voltage": None,
        "hv_min_discharge_voltage": None,
        "hv_max_charge_current": None,
        "hv_parallel_count": None,
        "peak_shaving_export_limit_enabled": None,
        "peak_shaving_export_limit": None,
        "peak_shaving_enabled": None,
        "peak_shaving_threshold": None,
        "peak_shaving_import_limit_enabled": None,
        "peak_shaving_import_limit": None,
        "peak_shaving_power": None,
        "valley_filling_power": None,
        "p_combined_generation": None,
        "grid_import_power": 0,
        "grid_export_power": 21,  # p_grid_out=21 → exporting
        "battery_charge_power": 0,
        "battery_discharge_power": 360,  # p_battery=360 → discharging
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


@pytest.mark.parametrize(
    "pv_today, grid_out_day, pv_total, grid_out_total, expected_today, expected_total",
    [
        # Normal: PV > export → positive self-consumption
        (8.1, 0.0, 93.0, 0.6, 8.1, 92.4),
        # Clamp: export exceeds PV (battery-to-grid) → floor at 0
        (1.0, 3.0, 10.0, 15.0, 0.0, 0.0),
        # Exact zero: export equals PV
        (5.0, 5.0, 50.0, 50.0, 0.0, 0.0),
    ],
)
def test_e_self_consumption_computed_formula(
    pv_today, grid_out_day, pv_total, grid_out_total, expected_today, expected_total
):
    """Self-consumption = max(0, PV − grid_export); battery-to-grid clamps at 0.

    Both fields are @computed_field on SinglePhaseInverter; today uses IR(44) and
    IR(25), total uses IR(45/46) and IR(21/22).
    """
    from givenergy_modbus.model.register import IR

    # uint32 fields span two registers (hi word, lo word); hi=0 for small values.
    # e_grid_out_total → IR(21)=hi, IR(22)=lo; e_pv_generation_total → IR(45)=hi, IR(46)=lo.
    inv = SinglePhaseInverter.from_register_cache(
        RegisterCache(
            {
                IR(44): round(pv_today * 10),  # e_pv_generation_today (deci)
                IR(25): round(grid_out_day * 10),  # e_grid_out_day (deci)
                IR(45): 0,
                IR(46): round(pv_total * 10),  # e_pv_generation_total lo word
                IR(21): 0,
                IR(22): round(grid_out_total * 10),  # e_grid_out_total lo word
            }
        )
    )
    assert inv.e_self_consumption_today == pytest.approx(expected_today)  # type: ignore[attr-defined]
    assert inv.e_self_consumption_total == pytest.approx(expected_total)  # type: ignore[attr-defined]
    assert "e_self_consumption_today" in inv.model_dump()
    assert "e_self_consumption_total" in inv.model_dump()


def test_e_self_consumption_none_when_any_input_missing():
    """Returns None when any input register is absent — no partial guessing."""
    from givenergy_modbus.model.register import IR

    # today: missing pv → None
    inv = SinglePhaseInverter.from_register_cache(RegisterCache({IR(25): 0}))
    assert inv.e_self_consumption_today is None  # type: ignore[attr-defined]

    # today: missing grid_out → None
    inv = SinglePhaseInverter.from_register_cache(RegisterCache({IR(44): 81}))
    assert inv.e_self_consumption_today is None  # type: ignore[attr-defined]

    # total: missing pv → None
    inv = SinglePhaseInverter.from_register_cache(RegisterCache({IR(21): 0, IR(22): 6}))
    assert inv.e_self_consumption_total is None  # type: ignore[attr-defined]

    # total: missing grid_out → None
    inv = SinglePhaseInverter.from_register_cache(RegisterCache({IR(45): 0, IR(46): 930}))
    assert inv.e_self_consumption_total is None  # type: ignore[attr-defined]


def _gen1_pv_direct_cache(pv_today, grid_out_day, battery_charge, ac_charge):
    """A HYBRID_GEN1 register cache populated for the e_pv_direct_today inputs.

    GEN1 routes e_battery_charge_today → alt2 (IR183); ac_charge is IR(35).
    All energy registers are deci-scaled (0.1 kWh).
    """
    from givenergy_modbus.model.register import HR, IR

    return RegisterCache(
        {
            HR(0): 0x2001,  # HYBRID_GEN1
            HR(21): 449,
            IR(44): round(pv_today * 10),  # e_pv_generation_today
            IR(25): round(grid_out_day * 10),  # e_grid_out_day
            IR(183): round(battery_charge * 10),  # e_battery_charge_today (GEN1 alt2)
            IR(35): round(ac_charge * 10),  # e_ac_charge_today
        }
    )


@pytest.mark.parametrize(
    "pv_today, grid_out_day, battery_charge, ac_charge, expected",
    [
        # PV 10, export 1, battery_charge 7 (3 PV + 4 AC), ac_charge 4 → pv_to_batt 3 → 10−1−3 = 6
        (10.0, 1.0, 7.0, 4.0, 6.0),
        # pure-solar (no AC charge): pv_to_batt = battery_charge → 10−1−3 = 6
        (10.0, 1.0, 3.0, 0.0, 6.0),
        # export-heavy: difference goes negative → clamped at 0 (lower bound)
        (5.0, 8.0, 0.0, 0.0, 0.0),
        # all PV straight to load (no charge, no export) → 9
        (9.0, 0.0, 0.0, 0.0, 9.0),
        # AC-charge overcompensation: ac_charge (9.3) > battery_charge (9.0) — conversion
        # loss / counter skew. pv_to_batt floors at 0, so result is clamped to pv − export
        # (8.1), NOT inflated to 8.4 (upper bound — Codex review on #313).
        (8.1, 0.0, 9.0, 9.3, 8.1),
    ],
)
def test_e_pv_direct_today_formula(pv_today, grid_out_day, battery_charge, ac_charge, expected):
    """PV-direct = max(0, (pv − export) − max(0, battery_charge − ac_charge)) on a GEN1 hybrid.

    The ac_charge term nets out grid-sourced battery charging that e_battery_charge lumps
    in; the lower clamp keeps it ≥ 0 when export exceeds PV; flooring pv_to_battery at 0
    keeps direct PV ≤ total on-site PV when ac_charge overshoots battery_charge.
    """
    inv = SinglePhaseInverter.from_register_cache(
        _gen1_pv_direct_cache(pv_today, grid_out_day, battery_charge, ac_charge)
    )
    assert inv.e_pv_direct_today == pytest.approx(expected)  # type: ignore[attr-defined]
    assert "e_pv_direct_today" in inv.model_dump()
    # Invariant: direct PV is a subset of on-site PV self-consumption, never larger.
    assert inv.e_pv_direct_today <= inv.e_self_consumption_today + 1e-9  # type: ignore[attr-defined]


def test_e_pv_direct_today_none_on_ineligible_models():
    """AC-coupled and All-in-One return None — their PV registers are mislabelled (#293).

    Both have e_battery_charge_today resolving (AC/AIO route today→alt1), so a plain
    None-guard would let them through; the explicit topology gate is what blocks them.
    """
    from givenergy_modbus.model.register import HR, IR

    # AC-coupled (0x3001): every input present, but is_ac_coupled gates it out.
    ac = SinglePhaseInverter.from_register_cache(
        RegisterCache({HR(0): 0x3001, HR(21): 282, IR(44): 100, IR(25): 10, IR(36): 70, IR(35): 40})
    )
    assert ac.is_ac_coupled is True  # type: ignore[attr-defined]
    assert ac.e_battery_charge_today == 7.0  # resolves (today→alt1) — so the gate, not None-prop, blocks
    assert ac.e_pv_direct_today is None  # type: ignore[attr-defined]

    # All-in-One (0x8001): PV register is non-PV here (#293) → gated out.
    aio = SinglePhaseInverter.from_register_cache(
        RegisterCache({HR(0): 0x8001, HR(21): 612, IR(44): 100, IR(25): 10, IR(36): 70, IR(35): 40})
    )
    assert aio.e_battery_charge_today == 7.0
    assert aio.e_pv_direct_today is None  # type: ignore[attr-defined]


def test_e_pv_direct_today_none_when_battery_charge_unavailable():
    """A DC model with no battery-charge routing (e.g. GEN3) → None, not a wrong value.

    e_battery_charge_today only routes on HYBRID_GEN1 among DC models, so GEN3 returns
    None and the field propagates that rather than treating charge as zero.
    """
    from givenergy_modbus.model.register import HR, IR

    gen3 = SinglePhaseInverter.from_register_cache(
        RegisterCache({HR(0): 0x2003, HR(21): 303, IR(44): 100, IR(25): 10, IR(35): 40})
    )
    assert gen3.e_battery_charge_today is None
    assert gen3.e_pv_direct_today is None  # type: ignore[attr-defined]

    # Missing ac_charge (IR35) on an otherwise-eligible GEN1 → None (no partial guess).
    no_ac = SinglePhaseInverter.from_register_cache(
        RegisterCache({HR(0): 0x2001, HR(21): 449, IR(44): 100, IR(25): 10, IR(183): 70})
    )
    assert no_ac.e_pv_direct_today is None  # type: ignore[attr-defined]


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
    assert idle.charge_status_label is ChargeStatus.IDLE

    charging = SinglePhaseInverter.from_register_cache(RegisterCache({IR(14): 2}))
    assert charging.charge_status_label is ChargeStatus.CHARGING

    finishing = SinglePhaseInverter.from_register_cache(RegisterCache({IR(14): 3}))
    assert finishing.charge_status_label is ChargeStatus.FINISHING

    discharging = SinglePhaseInverter.from_register_cache(RegisterCache({IR(14): 5}))
    assert discharging.charge_status_label is ChargeStatus.DISCHARGING

    unknown = SinglePhaseInverter.from_register_cache(RegisterCache({IR(14): 99}))
    assert unknown.charge_status_label is None

    # Raw field still accessible via model_dump() without triggering the deprecation warning.
    assert idle.model_dump()["charge_status"] == 0
    assert unknown.model_dump()["charge_status"] == 99

    # Direct attribute access emits a DeprecationWarning pointing to charge_status_label.
    with pytest.warns(DeprecationWarning, match="charge_status_label"):
        _ = idle.charge_status


def test_directional_power_sensors():
    """Non-negative directional power sensors derived from p_grid_out and p_battery (#205)."""
    from givenergy_modbus.model.register import IR

    # Exporting: p_grid_out > 0
    exporting = SinglePhaseInverter.from_register_cache(RegisterCache({IR(30): 1000}))
    assert exporting.grid_export_power == 1000
    assert exporting.grid_import_power == 0

    # Importing: p_grid_out < 0 (raw uint16 = 65536 - 500 = 65036)
    importing = SinglePhaseInverter.from_register_cache(RegisterCache({IR(30): 65036}))
    assert importing.grid_import_power == 500
    assert importing.grid_export_power == 0

    # Grid idle
    grid_idle = SinglePhaseInverter.from_register_cache(RegisterCache({IR(30): 0}))
    assert grid_idle.grid_import_power == 0
    assert grid_idle.grid_export_power == 0

    # Missing register → None
    missing = SinglePhaseInverter.from_register_cache(RegisterCache({}))
    assert missing.grid_import_power is None
    assert missing.grid_export_power is None
    assert missing.battery_charge_power is None
    assert missing.battery_discharge_power is None

    # Discharging: p_battery > 0
    discharging = SinglePhaseInverter.from_register_cache(RegisterCache({IR(52): 3000}))
    assert discharging.battery_discharge_power == 3000
    assert discharging.battery_charge_power == 0

    # Charging: p_battery < 0 (raw uint16 = 65536 - 2000 = 63536)
    charging = SinglePhaseInverter.from_register_cache(RegisterCache({IR(52): 63536}))
    assert charging.battery_charge_power == 2000
    assert charging.battery_discharge_power == 0


def test_installer_config_block_decodes_from_populated_cache():
    """HR(300-351) installer-config registers decode from a populated cache.

    Gap-fill from the GE app 4.0.7 binary. Guards the address/converter mapping
    (the all-None snapshots can't catch a wrong HR address or bool-vs-uint16 typing).
    """
    cache = RegisterCache(
        registers={
            HR(300): 1,  # enable_plant_mode (bool)
            HR(301): 2,  # plant_role (uint16)
            HR(307): 2300,  # eps_nominal_voltage
            HR(331): 1,  # force_off_grid (bool)
            HR(333): 1,  # enable_ev_charger (bool)
            HR(336): 80,  # ev_charger_soc_limit
            HR(343): 0,  # enable_generator (bool)
            HR(347): 1,  # disable_leds (bool)
            HR(351): 4,  # inverter_operating_mode
        }
    )
    d = SinglePhaseInverter.from_register_cache(cache).model_dump()
    assert d["enable_plant_mode"] is True
    assert d["plant_role"] == 2
    assert d["eps_nominal_voltage"] == 2300
    assert d["force_off_grid"] is True
    assert d["enable_ev_charger"] is True
    assert d["ev_charger_soc_limit"] == 80
    assert d["enable_generator"] is False
    assert d["disable_leds"] is True
    assert d["inverter_operating_mode"] == 4


def test_three_phase_grid_config_gaps_decode_from_populated_cache():
    """HR(1081-1087) QU-curve and HR(1102-1103) export-limit gaps decode (app 4.0.7)."""
    from givenergy_modbus.model.inverter_threephase import ThreePhaseInverter

    cache = RegisterCache(
        registers={
            HR(1081): 2530,  # qu_curve_volt_high_point_1
            HR(1085): 50,  # voltage_reactive_power_percentage
            HR(1102): 3680,  # export_power_limit
            HR(1103): 1,  # enable_export_limit (bool)
        }
    )
    d = ThreePhaseInverter.from_register_cache(cache).model_dump()
    assert d["qu_curve_volt_high_point_1"] == 2530
    assert d["voltage_reactive_power_percentage"] == 50
    assert d["export_power_limit"] == 3680
    assert d["enable_export_limit"] is True


@pytest.mark.parametrize(
    "old_name,new_name,hr,raw_value,expected",
    [
        # Trip band (HR63-70)
        ("v_ac_low_limit_1", "v_ac_low_limit_trip", 63, 2060, 206.0),
        ("v_ac_high_limit_1", "v_ac_high_limit_trip", 64, 2740, 274.0),
        ("f_ac_low_limit_1", "f_ac_low_limit_trip", 65, 4700, 47.0),
        ("f_ac_high_limit_1", "f_ac_high_limit_trip", 66, 5198, 51.98),
        ("t_ac_low_voltage_1", "t_ac_low_voltage_trip", 67, 126, 1.26),
        ("t_ac_high_voltage_1", "t_ac_high_voltage_trip", 68, 27, 0.27),
        ("t_ac_low_freq_1", "t_ac_low_freq_trip", 69, 24, 0.24),
        ("t_ac_high_freq_1", "t_ac_high_freq_trip", 70, 28, 0.28),
        # Reconnect band (HR71-78)
        ("v_ac_low_limit_2", "v_ac_low_limit_reconnect", 71, 1840, 184.0),
        ("v_ac_high_limit_2", "v_ac_high_limit_reconnect", 72, 2620, 262.0),
        ("f_ac_low_limit_2", "f_ac_low_limit_reconnect", 73, 4745, 47.45),
        ("f_ac_high_limit_2", "f_ac_high_limit_reconnect", 74, 5200, 52.0),
        ("t_ac_low_voltage_2", "t_ac_low_voltage_reconnect", 75, 126, 1.26),
        ("t_ac_high_voltage_2", "t_ac_high_voltage_reconnect", 76, 52, 0.52),
        ("t_ac_low_freq_2", "t_ac_low_freq_reconnect", 77, 1, 0.01),
        ("t_ac_high_freq_2", "t_ac_high_freq_reconnect", 78, 28, 0.28),
        # Grid band (HR79-82)
        ("v_ac_low_limit_3", "v_ac_low_limit_grid", 79, 1755, 175.5),
        ("v_ac_high_limit_3", "v_ac_high_limit_grid", 80, 2837, 283.7),
        ("f_ac_low_limit_3", "f_ac_low_limit_grid", 81, 4700, 47.0),
        ("f_ac_high_limit_3", "f_ac_high_limit_grid", 82, 5200, 52.0),
    ],
)
def test_grid_protection_rename_and_deprecated_alias_single_phase(old_name, new_name, hr, raw_value, expected):
    """HR(63-82) renamed _1/_2/_3 → _trip/_reconnect/_grid; old names are deprecated aliases."""
    cache = RegisterCache({HR(hr): raw_value})
    inv = SinglePhaseInverter.from_register_cache(cache)

    # New name returns the value with no warning.
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        assert getattr(inv, new_name) == pytest.approx(expected)  # type: ignore[attr-defined]
    assert [x for x in w if issubclass(x.category, DeprecationWarning)] == []

    # Deprecated alias warns and returns the same value.
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        assert getattr(inv, old_name) == pytest.approx(expected)  # type: ignore[attr-defined]
    deprecations = [x for x in w if issubclass(x.category, DeprecationWarning)]
    assert len(deprecations) == 1
    assert new_name in str(deprecations[0].message)

    # model_dump() uses the new name only.
    dumped = inv.model_dump()
    assert new_name in dumped
    assert old_name not in dumped


@pytest.mark.parametrize(
    "old_name,new_name,hr,raw_value,expected",
    [
        # Trip band (HR1018-1021)
        ("v_grid_low_limit_1", "v_grid_low_limit_trip", 1018, 2060, 206.0),
        ("v_grid_high_limit_1", "v_grid_high_limit_trip", 1019, 2740, 274.0),
        ("f_grid_low_limit_1", "f_grid_low_limit_trip", 1020, 4700, 47.0),
        ("f_grid_high_limit_1", "f_grid_high_limit_trip", 1021, 5198, 51.98),
        # Reconnect band (HR1022-1025)
        ("v_grid_low_limit_2", "v_grid_low_limit_reconnect", 1022, 1840, 184.0),
        ("v_grid_high_limit_2", "v_grid_high_limit_reconnect", 1023, 2620, 262.0),
        ("f_grid_low_limit_2", "f_grid_low_limit_reconnect", 1024, 4745, 47.45),
        ("f_grid_high_limit_2", "f_grid_high_limit_reconnect", 1025, 5200, 52.0),
        # Grid band (HR1026-1029)
        ("v_grid_low_limit_3", "v_grid_low_limit_grid", 1026, 1755, 175.5),
        ("v_grid_high_limit_3", "v_grid_high_limit_grid", 1027, 2837, 283.7),
        ("f_grid_low_limit_3", "f_grid_low_limit_grid", 1028, 4700, 47.0),
        ("f_grid_high_limit_3", "f_grid_high_limit_grid", 1029, 5200, 52.0),
        # Time limits (HR1034-1041)
        ("time_grid_low_voltage_limit_1", "time_grid_low_voltage_limit_trip", 1034, 126, 1.26),
        ("time_grid_high_voltage_limit_1", "time_grid_high_voltage_limit_trip", 1035, 27, 0.27),
        ("time_grid_low_voltage_limit_2", "time_grid_low_voltage_limit_reconnect", 1036, 126, 1.26),
        ("time_grid_high_voltage_limit_2", "time_grid_high_voltage_limit_reconnect", 1037, 52, 0.52),
        ("time_grid_low_freq_limit_1", "time_grid_low_freq_limit_trip", 1038, 1, 0.01),
        ("time_grid_high_freq_limit_1", "time_grid_high_freq_limit_trip", 1039, 28, 0.28),
        ("time_grid_low_freq_limit_2", "time_grid_low_freq_limit_reconnect", 1040, 1, 0.01),
        ("time_grid_high_freq_limit_2", "time_grid_high_freq_limit_reconnect", 1041, 28, 0.28),
    ],
)
def test_grid_protection_rename_and_deprecated_alias_three_phase(old_name, new_name, hr, raw_value, expected):
    """HR(1018-1041) renamed _1/_2/_3 → _trip/_reconnect/_grid; old names are deprecated aliases."""
    from givenergy_modbus.model.inverter_threephase import ThreePhaseInverter

    cache = RegisterCache({HR(hr): raw_value})
    inv = ThreePhaseInverter.from_register_cache(cache)

    # New name returns the value with no warning.
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        assert getattr(inv, new_name) == pytest.approx(expected)  # type: ignore[attr-defined]
    assert [x for x in w if issubclass(x.category, DeprecationWarning)] == []

    # Deprecated alias warns and returns the same value.
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        assert getattr(inv, old_name) == pytest.approx(expected)  # type: ignore[attr-defined]
    deprecations = [x for x in w if issubclass(x.category, DeprecationWarning)]
    assert len(deprecations) == 1
    assert new_name in str(deprecations[0].message)

    # model_dump() uses the new name only.
    dumped = inv.model_dump()
    assert new_name in dumped
    assert old_name not in dumped
