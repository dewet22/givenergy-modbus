from enum import Enum

from pydantic import ConfigDict, computed_field, create_model

from givenergy_modbus.model.register import HR, IR, RegisterGetter
from givenergy_modbus.model.register import Converter as C
from givenergy_modbus.model.register import RegisterDefinition as Def


class Model(str, Enum):
    """Known models of inverters.

    Values are the first digit of the device type code reported by the inverter.
    Note: Gen 2 inverters with an 'EA' serial prefix were previously mapped via a
    serial-prefix lookup table (removed in 1.0). Their device type code first digit
    is unknown — if EA-prefix units report a code not listed here, _missing_ will
    raise ValueError. A field report from a Gen 2 owner is needed to add support.
    """

    HYBRID = "2"
    AC = "3"
    HYBRID_3PH = "4"
    EMS = "5"
    AC_3PH = "6"
    GATEWAY = "7"
    ALL_IN_ONE = "8"

    @classmethod
    def _missing_(cls, key):
        """Pick model from the first digit of the device type code."""
        return cls(key[0])

    @property
    def system_battery_voltage(self) -> float:
        """Represent nominal battery voltage for this system."""
        if self.value == Model.ALL_IN_ONE:
            return 317.0
        elif self.value in [Model.HYBRID_3PH, Model.AC_3PH]:
            return 76.8
        else:
            return 51.2


class UsbDevice(int, Enum):
    """USB devices that can be inserted into inverters."""

    NONE = 0
    WIFI = 1
    DISK = 2


class BatteryPowerMode(int, Enum):
    """Battery discharge strategy."""

    EXPORT = 0
    SELF_CONSUMPTION = 1


class BatteryCalibrationStage(int, Enum):
    """Battery calibration stages."""

    OFF = 0
    DISCHARGE = 1
    SET_LOWER_LIMIT = 2
    CHARGE = 3
    SET_UPPER_LIMIT = 4
    BALANCE = 5
    SET_FULL_CAPACITY = 6
    FINISH = 7


class MeterType(int, Enum):
    """Installed meter type."""

    CT_OR_EM418 = 0
    EM115 = 1


class BatteryType(int, Enum):
    """Installed battery type."""

    LEAD_ACID = 0
    LITHIUM = 1


class PowerFactorFunctionModel(int, Enum):
    """Power Factor function model."""

    PF_1 = 0
    PF_BY_SET = 1
    DEFAULT_PF_LINE = 2
    USER_PF_LINE = 3
    UNDER_EXCITED_INDUCTIVE_REACTIVE_POWER = 4
    OVER_EXCITED_CAPACITIVE_REACTIVE_POWER = 5
    QV_MODEL = 6


class Status(int, Enum):
    """Inverter status."""

    WAITING = 0
    NORMAL = 1
    WARNING = 2
    FAULT = 3
    FLASHING_FIRMWARE_UPDATE = 4


class InverterRegisterGetter(RegisterGetter):
    """Structured format for all inverter attributes."""

    REGISTER_LUT = {
        #
        # Holding Registers, block 0-59
        #
        "device_type_code": Def(C.hex, None, HR(0)),
        "model": Def(C.hex, Model, HR(0)),
        "module": Def(C.uint32, (C.hex, 8), HR(1), HR(2)),
        "num_mppt": Def((C.duint8, 0), None, HR(3)),
        "num_phases": Def((C.duint8, 1), None, HR(3)),
        # HR(4-6) unused
        "enable_ammeter": Def(C.bool, None, HR(7)),
        "first_battery_serial_number": Def(C.string, None, HR(8), HR(9), HR(10), HR(11), HR(12)),
        "serial_number": Def(C.string, None, HR(13), HR(14), HR(15), HR(16), HR(17)),
        "first_battery_bms_firmware_version": Def(C.uint16, None, HR(18)),
        "dsp_firmware_version": Def(C.uint16, None, HR(19)),
        "enable_charge_target": Def(C.bool, None, HR(20)),
        "arm_firmware_version": Def(C.uint16, None, HR(21)),
        "firmware_version": Def(C.firmware_version, None, HR(19), HR(21)),
        "usb_device_inserted": Def(C.uint16, UsbDevice, HR(22)),
        "select_arm_chip": Def(C.bool, None, HR(23)),
        "variable_address": Def(C.uint16, None, HR(24)),
        "variable_value": Def(C.uint16, None, HR(25)),
        "grid_port_max_power_output": Def(C.uint16, None, HR(26)),
        "battery_power_mode": Def(C.uint16, BatteryPowerMode, HR(27)),  # eco mode
        "enable_60hz_freq_mode": Def(C.bool, None, HR(28)),
        "battery_calibration_stage": Def(C.uint16, BatteryCalibrationStage, HR(29)),
        "modbus_address": Def(C.uint16, None, HR(30)),
        "charge_slot_2": Def(C.timeslot, None, HR(31), HR(32)),
        "user_code": Def(C.uint16, None, HR(33)),
        "modbus_version": Def(C.centi, (C.fstr, "0.2f"), HR(34)),
        "system_time": Def(C.datetime, None, HR(35), HR(36), HR(37), HR(38), HR(39), HR(40)),
        "enable_drm_rj45_port": Def(C.bool, None, HR(41)),
        "enable_reversed_ct_clamp": Def(C.bool, None, HR(42)),
        "charge_soc": Def((C.duint8, 0), None, HR(43)),
        "discharge_soc": Def((C.duint8, 1), None, HR(43)),
        "discharge_slot_2": Def(C.timeslot, None, HR(44), HR(45)),
        "bms_firmware_version": Def(C.uint16, None, HR(46)),
        "meter_type": Def(C.uint16, MeterType, HR(47)),
        "enable_reversed_115_meter": Def(C.bool, None, HR(48)),
        "enable_reversed_418_meter": Def(C.bool, None, HR(49)),
        "active_power_rate": Def(C.uint16, None, HR(50)),
        "reactive_power_rate": Def(C.uint16, None, HR(51)),
        "power_factor": Def(C.uint16, None, HR(52)),  # /10_000 - 1
        "enable_inverter_auto_restart": Def((C.duint8, 0), C.bool, HR(53)),
        "enable_inverter": Def((C.duint8, 1), C.bool, HR(53)),
        "battery_type": Def(C.uint16, BatteryType, HR(54)),
        "battery_capacity_ah": Def(C.uint16, None, HR(55)),
        "discharge_slot_1": Def(C.timeslot, None, HR(56), HR(57)),
        "enable_auto_judge_battery_type": Def(C.bool, None, HR(58)),
        "enable_discharge": Def(C.bool, None, HR(59)),
        #
        # Holding Registers, block 60-119
        #
        "v_pv_start": Def(C.uint16, C.deci, HR(60)),
        "start_countdown_timer": Def(C.uint16, None, HR(61)),
        "restart_delay_time": Def(C.uint16, None, HR(62)),
        # skip protection settings HR(63-93)
        "charge_slot_1": Def(C.timeslot, None, HR(94), HR(95)),
        "enable_charge": Def(C.bool, None, HR(96)),
        "battery_low_voltage_protection_limit": Def(C.uint16, C.centi, HR(97)),
        "battery_high_voltage_protection_limit": Def(C.uint16, C.centi, HR(98)),
        # skip voltage adjustment settings 99-104
        "battery_voltage_adjust": Def(C.uint16, C.centi, HR(105)),
        # skip voltage adjustment settings 106-107
        "battery_low_force_charge_time": Def(C.uint16, None, HR(108)),
        "enable_bms_read": Def(C.bool, None, HR(109)),
        "battery_soc_reserve": Def(C.uint16, None, HR(110)),
        "battery_charge_limit": Def(C.uint16, None, HR(111)),
        "battery_discharge_limit": Def(C.uint16, None, HR(112)),
        "enable_buzzer": Def(C.bool, None, HR(113)),
        "battery_discharge_min_power_reserve": Def(C.uint16, None, HR(114)),
        # 'island_check_continue': Def(C.uint16, None, HR(115)),
        "charge_target_soc": Def(C.uint16, None, HR(116)),  # requires enable_charge_target
        "charge_soc_stop_2": Def(C.uint16, None, HR(117)),
        "discharge_soc_stop_2": Def(C.uint16, None, HR(118)),
        "charge_soc_stop_1": Def(C.uint16, None, HR(119)),
        #
        # Holding Registers, block 120-179
        #
        "discharge_soc_stop_1": Def(C.uint16, None, HR(120)),
        "enable_local_command_test": Def(C.bool, None, HR(121)),
        "power_factor_function_model": Def(C.uint16, PowerFactorFunctionModel, HR(122)),
        "frequency_load_limit_rate": Def(C.uint16, None, HR(123)),
        "enable_low_voltage_fault_ride_through": Def(C.bool, None, HR(124)),
        "enable_frequency_derating": Def(C.bool, None, HR(125)),
        "enable_above_6kw_system": Def(C.bool, None, HR(126)),
        "start_system_auto_test": Def(C.bool, None, HR(127)),
        "enable_spi": Def(C.bool, None, HR(128)),
        # skip PF configuration and protection settings 129-162
        "inverter_reboot": Def(C.uint16, None, HR(163)),
        "enable_rtc": Def(C.bool, None, HR(166)),
        "threephase_balance_mode": Def(C.uint16, None, HR(167)),
        "threephase_abc": Def(C.uint16, None, HR(168)),
        "threephase_balance_1": Def(C.uint16, None, HR(169)),
        "threephase_balance_2": Def(C.uint16, None, HR(170)),
        "threephase_balance_3": Def(C.uint16, None, HR(171)),
        # HR(172-174) unused
        "enable_battery_on_pv_or_grid": Def(C.bool, None, HR(175)),
        "debug_inverter": Def(C.uint16, None, HR(176)),
        "enable_ups_mode": Def(C.bool, None, HR(177)),
        "enable_g100_limit_switch": Def(C.bool, None, HR(178)),
        "enable_battery_cable_impedance_alarm": Def(C.bool, None, HR(179)),
        #
        # Holding Registers, block 180-239
        #
        "enable_standard_self_consumption_logic": Def(C.bool, None, HR(199)),
        "cmd_bms_flash_update": Def(C.bool, None, HR(200)),
        "inverter_errors": Def(C.uint32, None, HR(223), HR(224)),
        # 202-239 - Hot Water Diverter?
        #
        # Holding Registers, block 240-299
        # Gen 3 timeslots
        #
        "charge_target_soc_1": Def(C.uint16, None, HR(242)),
        "charge_slot_2_x": Def(C.timeslot, None, HR(243), HR(244)),
        "charge_target_soc_2": Def(C.uint16, None, HR(245)),
        "charge_slot_3": Def(C.timeslot, None, HR(246), HR(247)),
        "charge_target_soc_3": Def(C.uint16, None, HR(248)),
        "charge_slot_4": Def(C.timeslot, None, HR(249), HR(250)),
        "charge_target_soc_4": Def(C.uint16, None, HR(251)),
        "charge_slot_5": Def(C.timeslot, None, HR(252), HR(253)),
        "charge_target_soc_5": Def(C.uint16, None, HR(254)),
        "charge_slot_6": Def(C.timeslot, None, HR(255), HR(256)),
        "charge_target_soc_6": Def(C.uint16, None, HR(257)),
        "charge_slot_7": Def(C.timeslot, None, HR(258), HR(259)),
        "charge_target_soc_7": Def(C.uint16, None, HR(260)),
        "charge_slot_8": Def(C.timeslot, None, HR(261), HR(262)),
        "charge_target_soc_8": Def(C.uint16, None, HR(263)),
        "charge_slot_9": Def(C.timeslot, None, HR(264), HR(265)),
        "charge_target_soc_9": Def(C.uint16, None, HR(266)),
        "charge_slot_10": Def(C.timeslot, None, HR(267), HR(268)),
        "charge_target_soc_10": Def(C.uint16, None, HR(269)),
        "discharge_target_soc_1": Def(C.uint16, None, HR(272)),
        "discharge_target_soc_2": Def(C.uint16, None, HR(275)),
        "discharge_slot_3": Def(C.timeslot, None, HR(276), HR(277)),
        "discharge_target_soc_3": Def(C.uint16, None, HR(278)),
        "discharge_slot_4": Def(C.timeslot, None, HR(279), HR(280)),
        "discharge_target_soc_4": Def(C.uint16, None, HR(281)),
        "discharge_slot_5": Def(C.timeslot, None, HR(282), HR(283)),
        "discharge_target_soc_5": Def(C.uint16, None, HR(284)),
        "discharge_slot_6": Def(C.timeslot, None, HR(285), HR(286)),
        "discharge_target_soc_6": Def(C.uint16, None, HR(287)),
        "discharge_slot_7": Def(C.timeslot, None, HR(288), HR(289)),
        "discharge_target_soc_7": Def(C.uint16, None, HR(290)),
        "discharge_slot_8": Def(C.timeslot, None, HR(291), HR(292)),
        "discharge_target_soc_8": Def(C.uint16, None, HR(293)),
        "discharge_slot_9": Def(C.timeslot, None, HR(294), HR(295)),
        "discharge_target_soc_9": Def(C.uint16, None, HR(296)),
        "discharge_slot_10": Def(C.timeslot, None, HR(297), HR(298)),
        "discharge_target_soc_10": Def(C.uint16, None, HR(299)),
        #
        # Holding Registers, block 300-359
        # Single Phase New registers
        #
        "battery_charge_limit_ac": Def(C.uint16, None, HR(313)),
        "battery_discharge_limit_ac": Def(C.uint16, None, HR(314)),
        "battery_pause_mode": Def(C.uint16, None, HR(318)),
        "battery_pause_slot_1": Def(C.timeslot, None, HR(319), HR(320)),
        #
        # Holding Registers, block 4080-4139
        #
        "pv_power_setting": Def(C.uint32, None, HR(4107), HR(4108)),
        "e_battery_discharge_total2": Def(C.uint32, None, HR(4109), HR(4110)),
        "e_battery_charge_total2": Def(C.uint32, None, HR(4111), HR(4112)),
        "e_battery_discharge_today": Def(C.uint16, None, HR(4113)),
        "e_battery_charge_today": Def(C.uint16, None, HR(4114)),
        #
        # Holding Registers, block 4140-4199
        #
        "e_inverter_export_total": Def(C.uint32, None, HR(4141), HR(4142)),
        #
        # Input Registers, block 0-59
        #
        "status": Def(C.uint16, Status, IR(0)),
        "v_pv1": Def(C.deci, None, IR(1)),
        "v_pv2": Def(C.deci, None, IR(2)),
        "v_p_bus": Def(C.deci, None, IR(3)),
        "v_n_bus": Def(C.deci, None, IR(4)),
        "v_ac1": Def(C.deci, None, IR(5)),
        "e_battery_throughput": Def(C.uint32, C.deci, IR(6), IR(7)),
        "i_pv1": Def(C.deci, None, IR(8)),
        "i_pv2": Def(C.deci, None, IR(9)),
        "i_ac1": Def(C.deci, None, IR(10)),
        "e_pv_total": Def(C.uint32, C.deci, IR(11), IR(12)),
        "f_ac1": Def(C.centi, None, IR(13)),
        "charge_status": Def(C.uint16, None, IR(14)),
        "v_highbrigh_bus": Def(C.deci, None, IR(15)),
        "pf_inverter_output_now": Def(C.uint16, None, IR(16)),
        "e_pv1_day": Def(C.deci, None, IR(17)),
        "p_pv1": Def(C.uint16, None, IR(18)),
        "e_pv2_day": Def(C.deci, None, IR(19)),
        "p_pv2": Def(C.uint16, None, IR(20)),
        "e_grid_out_total": Def(C.uint32, C.deci, IR(21), IR(22)),
        "e_solar_diverter": Def(C.deci, None, IR(23)),
        "p_grid_out_ph1": Def(C.int16, None, IR(24)),
        "e_grid_out_day": Def(C.deci, None, IR(25)),
        "e_grid_in_day": Def(C.deci, None, IR(26)),
        "e_inverter_in_total": Def(C.uint32, C.deci, IR(27), IR(28)),
        "e_discharge_year": Def(C.deci, None, IR(29)),
        "p_grid_out": Def(C.int16, None, IR(30)),
        "p_backup": Def(C.uint16, None, IR(31)),  # EPS
        "e_grid_in_total": Def(C.uint32, C.deci, IR(32), IR(33)),
        # IR(34) unknown, skip
        "e_load_day": Def(C.deci, None, IR(35)),
        "e_battery_charge_day": Def(C.deci, None, IR(36)),
        "e_battery_discharge_day": Def(C.deci, None, IR(37)),
        "countdown": Def(C.uint16, None, IR(38)),
        "fault_code": Def(C.uint32, (C.hex, 8), IR(39), IR(40)),
        "t_inverter_heatsink": Def(C.deci, None, IR(41)),
        "p_load_demand": Def(C.uint16, None, IR(42)),
        "p_grid_apparent": Def(C.uint16, None, IR(43)),
        "e_inverter_out_day": Def(C.deci, None, IR(44)),
        "e_inverter_out_total": Def(C.uint32, C.deci, IR(45), IR(46)),
        "work_time_total": Def(C.uint32, None, IR(47), IR(48)),
        "system_mode": Def(C.uint16, None, IR(49)),
        "v_battery": Def(C.centi, None, IR(50)),
        "i_battery": Def(C.int16, C.centi, IR(51)),
        "p_battery": Def(C.int16, None, IR(52)),
        "v_ac1_output": Def(C.deci, None, IR(53)),  # might be v_eps_backup?
        "f_ac1_output": Def(C.centi, None, IR(54)),  # might be f_eps_backup?
        "t_charger": Def(C.deci, None, IR(55)),
        "t_battery": Def(C.deci, None, IR(56)),
        "charger_warning_code": Def(C.uint16, None, IR(57)),
        "i_grid_port": Def(C.centi, None, IR(58)),
        "battery_soc": Def(C.uint16, None, IR(59)),
        #
        # Input Registers, block 180-239
        #
        "e_battery_discharge_2": Def(C.deci, None, IR(180)),
        "e_battery_charge_2": Def(C.deci, None, IR(181)),
        "e_battery_discharge_day_2": Def(C.deci, None, IR(182)),
        "e_battery_charge_day_2": Def(C.deci, None, IR(183)),
        #
        # Input Registers, block 240-300
        # Gen3
        #
        "p_combined_generation": Def(C.uint32, None, IR(247), IR(248)),
    }


_InverterBase = create_model(  # type: ignore[call-overload]
    "Inverter",
    __config__=ConfigDict(frozen=True),
    **InverterRegisterGetter.to_fields(),
)


class Inverter(_InverterBase):  # type: ignore[valid-type,misc]
    """GivEnergy inverter data model."""

    @classmethod
    def from_register_cache(cls, register_cache) -> "Inverter":
        """Construct an Inverter from a RegisterCache."""
        return cls.model_validate(InverterRegisterGetter(register_cache).build())

    def p_pv(self) -> int:
        """Computes the total PV power."""
        return self.p_pv1 + self.p_pv2  # type: ignore[attr-defined]

    def e_pv_day(self) -> float:
        """Computes the total PV energy for the day."""
        return self.e_pv1_day + self.e_pv2_day  # type: ignore[attr-defined]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def battery_capacity_kwh(self) -> float | None:
        """Returns the nominal battery capacity in kWh, derived from Ah and model voltage."""
        if self.battery_capacity_ah is None or self.model is None:  # type: ignore[attr-defined]
            return None
        return self.battery_capacity_ah * self.model.system_battery_voltage / 1000  # type: ignore[attr-defined]
