import datetime
from enum import Enum
from typing import TypedDict, cast

from .register_banks import HoldingRegister, InputRegister


class Model(Enum):
    """Inverter models, as determined from their serial number prefix."""

    CE = 'AC'
    ED = "Gen2"
    SA = "Hybrid"


class InverterData(TypedDict):
    """Structured format for all attributes."""

    inverter_serial_number: str
    model: str
    device_type_code: int
    inverter_module: int
    input_tracker_num: int
    output_phase_num: int
    battery_serial_number: str
    battery_firmware_version: int
    dsp_firmware_version: int
    arm_firmware_version: int
    winter_mode: bool
    wifi_or_u_disk: int
    select_dsp_or_arm: int
    grid_port_max_output_power: int
    battery_power_mode: int
    fre_mode: int
    soc_force_adjust: int
    communicate_address: int
    charge_slot_1: tuple[datetime.time, datetime.time]
    charge_slot_2: tuple[datetime.time, datetime.time]
    discharge_slot_1: tuple[datetime.time, datetime.time]
    discharge_slot_2: tuple[datetime.time, datetime.time]
    modbus_version: float
    system_time: datetime.datetime
    drm_enable: bool
    ct_adjust: int
    charge_and_discharge_soc: int
    bms_version: int
    b_meter_type: int
    b_115_meter_direct: int
    b_418_meter_direct: int
    active_p_rate: int
    reactive_p_rate: int
    power_factor: int
    inverter_state: int
    battery_type: int
    battery_nominal_capacity: int
    auto_judge_battery_type_enable: int
    discharge_enable: bool
    input_start_voltage: int
    start_time: int
    restart_delay_time: int
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
    battery_smart_charge: bool
    discharge_low_limit: int
    charger_high_limit: int
    pv1_volt_adjust: int
    pv2_volt_adjust: int
    grid_r_volt_adjust: int
    grid_s_volt_adjust: int
    grid_t_volt_adjust: int
    grid_power_adjust: int
    battery_volt_adjust: int
    pv1_power_adjust: int
    pv2_power_adjust: int
    battery_low_force_charge_time: int
    bms_type: int
    shallow_charge: int
    battery_charge_limit: int
    battery_discharge_limit: int
    buzzer_sw: int
    battery_power_reserve: int
    island_check_continue: int
    battery_target_soc: int
    chg_soc_stop2: int
    discharge_soc_stop2: int
    chg_soc_stop: int
    discharge_soc_stop: int

    # Input registers
    inverter_status: int
    v_pv1: float
    v_pv2: float
    v_p_bus_inside: float
    v_n_bus_inside: float
    v_single_phase_grid: float
    e_battery_throughput: float
    i_pv1: float
    i_pv2: float
    i_grid_output_single_phase: float
    p_pv_total_generating_capacity: float
    f_grid_three_single_phase: float
    charge_status: float
    v_highbrigh_bus: float
    pf_inverter_output_now: float
    e_pv1_day: float
    p_pv1: float
    e_pv2_day: float
    p_pv2: float
    e_pv_day: float
    pv_mate: float
    p_grid_output_three_single_phase: int
    e_grid_out_day: float
    e_grid_in_day: float
    e_inverter_in_total: float
    e_discharge_year: float
    p_grid_output: int
    p_backup: int
    p_grid_in_total: float
    e_total_load_day: float
    e_battery_charge_day: float
    e_battery_discharge_day: float
    p_countdown: int
    fault_code: int
    temp_inverter: float
    p_load_total: int
    p_grid_apparent: int
    e_generated_day: float
    e_generated_total: float
    work_time_total: int
    system_mode: int  # 1 = grid-tie?
    v_bat: float
    i_bat: float
    p_bat: int
    v_output: float
    f_output: float
    temp_charger: float
    temp_battery: float
    charger_warning_code: int
    p_grid_port: float
    battery_percent: int
    v_battery_cell01: float
    v_battery_cell02: float
    v_battery_cell03: float
    v_battery_cell04: float
    v_battery_cell05: float
    v_battery_cell06: float
    v_battery_cell07: float
    v_battery_cell08: float
    v_battery_cell09: float
    v_battery_cell10: float
    v_battery_cell11: float
    v_battery_cell12: float
    v_battery_cell13: float
    v_battery_cell14: float
    v_battery_cell15: float
    v_battery_cell16: float
    temp_battery_cell1: float
    temp_battery_cell2: float
    temp_battery_cell3: float
    temp_battery_cell4: float
    v_battery_sum: float
    temp_mos: float
    v_battery_out: float
    battery_full_capacity: float
    battery_design_capacity: float
    battery_remaining_capacity: float
    battery_status_1_2: int
    battery_status_3_4: int
    battery_status_5_6: int
    battery_status_7: int
    battery_warning_1_2: int
    battery_cycles: int
    battery_no_of_cells: int
    bms_firmware_version: int
    battery_soc: int
    battery_design_capacity_2: float
    e_battery_discharge_ac_total: float
    e_battery_charge_ac_total: float
    battery_serial_number_2: str
    usb_inserted: bool
    e_battery_discharge_total: float
    e_battery_charge_total: float


class Inverter:
    """Models an inverter device."""

    holding_registers: list[int]  # raw register values cache
    input_registers: list[int]  # raw register values cache

    def __init__(self, holding_registers, input_registers):
        """Constructor."""
        self.holding_registers = holding_registers
        self.input_registers = input_registers

        self.inverter_serial_number = (
            self.inverter_serial_number_5
            + self.inverter_serial_number_4
            + self.inverter_serial_number_3
            + self.inverter_serial_number_2
            + self.inverter_serial_number_1
        )
        self.serial_number = self.inverter_serial_number
        self.model = Model[self.serial_number[0:2]].value
        self.inverter_firmware_version = f'D0.{self.dsp_firmware_version}-A0.{self.arm_firmware_version}'
        self.input_tracker_num = self.input_tracker_num_and_output_phase_num >> 8
        self.output_phase_num = self.input_tracker_num_and_output_phase_num & 0xFF
        self.modbus_version = f'{self.modbus_version:0.2f}'
        self.battery_serial_number = (
            self.battery_serial_number_5
            + self.battery_serial_number_4
            + self.battery_serial_number_3
            + self.battery_serial_number_2
            + self.battery_serial_number_1
        )
        self.battery_serial_number_2 = (
            self.battery_serial_number_2_5
            + self.battery_serial_number_2_4
            + self.battery_serial_number_2_3
            + self.battery_serial_number_2_2
            + self.battery_serial_number_2_1
        )
        self.system_time = datetime.datetime(
            year=self.system_time_year + 2000,
            month=self.system_time_month,
            day=self.system_time_day,
            hour=self.system_time_hour,
            minute=self.system_time_minute,
            second=self.system_time_second,
        )
        self.charge_slot_1 = (self.charge_slot_1_start, self.charge_slot_1_end)
        self.charge_slot_2 = (self.charge_slot_2_start, self.charge_slot_2_end)
        self.discharge_slot_1 = (self.discharge_slot_1_start, self.discharge_slot_1_end)
        self.discharge_slot_2 = (self.discharge_slot_2_start, self.discharge_slot_2_end)

    def __getattr__(self, item: str):
        """Magic attributes that look up and render register values."""
        item = item.upper()

        for bank, values in {HoldingRegister: self.holding_registers, InputRegister: self.input_registers}.items():
            if item in bank.__members__:
                return bank[item].render(values[bank[item].value])
            if item + '_H' in bank.__members__:
                # double-word composite registers
                # fmt: off
                return (
                    bank[(item + '_H')].render(values[bank[(item + '_H')].value])
                    + bank[(item + '_L')].render(values[bank[(item + '_L')].value])
                )
                # fmt: on
        raise KeyError(item)

    def to_dict(self) -> InverterData:
        """Return inverter attributes as a typed dict specified by InverterData."""
        ret = {}
        for k in InverterData.__annotations__.keys():
            ret[k] = getattr(self, k)
        return cast(InverterData, ret)

    def debug(self):
        """Dump the internal state of registers and their value representations."""
        print('#' * 140)
        for i, v in enumerate(self.holding_registers):
            r = HoldingRegister(i)
            print(
                f'{i:3} {r.name:40} {r.type.name:15} {r.scaling.name:5} '
                f'{r.scaling.value:5} 0x{v:04x} {v:10} {r.render(v):>20}'
            )

        print('#' * 140)
        for i, v in enumerate(self.input_registers):
            r = InputRegister(i)
            print(
                f'{i:3} {r.name:40} {r.type.name:15} {r.scaling.name:5} '
                f'{r.scaling.value:5} 0x{v:04x} {v:10} {r.render(v):>20}'
            )
