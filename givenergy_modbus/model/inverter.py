from enum import IntEnum, Enum

from pydantic import BaseConfig, create_model

from givenergy_modbus.model.register import HR, IR
from givenergy_modbus.model.register import DataType as DT
from givenergy_modbus.model.register import RegisterDefinition as Def
from givenergy_modbus.model.register import RegisterGetter


class Model(Enum):
    """Known models of inverters."""

    HYBRID = '2'
    AC = '3'
    HYBRID_3PH = '4'
    AC_3PH = '6'
    EMS = '5'
    GATEWAY = '7'
    ALL_IN_ONE = '8'

    @classmethod
    def _missing_(cls, key: str):
        """Pick model from the first digit of the device type code."""
        return cls(key[0])


class UsbDevice(IntEnum):
    """USB devices that can be inserted into inverters."""

    NONE = 0
    WIFI = 1
    DISK = 2


class BatteryPowerMode(IntEnum):
    """Battery discharge strategy."""

    EXPORT = 0
    SELF_CONSUMPTION = 1


class BatteryCalibrationStage(IntEnum):
    """Battery calibration stages."""

    OFF = 0
    DISCHARGE = 1
    SET_LOWER_LIMIT = 2
    CHARGE = 3
    SET_UPPER_LIMIT = 4
    BALANCE = 5
    SET_FULL_CAPACITY = 6
    FINISH = 7


class MeterType(IntEnum):
    """Installed meter type."""

    CT_OR_EM418 = 0
    EM115 = 1


class BatteryType(IntEnum):
    """Installed battery type."""

    LEAD_ACID = 0
    LITHIUM = 1


class PowerFactorFunctionModel(IntEnum):
    """Power Factor function model."""

    PF_1 = 0
    PF_BY_SET = 1
    DEFAULT_PF_LINE = 2
    USER_PF_LINE = 3
    UNDER_EXCITED_INDUCTIVE_REACTIVE_POWER = 4
    OVER_EXCITED_CAPACITIVE_REACTIVE_POWER = 5
    QV_MODEL = 6


class InverterStatus(IntEnum):
    """Inverter status."""

    WAITING = 0
    NORMAL = 1
    WARNING = 2
    FAULT = 3
    FLASHING_FIRMWARE = 4


class InverterRegisterGetter(RegisterGetter):
    """Structured format for all inverter attributes."""

    REGISTER_LUT = {
        # Holding Registers, block 0-59
        'device_type_code': Def(DT.hex, None, HR(0)),
        'model': Def(DT.hex, Model, HR(0)),
        'module': Def(DT.uint32, (DT.hex, 8), HR(1), HR(2)),
        'num_mppt': Def((DT.duint8, 0), None, HR(3)),
        'num_phases': Def((DT.duint8, 1), None, HR(3)),
        # HR(4-6) unused
        'enable_ammeter': Def(DT.bool, None, HR(7)),
        'first_battery_serial_number': Def(DT.string, None, HR(8), HR(9), HR(10), HR(11), HR(12)),
        'serial_number': Def(DT.string, None, HR(13), HR(14), HR(15), HR(16), HR(17)),
        'first_battery_bms_firmware_version': Def(DT.uint16, None, HR(18)),
        'dsp_firmware_version': Def(DT.uint16, None, HR(19)),
        'enable_charge_target': Def(DT.bool, None, HR(20)),
        'arm_firmware_version': Def(DT.uint16, None, HR(21)),
        'usb_device_inserted': Def(DT.uint16, UsbDevice, HR(22)),
        'select_arm_chip': Def(DT.bool, None, HR(23)),
        # variable_address=rc[HR(24)],
        # variable_value=rc[HR(25)],
        'grid_port_max_power_output': Def(DT.uint16, None, HR(26)),
        'battery_power_mode': Def(DT.uint16, BatteryPowerMode, HR(27)),
        'enable_60hz_freq_mode': Def(DT.bool, None, HR(28)),
        'battery_calibration_stage': Def(DT.uint16, BatteryCalibrationStage, HR(29)),
        'modbus_address': Def(DT.uint16, None, HR(30)),
        'charge_slot_2': Def(DT.timeslot, None, HR(31), HR(32)),
        # user_code=rc[HR(33)],
        # Input Registers, block 0-59
        'status': Def(DT.uint16, InverterStatus, IR(0)),
    }

    # def from_registers(cls, rc: RegisterCache) -> 'Inverter':
    #     """Constructor parsing registers directly."""
    #     return Inverter(
    #         # firmware_version=f'D0.{dsp_fw}-A0.{arm_fw}',

    #         modbus_version=f'{rc[HR(34)] / 100:0.2f}',
    #         system_time=rc.to_datetime(HR(35), HR(36), HR(37), HR(38), HR(39), HR(40)),
    #         enable_drm_rj45_port=bool(rc[HR(41)]),
    #         reverse_ct=bool(rc[HR(42)]),
    #         charge_soc=(c_d_soc := rc.to_duint8(HR(43)))[0],
    #         discharge_soc=c_d_soc[1],
    #         discharge_slot_2=rc.to_timeslot(HR(44), HR(45)),
    #         bms_firmware_version=rc[HR(46)],
    #         meter_type=MeterType(rc[HR(47)]),
    #         reverse_115_meter=bool(rc[HR(48)]),
    #         reverse_418_meter=bool(rc[HR(49)]),
    #         active_power_rate=rc[HR(50)],
    #         reactive_power_rate=rc[HR(51)],
    #         power_factor=rc[HR(52)] / 10000 - 1,
    #         enable_inverter=bool((state := rc.to_duint8(HR(53)))[1]),
    #         enable_inverter_auto_restart=bool(state[0]),
    #         battery_type=BatteryType(rc[HR(54)]),
    #         battery_capacity=rc[HR(55)],
    #         discharge_slot_1=rc.to_timeslot(HR(56), HR(57)),
    #         enable_auto_judge_battery_type=bool(rc[HR(58)]),
    #         enable_discharge=bool(rc[HR(59)]),
    #         # 60
    #         pv_start_voltage=rc[HR(60)] / 10,
    #         start_countdown_timer=rc[HR(61)],
    #         restart_delay_time=rc[HR(62)],
    #         # skip protection settings 63-93
    #         charge_slot_1=rc.to_timeslot(HR(94), HR(95)),
    #         enable_charge=bool(rc[HR(96)]),
    #         battery_low_voltage_protection_limit=rc[HR(97)] / 100,
    #         battery_high_voltage_protection_limit=rc[HR(98)] / 100,
    #         # skip voltage adjustment settings 99-107
    #         battery_low_force_charge_time=rc[HR(108)],
    #         enable_bms_read=bool(rc[HR(109)]),
    #         battery_soc_reserve=rc[HR(110)],
    #         battery_charge_limit=rc[HR(111)],
    #         battery_discharge_limit=rc[HR(112)],
    #         enable_buzzer=bool(rc[HR(113)]),
    #         battery_discharge_min_power_reserve=rc[HR(114)],
    #         island_check_continue=rc[HR(115)],
    #         charge_target_soc=rc[HR(116)],  # requires enable_charge_target
    #         charge_soc_stop_2=rc[HR(117)],
    #         discharge_soc_stop_2=rc[HR(118)],
    #         charge_soc_stop_1=rc[HR(119)],
    #         # 120
    #         discharge_soc_stop_1=rc[HR(120)],
    #         local_command_test=bool(rc[HR(121)]),
    #         power_factor_function_model=PowerFactorFunctionModel(rc[HR(122)]),
    #         frequency_load_limit_rate=rc[HR(123)],
    #         enable_low_voltage_fault_ride_through=bool(rc[HR(124)]),
    #         enable_frequency_derating=bool(rc[HR(125)]),
    #         enable_above_6kw_system=bool(rc[HR(126)]),
    #         start_system_auto_test=bool(rc[HR(127)]),
    #         enable_spi=bool(rc[HR(128)]),
    #         # skip PF configuration and protection settings 129-166
    #         threephase_balance_mode=rc[HR(167)],
    #         threephase_abc=rc[HR(168)],
    #         threephase_balance_1=rc[HR(169)],
    #         threephase_balance_2=rc[HR(170)],
    #         threephase_balance_3=rc[HR(171)],
    #         enable_battery_on_pv_or_grid=bool(rc[HR(175)]),
    #         debug_inverter=rc[HR(176)],
    #         enable_ups_mode=bool(rc[HR(177)]),
    #         enable_g100_limit_switch=bool(rc[HR(178)]),
    #         enable_battery_cable_impedance_alarm=bool(rc[HR(179)]),
    #         # 180
    #         enable_standard_self_consumption_logic=bool(rc[HR(199)]),
    #         cmd_bms_flash_update=bool(rc[HR(200)]),
    #         # 4080
    #         pv_power_setting=rc.to_uint32(HR(4107), HR(4108)),
    #         e_battery_discharge_total_2=rc.to_uint32(HR(4109), HR(4110)),
    #         e_battery_charge_total_2=rc.to_uint32(HR(4111), HR(4112)),
    #         e_battery_discharge_today_3=rc[HR(4113)],
    #         e_battery_charge_today_3=rc[HR(4114)],
    #         e_inverter_export_total=rc.to_uint32(HR(4141), HR(4142)),
    #     )

    # @computed('p_pv')
    # def compute_p_pv(p_pv1: int, p_pv2: int, **kwargs) -> int:
    #     """Computes the discharge slot 2."""
    #     return p_pv1 + p_pv2

    # @computed('e_pv_day')
    # def compute_e_pv_day(e_pv1_day: float, e_pv2_day: float, **kwargs) -> float:
    #     """Computes the discharge slot 2."""
    #     return e_pv1_day + e_pv2_day


class InverterConfig(BaseConfig):
    """Pydantic configuration for the Inverter class."""

    orm_mode = True
    getter_dict = InverterRegisterGetter


# class Inverter(GivEnergyBaseModel):
#     """Structured format for all inverter attributes."""
#
#     # Device details
#     device_type_code: str
#     model: Model
#     module: str
#     serial_number: str
#     dsp_firmware_version: int
#     arm_firmware_version: int
#     firmware_version: str
#     modbus_address: int
#     modbus_version: str
#
#     # Installation configuration
#     num_mppt: int
#     num_phases: int
#     usb_device_inserted: UsbDevice
#     enable_ammeter: bool
#     select_arm_chip: bool
#     system_time: datetime.datetime
#     enable_inverter: bool
#     enable_inverter_auto_restart: bool
#
#     grid_port_max_power_output: int
#     enable_60hz_freq_mode: bool
#     enable_drm_rj45_port: bool
#     reverse_ct: bool
#     meter_type: int
#     reverse_115_meter: bool
#     reverse_418_meter: bool
#     enable_buzzer: bool
#     enable_low_voltage_fault_ride_through: bool
#     enable_frequency_derating: bool
#     enable_above_6kw_system: bool
#     start_system_auto_test: bool
#     enable_spi: bool
#     enable_standard_self_consumption_logic: bool
#     cmd_bms_flash_update: bool
#
#     # pf_cmd_memory_state: bool
#     # pf_limit_lp1_lp: int
#     # pf_limit_lp1_pf: float
#     # pf_limit_lp2_lp: int
#     # pf_limit_lp2_pf: float
#     # pf_limit_lp3_lp: int
#     # pf_limit_lp3_pf: float
#     # pf_limit_lp4_lp: int
#     # pf_limit_lp4_pf: float
#     frequency_load_limit_rate: int
#
#     # pv1_voltage_adjust: int
#     # pv2_voltage_adjust: int
#     # grid_r_voltage_adjust: int
#     # grid_s_voltage_adjust: int
#     # grid_t_voltage_adjust: int
#     # grid_power_adjust: int
#     # battery_voltage_adjust: int
#     # pv1_power_adjust: int
#     # pv2_power_adjust: int
#
#     active_power_rate: int
#     reactive_power_rate: int
#     power_factor: int
#     power_factor_function_model: PowerFactorFunctionModel
#     start_countdown_timer: int
#     restart_delay_time: int
#
#     # # Fault conditions
#     # dci_1_i: float
#     # dci_1_time: int
#     # dci_2_i: float
#     # dci_2_time: int
#     # f_ac_high_c: float
#     # f_ac_high_in: float
#     # f_ac_high_in_time: int
#     # f_ac_high_out: float
#     # f_ac_high_out_time: int
#     # f_ac_low_c: float
#     # f_ac_low_in: float
#     # f_ac_low_in_time: int
#     # f_ac_low_out: float
#     # f_ac_low_out_time: int
#     # gfci_1_i: float
#     # gfci_1_time: int
#     # gfci_2_i: float
#     # gfci_2_time: int
#     # v_ac_high_c: float
#     # v_ac_high_in: float
#     # v_ac_high_in_time: int
#     # v_ac_high_out: float
#     # v_ac_high_out_time: int
#     # v_ac_low_c: float
#     # v_ac_low_in: float
#     # v_ac_low_in_time: int
#     # v_ac_low_out: float
#     # v_ac_low_out_time: int
#     #
#     # iso_fault_value: float
#     # gfci_fault_value: float
#     # dci_fault_value: float
#     # v_pv_fault_value: float
#     # v_ac_fault_value: float
#     # f_ac_fault_value: float
#     # temp_fault_value: float
#     #
#     # iso1: int
#     # iso2: int
#     local_command_test: bool
#
#     # Battery configuration
#     first_battery_serial_number: str
#     first_battery_bms_firmware_version: int
#     battery_power_mode: BatteryPowerMode
#     bms_firmware_version: int
#     enable_bms_read: bool
#     battery_type: BatteryType
#     battery_capacity: int
#     enable_auto_judge_battery_type: bool
#     pv_start_voltage: float
#     battery_low_voltage_protection_limit: float
#     battery_high_voltage_protection_limit: float
#
#     enable_discharge: bool
#     enable_charge: bool
#     enable_charge_target: bool
#     battery_calibration_stage: BatteryCalibrationStage
#
#     charge_slot_1: TimeSlot
#     charge_slot_2: TimeSlot
#     discharge_slot_1: TimeSlot
#     discharge_slot_2: TimeSlot
#     charge_soc: int
#     discharge_soc: int
#
#     battery_low_force_charge_time: int
#     battery_soc_reserve: int
#     battery_charge_limit: int
#     battery_discharge_limit: int
#     island_check_continue: int
#     battery_discharge_min_power_reserve: int
#     charge_target_soc: int
#     charge_soc_stop_2: int
#     discharge_soc_stop_2: int
#     charge_soc_stop_1: int
#     discharge_soc_stop_1: int
#
#     # inverter_status: int
#     # system_mode: int
#     # inverter_countdown: int
#     # charge_status: int
#     # battery_percent: int
#     # charger_warning_code: int
#     # work_time_total: int
#     # fault_code: int
#     #
#     # e_battery_charge_day: float
#     # e_battery_charge_day_2: float
#     # e_battery_charge_total: float
#     # e_battery_discharge_day: float
#     # e_battery_discharge_day_2: float
#     # e_battery_discharge_total: float
#     # e_battery_throughput_total: float
#     # e_discharge_year: float
#     # e_inverter_out_day: float
#     # e_inverter_out_total: float
#     # e_grid_out_day: float
#     # e_grid_in_day: float
#     # e_grid_in_total: float
#     # e_grid_out_total: float
#     # e_inverter_in_day: float
#     # e_inverter_in_total: float
#     # e_pv1_day: float
#     # e_pv2_day: float
#     # e_pv_day: Computed[float]
#     # e_solar_diverter: float
#     # f_ac1: float
#     # f_eps_backup: float
#     # i_ac1: float
#     # i_battery: float
#     # i_grid_port: float
#     # i_pv1: float
#     # i_pv2: float
#     # p_battery: int
#     # p_eps_backup: int
#     # p_grid_apparent: int
#     # p_grid_out: int
#     # p_inverter_out: int
#     # p_load_demand: int
#     # p_pv1: int
#     # p_pv2: int
#     # p_pv: Computed[int]
#     # e_pv_total: float
#     # pf_inverter_out: float
#     # temp_battery: float
#     # temp_charger: float
#     # temp_inverter_heatsink: float
#     # v_ac1: float
#     # v_battery: float
#     # v_eps_backup: float
#     # v_highbrigh_bus: int
#     # v_n_bus: float
#     # v_p_bus: float
#     # v_pv1: float
#     # v_pv2: float
#     #
#     # real_v_f_value: float
#     # remote_bms_restart: bool
#     # safety_time_limit: float
#     # safety_v_f_limit: float
#     # test_treat_time: int
#     # test_treat_value: float
#     # test_value: float
#     # user_code: int
#     # v_10_min_protection: float
#
#     threephase_balance_mode: int
#     threephase_abc: int
#     threephase_balance_1: int
#     threephase_balance_2: int
#     threephase_balance_3: int
#
#     enable_battery_on_pv_or_grid: bool
#     debug_inverter: int
#     enable_ups_mode: bool
#     enable_g100_limit_switch: bool
#     enable_battery_cable_impedance_alarm: bool
#
#     pv_power_setting: int
#     e_battery_discharge_total_2: int
#     e_battery_charge_total_2: int
#     e_battery_discharge_today_3: int
#     e_battery_charge_today_3: int
#     e_inverter_export_total: int
#
#     @classmethod
#     def from_registers(cls, rc: RegisterCache) -> 'Inverter':
#         """Constructor parsing registers directly."""
#         return Inverter(
#             device_type_code=(dtc := rc.to_hex_string(HR(0))),
#             model=Model(int(dtc[0], 16)),
#             module=(rc.to_hex_string(HR(1), HR(2))),
#             num_mppt=(num_mppt_phases := rc.to_duint8(HR(3)))[0],
#             num_phases=num_mppt_phases[1],
#             enable_ammeter=bool(rc[HR(7)]),
#             first_battery_serial_number=rc.to_string(HR(8), HR(9), HR(10), HR(11), HR(12)),
#             serial_number=rc.to_string(HR(13), HR(14), HR(15), HR(16), HR(17)),
#             first_battery_bms_firmware_version=rc[HR(18)],
#             dsp_firmware_version=(dsp_fw := rc[HR(19)]),
#             enable_charge_target=bool(rc[HR(20)]),
#             arm_firmware_version=(arm_fw := rc[HR(21)]),
#             firmware_version=f'D0.{dsp_fw}-A0.{arm_fw}',
#             usb_device_inserted=UsbDevice(rc[HR(22)]),
#             select_arm_chip=bool(rc[HR(23)]),
#             variable_address=rc[HR(24)],
#             variable_value=rc[HR(25)],
#             grid_port_max_power_output=rc[HR(26)],
#             battery_power_mode=BatteryPowerMode(rc[HR(27)]),
#             enable_60hz_freq_mode=bool(rc[HR(28)]),
#             battery_calibration_stage=BatteryCalibrationStage(rc[HR(29)]),
#             modbus_address=rc[HR(30)],
#             charge_slot_2=rc.to_timeslot(HR(31), HR(32)),
#             user_code=rc[HR(33)],
#             modbus_version=f'{rc[HR(34)] / 100:0.2f}',
#             system_time=rc.to_datetime(HR(35), HR(36), HR(37), HR(38), HR(39), HR(40)),
#             enable_drm_rj45_port=bool(rc[HR(41)]),
#             reverse_ct=bool(rc[HR(42)]),
#             charge_soc=(c_d_soc := rc.to_duint8(HR(43)))[0],
#             discharge_soc=c_d_soc[1],
#             discharge_slot_2=rc.to_timeslot(HR(44), HR(45)),
#             bms_firmware_version=rc[HR(46)],
#             meter_type=MeterType(rc[HR(47)]),
#             reverse_115_meter=bool(rc[HR(48)]),
#             reverse_418_meter=bool(rc[HR(49)]),
#             active_power_rate=rc[HR(50)],
#             reactive_power_rate=rc[HR(51)],
#             power_factor=rc[HR(52)] / 10000 - 1,
#             enable_inverter=bool((state := rc.to_duint8(HR(53)))[1]),
#             enable_inverter_auto_restart=bool(state[0]),
#             battery_type=BatteryType(rc[HR(54)]),
#             battery_capacity=rc[HR(55)],
#             discharge_slot_1=rc.to_timeslot(HR(56), HR(57)),
#             enable_auto_judge_battery_type=bool(rc[HR(58)]),
#             enable_discharge=bool(rc[HR(59)]),
#             # 60
#             pv_start_voltage=rc[HR(60)] / 10,
#             start_countdown_timer=rc[HR(61)],
#             restart_delay_time=rc[HR(62)],
#             # skip protection settings 63-93
#             charge_slot_1=rc.to_timeslot(HR(94), HR(95)),
#             enable_charge=bool(rc[HR(96)]),
#             battery_low_voltage_protection_limit=rc[HR(97)] / 100,
#             battery_high_voltage_protection_limit=rc[HR(98)] / 100,
#             # skip voltage adjustment settings 99-107
#             battery_low_force_charge_time=rc[HR(108)],
#             enable_bms_read=bool(rc[HR(109)]),
#             battery_soc_reserve=rc[HR(110)],
#             battery_charge_limit=rc[HR(111)],
#             battery_discharge_limit=rc[HR(112)],
#             enable_buzzer=bool(rc[HR(113)]),
#             battery_discharge_min_power_reserve=rc[HR(114)],
#             island_check_continue=rc[HR(115)],
#             charge_target_soc=rc[HR(116)],  # requires enable_charge_target
#             charge_soc_stop_2=rc[HR(117)],
#             discharge_soc_stop_2=rc[HR(118)],
#             charge_soc_stop_1=rc[HR(119)],
#             # 120
#             discharge_soc_stop_1=rc[HR(120)],
#             local_command_test=bool(rc[HR(121)]),
#             power_factor_function_model=PowerFactorFunctionModel(rc[HR(122)]),
#             frequency_load_limit_rate=rc[HR(123)],
#             enable_low_voltage_fault_ride_through=bool(rc[HR(124)]),
#             enable_frequency_derating=bool(rc[HR(125)]),
#             enable_above_6kw_system=bool(rc[HR(126)]),
#             start_system_auto_test=bool(rc[HR(127)]),
#             enable_spi=bool(rc[HR(128)]),
#             # skip PF configuration and protection settings 129-166
#             threephase_balance_mode=rc[HR(167)],
#             threephase_abc=rc[HR(168)],
#             threephase_balance_1=rc[HR(169)],
#             threephase_balance_2=rc[HR(170)],
#             threephase_balance_3=rc[HR(171)],
#             enable_battery_on_pv_or_grid=bool(rc[HR(175)]),
#             debug_inverter=rc[HR(176)],
#             enable_ups_mode=bool(rc[HR(177)]),
#             enable_g100_limit_switch=bool(rc[HR(178)]),
#             enable_battery_cable_impedance_alarm=bool(rc[HR(179)]),
#             # 180
#             enable_standard_self_consumption_logic=bool(rc[HR(199)]),
#             cmd_bms_flash_update=bool(rc[HR(200)]),
#             # 4080
#             pv_power_setting=rc.to_uint32(HR(4107), HR(4108)),
#             e_battery_discharge_total_2=rc.to_uint32(HR(4109), HR(4110)),
#             e_battery_charge_total_2=rc.to_uint32(HR(4111), HR(4112)),
#             e_battery_discharge_today_3=rc[HR(4113)],
#             e_battery_charge_today_3=rc[HR(4114)],
#             e_inverter_export_total=rc.to_uint32(HR(4141), HR(4142)),
#         )
#
#     # @computed('p_pv')
#     # def compute_p_pv(p_pv1: int, p_pv2: int, **kwargs) -> int:
#     #     """Computes the discharge slot 2."""
#     #     return p_pv1 + p_pv2
#     #
#     # @computed('e_pv_day')
#     # def compute_e_pv_day(e_pv1_day: float, e_pv2_day: float, **kwargs) -> float:
#     #     """Computes the discharge slot 2."""
#     #     return e_pv1_day + e_pv2_day

Inverter = create_model(
    'Inverter', __config__=InverterConfig, **InverterRegisterGetter.to_fields()
)  # type: ignore[call-overload]
# , **{'model': 'Foo'}
