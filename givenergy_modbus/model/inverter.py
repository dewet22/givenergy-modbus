import logging
from enum import IntEnum

from givenergy_modbus.client import TimeSlot
from givenergy_modbus.model import GivEnergyBaseModel
from givenergy_modbus.model.register import HoldingRegister as HR
from givenergy_modbus.model.register_cache import RegisterCache

_logger = logging.getLogger(__name__)


class Model(IntEnum):
    """Known models of inverters."""

    UNKNOWN = -1
    HYBRID = 2
    AC = 3
    HYBRID_3PH = 4
    AC_3PH = 6
    EMS = 5
    GATEWAY = 7
    ALL_IN_ONE = 8

    @classmethod
    def _missing_(cls, value):
        return cls.UNKNOWN


class UsbDevice(IntEnum):
    """USB devices that can be inserted into inverters."""

    UNKNOWN = -1
    NONE = 0
    WIFI = 1
    DISK = 2

    @classmethod
    def _missing_(cls, value):
        return cls.UNKNOWN


class BatteryPowerMode(IntEnum):
    """Battery discharge strategy."""

    UNKNOWN = -1
    EXPORT = 0
    SELF_CONSUMPTION = 1

    @classmethod
    def _missing_(cls, value):
        return cls.UNKNOWN


class BatteryCalibrationStage(IntEnum):
    """Battery calibration stages."""

    UNKNOWN = -1
    OFF = 0
    DISCHARGE = 1
    SET_LOWER_LIMIT = 2
    CHARGE = 3
    SET_UPPER_LIMIT = 4
    BALANCE = 5
    SET_FULL_CAPACITY = 6
    FINISH = 7

    @classmethod
    def _missing_(cls, value):
        return cls.UNKNOWN


class Inverter(GivEnergyBaseModel):
    """Structured format for all inverter attributes."""

    # Device details
    device_type_code: str
    model: Model
    module: str
    serial_number: str
    dsp_firmware_version: int
    arm_firmware_version: int
    firmware_version: str
    modbus_address: int

    # Installation configuration
    num_mppt: int
    num_phases: int
    usb_device_inserted: UsbDevice
    enable_ammeter: bool
    select_arm_chip: bool
    # modbus_version: float
    # system_time: Computed[datetime.datetime]
    # inverter_state: tuple[int, int]
    #
    # meter_type: int
    # reverse_115_meter_direct: bool
    # reverse_418_meter_direct: bool
    # enable_drm_rj45_port: bool
    # ct_adjust: int
    # enable_buzzer: bool
    #
    grid_port_max_power_output: int
    enable_60hz_freq_mode: bool
    # enable_above_6kw_system: bool
    # enable_frequency_derating: bool
    # enable_low_voltage_fault_ride_through: bool
    # enable_spi: bool
    #
    # pv1_voltage_adjust: int
    # pv2_voltage_adjust: int
    # grid_r_voltage_adjust: int
    # grid_s_voltage_adjust: int
    # grid_t_voltage_adjust: int
    # grid_power_adjust: int
    # battery_voltage_adjust: int
    # pv1_power_adjust: int
    # pv2_power_adjust: int
    #
    # active_power_rate: int
    # reactive_power_rate: int
    # power_factor: int
    # power_factor_function_model: int
    # inverter_start_time: int
    # inverter_restart_delay_time: int
    #
    # # Fault conditions
    # dci_1_i: float
    # dci_1_time: int
    # dci_2_i: float
    # dci_2_time: int
    # f_ac_high_c: float
    # f_ac_high_in: float
    # f_ac_high_in_time: int
    # f_ac_high_out: float
    # f_ac_high_out_time: int
    # f_ac_low_c: float
    # f_ac_low_in: float
    # f_ac_low_in_time: int
    # f_ac_low_out: float
    # f_ac_low_out_time: int
    # gfci_1_i: float
    # gfci_1_time: int
    # gfci_2_i: float
    # gfci_2_time: int
    # v_ac_high_c: float
    # v_ac_high_in: float
    # v_ac_high_in_time: int
    # v_ac_high_out: float
    # v_ac_high_out_time: int
    # v_ac_low_c: float
    # v_ac_low_in: float
    # v_ac_low_in_time: int
    # v_ac_low_out: float
    # v_ac_low_out_time: int
    #
    # iso_fault_value: float
    # gfci_fault_value: float
    # dci_fault_value: float
    # v_pv_fault_value: float
    # v_ac_fault_value: float
    # f_ac_fault_value: float
    # temp_fault_value: float
    #
    # iso1: int
    # iso2: int
    # local_command_test: bool
    #
    # # Battery configuration
    first_battery_serial_number: str
    first_battery_bms_firmware_version: int
    battery_power_mode: BatteryPowerMode
    # enable_bms_read: bool
    # battery_type: int
    # battery_nominal_capacity: float
    # enable_auto_judge_battery_type: bool
    # v_pv_input_start: float
    # v_battery_under_protection_limit: float
    # v_battery_over_protection_limit: float
    #
    # enable_discharge: bool
    # enable_charge: bool
    enable_charge_target: bool
    battery_calibration_stage: BatteryCalibrationStage
    #
    # charge_slot_1: tuple[datetime.time, datetime.time]
    charge_slot_2: TimeSlot
    # discharge_slot_1: tuple[datetime.time, datetime.time]
    # discharge_slot_2: tuple[datetime.time, datetime.time]
    # charge_and_discharge_soc: tuple[int, int]
    #
    # battery_low_force_charge_time: int
    # battery_soc_reserve: int
    # battery_charge_limit: int
    # battery_discharge_limit: int
    # island_check_continue: int
    # battery_discharge_min_power_reserve: int
    # charge_target_soc: int
    # charge_soc_stop_2: int
    # discharge_soc_stop_2: int
    # charge_soc_stop_1: int
    # discharge_soc_stop_1: int
    #
    # inverter_status: int
    # system_mode: int
    # inverter_countdown: int
    # charge_status: int
    # battery_percent: int
    # charger_warning_code: int
    # work_time_total: int
    # fault_code: int
    #
    # e_battery_charge_day: float
    # e_battery_charge_day_2: float
    # e_battery_charge_total: float
    # e_battery_discharge_day: float
    # e_battery_discharge_day_2: float
    # e_battery_discharge_total: float
    # e_battery_throughput_total: float
    # e_discharge_year: float
    # e_inverter_out_day: float
    # e_inverter_out_total: float
    # e_grid_out_day: float
    # e_grid_in_day: float
    # e_grid_in_total: float
    # e_grid_out_total: float
    # e_inverter_in_day: float
    # e_inverter_in_total: float
    # e_pv1_day: float
    # e_pv2_day: float
    # e_pv_day: Computed[float]
    # e_solar_diverter: float
    # f_ac1: float
    # f_eps_backup: float
    # i_ac1: float
    # i_battery: float
    # i_grid_port: float
    # i_pv1: float
    # i_pv2: float
    # p_battery: int
    # p_eps_backup: int
    # p_grid_apparent: int
    # p_grid_out: int
    # p_inverter_out: int
    # p_load_demand: int
    # p_pv1: int
    # p_pv2: int
    # p_pv: Computed[int]
    # e_pv_total: float
    # pf_inverter_out: float
    # temp_battery: float
    # temp_charger: float
    # temp_inverter_heatsink: float
    # v_ac1: float
    # v_battery: float
    # v_eps_backup: float
    # v_highbrigh_bus: int
    # v_n_bus: float
    # v_p_bus: float
    # v_pv1: float
    # v_pv2: float
    #
    # pf_cmd_memory_state: bool
    # pf_limit_lp1_lp: int
    # pf_limit_lp1_pf: float
    # pf_limit_lp2_lp: int
    # pf_limit_lp2_pf: float
    # pf_limit_lp3_lp: int
    # pf_limit_lp3_pf: float
    # pf_limit_lp4_lp: int
    # pf_limit_lp4_pf: float
    # frequency_load_limit_rate: int
    #
    # real_v_f_value: float
    # remote_bms_restart: bool
    # safety_time_limit: float
    # safety_v_f_limit: float
    # start_system_auto_test: bool
    # test_treat_time: int
    # test_treat_value: float
    # test_value: float
    # user_code: int
    # v_10_min_protection: float
    #
    # variable_address: int
    # variable_value: int
    #
    # # inverter_reboot: int

    @classmethod
    def from_registers(cls, register_cache: RegisterCache) -> 'Inverter':
        """Constructor parsing registers directly."""
        return Inverter(
            device_type_code=(dtc := register_cache.to_hex_string(HR(0))),
            model=Model(int(dtc[0], 16)),
            module=(register_cache.to_hex_string(HR(1), HR(2))),
            num_mppt=(num_mppt_phases := register_cache.to_duint8(HR(3)))[0],
            num_phases=num_mppt_phases[1],
            enable_ammeter=bool(register_cache[HR(7)]),
            first_battery_serial_number=register_cache.to_string(HR(8), HR(9), HR(10), HR(11), HR(12)),
            serial_number=register_cache.to_string(HR(13), HR(14), HR(15), HR(16), HR(17)),
            first_battery_bms_firmware_version=register_cache[HR(18)],
            dsp_firmware_version=(dsp_fw := register_cache[HR(19)]),
            enable_charge_target=bool(register_cache[HR(20)]),
            arm_firmware_version=(arm_fw := register_cache[HR(21)]),
            firmware_version=f'D0.{dsp_fw}-A0.{arm_fw}',
            usb_device_inserted=UsbDevice(register_cache[HR(22)]),
            select_arm_chip=bool(register_cache[HR(23)]),
            grid_port_max_power_output=register_cache[HR(26)],
            battery_power_mode=BatteryPowerMode(register_cache[HR(27)]),
            enable_60hz_freq_mode=bool(register_cache[HR(28)]),
            battery_calibration_stage=BatteryCalibrationStage(register_cache[HR(29)]),
            modbus_address=register_cache[HR(30)],
            charge_slot_2=register_cache.to_timeslot(HR(31), HR(32)),
        )

    # @computed('charge_slot_1')
    # def compute_charge_slot_1(
    #     charge_slot_1_start: datetime.time, charge_slot_1_end: datetime.time, **kwargs
    # ) -> tuple[datetime.time, datetime.time]:
    #     """Computes the charge slot 1."""
    #     return charge_slot_1_start, charge_slot_1_end
    #
    # @computed('charge_slot_2')
    # def compute_discharge_slot_2(
    #     charge_slot_2_start: datetime.time, charge_slot_2_end: datetime.time, **kwargs
    # ) -> tuple[datetime.time, datetime.time]:
    #     """Computes the charge slot 2."""
    #     return charge_slot_2_start, charge_slot_2_end
    #
    # @computed('discharge_slot_1')
    # def compute_discharge_slot_1(
    #     discharge_slot_1_start: datetime.time, discharge_slot_1_end: datetime.time, **kwargs
    # ) -> tuple[datetime.time, datetime.time]:
    #     """Computes the discharge slot 1."""
    #     return discharge_slot_1_start, discharge_slot_1_end
    #
    # @computed('discharge_slot_2')
    # def compute_discharge_slot_2(
    #     discharge_slot_2_start: datetime.time, discharge_slot_2_end: datetime.time, **kwargs
    # ) -> tuple[datetime.time, datetime.time]:
    #     """Computes the discharge slot 2."""
    #     return discharge_slot_2_start, discharge_slot_2_end
    #
    # @computed('system_time')
    # def compute_system_time(
    #     system_time_year: int,
    #     system_time_month: int,
    #     system_time_day: int,
    #     system_time_hour: int,
    #     system_time_minute: int,
    #     system_time_second: int,
    #     **kwargs,
    # ) -> datetime.datetime:
    #     """Computes the system time."""
    #     return datetime.datetime(
    #         system_time_year + 2000,
    #         system_time_month,
    #         system_time_day,
    #         system_time_hour,
    #         system_time_minute,
    #         system_time_second,
    #     )
    #
    # @computed('p_pv')
    # def compute_p_pv(p_pv1: int, p_pv2: int, **kwargs) -> int:
    #     """Computes the discharge slot 2."""
    #     return p_pv1 + p_pv2
    #
    # @computed('e_pv_day')
    # def compute_e_pv_day(e_pv1_day: float, e_pv2_day: float, **kwargs) -> float:
    #     """Computes the discharge slot 2."""
    #     return e_pv1_day + e_pv2_day
