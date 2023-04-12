import datetime
import logging
from enum import Enum
from typing import Tuple

from pydantic import root_validator

from givenergy_modbus.model import GivEnergyBaseModel

_logger = logging.getLogger(__name__)


class Model(str, Enum):
    """Known models of inverters."""

    AC = 'AC'
    Gen2 = 'Gen2'
    Hybrid = 'Hybrid'
    Unknown = 'Unknown'

    @classmethod
    def from_serial_number(cls, serial_number: str):
        """Return the appropriate model from a given serial number."""
        serial_prefix_to_models_lut = {
            'CE': cls.AC,
            'ED': cls.Gen2,
            'EA': cls.Gen2,
            'SA': cls.Hybrid,
            'SD': cls.Hybrid,
        }
        prefix = serial_number[:2]
        if prefix in serial_prefix_to_models_lut:
            return serial_prefix_to_models_lut[prefix]
        else:
            _logger.error(f'Cannot determine model number from serial number {serial_number!r}')
            return cls.Unknown


class Inverter(GivEnergyBaseModel):
    """Structured format for all inverter attributes."""

    # Device details
    inverter_serial_number: str
    device_type_code: str
    inverter_module: int
    inverter_firmware_version: str
    dsp_firmware_version: int
    arm_firmware_version: int
    usb_device_inserted: int
    select_arm_chip: bool
    bms_chip_version: int
    inverter_modbus_address: int
    modbus_version: float
    system_time: datetime.datetime
    inverter_state: Tuple[int, int]

    # Installation configuration
    meter_type: int
    reverse_115_meter_direct: bool
    reverse_418_meter_direct: bool
    enable_drm_rj45_port: bool
    ct_adjust: int
    enable_buzzer: bool
    num_mppt: int
    num_phases: int
    enable_ammeter: bool
    grid_port_max_power_output: int
    enable_60hz_freq_mode: bool
    enable_above_6kw_system: bool
    enable_frequency_derating: bool
    enable_low_voltage_fault_ride_through: bool
    enable_spi: bool

    pv1_voltage_adjust: int
    pv2_voltage_adjust: int
    grid_r_voltage_adjust: int
    grid_s_voltage_adjust: int
    grid_t_voltage_adjust: int
    grid_power_adjust: int
    battery_voltage_adjust: int
    pv1_power_adjust: int
    pv2_power_adjust: int

    active_power_rate: int
    reactive_power_rate: int
    power_factor: int
    power_factor_function_model: int
    inverter_start_time: int
    inverter_restart_delay_time: int

    # Fault conditions
    dci_1_i: float
    dci_1_time: int
    dci_2_i: float
    dci_2_time: int
    f_ac_high_c: float
    f_ac_high_in: float
    f_ac_high_in_time: int
    f_ac_high_out: float
    f_ac_high_out_time: int
    f_ac_low_c: float
    f_ac_low_in: float
    f_ac_low_in_time: int
    f_ac_low_out: float
    f_ac_low_out_time: int
    gfci_1_i: float
    gfci_1_time: int
    gfci_2_i: float
    gfci_2_time: int
    v_ac_high_c: float
    v_ac_high_in: float
    v_ac_high_in_time: int
    v_ac_high_out: float
    v_ac_high_out_time: int
    v_ac_low_c: float
    v_ac_low_in: float
    v_ac_low_in_time: int
    v_ac_low_out: float
    v_ac_low_out_time: int

    iso_fault_value: float
    gfci_fault_value: float
    dci_fault_value: float
    v_pv_fault_value: float
    v_ac_fault_value: float
    f_ac_fault_value: float
    temp_fault_value: float

    iso1: int
    iso2: int
    local_command_test: bool

    # Battery configuration
    inverter_battery_serial_number: str
    inverter_battery_bms_firmware_version: int
    enable_bms_read: bool
    battery_type: int
    battery_nominal_capacity: float
    enable_auto_judge_battery_type: bool
    v_pv_input_start: float
    v_battery_under_protection_limit: float
    v_battery_over_protection_limit: float

    enable_discharge: bool
    enable_charge: bool
    enable_charge_target: bool
    battery_power_mode: int
    soc_force_adjust: int

    charge_slot_1: Tuple[datetime.time, datetime.time]
    charge_slot_2: Tuple[datetime.time, datetime.time]
    discharge_slot_1: Tuple[datetime.time, datetime.time]
    discharge_slot_2: Tuple[datetime.time, datetime.time]
    charge_and_discharge_soc: Tuple[int, int]

    battery_low_force_charge_time: int
    battery_soc_reserve: int
    battery_charge_limit: int
    battery_discharge_limit: int
    island_check_continue: int
    battery_discharge_min_power_reserve: int
    charge_target_soc: int
    charge_soc_stop_2: int
    discharge_soc_stop_2: int
    charge_soc_stop_1: int
    discharge_soc_stop_1: int

    inverter_status: int
    system_mode: int
    inverter_countdown: int
    charge_status: int
    battery_percent: int
    charger_warning_code: int
    work_time_total: int
    fault_code: int

    e_battery_charge_day: float
    e_battery_charge_day_2: float
    e_battery_charge_total: float
    e_battery_discharge_day: float
    e_battery_discharge_day_2: float
    e_battery_discharge_total: float
    e_battery_throughput_total: float
    e_discharge_year: float
    e_inverter_out_day: float
    e_inverter_out_total: float
    e_grid_out_day: float
    e_grid_in_day: float
    e_grid_in_total: float
    e_grid_out_total: float
    e_inverter_in_day: float
    e_inverter_in_total: float
    e_pv1_day: float
    e_pv2_day: float
    e_pv_day: float  # virtual
    e_solar_diverter: float
    f_ac1: float
    f_eps_backup: float
    i_ac1: float
    i_battery: float
    i_grid_port: float
    i_pv1: float
    i_pv2: float
    p_battery: int
    p_eps_backup: int
    p_grid_apparent: int
    p_grid_out: int
    p_inverter_out: int
    p_load_demand: int
    p_pv1: int
    p_pv2: int
    p_pv: int  # virtual
    e_pv_total: float
    pf_inverter_out: float
    temp_battery: float
    temp_charger: float
    temp_inverter_heatsink: float
    v_ac1: float
    v_battery: float
    v_eps_backup: float
    v_highbrigh_bus: int
    v_n_bus: float
    v_p_bus: float
    v_pv1: float
    v_pv2: float

    pf_cmd_memory_state: bool
    pf_limit_lp1_lp: int
    pf_limit_lp1_pf: float
    pf_limit_lp2_lp: int
    pf_limit_lp2_pf: float
    pf_limit_lp3_lp: int
    pf_limit_lp3_pf: float
    pf_limit_lp4_lp: int
    pf_limit_lp4_pf: float
    frequency_load_limit_rate: int

    real_v_f_value: float
    remote_bms_restart: bool
    safety_time_limit: float
    safety_v_f_limit: float
    start_system_auto_test: bool
    test_treat_time: int
    test_treat_value: float
    test_value: float
    user_code: int
    v_10_min_protection: float

    variable_address: int
    variable_value: int

    inverter_reboot: int

    @root_validator
    def compute_model(cls, values) -> dict:
        """Computes the inverter model from the serial number prefix."""
        if 'inverter_serial_number' in values:
            values['inverter_model'] = Model.from_serial_number(values['inverter_serial_number'])
        else:
            values['inverter_model'] = Model.Unknown
        return values
