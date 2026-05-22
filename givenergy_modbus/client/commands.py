"""High-level methods for interacting with a remote system."""

from datetime import datetime
from datetime import time as dt_time
from typing import TYPE_CHECKING, ClassVar
from warnings import deprecated  # type: ignore[attr-defined]

from givenergy_modbus.model import TimeSlot
from givenergy_modbus.model.battery import BatteryPauseMode
from givenergy_modbus.model.slot_map import SINGLE_PHASE_SLOTS, SlotMap
from givenergy_modbus.pdu import (
    ReadHoldingRegistersRequest,
    ReadInputRegistersRequest,
    TransparentRequest,
    WriteHoldingRegisterRequest,
)


class RegisterMap:
    """Mapping of holding register function to location."""

    ENABLE_CHARGE_TARGET = 20
    BATTERY_POWER_MODE = 27
    SOC_FORCE_ADJUST = 29
    CHARGE_SLOT_2_START = 31
    CHARGE_SLOT_2_END = 32
    SYSTEM_TIME_YEAR = 35
    SYSTEM_TIME_MONTH = 36
    SYSTEM_TIME_DAY = 37
    SYSTEM_TIME_HOUR = 38
    SYSTEM_TIME_MINUTE = 39
    SYSTEM_TIME_SECOND = 40
    DISCHARGE_SLOT_2_START = 44
    DISCHARGE_SLOT_2_END = 45
    ACTIVE_POWER_RATE = 50
    DISCHARGE_SLOT_1_START = 56
    DISCHARGE_SLOT_1_END = 57
    ENABLE_DISCHARGE = 59
    CHARGE_SLOT_1_START = 94
    CHARGE_SLOT_1_END = 95
    ENABLE_CHARGE = 96
    BATTERY_SOC_RESERVE = 110
    BATTERY_CHARGE_LIMIT = 111
    BATTERY_DISCHARGE_LIMIT = 112
    BATTERY_DISCHARGE_MIN_POWER_RESERVE = 114
    CHARGE_TARGET_SOC = 116
    REBOOT = 163
    ENABLE_RTC = 166
    CHARGE_SLOT_3_START = 246
    CHARGE_SLOT_3_END = 247
    CHARGE_SLOT_4_START = 249
    CHARGE_SLOT_4_END = 250
    CHARGE_SLOT_5_START = 252
    CHARGE_SLOT_5_END = 253
    CHARGE_SLOT_6_START = 255
    CHARGE_SLOT_6_END = 256
    CHARGE_SLOT_7_START = 258
    CHARGE_SLOT_7_END = 259
    CHARGE_SLOT_8_START = 261
    CHARGE_SLOT_8_END = 262
    CHARGE_SLOT_9_START = 264
    CHARGE_SLOT_9_END = 265
    CHARGE_SLOT_10_START = 267
    CHARGE_SLOT_10_END = 268
    DISCHARGE_SLOT_3_START = 276
    DISCHARGE_SLOT_3_END = 277
    DISCHARGE_SLOT_4_START = 279
    DISCHARGE_SLOT_4_END = 280
    DISCHARGE_SLOT_5_START = 282
    DISCHARGE_SLOT_5_END = 283
    DISCHARGE_SLOT_6_START = 285
    DISCHARGE_SLOT_6_END = 286
    DISCHARGE_SLOT_7_START = 288
    DISCHARGE_SLOT_7_END = 289
    DISCHARGE_SLOT_8_START = 291
    DISCHARGE_SLOT_8_END = 292
    DISCHARGE_SLOT_9_START = 294
    DISCHARGE_SLOT_9_END = 295
    DISCHARGE_SLOT_10_START = 297
    DISCHARGE_SLOT_10_END = 298
    BATTERY_CHARGE_LIMIT_AC = 313
    BATTERY_DISCHARGE_LIMIT_AC = 314
    BATTERY_PAUSE_MODE = 318
    BATTERY_PAUSE_SLOT_START = 319
    BATTERY_PAUSE_SLOT_END = 320
    AC_CHARGE_ENABLE = 1112
    FORCE_DISCHARGE_ENABLE = 1122
    FORCE_CHARGE_ENABLE = 1123
    EMS_PLANT_ENABLE = 2040
    EXPORT_SLOT_1_START = 2062
    EXPORT_SLOT_1_END = 2063
    EXPORT_SLOT_2_START = 2065
    EXPORT_SLOT_2_END = 2066
    EXPORT_SLOT_3_START = 2068
    EXPORT_SLOT_3_END = 2069


def refresh_plant_data(complete: bool, number_batteries: int = 1, max_batteries: int = 5) -> list[TransparentRequest]:
    """Refresh plant data."""
    requests: list[TransparentRequest] = [
        ReadInputRegistersRequest(base_register=0, register_count=60, device_address=0x32),
        ReadInputRegistersRequest(base_register=180, register_count=60, device_address=0x32),
    ]
    if complete:
        requests.append(ReadHoldingRegistersRequest(base_register=0, register_count=60, device_address=0x32))
        requests.append(ReadHoldingRegistersRequest(base_register=60, register_count=60, device_address=0x32))
        requests.append(ReadHoldingRegistersRequest(base_register=120, register_count=60, device_address=0x32))
        requests.append(ReadInputRegistersRequest(base_register=120, register_count=60, device_address=0x32))
        number_batteries = max_batteries
    for i in range(number_batteries):
        requests.append(ReadInputRegistersRequest(base_register=60, register_count=60, device_address=0x32 + i))
    return requests


def disable_charge_target() -> list[TransparentRequest]:
    """Removes SOC limit and target 100% charging."""
    return [
        WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE_TARGET, False),
        WriteHoldingRegisterRequest(RegisterMap.CHARGE_TARGET_SOC, 100),
    ]


def set_charge_target(target_soc: int) -> list[TransparentRequest]:
    """Sets inverter to stop charging when SOC reaches the desired level. Also referred to as "winter mode"."""
    if not 4 <= target_soc <= 100:
        raise ValueError(f"Charge Target SOC ({target_soc}) must be in [4-100]%")
    ret = set_enable_charge(True)
    if target_soc == 100:
        ret.extend(disable_charge_target())
    else:
        ret.append(WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE_TARGET, True))
        ret.append(WriteHoldingRegisterRequest(RegisterMap.CHARGE_TARGET_SOC, target_soc))
    return ret


def set_enable_charge(enabled: bool) -> list[TransparentRequest]:
    """Enable the battery to charge, depending on the mode and slots set."""
    return [WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE, enabled)]


def set_enable_discharge(enabled: bool) -> list[TransparentRequest]:
    """Enable the battery to discharge, depending on the mode and slots set."""
    return [WriteHoldingRegisterRequest(RegisterMap.ENABLE_DISCHARGE, enabled)]


def set_inverter_reboot() -> list[TransparentRequest]:
    """Restart the inverter."""
    return [WriteHoldingRegisterRequest(RegisterMap.REBOOT, 100)]


def set_calibrate_battery_soc(val: int = 1) -> list[TransparentRequest]:
    """Set the inverter to recalibrate the battery state of charge estimation.

    val: 0 = Stop, 1 = Start, 3 = Charge Only
    """
    if val not in (0, 1, 3):
        raise ValueError(f"Battery calibration mode ({val}) must be 0 (Stop), 1 (Start) or 3 (Charge Only)")
    return [WriteHoldingRegisterRequest(RegisterMap.SOC_FORCE_ADJUST, val)]


@deprecated("use set_enable_charge(True) instead")
def enable_charge() -> list[TransparentRequest]:
    """Enable the battery to charge, depending on the mode and slots set."""
    return set_enable_charge(True)


@deprecated("use set_enable_charge(False) instead")
def disable_charge() -> list[TransparentRequest]:
    """Prevent the battery from charging at all."""
    return set_enable_charge(False)


@deprecated("use set_enable_discharge(True) instead")
def enable_discharge() -> list[TransparentRequest]:
    """Enable the battery to discharge, depending on the mode and slots set."""
    return set_enable_discharge(True)


@deprecated("use set_enable_discharge(False) instead")
def disable_discharge() -> list[TransparentRequest]:
    """Prevent the battery from discharging at all."""
    return set_enable_discharge(False)


def set_discharge_mode_max_power() -> list[TransparentRequest]:
    """Set the battery discharge mode to maximum power, exporting to the grid if it exceeds load demand."""
    return [WriteHoldingRegisterRequest(RegisterMap.BATTERY_POWER_MODE, 0)]


def set_discharge_mode_to_match_demand() -> list[TransparentRequest]:
    """Set the battery discharge mode to match demand, avoiding exporting power to the grid."""
    return [WriteHoldingRegisterRequest(RegisterMap.BATTERY_POWER_MODE, 1)]


@deprecated("Use set_battery_soc_reserve(val) instead")
def set_shallow_charge(val: int) -> list[TransparentRequest]:
    """Set the minimum level of charge to maintain."""
    return set_battery_soc_reserve(val)


def set_battery_soc_reserve(val: int) -> list[TransparentRequest]:
    """Set the minimum level of charge to maintain."""
    # TODO what are valid values? 4-100?
    val = int(val)
    if not 4 <= val <= 100:
        raise ValueError(f"Minimum SOC / shallow charge ({val}) must be in [4-100]%")
    return [WriteHoldingRegisterRequest(RegisterMap.BATTERY_SOC_RESERVE, val)]


def set_battery_charge_limit(val: int) -> list[TransparentRequest]:
    """Set the battery charge power limit as percentage. 50% (2.6 kW) is the maximum for most inverters."""
    val = int(val)
    if not 0 <= val <= 50:
        raise ValueError(f"Specified Charge Limit ({val}%) is not in [0-50]%")
    return [WriteHoldingRegisterRequest(RegisterMap.BATTERY_CHARGE_LIMIT, val)]


def set_battery_discharge_limit(val: int) -> list[TransparentRequest]:
    """Set the battery discharge power limit as percentage. 50% (2.6 kW) is the maximum for most inverters."""
    val = int(val)
    if not 0 <= val <= 50:
        raise ValueError(f"Specified Discharge Limit ({val}%) is not in [0-50]%")
    return [WriteHoldingRegisterRequest(RegisterMap.BATTERY_DISCHARGE_LIMIT, val)]


def set_battery_power_reserve(val: int) -> list[TransparentRequest]:
    """Set the battery power reserve to maintain."""
    # TODO what are valid values?
    val = int(val)
    if not 4 <= val <= 100:
        raise ValueError(f"Battery power reserve ({val}) must be in [4-100]%")
    return [WriteHoldingRegisterRequest(RegisterMap.BATTERY_DISCHARGE_MIN_POWER_RESERVE, val)]


def set_active_power_rate(target: int) -> list[TransparentRequest]:
    """Set the inverter's active power output as a percentage of its rated capacity."""
    target = int(target)
    if not 0 <= target <= 100:
        raise ValueError(f"Active power rate ({target}) must be in [0-100]%")
    return [WriteHoldingRegisterRequest(RegisterMap.ACTIVE_POWER_RATE, target)]


def set_enable_rtc(enabled: bool) -> list[TransparentRequest]:
    """Enable the Real Time Clock register to persist settings to EEPROM."""
    return [WriteHoldingRegisterRequest(RegisterMap.ENABLE_RTC, enabled)]


def set_battery_charge_limit_ac(val: int) -> list[TransparentRequest]:
    """Set the battery AC charge power limit as a percentage."""
    val = int(val)
    if not 1 <= val <= 100:
        raise ValueError(f"Specified AC Charge Limit ({val}%) is not in [1-100]%")
    return [WriteHoldingRegisterRequest(RegisterMap.BATTERY_CHARGE_LIMIT_AC, val)]


def set_battery_discharge_limit_ac(val: int) -> list[TransparentRequest]:
    """Set the battery AC discharge power limit as a percentage."""
    val = int(val)
    if not 1 <= val <= 100:
        raise ValueError(f"Specified AC Discharge Limit ({val}%) is not in [1-100]%")
    return [WriteHoldingRegisterRequest(RegisterMap.BATTERY_DISCHARGE_LIMIT_AC, val)]


def set_battery_pause_mode(val: BatteryPauseMode) -> list[TransparentRequest]:
    """Set the battery pause mode."""
    return [WriteHoldingRegisterRequest(RegisterMap.BATTERY_PAUSE_MODE, val)]


def set_pause_slot_start(t: dt_time | None) -> list[TransparentRequest]:
    """Set just the start of the battery pause slot, or clear it if t is None."""
    return _set_slot_endpoint(RegisterMap.BATTERY_PAUSE_SLOT_START, t)


def set_pause_slot_end(t: dt_time | None) -> list[TransparentRequest]:
    """Set just the end of the battery pause slot, or clear it if t is None."""
    return _set_slot_endpoint(RegisterMap.BATTERY_PAUSE_SLOT_END, t)


def set_pause_slot(slot: TimeSlot | None) -> list[TransparentRequest]:
    """Set the battery pause time slot, or clear it if slot is None."""
    start = slot.start if slot else None
    end = slot.end if slot else None
    return set_pause_slot_start(start) + set_pause_slot_end(end)


def set_ac_charge(enabled: bool) -> list[TransparentRequest]:
    """Enable AC charging on three-phase inverters."""
    return [WriteHoldingRegisterRequest(RegisterMap.AC_CHARGE_ENABLE, enabled)]


def set_force_charge(enabled: bool) -> list[TransparentRequest]:
    """Enable forced battery charging on three-phase inverters."""
    return [WriteHoldingRegisterRequest(RegisterMap.FORCE_CHARGE_ENABLE, enabled)]


def set_force_discharge(enabled: bool) -> list[TransparentRequest]:
    """Enable forced battery discharging on three-phase inverters."""
    return [WriteHoldingRegisterRequest(RegisterMap.FORCE_DISCHARGE_ENABLE, enabled)]


def set_ems_plant(enabled: bool) -> list[TransparentRequest]:
    """Enable EMS plant control."""
    return [WriteHoldingRegisterRequest(RegisterMap.EMS_PLANT_ENABLE, enabled)]


def _export_slot_registers(idx: int) -> tuple[int, int]:
    if not 1 <= idx <= 3:
        raise ValueError(f"Export slot index ({idx}) must be in [1-3]")
    return getattr(RegisterMap, f"EXPORT_SLOT_{idx}_START"), getattr(RegisterMap, f"EXPORT_SLOT_{idx}_END")


def set_export_slot_start(idx: int, t: dt_time | None) -> list[TransparentRequest]:
    """Set just the start of an export time slot by index (1–3), or clear it if t is None."""
    hr_start, _ = _export_slot_registers(idx)
    return _set_slot_endpoint(hr_start, t)


def set_export_slot_end(idx: int, t: dt_time | None) -> list[TransparentRequest]:
    """Set just the end of an export time slot by index (1–3), or clear it if t is None."""
    _, hr_end = _export_slot_registers(idx)
    return _set_slot_endpoint(hr_end, t)


def set_export_slot(idx: int, slot: TimeSlot | None) -> list[TransparentRequest]:
    """Set an export time slot by index (1–3), or clear it if slot is None."""
    _export_slot_registers(idx)  # index validation
    start = slot.start if slot else None
    end = slot.end if slot else None
    return set_export_slot_start(idx, start) + set_export_slot_end(idx, end)


def _set_slot_endpoint(hr: int, t: dt_time | None) -> list[TransparentRequest]:
    """Write a single slot-endpoint register: HHMM-encoded time, or 0 to clear."""
    return [WriteHoldingRegisterRequest(hr, int(t.strftime("%H%M")) if t else 0)]


def _resolve_slot_registers(discharge: bool, idx: int, slot_map: SlotMap) -> tuple[int, int]:
    slots = slot_map.discharge_slots if discharge else slot_map.charge_slots
    n = len(slots)
    if not 1 <= idx <= n:
        label = "Discharge" if discharge else "Charge"
        raise ValueError(f"{label} slot index ({idx}) must be in [1-{n}] for the given slot map")
    return slots[idx - 1]


def set_charge_slot_start(idx: int, t: dt_time | None, slot_map: SlotMap) -> list[TransparentRequest]:
    """Set just the start of a charge slot by index (1-based), or clear it if t is None."""
    hr_start, _ = _resolve_slot_registers(False, idx, slot_map)
    return _set_slot_endpoint(hr_start, t)


def set_charge_slot_end(idx: int, t: dt_time | None, slot_map: SlotMap) -> list[TransparentRequest]:
    """Set just the end of a charge slot by index (1-based), or clear it if t is None."""
    _, hr_end = _resolve_slot_registers(False, idx, slot_map)
    return _set_slot_endpoint(hr_end, t)


def set_discharge_slot_start(idx: int, t: dt_time | None, slot_map: SlotMap) -> list[TransparentRequest]:
    """Set just the start of a discharge slot by index (1-based), or clear it if t is None."""
    hr_start, _ = _resolve_slot_registers(True, idx, slot_map)
    return _set_slot_endpoint(hr_start, t)


def set_discharge_slot_end(idx: int, t: dt_time | None, slot_map: SlotMap) -> list[TransparentRequest]:
    """Set just the end of a discharge slot by index (1-based), or clear it if t is None."""
    _, hr_end = _resolve_slot_registers(True, idx, slot_map)
    return _set_slot_endpoint(hr_end, t)


def set_charge_slot(idx: int, timeslot: TimeSlot, slot_map: SlotMap) -> list[TransparentRequest]:
    """Set charge slot start & end times by index (1-based)."""
    start = timeslot.start if timeslot else None
    end = timeslot.end if timeslot else None
    return set_charge_slot_start(idx, start, slot_map) + set_charge_slot_end(idx, end, slot_map)


def reset_charge_slot(idx: int, slot_map: SlotMap) -> list[TransparentRequest]:
    """Reset charge slot to zero/disabled by index (1-based)."""
    return set_charge_slot_start(idx, None, slot_map) + set_charge_slot_end(idx, None, slot_map)


def set_discharge_slot(idx: int, timeslot: TimeSlot, slot_map: SlotMap) -> list[TransparentRequest]:
    """Set discharge slot start & end times by index (1-based)."""
    start = timeslot.start if timeslot else None
    end = timeslot.end if timeslot else None
    return set_discharge_slot_start(idx, start, slot_map) + set_discharge_slot_end(idx, end, slot_map)


def reset_discharge_slot(idx: int, slot_map: SlotMap) -> list[TransparentRequest]:
    """Reset discharge slot to zero/disabled by index (1-based)."""
    return set_discharge_slot_start(idx, None, slot_map) + set_discharge_slot_end(idx, None, slot_map)


@deprecated("use set_charge_slot(1, timeslot, slot_map) instead")
def set_charge_slot_1(timeslot: TimeSlot, slot_map: SlotMap = SINGLE_PHASE_SLOTS) -> list[TransparentRequest]:
    """Deprecated: use set_charge_slot(1, timeslot, slot_map)."""
    return set_charge_slot(1, timeslot, slot_map)


@deprecated("use reset_charge_slot(1, slot_map) instead")
def reset_charge_slot_1(slot_map: SlotMap = SINGLE_PHASE_SLOTS) -> list[TransparentRequest]:
    """Deprecated: use reset_charge_slot(1, slot_map)."""
    return reset_charge_slot(1, slot_map)


@deprecated("use set_charge_slot(2, timeslot, slot_map) instead")
def set_charge_slot_2(timeslot: TimeSlot, slot_map: SlotMap = SINGLE_PHASE_SLOTS) -> list[TransparentRequest]:
    """Deprecated: use set_charge_slot(2, timeslot, slot_map)."""
    return set_charge_slot(2, timeslot, slot_map)


@deprecated("use reset_charge_slot(2, slot_map) instead")
def reset_charge_slot_2(slot_map: SlotMap = SINGLE_PHASE_SLOTS) -> list[TransparentRequest]:
    """Deprecated: use reset_charge_slot(2, slot_map)."""
    return reset_charge_slot(2, slot_map)


@deprecated("use set_discharge_slot(1, timeslot, slot_map) instead")
def set_discharge_slot_1(timeslot: TimeSlot, slot_map: SlotMap = SINGLE_PHASE_SLOTS) -> list[TransparentRequest]:
    """Deprecated: use set_discharge_slot(1, timeslot, slot_map)."""
    return set_discharge_slot(1, timeslot, slot_map)


@deprecated("use reset_discharge_slot(1, slot_map) instead")
def reset_discharge_slot_1(slot_map: SlotMap = SINGLE_PHASE_SLOTS) -> list[TransparentRequest]:
    """Deprecated: use reset_discharge_slot(1, slot_map)."""
    return reset_discharge_slot(1, slot_map)


@deprecated("use set_discharge_slot(2, timeslot, slot_map) instead")
def set_discharge_slot_2(timeslot: TimeSlot, slot_map: SlotMap = SINGLE_PHASE_SLOTS) -> list[TransparentRequest]:
    """Deprecated: use set_discharge_slot(2, timeslot, slot_map)."""
    return set_discharge_slot(2, timeslot, slot_map)


@deprecated("use reset_discharge_slot(2, slot_map) instead")
def reset_discharge_slot_2(slot_map: SlotMap = SINGLE_PHASE_SLOTS) -> list[TransparentRequest]:
    """Deprecated: use reset_discharge_slot(2, slot_map)."""
    return reset_discharge_slot(2, slot_map)


def set_system_date_time(dt: datetime) -> list[TransparentRequest]:
    """Set the date & time of the inverter."""
    return [
        WriteHoldingRegisterRequest(RegisterMap.SYSTEM_TIME_YEAR, dt.year - 2000),
        WriteHoldingRegisterRequest(RegisterMap.SYSTEM_TIME_MONTH, dt.month),
        WriteHoldingRegisterRequest(RegisterMap.SYSTEM_TIME_DAY, dt.day),
        WriteHoldingRegisterRequest(RegisterMap.SYSTEM_TIME_HOUR, dt.hour),
        WriteHoldingRegisterRequest(RegisterMap.SYSTEM_TIME_MINUTE, dt.minute),
        WriteHoldingRegisterRequest(RegisterMap.SYSTEM_TIME_SECOND, dt.second),
    ]


def set_mode_dynamic() -> list[TransparentRequest]:
    """Set system to Dynamic / Eco mode.

    This mode is designed to maximise use of solar generation. The battery will charge from excess solar
    generation to avoid exporting power, and discharge to meet load demand when solar power is insufficient to
    avoid importing power. This mode is useful if you want to maximise self-consumption of renewable generation
    and minimise the amount of energy drawn from the grid.
    """
    # r27=1 r110=4 r59=0
    return set_discharge_mode_to_match_demand() + set_battery_soc_reserve(4) + set_enable_discharge(False)


def set_mode_storage(
    discharge_slot_1: TimeSlot = TimeSlot.from_repr(1600, 700),
    discharge_slot_2: TimeSlot | None = None,
    discharge_for_export: bool = False,
) -> list[TransparentRequest]:
    """Set system to storage mode with specific discharge slots(s).

    This mode stores excess solar generation during the day and holds that energy ready for use later in the day.
    By default, the battery will start to discharge from 4pm-7am to cover energy demand during typical peak
    hours. This mode is particularly useful if you get charged more for your electricity at certain times to
    utilise the battery when it is most effective. If the second time slot isn't specified, it will be cleared.

    You can optionally also choose to export excess energy: instead of discharging to meet only your load demand,
    the battery will discharge at full power and any excess will be exported to the grid. This is useful if you
    have a variable export tariff (e.g. Agile export) and you want to target the peak times of day (e.g. 4pm-7pm)
    when it is most valuable to export energy.
    """
    if discharge_for_export:
        ret = set_discharge_mode_max_power()  # r27=0
    else:
        ret = set_discharge_mode_to_match_demand()  # r27=1
    # Intentionally do not set BATTERY_SOC_RESERVE (r110): forcing it to 100
    # disables discharge entirely on Gen2 (and is not what the official portal
    # does when selecting Timed Discharge / Timed Export presets). Callers who
    # want a specific reserve should set it explicitly via set_battery_soc_reserve().
    ret.extend(set_enable_discharge(True))  # r59=1
    ret.extend(set_discharge_slot(1, discharge_slot_1, SINGLE_PHASE_SLOTS))
    if discharge_slot_2:
        ret.extend(set_discharge_slot(2, discharge_slot_2, SINGLE_PHASE_SLOTS))
    else:
        ret.extend(reset_discharge_slot(2, SINGLE_PHASE_SLOTS))
    return ret


class _InverterCommands:
    """Commands every inverter supports, mixed into Inverter model classes.

    Methods delegate to the module-level primitive functions above so the
    primitives stay accessible to lower-level callers (tests, alternate code
    paths). The mixin's value-add is twofold: it removes the boilerplate of
    threading `slot_map` through every slot call (it's read from `self`), and
    it carries a per-model `WRITE_SAFE_REGISTERS` set so model-specific
    mixins can constrain the allowlist further than the global one.

    The base mixin's `WRITE_SAFE_REGISTERS` is the universally-applicable
    subset — registers every inverter accepts writes to. Three-phase / EMS /
    pause-mode commands and their registers will land in additional mixins
    (composed onto the relevant inverter classes) in later 2.x minors once
    the model-vs-firmware ambiguities flagged on #75 are resolved against
    real wire data.
    """

    # The slot setters below read self.slot_map. The attribute is provided by
    # the composed inverter class as a @property on SinglePhaseInverter /
    # ThreePhaseInverter — declare it under TYPE_CHECKING as a property here
    # so mypy sees the contract without creating a runtime annotation that
    # pydantic would try to register as a model field. Matching the subclass
    # property shape (read-only) keeps mypy happy that the subclass override
    # isn't widening the type.
    if TYPE_CHECKING:

        @property
        def slot_map(self) -> SlotMap: ...

    # Universally-applicable subset of pdu.write_registers.WRITE_SAFE_REGISTERS.
    # Excludes 313/314 (BATTERY_*_LIMIT_AC — ambiguous), 318-320 (pause mode),
    # 1112/1122/1123 (three-phase), and 2040/2062-2069 (EMS).
    WRITE_SAFE_REGISTERS: ClassVar[frozenset[int]] = frozenset(
        {
            20,  # ENABLE_CHARGE_TARGET
            27,  # BATTERY_POWER_MODE
            29,  # SOC_FORCE_ADJUST
            31,
            32,  # CHARGE_SLOT_2
            35,
            36,
            37,
            38,
            39,
            40,  # SYSTEM_TIME_*
            44,
            45,  # DISCHARGE_SLOT_2
            50,  # ACTIVE_POWER_RATE
            56,
            57,  # DISCHARGE_SLOT_1
            59,  # ENABLE_DISCHARGE
            94,
            95,  # CHARGE_SLOT_1
            96,  # ENABLE_CHARGE
            110,  # BATTERY_SOC_RESERVE
            111,  # BATTERY_CHARGE_LIMIT
            112,  # BATTERY_DISCHARGE_LIMIT
            114,  # BATTERY_DISCHARGE_MIN_POWER_RESERVE
            116,  # CHARGE_TARGET_SOC
            163,  # REBOOT
            166,  # ENABLE_RTC
            246,
            247,
            249,
            250,
            252,
            253,
            255,
            256,
            258,
            259,
            261,
            262,
            264,
            265,
            267,
            268,  # CHARGE_SLOT_3..10
            276,
            277,
            279,
            280,
            282,
            283,
            285,
            286,
            288,
            289,
            291,
            292,
            294,
            295,
            297,
            298,  # DISCHARGE_SLOT_3..10
        }
    )

    # --- charge target -------------------------------------------------------

    def disable_charge_target(self) -> list[TransparentRequest]:
        """Disable use of a charge target so the battery charges to 100%."""
        return disable_charge_target()

    def set_charge_target(self, target_soc: int) -> list[TransparentRequest]:
        """Sets inverter to stop charging when SOC reaches the desired level (4-100)."""
        return set_charge_target(target_soc)

    # --- charge/discharge enable --------------------------------------------

    def set_enable_charge(self, enabled: bool) -> list[TransparentRequest]:
        """Enable or disable battery charging."""
        return set_enable_charge(enabled)

    def set_enable_discharge(self, enabled: bool) -> list[TransparentRequest]:
        """Enable or disable battery discharging."""
        return set_enable_discharge(enabled)

    # --- inverter-level controls --------------------------------------------

    def set_inverter_reboot(self) -> list[TransparentRequest]:
        """Trigger the inverter to reboot."""
        return set_inverter_reboot()

    def set_calibrate_battery_soc(self, val: int = 1) -> list[TransparentRequest]:
        """Set the inverter to recalibrate the battery SOC estimation."""
        return set_calibrate_battery_soc(val)

    def set_active_power_rate(self, target: int) -> list[TransparentRequest]:
        """Limit the inverter's total output power as a percentage of its rated value (0-100)."""
        return set_active_power_rate(target)

    def set_enable_rtc(self, enabled: bool) -> list[TransparentRequest]:
        """Enable or disable the inverter's real-time clock."""
        return set_enable_rtc(enabled)

    def set_system_date_time(self, dt: datetime) -> list[TransparentRequest]:
        """Set the date & time of the inverter."""
        return set_system_date_time(dt)

    # --- discharge mode ------------------------------------------------------

    def set_discharge_mode_max_power(self) -> list[TransparentRequest]:
        """Set the battery discharge mode to maximum power, exporting to the grid if it exceeds load demand."""
        return set_discharge_mode_max_power()

    def set_discharge_mode_to_match_demand(self) -> list[TransparentRequest]:
        """Set the battery discharge mode to match demand, avoiding exporting to the grid."""
        return set_discharge_mode_to_match_demand()

    # --- battery limits/reserves --------------------------------------------

    def set_battery_soc_reserve(self, val: int) -> list[TransparentRequest]:
        """Set the minimum SOC reserve the battery is kept at, even in dynamic mode (4-100)."""
        return set_battery_soc_reserve(val)

    def set_battery_charge_limit(self, val: int) -> list[TransparentRequest]:
        """Set the battery charge power limit as a percentage of the rated charge power (0-50)."""
        return set_battery_charge_limit(val)

    def set_battery_discharge_limit(self, val: int) -> list[TransparentRequest]:
        """Set the battery discharge power limit as a percentage of the rated discharge power (0-50)."""
        return set_battery_discharge_limit(val)

    def set_battery_power_reserve(self, val: int) -> list[TransparentRequest]:
        """Set the minimum SOC reserve below which the battery will not discharge (4-100)."""
        return set_battery_power_reserve(val)

    # --- slots (use self.slot_map) ------------------------------------------

    def set_charge_slot_start(self, idx: int, t: dt_time | None) -> list[TransparentRequest]:
        """Set just the start of a charge slot by index (1-based), or clear it if t is None."""
        return set_charge_slot_start(idx, t, self.slot_map)

    def set_charge_slot_end(self, idx: int, t: dt_time | None) -> list[TransparentRequest]:
        """Set just the end of a charge slot by index (1-based), or clear it if t is None."""
        return set_charge_slot_end(idx, t, self.slot_map)

    def set_discharge_slot_start(self, idx: int, t: dt_time | None) -> list[TransparentRequest]:
        """Set just the start of a discharge slot by index (1-based), or clear it if t is None."""
        return set_discharge_slot_start(idx, t, self.slot_map)

    def set_discharge_slot_end(self, idx: int, t: dt_time | None) -> list[TransparentRequest]:
        """Set just the end of a discharge slot by index (1-based), or clear it if t is None."""
        return set_discharge_slot_end(idx, t, self.slot_map)

    def set_charge_slot(self, idx: int, timeslot: TimeSlot) -> list[TransparentRequest]:
        """Set charge slot start & end times by index (1-based)."""
        return set_charge_slot(idx, timeslot, self.slot_map)

    def reset_charge_slot(self, idx: int) -> list[TransparentRequest]:
        """Reset charge slot to zero/disabled by index (1-based)."""
        return reset_charge_slot(idx, self.slot_map)

    def set_discharge_slot(self, idx: int, timeslot: TimeSlot) -> list[TransparentRequest]:
        """Set discharge slot start & end times by index (1-based)."""
        return set_discharge_slot(idx, timeslot, self.slot_map)

    def reset_discharge_slot(self, idx: int) -> list[TransparentRequest]:
        """Reset discharge slot to zero/disabled by index (1-based)."""
        return reset_discharge_slot(idx, self.slot_map)

    # --- preset modes --------------------------------------------------------

    def set_mode_dynamic(self) -> list[TransparentRequest]:
        """Set system to Dynamic / Eco mode."""
        return set_mode_dynamic()

    def set_mode_storage(
        self,
        discharge_slot_1: TimeSlot,
        discharge_slot_2: TimeSlot | None = None,
        discharge_for_export: bool = False,
    ) -> list[TransparentRequest]:
        """Set system to Storage mode with specific discharge slot(s)."""
        return set_mode_storage(discharge_slot_1, discharge_slot_2, discharge_for_export)
