# type: ignore  # shut up mypy, it seems to struggle with this file
import datetime
import logging
from enum import Enum

from pydantic import BaseModel, Field, root_validator

from .register_getter import RegisterGetter

_logger = logging.getLogger(__package__)


class Model(Enum):
    """Known models of inverters."""

    AC = 'CE'
    Gen2 = 'ED'
    Hybrid = 'SA'


class Inverter(BaseModel):
    """Structured format for all inverter attributes."""

    class Config:  # noqa: D106
        orm_mode = True
        getter_dict = RegisterGetter
        allow_mutation = False

    # Installation details
    serial_number: str = Field(alias='inverter_serial_number')
    device_type_code: str
    inverter_module: int
    dsp_firmware_version: int
    arm_firmware_version: int
    usb_device_inserted: int
    select_arm_chip: bool
    meter_type: int
    reverse_115_meter_direct: bool
    reverse_418_meter_direct: bool
    enable_drm_rj45_port: bool
    ct_adjust: int
    enable_buzzer: bool

    num_mppt: int
    num_phases: int
    enable_ammeter: bool
    p_grid_port_max_output: int
    enable_60hz_freq_mode: bool
    inverter_modbus_address: int
    modbus_version: float
    pv1_voltage_adjust: int
    pv2_voltage_adjust: int
    grid_r_voltage_adjust: int
    grid_s_voltage_adjust: int
    grid_t_voltage_adjust: int
    grid_power_adjust: int
    battery_voltage_adjust: int
    pv1_power_adjust: int
    pv2_power_adjust: int

    system_time: datetime.datetime
    active_power_rate: int
    reactive_power_rate: int
    power_factor: int
    inverter_state: tuple[int, int]
    inverter_start_time: int
    inverter_restart_delay_time: int

    # Fault conditions
    v_ac_low_out: float
    v_ac_high_out: float
    f_ac_low_out: float
    f_ac_high_out: float
    v_ac_low_out_time: datetime.time
    v_ac_high_out_time: datetime.time
    f_ac_low_out_time: datetime.time
    f_ac_high_out_time: datetime.time
    v_ac_low_in: float
    v_ac_high_in: float
    f_ac_low_in: float
    f_ac_high_in: float
    v_ac_low_in_time: datetime.time
    v_ac_high_in_time: datetime.time
    f_ac_low_in_time: datetime.time
    f_ac_high_in_time: datetime.time
    v_ac_low_c: float
    v_ac_high_c: float
    f_ac_low_c: float
    f_ac_high_c: float
    gfci_1_i: float
    gfci_1_time: datetime.time
    gfci_2_i: float
    gfci_2_time: datetime.time
    dci_1_i: float
    dci_1_time: datetime.time
    dci_2_i: float
    dci_2_time: datetime.time

    # Battery
    first_battery_serial_number: str
    first_battery_bms_firmware_version: int
    enable_bms_read: bool
    battery_type: int
    battery_nominal_capacity: float
    enable_auto_judge_battery_type: bool

    enable_charge_target: bool
    battery_power_mode: int
    soc_force_adjust: int

    charge_slot_1: tuple[datetime.time, datetime.time]
    charge_slot_2: tuple[datetime.time, datetime.time]
    discharge_slot_1: tuple[datetime.time, datetime.time]
    discharge_slot_2: tuple[datetime.time, datetime.time]
    charge_and_discharge_soc: tuple[int, int]

    enable_discharge: bool
    v_pv_input_start: float
    enable_charge: bool
    v_battery_under_protection_limit: float
    v_battery_over_protection_limit: float

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

    # InputRegisters
    inverter_status: int
    v_pv1: float
    v_pv2: float
    v_p_bus: float
    v_n_bus: float
    v_ac1: float
    e_battery_throughput: float
    i_pv1: float
    i_pv2: float
    i_ac1: float
    p_pv_total_generating_capacity: float
    f_ac1: float
    charge_status: int
    v_highbrigh_bus: int
    pf_inverter_output: float
    e_pv1_day: float
    p_pv1: int
    e_pv2_day: float
    p_pv2: int
    e_grid_export_day: float
    e_solar_diverter: float
    p_inverter_output: int
    e_grid_out_day: float
    e_grid_in_day: float
    e_inverter_in_total: float
    e_discharge_year: float
    p_grid_output: int
    p_eps: int
    e_grid_import_total: float
    e_inverter_charge_day: float
    e_battery_charge_day: float
    e_battery_discharge_day: float
    inverter_countdown: int
    fault_code: int
    temp_inverter_heatsink: float
    p_load_demand: int
    p_grid_apparent: int
    e_generated_day: float
    e_generated_total: float
    work_time_total: int
    system_mode: int
    v_battery: float
    i_battery: float
    p_battery: int
    v_eps: float
    f_eps: float
    temp_charger: float
    temp_battery: float
    charger_warning_code: int
    i_grid_port: float
    battery_percent: int
    e_battery_discharge_total: float
    e_battery_charge_total: float

    @root_validator
    def compute_model(cls, values) -> dict:
        """Computes the inverter model from the serial number prefix."""
        values['model'] = Model(values['serial_number'][:2])
        return values

    @root_validator
    def compute_firmware_version(cls, values) -> dict:
        """Virtual method to inject a firmware version similar to what the dashboard shows."""
        values['firmware_version'] = f'D0.{values["dsp_firmware_version"]}-A0.{values["arm_firmware_version"]}'
        return values
