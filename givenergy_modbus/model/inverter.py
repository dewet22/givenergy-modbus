import math
import warnings
from enum import Enum, IntEnum, StrEnum
from typing import ClassVar

from pydantic import ConfigDict, computed_field, create_model

from givenergy_modbus.client.commands import _InverterCommands
from givenergy_modbus.model.battery import ExportPriority
from givenergy_modbus.model.register import HR, IR, RegisterGetter, RegisterMetadataMixin
from givenergy_modbus.model.register import Converter as C
from givenergy_modbus.model.register import RegisterDefinition as Def


class Model(str, Enum):
    """Known models of inverters.

    Single-digit values are the coarse family (first digit of the DTC); these are
    what `Model(dtc_string)` returns via `_missing_` for backward compatibility.
    Two-character and "20gN" values are more specific variants reachable via
    `resolve_model(raw_dtc, arm_fw)` or by direct construction e.g. `Model("81")`.

    Note: Gen 2 inverters with an 'EA' serial prefix were previously mapped via a
    serial-prefix lookup table (removed in 1.0). Their device type code first digit
    is unknown — if EA-prefix units report a code not listed here, _missing_ will
    raise ValueError. A field report from a Gen 2 owner is needed to add support.
    """

    # Coarse families (first digit of DTC) — backward-compatible values
    HYBRID = "2"
    AC = "3"
    HYBRID_3PH = "4"
    EMS = "5"
    AC_3PH = "6"
    GATEWAY = "7"
    ALL_IN_ONE = "8"

    # Specific variants (two-digit DTC prefix or firmware-disambiguated)
    HYBRID_GEN1 = "20g1"
    HYBRID_GEN2 = "20g2"
    HYBRID_GEN3 = "20g3"
    POLAR = "21"
    AIO_COMMERCIAL = "41"
    EMS_COMMERCIAL = "51"
    HYBRID_HV_GEN3 = "81"
    ALL_IN_ONE_HYBRID = "82"
    HYBRID_GEN4 = "83"

    @classmethod
    def _missing_(cls, value):
        """Pick model from the first digit of the device type code."""
        if not isinstance(value, str) or len(value) <= 1:
            return None
        return cls(value[0])

    @property
    def system_battery_voltage(self) -> float:
        """Represent nominal battery voltage for this system."""
        if self.value == Model.ALL_IN_ONE:
            return 307.0
        elif self.value in [Model.HYBRID_3PH, Model.AC_3PH]:
            return 76.8
        else:
            return 51.2


# SlotMap, SINGLE_PHASE_SLOTS, EXTENDED_SLOTS live in model.slot_map so they can
# be referenced by client.commands without producing a circular import (the
# inverter command mixin in client.commands needs to be importable here for
# class composition). Re-exported here for backward compatibility with existing
# `from givenergy_modbus.model.inverter import ...` callers.
from givenergy_modbus.model.slot_map import EXTENDED_SLOTS, SINGLE_PHASE_SLOTS, SlotMap  # noqa: E402

# ARM firmware version century → HYBRID generation for DTC prefix "20"
_HYBRID_FW_CENTURY_TO_GEN: dict[int, Model] = {
    3: Model.HYBRID_GEN3,
    8: Model.HYBRID_GEN2,
    9: Model.HYBRID_GEN2,
}

# Two-digit DTC prefix → specific Model variant (where distinct from single-digit family)
_DTC_PREFIX_TO_MODEL: dict[str, Model] = {
    "21": Model.POLAR,
    "41": Model.AIO_COMMERCIAL,
    "51": Model.EMS_COMMERCIAL,
    "81": Model.HYBRID_HV_GEN3,
    "82": Model.ALL_IN_ONE_HYBRID,
    "83": Model.HYBRID_GEN4,
}

# AC-coupled inverters: no integrated DC battery, so they expose dedicated AC
# charge/discharge limit registers (HR313/314) that DC-coupled models don't.
# Both are coarse families with no specific sub-variants, so the set is complete
# (an AC DTC like 0x3001 resolves to Model.AC via Model._missing_). Consumers gate
# AC-only controls on this rather than re-deriving the model set themselves.
AC_COUPLED_MODELS: frozenset[Model] = frozenset({Model.AC, Model.AC_3PH})

# Rated AC output power in watts, keyed by 4-char hex device type code.
# Sourced from britkat1980/giv_tcp:dev3; likely not exhaustive for all variants.
_DTC_RATED_POWER: dict[str, int] = {
    "2001": 5000,
    "2002": 4600,
    "2003": 3600,
    "2101": 5000,
    "2102": 4600,
    "2103": 3600,
    "2104": 6000,
    "2105": 7000,
    "2106": 8000,
    "2201": 5000,
    "2202": 4600,
    "2203": 3600,
    "2204": 6000,
    "2205": 7000,
    "2206": 8000,
    "2301": 5000,
    "2302": 4600,
    "2303": 3600,
    "2304": 6000,
    "3001": 3000,
    "3002": 3600,
    "4001": 6000,
    "4002": 8000,
    "4003": 10000,
    "4004": 11000,
    "7001": 12000,
    "8001": 6000,
    "8002": 3600,
    "8003": 5000,
    "8101": 6000,
    "8102": 8000,
    "8103": 10000,
    "8201": 6000,
    "8202": 8000,
    "8203": 10000,
    "8204": 12000,
    "8304": 6000,
}


_DTC_BATPOWER: dict[str, int] = {
    "2201": 5400,
    "3001": 3000,
    "3002": 3000,
    "8001": 6000,
    "8002": 3600,
    "8003": 5000,
    "8102": 8000,
    "8103": 10000,
}


def _battery_max_power(dtc_str: str, fw: int) -> int | None:
    """Map DTC hex string + ARM firmware to rated battery charge/discharge power in watts.

    Returns None for an unmapped DTC — the table is incomplete and unverified against
    hardware docs, so an unknown model is an honest "unknown", not 0 W. Consumers must
    treat None as "rated power unavailable" rather than "no capacity" (the latter is what
    a 0 would have implied to e.g. a watt↔percent conversion or a dispatch coordinator).
    """
    if dtc_str is None or fw is None:
        return None
    if dtc_str[:2] == "20":
        return 3600 if math.floor(int(fw) / 100) in (3, 8, 9) else 2600
    return _DTC_BATPOWER.get(dtc_str)


def _inverter_fault_code(val: int) -> list[str] | None:
    """Decode a 32-bit inverter fault bitmask into a list of active fault names.

    Bit table sourced from britkat1980/givenergy-modbus-async; not verified against
    official firmware documentation (contact @britkat1980 for provenance).
    Three-phase units use a different 9-word fault register layout (IR 1300–1307).
    """
    if val is None:
        return None
    _FAULTS = [
        None,
        None,
        None,
        "Backup Overload Fault",
        None,
        None,
        "Grid Monitor Comm Fault",
        "ARM Comms Fault",
        "Consistent Fault",
        "EEPROM Fault",
        None,
        None,
        None,
        None,
        None,
        None,
        "Inverter Frequency Fault",
        "Relay Fault",
        "Inverter Voltage Fault",
        "GFCI Fault",
        "Hail Sensor Fault",
        "DSP Comms Fault",
        "Bus over voltage",
        "Inverter Current Fault",
        "No Utility",
        "PV Isolation Fault",
        "Current leak high",
        "DCI high",
        "PV Over voltage",
        "Grid voltage Fault",
        "Grid Frequency Fault",
        "Inverter NTC Fault",
        None,
    ]
    bits = f"{val:032b}"
    return [f for i, b in enumerate(bits) if b == "1" and (f := _FAULTS[i]) is not None]


def resolve_model(raw_dtc: int, arm_fw: int) -> Model:
    """Return the most specific Model for a given device type code and ARM firmware version.

    `raw_dtc` is the raw integer value of HR(0) (e.g. 0x2001).
    `arm_fw` is the raw ARM firmware version integer from HR(21).

    Use this in preference to plain `Model(dtc)` when you have both values available.
    `Model(dtc)` continues to work and returns the coarse family for backward compat.
    """
    dtc = f"{raw_dtc:04x}"
    prefix = dtc[:2]
    if prefix == "20":
        return _HYBRID_FW_CENTURY_TO_GEN.get(arm_fw // 100, Model.HYBRID_GEN1)
    return _DTC_PREFIX_TO_MODEL.get(prefix, Model(dtc))


def inverter_address_for(model: Model) -> int:
    """Return the modbus device address the inverter's registers are served at.

    `0x11` is the canonical inverter address for all models. AC and HYBRID_GEN1
    units additionally expose their registers at `0x31` — a facade over the same
    register file (value-equality verified across 114 shared HR registers on a
    live HYBRID_GEN1, and byte-identical HR banks on two live AC units; #189) —
    but `0x11` is where the official app reads and writes, and where ``detect()``
    always reads identity. EMS and All-in-One controllers likewise serve all
    their data — including the IR/HR(2040) rollup — at `0x11`.

    Capabilities persisted before the `0x31` retirement may still carry an
    explicit ``inverter_address`` of `0x31`; that keeps working (the hardware
    facade still answers there) and self-heals to `0x11` on the next
    ``detect()``.
    """
    return 0x11


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


class WorkMode(IntEnum):
    """Inverter work mode."""

    INITIALISING = 0
    OFF_GRID = 1
    ON_GRID = 2
    FAULT = 3
    UPDATE = 4

    @classmethod
    def _missing_(cls, value):
        return cls.INITIALISING


class Certification(IntEnum):
    """Grid compliance certification."""

    UNKNOWN = 0
    G98 = 8
    G99 = 12
    G98_NI = 16
    G99_NI = 17

    @classmethod
    def _missing_(cls, value):
        return cls.UNKNOWN


class InverterType(IntEnum):
    """Inverter phase and voltage type."""

    SINGLE_PHASE_LV = 0
    SINGLE_PHASE_HV = 1
    THREE_PHASE_LV = 2
    THREE_PHASE_HV = 3

    @classmethod
    def _missing_(cls, value):
        return cls.SINGLE_PHASE_LV


class Generation(StrEnum):
    """Inverter hardware generation."""

    GEN1 = "Gen 1"
    GEN2 = "Gen 2"
    GEN3 = "Gen 3"
    GEN3_PLUS = "Gen 3+"
    GEN4 = "Gen 4"
    AIO2 = "AIO 2"
    UNKNOWN = "Unknown"


_DTC_PREFIX_TO_PHASE = {
    "2": 1,
    "3": 1,
    "4": 3,
    "5": 1,
    "6": 3,
    "7": 1,
    "8": 1,
}


class Phase(IntEnum):
    """Number of AC phases."""

    ONE = 1
    THREE = 3

    @classmethod
    def _missing_(cls, value):
        """Accept a DTC string and map its first digit to a phase count."""
        if isinstance(value, str) and value[:1] in _DTC_PREFIX_TO_PHASE:
            return cls(_DTC_PREFIX_TO_PHASE[value[:1]])
        return None


class ChargeStatus(IntEnum):
    """Known charge-status codes observed on single-phase inverters (IR(14), #222).

    Raw int accessible via `charge_status`; typed label via `charge_status_label`.
    Unknown codes decode to ``None`` via `charge_status_label` rather than raising.
    """

    IDLE = 0
    CHARGING = 2
    FINISHING = 3
    DISCHARGING = 5


def _charge_status_from(code: int) -> "ChargeStatus | None":
    """Lenient ChargeStatus decode — returns None for unknown codes (#222)."""
    try:
        return ChargeStatus(code)
    except ValueError:
        return None


class SinglePhaseInverterRegisterGetter(RegisterGetter):
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
        # HR(8-12) was first_battery_serial_number — removed (#191): GivTCP-heritage,
        # unused, unverifiable; on AIO firmware it held the unit serial byte-swapped,
        # not a battery serial. Still redacted in captures via an explicit serial group
        # in client._build_serial_register_groups (recoverable to the real serial).
        "serial_number": Def(C.serial, None, HR(13), HR(14), HR(15), HR(16), HR(17)),
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
        # Offset-unsigned PF: (raw / 10,000) − 1. See Converter.pf for the encoding
        # rationale and its distinction from the meter's pf_signed registers.
        "power_factor": Def(C.pf, None, HR(52), min=-1.0, max=1.0),
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
        "v_pv_start": Def(C.uint16, C.deci, HR(60), min=0.0, max=2000.0),
        "start_countdown_timer": Def(C.uint16, None, HR(61)),
        "restart_delay_time": Def(C.uint16, None, HR(62)),
        # AC grid protection — voltage/frequency limits and trip-time settings.
        # Names aligned with the three-phase equivalents in inverter_threephase.py.
        # Converters inferred from the 3ph parallel block (HR1018-1042); unverified
        # against a live single-phase capture — mark uncertain with raw uint16 if
        # a future capture disagrees.
        "v_ac_low_limit_1": Def(C.uint16, C.deci, HR(63), min=0.0, max=500.0),
        "v_ac_high_limit_1": Def(C.uint16, C.deci, HR(64), min=0.0, max=500.0),
        "f_ac_low_limit_1": Def(C.uint16, C.centi, HR(65), min=40.0, max=70.0),
        "f_ac_high_limit_1": Def(C.uint16, C.centi, HR(66), min=40.0, max=70.0),
        "t_ac_low_voltage_1": Def(C.uint16, C.centi, HR(67)),
        "t_ac_high_voltage_1": Def(C.uint16, C.centi, HR(68)),
        "t_ac_low_freq_1": Def(C.uint16, C.centi, HR(69)),
        "t_ac_high_freq_1": Def(C.uint16, C.centi, HR(70)),
        "v_ac_low_limit_2": Def(C.uint16, C.deci, HR(71), min=0.0, max=500.0),
        "v_ac_high_limit_2": Def(C.uint16, C.deci, HR(72), min=0.0, max=500.0),
        "f_ac_low_limit_2": Def(C.uint16, C.centi, HR(73), min=40.0, max=70.0),
        "f_ac_high_limit_2": Def(C.uint16, C.centi, HR(74), min=40.0, max=70.0),
        "t_ac_low_voltage_2": Def(C.uint16, C.centi, HR(75)),
        "t_ac_high_voltage_2": Def(C.uint16, C.centi, HR(76)),
        "t_ac_low_freq_2": Def(C.uint16, C.centi, HR(77)),
        "t_ac_high_freq_2": Def(C.uint16, C.centi, HR(78)),
        "v_ac_low_limit_3": Def(C.uint16, C.deci, HR(79), min=0.0, max=500.0),
        "v_ac_high_limit_3": Def(C.uint16, C.deci, HR(80), min=0.0, max=500.0),
        "f_ac_low_limit_3": Def(C.uint16, C.centi, HR(81), min=40.0, max=70.0),
        "f_ac_high_limit_3": Def(C.uint16, C.centi, HR(82), min=40.0, max=70.0),
        "v_ac_10min_protect": Def(C.uint16, C.deci, HR(83), min=0.0, max=500.0),
        # skip HR(84-93) — unlabelled in the app's writable map
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
        "enable_inverter_parallel_mode": Def(C.bool, None, HR(199)),
        "cmd_bms_flash_update": Def(C.bool, None, HR(200)),
        "inverter_errors": Def(C.uint32, None, HR(223), HR(224)),
        "inverter_fault_messages": Def(C.uint32, _inverter_fault_code, HR(223), HR(224)),
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
        # Holding Registers, block 554-573
        # Smart Load scheduling — 10 time-window slots (HR554-573).
        # app: "Smart Load Start/End Time 1..10"
        #
        "smart_load_slot_1": Def(C.timeslot, None, HR(554), HR(555)),
        "smart_load_slot_2": Def(C.timeslot, None, HR(556), HR(557)),
        "smart_load_slot_3": Def(C.timeslot, None, HR(558), HR(559)),
        "smart_load_slot_4": Def(C.timeslot, None, HR(560), HR(561)),
        "smart_load_slot_5": Def(C.timeslot, None, HR(562), HR(563)),
        "smart_load_slot_6": Def(C.timeslot, None, HR(564), HR(565)),
        "smart_load_slot_7": Def(C.timeslot, None, HR(566), HR(567)),
        "smart_load_slot_8": Def(C.timeslot, None, HR(568), HR(569)),
        "smart_load_slot_9": Def(C.timeslot, None, HR(570), HR(571)),
        "smart_load_slot_10": Def(C.timeslot, None, HR(572), HR(573)),
        #
        # Holding Registers, block 300-359
        # Single Phase New registers
        # This block is polled for non-EMS / non-gateway inverters; see client.py.
        #
        # HR(308-310): battery topology — rated power (W), rated current (A), max charge
        # percentage. Extracted from GE app 4.0.7 binary; scale unconfirmed on live hardware.
        "battery_nominal_power": Def(C.uint16, None, HR(308)),
        "battery_nominal_current": Def(C.uint16, None, HR(309)),
        "battery_max_charge_pct": Def(C.uint16, None, HR(310)),
        # HR(311): export priority — confirmed writable on Model.AC via portal observations
        # (hass#52): values 0/1/2 matched "Battery First / Grid First / Load First".
        "export_priority": Def(C.uint16, ExportPriority, HR(311)),
        "battery_charge_limit_ac": Def(C.uint16, None, HR(313)),
        "battery_discharge_limit_ac": Def(C.uint16, None, HR(314)),
        # HR(317): EPS enable — confirmed writable on Model.AC via portal observations
        # (hass#52): toggled 0/1 while the portal's "EPS" switch was flipped off/on.
        "enable_eps": Def(C.bool, None, HR(317)),
        "battery_pause_mode": Def(C.uint16, None, HR(318)),
        "battery_pause_slot_1": Def(C.timeslot, None, HR(319), HR(320)),
        #
        # Holding Registers, block 499-510
        # HV cabinet topology — extracted from GE app 4.0.7 binary; poll gated off for
        # every model pending a confirming hardware capture (see _HV_CABINET_MODELS in
        # plant.py). Values are raw uint16 counts/ratings; exact scaling unconfirmed.
        #
        "hv_cabinet_count": Def(C.uint16, None, HR(499)),
        "hv_racks_per_cabinet": Def(C.uint16, None, HR(500)),
        "hv_batteries_per_rack": Def(C.uint16, None, HR(501)),
        "hv_cells_per_battery": Def(C.uint16, None, HR(502)),
        "hv_total_cells": Def(C.uint16, None, HR(503)),
        "hv_temp_sensors_per_battery": Def(C.uint16, None, HR(504)),
        "hv_total_temp_sensors": Def(C.uint16, None, HR(505)),
        "hv_max_pcs_power": Def(C.uint16, None, HR(506)),
        "hv_max_charge_voltage": Def(C.uint16, None, HR(507)),
        "hv_min_discharge_voltage": Def(C.uint16, None, HR(508)),
        "hv_max_charge_current": Def(C.uint16, None, HR(509)),
        "hv_parallel_count": Def(C.uint16, None, HR(510)),
        #
        # Holding Registers, block 20000-20051
        # Peak-shaving / valley-filling — extracted from GE app 4.0.7 binary; poll gated
        # off for every model pending a confirming hardware capture (see _PEAK_SHAVING_MODELS
        # in plant.py). Sparse: defined registers at 20000-20003, 20020-20021, 20050-20051.
        #
        "peak_shaving_export_limit_enabled": Def(C.bool, None, HR(20000)),
        "peak_shaving_export_limit": Def(C.uint16, None, HR(20001)),
        "peak_shaving_enabled": Def(C.bool, None, HR(20002)),
        "peak_shaving_threshold": Def(C.uint16, None, HR(20003)),
        "peak_shaving_import_limit_enabled": Def(C.bool, None, HR(20020)),
        "peak_shaving_import_limit": Def(C.uint16, None, HR(20021)),
        "peak_shaving_power": Def(C.uint16, None, HR(20050)),
        "valley_filling_power": Def(C.uint16, None, HR(20051)),
        #
        # Holding Registers, block 4080-4139
        #
        "pv_power_setting": Def(C.uint32, None, HR(4107), HR(4108)),
        # DEAD: never polled. No read path in this repo or GivTCP requests HR>=4000
        # (our max poll base is HR(240); GivTCP's add_regs detect-probe candidates top
        # out at HR(300)). Defined for naming symmetry with the IR alt sources and as
        # scaffold for a future #48 "does this block respond on real hardware?" probe;
        # no model's _BATTERY_ENERGY_SOURCE routes here. The C.deci scaling diverges
        # from GivTCP's raw (None) defs — moot while unpolled, reconcile under #48.
        "e_battery_discharge_total_alt2": Def(C.uint32, C.deci, HR(4109), HR(4110)),
        "e_battery_charge_total_alt2": Def(C.uint32, C.deci, HR(4111), HR(4112)),
        "e_battery_discharge_today_alt3": Def(C.uint16, C.deci, HR(4113)),
        "e_battery_charge_today_alt3": Def(C.uint16, C.deci, HR(4114)),
        #
        # Holding Registers, block 4140-4199
        #
        "e_inverter_export_total": Def(C.uint32, None, HR(4141), HR(4142)),
        #
        # Input Registers, block 0-59
        #
        # Power-register physical nodes (single-phase Hybrid, empirically established
        # against SA2114G047 — see docs/usage.md "Power register measurement points"):
        # the instantaneous "grid" registers do NOT all measure the same point.
        #
        #   PV ─DC─┐                       ┌─► house load            IR(42) p_load_demand
        #          ├─[INVERTER]─AC─busbar──┤
        #   Bat ─DC┘   terminal            └─► grid CT ─► meter      IR(30) p_grid_out
        #          IR(24)/IR(43)/IR(58)         boundary
        #
        # IR(24) p_grid_out_ph1, IR(43) p_grid_apparent, IR(58) i_grid_port → INVERTER
        #   AC terminal (real W / apparent VA / current at the busbar).
        # IR(30) p_grid_out → EXTERNAL grid CT net flow (the meter boundary).
        # IR(42) p_load_demand → house load, independently sensed (not IR24−IR30).
        # The shared "grid" prefix hides that IR(24)≠IR(30) are different nodes.
        "status": Def(C.uint16, Status, IR(0)),
        "v_pv1": Def(C.deci, None, IR(1), min=0.0, max=2000.0),
        "v_pv2": Def(C.deci, None, IR(2), min=0.0, max=2000.0),
        "v_p_bus": Def(C.deci, None, IR(3)),
        "v_n_bus": Def(C.deci, None, IR(4)),
        "v_ac1": Def(C.deci, None, IR(5), min=0.0, max=500.0),
        "e_battery_throughput": Def(C.uint32, C.deci, IR(6), IR(7)),
        "i_pv1": Def(C.deci, None, IR(8), min=0.0, max=500.0),
        "i_pv2": Def(C.deci, None, IR(9), min=0.0, max=500.0),
        "i_ac1": Def(C.deci, None, IR(10), min=0.0, max=500.0),
        "e_pv_total": Def(C.uint32, C.deci, IR(11), IR(12)),
        "f_ac1": Def(C.centi, None, IR(13), min=40.0, max=70.0),
        "charge_status": Def(C.uint16, None, IR(14), deprecated="use charge_status_label"),
        "charge_status_label": Def(C.uint16, _charge_status_from, IR(14)),
        "v_highbrigh_bus": Def(C.deci, None, IR(15)),
        "pf_inverter_output_now": Def(C.pf, None, IR(16), min=-1.0, max=1.0),  # offset-unsigned, see power_factor
        "e_pv1_day": Def(C.deci, None, IR(17)),
        "p_pv1": Def(C.uint16, None, IR(18), max=50000),
        "e_pv2_day": Def(C.deci, None, IR(19)),
        "p_pv2": Def(C.uint16, None, IR(20), max=50000),
        "e_grid_out_total": Def(C.uint32, C.deci, IR(21), IR(22)),
        "e_solar_diverter": Def(C.deci, None, IR(23)),
        # Inverter AC grid-terminal real power (flow onto the busbar), +ve = delivering.
        # NOT the external grid CT despite the "grid_out" name — see the node note above.
        "p_grid_out_ph1": Def(C.int16, None, IR(24)),
        "e_grid_out_day": Def(C.deci, None, IR(25)),
        "e_grid_in_day": Def(C.deci, None, IR(26)),
        "e_inverter_in_total": Def(C.uint32, C.deci, IR(27), IR(28)),
        "e_discharge_year": Def(C.deci, None, IR(29)),
        # External grid-CT net flow at the meter boundary, +ve = export / −ve = import.
        # A DIFFERENT physical node from IR(24): IR(30) is the grid clamp, IR(24) is the
        # inverter terminal. (GivTCP's `grid_power` reads this same register.)
        "p_grid_out": Def(C.int16, None, IR(30)),
        "p_backup": Def(C.uint16, None, IR(31), max=50000),  # EPS
        "e_grid_in_total": Def(C.uint32, C.deci, IR(32), IR(33)),
        # IR(34) unknown, skip
        # IR(35) is AC-charge-today, NOT house-load/consumption. The GivTCP-era
        # "e_load_day" name was a mislabel (#174): sentinel cross-correlation via the
        # GE app's Energy-today screen confirmed IR(35) backs "AC charge today". The
        # app's "Consumption today" is computed, not a register — see e_consumption_today
        # on SinglePhaseInverter. Aligned to the existing three-phase e_ac_charge_today
        # name so the three-phase native (IR1376/7) overrides this inherited entry.
        "e_ac_charge_today": Def(C.deci, None, IR(35)),
        "e_battery_charge_today_alt1": Def(C.deci, None, IR(36)),
        "e_battery_discharge_today_alt1": Def(C.deci, None, IR(37)),
        "countdown": Def(C.uint16, None, IR(38)),
        "fault_code": Def(C.uint32, (C.hex, 8), IR(39), IR(40)),
        "t_inverter_heatsink": Def(C.deci, None, IR(41), min=-40.0, max=100.0),
        # House load / consumption at the busbar, independently sensed — empirically NOT
        # a derived IR(24)−IR(30) identity (residual non-zero in 68% of samples, though
        # small and centred on zero). That residual is NOT the EPS branch: across 259
        # EPS-active samples (HYBRID 0x31 + AIO 0x11) it tracks 0, not p_backup (IR31), so
        # IR42 already INCLUDES EPS ("of which", not additional) — consumers must not add
        # IR(31) on top. See tests/debug/eps_in_load_demand.py.
        "p_load_demand": Def(C.uint16, None, IR(42), max=50000),
        # Inverter AC grid-terminal apparent power (VA); pairs with IR(24), not IR(30)
        # (IR43/IR24 → plausible PF ~0.9; IR43/IR30 → impossible). Same node as IR(24).
        "p_grid_apparent": Def(C.uint16, None, IR(43), max=50000),
        # IR(44) is PV-generation-today and IR(45/46) is PV-generation-total (both
        # sentinel cross-correlation, #174), not the inverter AC output. Renamed from
        # "e_inverter_out_day" / "e_inverter_out_total"; the old names are kept as
        # deprecated @property aliases for a release.
        # NB: this rename is single-phase only. ThreePhaseInverter has its OWN native
        # e_inverter_out_total (IR1362/3) — a genuine, distinct register from its PV
        # total (e_pv_total, IR1374/5) — so the 3ph field is left untouched.
        "e_pv_generation_today": Def(C.deci, None, IR(44)),
        "e_pv_generation_total": Def(C.uint32, C.deci, IR(45), IR(46)),
        # Hours since first power-on. Wire data on HYBRID_GEN1 ticks once per
        # wall-clock hour and persists across reboots; cap at ~100 years to
        # reject obviously-garbage uint32 values. The `_hours` suffix carries
        # the unit at the call site (see #84); `work_time_total` is preserved
        # as a deprecated alias on the inverter classes for a release.
        "work_time_total_hours": Def(C.uint32, None, IR(47), IR(48), max=876_000),
        "system_mode": Def(C.uint16, None, IR(49)),
        "v_battery": Def(C.centi, None, IR(50), min=0.0, max=100.0),
        "i_battery": Def(C.int16, C.centi, IR(51), min=-300.0, max=300.0),
        "p_battery": Def(C.int16, None, IR(52)),
        "v_ac1_output": Def(C.deci, None, IR(53), min=0.0, max=500.0),  # might be v_eps_backup?
        "f_ac1_output": Def(C.centi, None, IR(54), min=40.0, max=70.0),  # might be f_eps_backup?
        "t_charger": Def(C.deci, None, IR(55), min=-40.0, max=100.0),
        "t_battery": Def(C.deci, None, IR(56), min=-40.0, max=100.0),
        "charger_warning_code": Def(C.uint16, None, IR(57)),
        # Inverter AC grid-terminal current; pairs with IR(24)/IR(43) (I×V ≈ IR43 VA),
        # the inverter terminal — not the external CT. Same node as IR(24).
        "i_grid_port": Def(C.centi, None, IR(58)),
        "battery_soc": Def(C.uint16, None, IR(59), min=0, max=100),
        #
        # Input Registers, block 180-239
        #
        "e_battery_discharge_total_alt1": Def(C.deci, None, IR(180)),
        "e_battery_charge_total_alt1": Def(C.deci, None, IR(181)),
        "e_battery_discharge_today_alt2": Def(C.deci, None, IR(182)),
        "e_battery_charge_today_alt2": Def(C.deci, None, IR(183)),
        #
        # Input Registers, block 240-300
        # Gen3
        #
        "p_combined_generation": Def(C.uint32, None, IR(247), IR(248), max=100000),
    }


# Per-(specific-model, metric) authoritative battery-energy source, keyed on the
# Model resolved by resolve_model() — NOT the coarse `self.model` family. Declared
# only where a wire capture positively confirms it; an absent model or metric routes
# to None (honest "no evidence yet" + a forcing function for which captures to chase).
# "today"/"total" each map to an altN whose register name is built as
# e_battery_{charge,discharge}_{metric}_{altN} (see _battery_energy / the LUT renames).
#
#   alt1 = IR(36/37) daily, IR(180/181) total   alt2 = IR(182/183) daily, HR total (dead)
#   alt3 = HR(4113/4114) daily (dead, never polled — see #48)
#
# Evidence (tests/fixtures/captures/): GEN1 populates the alt2 daily registers as
# authoritative (non-alt read 0 on some firmware) and IR alt1 totals (17526/14791).
# AC/AIO populate alt1 daily; their IR totals read a real 0 and where the lifetime
# total actually lives is unknown (the HR block is never polled by anyone) — so total
# is deliberately left undeclared → None rather than reporting a misleading 0.
_BATTERY_ENERGY_SOURCE: dict[Model, dict[str, str]] = {
    Model.HYBRID_GEN1: {"today": "alt2", "total": "alt1"},
    Model.AC: {"today": "alt1"},
    Model.ALL_IN_ONE: {"today": "alt1"},
}


_SinglePhaseInverterBase = create_model(  # type: ignore[call-overload]
    "SinglePhaseInverter",
    __config__=ConfigDict(frozen=True),
    **SinglePhaseInverterRegisterGetter.to_fields(),
)


class SinglePhaseInverter(  # type: ignore[valid-type,misc]
    _SinglePhaseInverterBase, _InverterCommands, RegisterMetadataMixin
):
    """GivEnergy single-phase inverter data model.

    Composes the `_InverterCommands` mixin so consumers can call
    `inverter.set_*(...)` directly instead of routing through
    `givenergy_modbus.client.commands.*`. The mixin reads `self.slot_map` so
    slot setters no longer need it threaded through by callers. Model-specific
    command mixins (three-phase, EMS, pause-mode) will compose in additively
    in later 2.x minors — see #75.
    """

    REGISTER_GETTER: ClassVar[type[RegisterGetter]] = SinglePhaseInverterRegisterGetter

    @classmethod
    def from_register_cache(cls, register_cache) -> "SinglePhaseInverter":
        """Construct a SinglePhaseInverter from a RegisterCache."""
        return cls.model_validate(SinglePhaseInverterRegisterGetter(register_cache).build())

    def p_pv(self) -> int | None:
        """Computes the total PV power, or None if either input is unavailable."""
        if self.p_pv1 is None or self.p_pv2 is None:  # type: ignore[attr-defined]
            return None
        return self.p_pv1 + self.p_pv2  # type: ignore[attr-defined]

    def e_pv_day(self) -> float | None:
        """Computes the total PV energy for the day, or None if either input is unavailable."""
        if self.e_pv1_day is None or self.e_pv2_day is None:  # type: ignore[attr-defined]
            return None
        return self.e_pv1_day + self.e_pv2_day  # type: ignore[attr-defined]

    def _battery_energy(self, direction: str, metric: str) -> float | None:
        """Route a battery-energy metric to this model's authoritative alt register.

        Which register location a firmware populates is a *static* property of the
        model, not something to infer from live values (the #119 lesson — see #76 /
        Codex review on #150). `_BATTERY_ENERGY_SOURCE` declares, per specific model,
        which `altN` source is authoritative for each metric; the value is returned
        verbatim including a legitimate 0.0. Returns None when the model or metric is
        undeclared (honest "no evidence yet") — no value inspection, no cross-source
        fallback. Resolves the *specific* model the way `slot_map` does: `self.model`
        decodes HR(0) alone and only yields the coarse family (e.g. HYBRID, not
        HYBRID_GEN1), which would miss the models we special-case.
        """
        dtc = self.device_type_code  # type: ignore[attr-defined]
        arm_fw = self.arm_firmware_version  # type: ignore[attr-defined]
        if dtc is None or arm_fw is None:
            return None
        model = resolve_model(int(dtc, 16), int(arm_fw))
        alt = _BATTERY_ENERGY_SOURCE.get(model, {}).get(metric)
        if alt is None:
            return None
        return getattr(self, f"e_battery_{direction}_{metric}_{alt}")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def e_battery_charge_today(self) -> float | None:
        """Canonical daily battery charge energy (kWh), routed by model (see #76)."""
        return self._battery_energy("charge", "today")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def e_battery_discharge_today(self) -> float | None:
        """Canonical daily battery discharge energy (kWh), routed by model (see #76)."""
        return self._battery_energy("discharge", "today")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def e_battery_charge_total(self) -> float | None:
        """Canonical total battery charge energy (kWh), routed by model (see #76)."""
        return self._battery_energy("charge", "total")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def e_battery_discharge_total(self) -> float | None:
        """Canonical total battery discharge energy (kWh), routed by model (see #76)."""
        return self._battery_energy("discharge", "total")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def grid_import_power(self) -> int | None:
        """Non-negative grid import power (W); zero when exporting or idle (#205)."""
        if self.p_grid_out is None:  # type: ignore[attr-defined]
            return None
        return max(0, -self.p_grid_out)  # type: ignore[attr-defined]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def grid_export_power(self) -> int | None:
        """Non-negative grid export power (W); zero when importing or idle (#205)."""
        if self.p_grid_out is None:  # type: ignore[attr-defined]
            return None
        return max(0, self.p_grid_out)  # type: ignore[attr-defined]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def battery_charge_power(self) -> int | None:
        """Non-negative battery charge power (W); zero when discharging or idle (#205)."""
        if self.p_battery is None:  # type: ignore[attr-defined]
            return None
        return max(0, -self.p_battery)  # type: ignore[attr-defined]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def battery_discharge_power(self) -> int | None:
        """Non-negative battery discharge power (W); zero when charging or idle (#205)."""
        if self.p_battery is None:  # type: ignore[attr-defined]
            return None
        return max(0, self.p_battery)  # type: ignore[attr-defined]

    @property
    def slot_map(self) -> SlotMap:
        """Register address pairs for the charge/discharge time slots on this model."""
        dtc = self.device_type_code  # type: ignore[attr-defined]
        arm_fw = self.arm_firmware_version  # type: ignore[attr-defined]
        if dtc is None or arm_fw is None:
            return SINGLE_PHASE_SLOTS
        model = resolve_model(int(dtc, 16), int(arm_fw))
        if model in (Model.ALL_IN_ONE, Model.HYBRID_GEN4, Model.HYBRID_HV_GEN3):
            return EXTENDED_SLOTS
        if model is Model.HYBRID_GEN3 and int(arm_fw) > 302:
            return EXTENDED_SLOTS
        return SINGLE_PHASE_SLOTS

    @computed_field  # type: ignore[prop-decorator]
    @property
    def battery_capacity_kwh(self) -> float | None:
        """Returns the nominal battery capacity in kWh, derived from Ah and model voltage."""
        if self.battery_capacity_ah is None or self.model is None:  # type: ignore[attr-defined]
            return None
        return self.battery_capacity_ah * self.model.system_battery_voltage / 1000  # type: ignore[attr-defined]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def battery_max_power(self) -> int | None:
        """Returns the rated battery charge/discharge power in watts, derived from model and firmware."""
        return _battery_max_power(self.device_type_code, self.arm_firmware_version)  # type: ignore[attr-defined]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def inverter_max_power(self) -> int | None:
        """Returns the rated inverter power in watts, derived from the device type code."""
        return _DTC_RATED_POWER.get(self.device_type_code)  # type: ignore[attr-defined]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_ac_coupled(self) -> bool:
        """True for AC-coupled inverters (no integrated DC battery).

        Coarse-family resolution is correct here: AC DTCs resolve to Model.AC /
        Model.AC_3PH and neither has specific sub-variants. False when the model is
        unknown (DTC unread).
        """
        return self.model in AC_COUPLED_MODELS  # type: ignore[attr-defined]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def e_consumption_today(self) -> float | None:
        """House consumption today (kWh), matching the GE app's "Consumption today".

        DERIVED, not metered: single-phase units expose no consumption register, so the
        GE app computes this value. Sentinel cross-correlation against the app's
        Energy-today screen (#174) recovered the exact formula:

            consumption = pv_generation + grid_import − grid_export − ac_charge

        Battery DC charge/discharge throughput nets out and is not a term. The result
        carries the same conversion-loss bias the app shows (energy balance overshoots
        real consumption by a few %). This is the GE-universe definition of
        "consumption" specifically — other plant equipment may define it differently.

        Three-phase units have a native e_load_today register and so do NOT get this
        computed field (it lives on SinglePhaseInverter only, not in the register LUT).
        Returns None if any input is unavailable.
        """
        pv = self.e_pv_generation_today  # type: ignore[attr-defined]
        grid_in = self.e_grid_in_day  # type: ignore[attr-defined]
        grid_out = self.e_grid_out_day  # type: ignore[attr-defined]
        ac_charge = self.e_ac_charge_today  # type: ignore[attr-defined]
        if None in (pv, grid_in, grid_out, ac_charge):
            return None
        return pv + grid_in - grid_out - ac_charge

    @computed_field  # type: ignore[prop-decorator]
    @property
    def e_self_consumption_today(self) -> float | None:
        """Self-consumption energy today (kWh): PV generation used on-site (GivTCP parity).

        DERIVED: PV generation today − grid export today, clamped at ≥ 0.

        Two limitations to be aware of:
        - Battery-to-grid export is counted in grid_out, so this slightly under-counts
          true self-consumption when the battery discharges to grid. GivTCP accepts this
          approximation; we match it here.
        - NOT monotonically increasing: when battery exports to grid, grid_out rises
          without pv_generation rising, causing the difference to dip. Consumers that
          use state_class TOTAL_INCREASING (e.g. HA energy dashboard) MUST apply their
          own monotonic clamp rather than consuming the raw value directly.

        Returns None if any input is unavailable.
        """
        pv = self.e_pv_generation_today  # type: ignore[attr-defined]
        grid_out = self.e_grid_out_day  # type: ignore[attr-defined]
        if None in (pv, grid_out):
            return None
        return max(0.0, pv - grid_out)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def e_self_consumption_total(self) -> float | None:
        """Lifetime self-consumption energy (kWh): PV generation used on-site (GivTCP parity).

        DERIVED: PV generation total − grid export total, clamped at ≥ 0.

        Same battery-to-grid under-count and non-monotonicity caveats as
        e_self_consumption_today: the difference of two running counters is not
        guaranteed to increase monotonically. Consumers using state_class
        TOTAL_INCREASING MUST apply a monotonic clamp (e.g. HA's monotonic=True
        sensor path) rather than consuming the raw value directly.

        Returns None if any input is unavailable.
        """
        pv = self.e_pv_generation_total  # type: ignore[attr-defined]
        grid_out = self.e_grid_out_total  # type: ignore[attr-defined]
        if None in (pv, grid_out):
            return None
        return max(0.0, pv - grid_out)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def e_pv_direct_today(self) -> float | None:
        """PV energy used directly by load today (kWh): solar bypassing battery and grid.

        DERIVED: (pv_generation − grid_export) − pv_to_battery, clamped to [0, pv − grid_export],
        where pv_to_battery = max(0, battery_charge − ac_charge).

        e_battery_charge lumps PV-sourced and AC-sourced charge into one counter, so the
        PV portion that went to the battery is battery_charge − ac_charge — subtracting it
        leaves the PV that reached load directly. Without the ac_charge term the figure
        would under-count by the day's AC-charge energy on time-of-use tariffs (Octopus Go
        / Predbat); for pure-solar systems ac_charge is 0 and it's a no-op.

        Both bounds matter. The lower clamp (≥ 0) handles export exceeding PV. The upper
        clamp (≤ pv − grid_export, via flooring pv_to_battery at 0) handles AC→DC
        conversion loss / counter skew making ac_charge momentarily exceed battery_charge:
        without it, direct PV could exceed total on-site PV self-consumption, which is
        nonsensical (a subset can't beat its superset) — Codex review on #313.

        Restricted to DC-coupled solar hybrids: on AC-coupled and All-in-One units the
        PV-generation registers (IR44/45-46) are mislabelled — they read non-zero on
        battery-only hardware (#293) — so the field returns None there rather than a
        confident wrong value. In practice e_battery_charge_today only routes on
        HYBRID_GEN1 today (see _BATTERY_ENERGY_SOURCE / #184), so the field is currently
        GEN1-effective and returns None on other DC models until that map widens.

        Only daily is offered: the lifetime equivalent needs e_ac_charge_total, which
        single-phase firmware does not expose (three-phase only, IR1378/9).

        NOT monotonically increasing intraday — a grid-export burst can dip it — so
        consumers using state_class TOTAL_INCREASING MUST apply their own monotonic clamp
        (e.g. HA's monotonic=True path). Returns None if any input is unavailable or the
        model is ineligible.
        """
        if self.is_ac_coupled or self.model is Model.ALL_IN_ONE:  # type: ignore[attr-defined]
            return None
        pv = self.e_pv_generation_today  # type: ignore[attr-defined]
        grid_out = self.e_grid_out_day  # type: ignore[attr-defined]
        battery_charge = self.e_battery_charge_today
        ac_charge = self.e_ac_charge_today  # type: ignore[attr-defined]
        if None in (pv, grid_out, battery_charge, ac_charge):
            return None
        # PV that charged the battery, floored at 0: AC→DC conversion loss / counter skew
        # can push ac_charge above battery_charge, which would otherwise make this negative
        # and inflate direct PV beyond total on-site PV. Round to the inputs' native 0.1 kWh
        # resolution — a deci-scaled difference accrues float noise that 1dp removes losslessly.
        pv_to_battery = max(0.0, battery_charge - ac_charge)
        return round(max(0.0, pv - grid_out - pv_to_battery), 1)

    # Plain @property (not @computed_field) so the deprecated alias doesn't
    # appear in model_dump() output. See #84 — renamed to work_time_total_hours
    # to put the unit at the call site.
    @property
    def work_time_total(self) -> int | None:
        """Deprecated alias for `work_time_total_hours`."""
        warnings.warn(
            "SinglePhaseInverter.work_time_total is deprecated; use work_time_total_hours",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.work_time_total_hours  # type: ignore[attr-defined,no-any-return]

    # Plain @property so the deprecated alias doesn't appear in model_dump().
    # HR(199) was decoded as enable_standard_self_consumption_logic (GivTCP-era guess);
    # the GE app names it "Enable Inverter Parallel Mode". The new field name is
    # enable_inverter_parallel_mode; this alias preserves back-compat for existing
    # consumers. Hass: keep your current entity using this property and fold the
    # entity-ID rename into the one-shot #106 migration — do NOT migrate now.
    @property
    def enable_standard_self_consumption_logic(self) -> bool | None:
        """Deprecated alias for `enable_inverter_parallel_mode`."""
        warnings.warn(
            "SinglePhaseInverter.enable_standard_self_consumption_logic is deprecated; "
            "use enable_inverter_parallel_mode",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.enable_inverter_parallel_mode  # type: ignore[attr-defined,no-any-return]

    # Plain @property so the deprecated alias doesn't appear in model_dump().
    # IR(44) was decoded as e_inverter_out_day (GivTCP-era guess); sentinel
    # cross-correlation (#174) confirmed it is PV-generation-today. Renamed to
    # e_pv_generation_today; this alias preserves back-compat for a release.
    @property
    def e_inverter_out_day(self) -> float | None:
        """Deprecated alias for `e_pv_generation_today`."""
        warnings.warn(
            "SinglePhaseInverter.e_inverter_out_day is deprecated; use e_pv_generation_today",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.e_pv_generation_today  # type: ignore[attr-defined,no-any-return]

    # IR(45/46) was decoded as e_inverter_out_total (GivTCP-era guess); the same
    # sentinel cross-correlation (#174) confirmed it is PV-generation-total. Renamed
    # to e_pv_generation_total; this alias preserves back-compat for a release.
    # Single-phase only: ThreePhaseInverter keeps its native e_inverter_out_total
    # (IR1362/3), which is a genuine register there, so no alias is defined on 3ph.
    @property
    def e_inverter_out_total(self) -> float | None:
        """Deprecated alias for `e_pv_generation_total`."""
        warnings.warn(
            "SinglePhaseInverter.e_inverter_out_total is deprecated; use e_pv_generation_total",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.e_pv_generation_total  # type: ignore[attr-defined,no-any-return]


def __getattr__(name: str):
    if name == "Inverter":
        warnings.warn(
            "Inverter has been renamed to SinglePhaseInverter and the alias will be removed in a future release. "
            "Use select_inverter() to obtain the correct model for a given device.",
            DeprecationWarning,
            stacklevel=2,
        )
        return SinglePhaseInverter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
