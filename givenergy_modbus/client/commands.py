"""High-level methods for interacting with a remote system."""

from datetime import datetime
from datetime import time as dt_time
from typing import TYPE_CHECKING, ClassVar

from typing_extensions import deprecated

from givenergy_modbus.exceptions import PlantNotDetected
from givenergy_modbus.model import TimeSlot
from givenergy_modbus.model.battery import BatteryPauseMode, ExportPriority
from givenergy_modbus.model.slot_map import EMS_SLOTS, SINGLE_PHASE_SLOTS, SlotMap
from givenergy_modbus.pdu import (
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
    EXPORT_PRIORITY = 311
    BATTERY_CHARGE_LIMIT_AC = 313
    BATTERY_DISCHARGE_LIMIT_AC = 314
    ENABLE_EPS = 317
    BATTERY_PAUSE_MODE = 318
    BATTERY_PAUSE_SLOT_START = 319
    BATTERY_PAUSE_SLOT_END = 320
    SMART_LOAD_SLOT_1_START = 554  # HR 554-573: 10 start/end pairs (slot N start = 554 + (N-1)*2)
    BATTERY_RESERVE_SOC = 1078  # three-phase only; no single-phase equivalent
    BATTERY_SOC_RESERVE_3PH = 1109  # three-phase shadow of BATTERY_SOC_RESERVE (110)
    CHARGE_TARGET_SOC_3PH = 1111  # three-phase shadow of CHARGE_TARGET_SOC (116)
    AC_CHARGE_ENABLE = 1112
    FORCE_DISCHARGE_ENABLE = 1122
    FORCE_CHARGE_ENABLE = 1123
    EMS_PLANT_ENABLE = 2040
    # EMS plant-level scheduling (HR 2044-2071). Slot start/end pairs live in
    # model/slot_map.EMS_SLOTS; the per-slot SoC targets and export limit are
    # scalar writes defined here. See model/ems.py for the read-side decode.
    EMS_DISCHARGE_TARGET_SOC_1 = 2046
    EMS_DISCHARGE_TARGET_SOC_2 = 2049
    EMS_DISCHARGE_TARGET_SOC_3 = 2052
    EMS_CHARGE_TARGET_SOC_1 = 2055
    EMS_CHARGE_TARGET_SOC_2 = 2058
    EMS_CHARGE_TARGET_SOC_3 = 2061
    EXPORT_SLOT_1_START = 2062
    EXPORT_SLOT_1_END = 2063
    EMS_EXPORT_TARGET_SOC_1 = 2064
    EXPORT_SLOT_2_START = 2065
    EXPORT_SLOT_2_END = 2066
    EMS_EXPORT_TARGET_SOC_2 = 2067
    EXPORT_SLOT_3_START = 2068
    EXPORT_SLOT_3_END = 2069
    EMS_EXPORT_TARGET_SOC_3 = 2070
    EMS_EXPORT_POWER_LIMIT = 2071
    # --- Installer-tier registers (accessible only via Client.installer_command()) ---
    # Grid protection — all require confirm=True (G98/G99/G100 compliance impact)
    V_AC_LOW_LIMIT_TRIP = 63
    V_AC_HIGH_LIMIT_TRIP = 64
    F_AC_LOW_LIMIT_TRIP = 65
    F_AC_HIGH_LIMIT_TRIP = 66
    T_AC_LOW_VOLTAGE_TRIP = 67
    T_AC_HIGH_VOLTAGE_TRIP = 68
    T_AC_LOW_FREQ_TRIP = 69
    T_AC_HIGH_FREQ_TRIP = 70
    V_AC_LOW_LIMIT_RECONNECT = 71
    V_AC_HIGH_LIMIT_RECONNECT = 72
    F_AC_LOW_LIMIT_RECONNECT = 73
    F_AC_HIGH_LIMIT_RECONNECT = 74
    T_AC_LOW_VOLTAGE_RECONNECT = 75
    T_AC_HIGH_VOLTAGE_RECONNECT = 76
    T_AC_LOW_FREQ_RECONNECT = 77
    T_AC_HIGH_FREQ_RECONNECT = 78
    V_AC_LOW_LIMIT_GRID = 79
    V_AC_HIGH_LIMIT_GRID = 80
    F_AC_LOW_LIMIT_GRID = 81
    F_AC_HIGH_LIMIT_GRID = 82
    V_AC_10MIN_PROTECT = 83
    ANTI_ISLANDING_DETECTION = 115
    RESET_ENERGY_TOTALS = 162
    GRID_IMPORT_LIMIT = 101
    GRID_IMPORT_LIMIT_ENABLED = 102
    BATTERY_NOMINAL_POWER = 308
    BATTERY_NOMINAL_CURRENT = 309
    BATTERY_MAX_CHARGE_PCT = 310
    ENABLE_PLANT_MODE = 300
    ENABLE_MICRO_GRID = 332
    ENABLE_EV_CHARGER = 333
    EV_CHARGER_SOC_LIMIT = 336
    ENABLE_GENERATOR = 343
    GENERATOR_START_SOC = 344
    GENERATOR_STOP_SOC = 345
    ENABLE_SMART_LOAD = 540
    SMART_LOAD_CONTROL_SOC = 541
    GENERAL_LOAD_CONTROL_SOC = 543
    GENERATOR_CONTROL_SOC = 544
    ENABLE_EXPORT_LIMIT_3PH = 1103
    ENABLE_IMPORT_LIMIT_3PH = 1131
    PEAK_SHAVING_EXPORT_LIMIT_ENABLED = 20000
    PEAK_SHAVING_EXPORT_LIMIT = 20001
    PEAK_SHAVING_ENABLED = 20002
    PEAK_SHAVING_THRESHOLD = 20003
    THREE_PHASE_FACTORY_RESET = 1016
    ENABLE_BLACK_START = 5003
    RESTORE_FACTORY_DEFAULTS = 5004


def _as_int(val: int | float, name: str) -> int:
    """Validate a numeric command argument as an integral number (audit L1).

    Fails loud on the silent-coercion caller-error class: bool subclasses int (True would
    write 1 or select slot 1's registers), a non-integral float would truncate (2.9 selecting
    slot 2), and a string is type confusion. Integral floats (50.0) are unambiguous and
    accepted. Numeric helpers route caller input through this instead of bare ``int(val)``.
    """
    if isinstance(val, bool) or not isinstance(val, int | float):
        raise ValueError(f"{name} must be a number, not {type(val).__name__}")
    i = int(val)
    if i != val:
        raise ValueError(f"{name} must be integral, got {val!r}")
    return i


@deprecated("Call Client.detect() then load_config()/refresh() instead — see PlantNotDetected.")
def refresh_plant_data(complete: bool, number_batteries: int = 1, max_batteries: int = 5) -> list[TransparentRequest]:
    """Removed: built a fixed 0x32-addressed poll that timed out on non-0x32 models.

    This helper hardcoded ``device_address=0x32`` for every read, which silently
    failed on models answering elsewhere (e.g. an All-in-One at 0x11 — issue #105).
    Capability-aware polling — ``Client.detect()`` then ``Client.load_config()`` /
    ``Client.refresh()`` — replaces it and addresses each device correctly.

    Kept as an import-compatible stub so existing imports don't break with an
    ``ImportError``; it raises ``PlantNotDetected`` to signpost the migration rather
    than rebuild the unsafe blind poll.
    """
    raise PlantNotDetected(
        "commands.refresh_plant_data() has been removed — it built a fixed 0x32 poll "
        "that timed out on models answering at other addresses (e.g. All-in-One at 0x11). "
        "Call Client.detect() once, then Client.load_config() / Client.refresh()."
    )


def disable_charge_target() -> list[TransparentRequest]:
    """Removes SOC limit and target 100% charging."""
    return [
        WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE_TARGET, 0),
        WriteHoldingRegisterRequest(RegisterMap.CHARGE_TARGET_SOC, 100),
    ]


def set_charge_target_enabled(target_soc: int) -> list[TransparentRequest]:
    """Enable charging and stop once SOC reaches target_soc. Also referred to as "winter mode"."""
    target_soc = _as_int(target_soc, "target_soc")
    if not 4 <= target_soc <= 100:
        raise ValueError(f"Charge Target SOC ({target_soc}) must be in [4-100]%")
    ret = set_enable_charge(True)
    if target_soc == 100:
        ret.extend(disable_charge_target())
    else:
        ret.append(WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE_TARGET, 1))
        ret.append(WriteHoldingRegisterRequest(RegisterMap.CHARGE_TARGET_SOC, target_soc))
    return ret


@deprecated("use set_charge_target_enabled(target_soc) instead")
def set_charge_target(target_soc: int) -> list[TransparentRequest]:
    """Deprecated: use set_charge_target_enabled(target_soc)."""
    return set_charge_target_enabled(target_soc)


def set_charge_target_soc(target_soc: int) -> list[TransparentRequest]:
    """Set only the charge target SOC (HR 116), leaving the charge / charge-target enable bits untouched."""
    target_soc = _as_int(target_soc, "target_soc")
    if not 4 <= target_soc <= 100:
        raise ValueError(f"Charge Target SOC ({target_soc}) must be in [4-100]%")
    return [WriteHoldingRegisterRequest(RegisterMap.CHARGE_TARGET_SOC, target_soc)]


def set_enable_charge(enabled: bool) -> list[TransparentRequest]:
    """Enable the battery to charge, depending on the mode and slots set."""
    return [WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE, 1 if enabled else 0)]


def set_enable_discharge(enabled: bool) -> list[TransparentRequest]:
    """Enable the battery to discharge, depending on the mode and slots set."""
    return [WriteHoldingRegisterRequest(RegisterMap.ENABLE_DISCHARGE, 1 if enabled else 0)]


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
    """Set the minimum level of charge to maintain.

    Bounds [4-100]% are unconfirmed against GE firmware docs (gone) but match
    GivTCP's independent choice for the same register — treat as the working
    assumption until a portal capture contradicts it.
    """
    val = _as_int(val, "val")
    if not 4 <= val <= 100:
        raise ValueError(f"Minimum SOC / shallow charge ({val}) must be in [4-100]%")
    return [WriteHoldingRegisterRequest(RegisterMap.BATTERY_SOC_RESERVE, val)]


def set_battery_reserve_soc(val: int) -> list[TransparentRequest]:
    """Set the battery reserve SOC on three-phase inverters (HR 1078, "Battery Reserve %").

    Three-phase only — single-phase units use set_battery_soc_reserve() (HR 110) instead.
    Bounds [4-100]% are unconfirmed (no GivTCP cross-reference exists for this register);
    treat as the working assumption until a live three-phase capture confirms them.
    """
    val = _as_int(val, "val")
    if not 4 <= val <= 100:
        raise ValueError(f"Battery reserve SOC ({val}) must be in [4-100]%")
    return [WriteHoldingRegisterRequest(RegisterMap.BATTERY_RESERVE_SOC, val)]


def disable_charge_target_3ph() -> list[TransparentRequest]:
    """Remove SOC limit and target 100% charging on three-phase inverters (HR 1111, shadows HR 116)."""
    return [
        WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE_TARGET, 0),
        WriteHoldingRegisterRequest(RegisterMap.CHARGE_TARGET_SOC_3PH, 100),
    ]


def set_battery_soc_reserve_3ph(val: int) -> list[TransparentRequest]:
    """Set the minimum SOC reserve on three-phase inverters (HR 1109, shadows single-phase HR 110)."""
    val = _as_int(val, "val")
    if not 4 <= val <= 100:
        raise ValueError(f"Minimum SOC / shallow charge ({val}) must be in [4-100]%")
    return [WriteHoldingRegisterRequest(RegisterMap.BATTERY_SOC_RESERVE_3PH, val)]


def set_charge_target_enabled_3ph(target_soc: int) -> list[TransparentRequest]:
    """Enable AC charging and set the charge target on three-phase inverters (HR 1111, shadows single-phase HR 116)."""
    target_soc = _as_int(target_soc, "target_soc")
    if not 4 <= target_soc <= 100:
        raise ValueError(f"Charge Target SOC ({target_soc}) must be in [4-100]%")
    ret = set_ac_charge(True)
    if target_soc == 100:
        ret.extend(
            [
                WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE_TARGET, 0),
                WriteHoldingRegisterRequest(RegisterMap.CHARGE_TARGET_SOC_3PH, 100),
            ]
        )
    else:
        ret.append(WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE_TARGET, 1))
        ret.append(WriteHoldingRegisterRequest(RegisterMap.CHARGE_TARGET_SOC_3PH, target_soc))
    return ret


@deprecated("use set_charge_target_enabled_3ph(target_soc) instead")
def set_charge_target_3ph(target_soc: int) -> list[TransparentRequest]:
    """Deprecated: use set_charge_target_enabled_3ph(target_soc)."""
    return set_charge_target_enabled_3ph(target_soc)


def set_charge_target_soc_3ph(target_soc: int) -> list[TransparentRequest]:
    """Set only the charge target SOC on three-phase inverters (HR 1111), leaving enable bits untouched."""
    target_soc = _as_int(target_soc, "target_soc")
    if not 4 <= target_soc <= 100:
        raise ValueError(f"Charge Target SOC ({target_soc}) must be in [4-100]%")
    return [WriteHoldingRegisterRequest(RegisterMap.CHARGE_TARGET_SOC_3PH, target_soc)]


def set_battery_charge_limit(val: int) -> list[TransparentRequest]:
    """Set the battery charge power limit as a percentage of rated charge power (0-100).

    This is a %-of-rated ceiling, not a current command. On DC-coupled hybrids the battery subsystem
    is often ~50% of inverter rating (Gen1: 2600 W of 5000 W), which is why GivTCP and older versions
    capped at 50. But the GE app itself writes >50 — field-tested writing 62% to HR(111) / 59% to
    HR(112) on a Gen1, both accepted — so the register tolerates it and the ~50% is model-specific.
    We accept 0-100 rather than hard-cap and wrongly reject valid values on hybrids with a larger
    battery subsystem. What the firmware does with a ceiling above the battery's capability (clamp to
    the real rating is the expectation) is not yet field-verified.
    """
    val = _as_int(val, "val")
    if not 0 <= val <= 100:
        raise ValueError(f"Specified Charge Limit ({val}%) is not in [0-100]%")
    return [WriteHoldingRegisterRequest(RegisterMap.BATTERY_CHARGE_LIMIT, val)]


def set_battery_discharge_limit(val: int) -> list[TransparentRequest]:
    """Set the battery discharge power limit as a percentage of rated discharge power (0-100).

    See :func:`set_battery_charge_limit` for why this accepts 0-100 (firmware clamps per-model)
    rather than the historical [0-50].
    """
    val = _as_int(val, "val")
    if not 0 <= val <= 100:
        raise ValueError(f"Specified Discharge Limit ({val}%) is not in [0-100]%")
    return [WriteHoldingRegisterRequest(RegisterMap.BATTERY_DISCHARGE_LIMIT, val)]


def set_battery_power_reserve(val: int) -> list[TransparentRequest]:
    """Set the battery power reserve to maintain.

    Bounds [4-100]% are unconfirmed against GE firmware docs (gone) but match
    GivTCP's independent choice for the same register — treat as the working
    assumption until a portal capture contradicts it.
    """
    val = _as_int(val, "val")
    if not 4 <= val <= 100:
        raise ValueError(f"Battery power reserve ({val}) must be in [4-100]%")
    return [WriteHoldingRegisterRequest(RegisterMap.BATTERY_DISCHARGE_MIN_POWER_RESERVE, val)]


def set_active_power_rate(target: int) -> list[TransparentRequest]:
    """Set the inverter's active power output as a percentage of its rated capacity.

    On an EMS-managed inverter this per-inverter write (HR50) is a silent no-op: it is accepted at
    the modbus layer (no error, unlike the AC-limit registers) but the EMS controller re-asserts its
    own value, so the change does not stick. There is no EMS-controller active-power-rate command to
    target instead (the EMS register block has none). See #304.
    """
    target = _as_int(target, "target")
    if not 0 <= target <= 100:
        raise ValueError(f"Active power rate ({target}) must be in [0-100]%")
    return [WriteHoldingRegisterRequest(RegisterMap.ACTIVE_POWER_RATE, target)]


def set_enable_rtc(enabled: bool) -> list[TransparentRequest]:
    """Enable the Real Time Clock register to persist settings to EEPROM."""
    return [WriteHoldingRegisterRequest(RegisterMap.ENABLE_RTC, 1 if enabled else 0)]


def set_export_priority(priority: ExportPriority) -> list[TransparentRequest]:
    """Set the export priority for surplus power on AC-coupled inverters.

    Determines where surplus energy goes: battery first, grid first, or load first.
    Confirmed writable on Model.AC via direct portal observations (hass#52).
    """
    # bool subclasses int, so ExportPriority(True) would resolve to BATTERY_FIRST (1) and pass as an
    # IntEnum — silently selecting a write mode. Reject it before the enum conversion (audit L1).
    if isinstance(priority, bool):
        raise ValueError(f"Export priority must be an ExportPriority, not bool (got {priority!r})")
    try:
        priority = ExportPriority(priority)
    except ValueError as e:
        raise ValueError(f"Invalid export priority: {priority}") from e
    return [WriteHoldingRegisterRequest(RegisterMap.EXPORT_PRIORITY, priority)]


def set_enable_eps(enabled: bool) -> list[TransparentRequest]:
    """Enable or disable Emergency Power Supply (EPS) mode on AC-coupled inverters.

    Confirmed writable on Model.AC via direct portal observations (hass#52).
    """
    return [WriteHoldingRegisterRequest(RegisterMap.ENABLE_EPS, 1 if enabled else 0)]


def set_battery_charge_limit_ac(val: int) -> list[TransparentRequest]:
    """Set the battery AC charge power limit as a percentage (1-100).

    The GE app exposes 0-100 for this control, but writing 0 to HR313/314 does NOT work in practice on
    (at least) the AC models tested — it ERRORs (hardware-confirmed via a single-phase AC tester:
    WriteHoldingRegisterResponse(ERROR) then a write timeout). So the floor is 1 and a 0 raises a clean
    ValueError rather than a doomed write; the 2.5.8 "0 disables" widening trusted the app range and was
    wrong. The 0-floor is AC-specific — the DC pair :func:`set_battery_charge_limit` legitimately
    accepts 0; writing 1 here drives the battery to near-zero.
    """
    val = _as_int(val, "val")
    if not 1 <= val <= 100:
        raise ValueError(f"Specified AC Charge Limit ({val}%) is not in [1-100]%")
    return [WriteHoldingRegisterRequest(RegisterMap.BATTERY_CHARGE_LIMIT_AC, val)]


def set_battery_discharge_limit_ac(val: int) -> list[TransparentRequest]:
    """Set the battery AC discharge power limit as a percentage (1-100).

    The GE app exposes 0-100 for this control, but writing 0 to HR313/314 does NOT work in practice on
    (at least) the AC models tested — it ERRORs (hardware-confirmed via a single-phase AC tester:
    WriteHoldingRegisterResponse(ERROR) then a write timeout). So the floor is 1 and a 0 raises a clean
    ValueError rather than a doomed write; the 2.5.8 "0 disables" widening trusted the app range and was
    wrong. The 0-floor is AC-specific — the DC pair :func:`set_battery_discharge_limit` legitimately
    accepts 0; writing 1 here drives the battery to near-zero.
    """
    val = _as_int(val, "val")
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


def set_smart_load_slot_start(idx: int, t: dt_time | None) -> list[TransparentRequest]:
    """Set the start time of Smart Load slot *idx* (1-based, 1–10), or clear it if t is None."""
    idx = _as_int(idx, "idx")
    if not (1 <= idx <= 10):
        raise ValueError(f"Smart Load slot index must be 1–10 (got {idx})")
    return _set_slot_endpoint(RegisterMap.SMART_LOAD_SLOT_1_START + (idx - 1) * 2, t)


def set_smart_load_slot_end(idx: int, t: dt_time | None) -> list[TransparentRequest]:
    """Set the end time of Smart Load slot *idx* (1-based, 1–10), or clear it if t is None."""
    idx = _as_int(idx, "idx")
    if not (1 <= idx <= 10):
        raise ValueError(f"Smart Load slot index must be 1–10 (got {idx})")
    return _set_slot_endpoint(RegisterMap.SMART_LOAD_SLOT_1_START + (idx - 1) * 2 + 1, t)


def set_smart_load_slot(idx: int, slot: "TimeSlot | None") -> list[TransparentRequest]:
    """Set Smart Load slot *idx* (1-based, 1–10) atomically, or clear it if slot is None."""
    start = slot.start if slot else None
    end = slot.end if slot else None
    return set_smart_load_slot_start(idx, start) + set_smart_load_slot_end(idx, end)


def set_ac_charge(enabled: bool) -> list[TransparentRequest]:
    """Enable AC charging on three-phase inverters."""
    return [WriteHoldingRegisterRequest(RegisterMap.AC_CHARGE_ENABLE, 1 if enabled else 0)]


def set_force_charge(enabled: bool) -> list[TransparentRequest]:
    """Enable forced battery charging on three-phase inverters."""
    return [WriteHoldingRegisterRequest(RegisterMap.FORCE_CHARGE_ENABLE, 1 if enabled else 0)]


def set_force_discharge(enabled: bool) -> list[TransparentRequest]:
    """Enable forced battery discharging on three-phase inverters."""
    return [WriteHoldingRegisterRequest(RegisterMap.FORCE_DISCHARGE_ENABLE, 1 if enabled else 0)]


def set_ems_plant(enabled: bool) -> list[TransparentRequest]:
    """Enable EMS plant control."""
    return [WriteHoldingRegisterRequest(RegisterMap.EMS_PLANT_ENABLE, 1 if enabled else 0)]


def _export_slot_registers(idx: int) -> tuple[int, int]:
    idx = _as_int(idx, "idx")  # True == 1 would silently select slot 1's registers
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


def _ems_target_soc(val: int) -> int:
    """Validate an EMS SoC target percentage (0-100)."""
    val = _as_int(val, "val")
    if not 0 <= val <= 100:
        raise ValueError(f"EMS target SoC ({val}) must be in [0-100]")
    return val


def set_ems_charge_slot(idx: int, timeslot: TimeSlot | None) -> list[TransparentRequest]:
    """Set an EMS plant charge time slot by index (1-3), or clear it if None."""
    if timeslot is None:
        return reset_charge_slot(idx, EMS_SLOTS)
    return set_charge_slot(idx, timeslot, EMS_SLOTS)


def set_ems_charge_slot_start(idx: int, t: dt_time | None) -> list[TransparentRequest]:
    """Set just the start of EMS plant charge slot idx (1-3), or clear it if None."""
    return set_charge_slot_start(idx, t, EMS_SLOTS)


def set_ems_charge_slot_end(idx: int, t: dt_time | None) -> list[TransparentRequest]:
    """Set just the end of EMS plant charge slot idx (1-3), or clear it if None."""
    return set_charge_slot_end(idx, t, EMS_SLOTS)


def set_ems_discharge_slot(idx: int, timeslot: TimeSlot | None) -> list[TransparentRequest]:
    """Set an EMS plant discharge time slot by index (1-3), or clear it if None."""
    if timeslot is None:
        return reset_discharge_slot(idx, EMS_SLOTS)
    return set_discharge_slot(idx, timeslot, EMS_SLOTS)


def set_ems_discharge_slot_start(idx: int, t: dt_time | None) -> list[TransparentRequest]:
    """Set just the start of EMS plant discharge slot idx (1-3), or clear it if None."""
    return set_discharge_slot_start(idx, t, EMS_SLOTS)


def set_ems_discharge_slot_end(idx: int, t: dt_time | None) -> list[TransparentRequest]:
    """Set just the end of EMS plant discharge slot idx (1-3), or clear it if None."""
    return set_discharge_slot_end(idx, t, EMS_SLOTS)


def set_ems_charge_target_soc(idx: int, target_soc: int) -> list[TransparentRequest]:
    """Set the SoC target (0-100%) for EMS plant charge slot idx (1-3)."""
    idx = _as_int(idx, "idx")
    if not 1 <= idx <= 3:
        raise ValueError(f"EMS charge slot index ({idx}) must be in [1-3]")
    return [
        WriteHoldingRegisterRequest(getattr(RegisterMap, f"EMS_CHARGE_TARGET_SOC_{idx}"), _ems_target_soc(target_soc))
    ]


def set_ems_discharge_target_soc(idx: int, target_soc: int) -> list[TransparentRequest]:
    """Set the SoC target (0-100%) for EMS plant discharge slot idx (1-3)."""
    idx = _as_int(idx, "idx")
    if not 1 <= idx <= 3:
        raise ValueError(f"EMS discharge slot index ({idx}) must be in [1-3]")
    return [
        WriteHoldingRegisterRequest(
            getattr(RegisterMap, f"EMS_DISCHARGE_TARGET_SOC_{idx}"), _ems_target_soc(target_soc)
        )
    ]


def set_ems_export_slot(idx: int, timeslot: TimeSlot | None) -> list[TransparentRequest]:
    """Set an EMS plant export time slot by index (1-3), or clear it if None.

    EMS export slots are the same HR(2062-2069) registers as `set_export_slot`
    (export slots are EMS-only and already target the EMS address 0x11) — this is
    the EMS-named alias for parity with `set_ems_charge_slot`/`set_ems_discharge_slot`.
    """
    return set_export_slot(idx, timeslot)


def set_ems_export_slot_start(idx: int, t: dt_time | None) -> list[TransparentRequest]:
    """Set just the start of EMS plant export slot idx (1-3), or clear it if None."""
    return set_export_slot_start(idx, t)


def set_ems_export_slot_end(idx: int, t: dt_time | None) -> list[TransparentRequest]:
    """Set just the end of EMS plant export slot idx (1-3), or clear it if None."""
    return set_export_slot_end(idx, t)


def set_ems_export_target_soc(idx: int, target_soc: int) -> list[TransparentRequest]:
    """Set the SoC target (0-100%) for EMS plant export slot idx (1-3)."""
    idx = _as_int(idx, "idx")
    if not 1 <= idx <= 3:
        raise ValueError(f"EMS export slot index ({idx}) must be in [1-3]")
    return [
        WriteHoldingRegisterRequest(getattr(RegisterMap, f"EMS_EXPORT_TARGET_SOC_{idx}"), _ems_target_soc(target_soc))
    ]


def set_ems_export_power_limit(watts: int) -> list[TransparentRequest]:
    """Set the EMS plant export power limit in watts.

    Bounded to a 16-bit holding register (0-65535) so an out-of-range value fails
    here rather than later at PDU-encode time as InvalidPduState.
    """
    watts = _as_int(watts, "watts")
    if not 0 <= watts <= 0xFFFF:
        raise ValueError(f"EMS export power limit ({watts}) must be in [0-65535] watts")
    return [WriteHoldingRegisterRequest(RegisterMap.EMS_EXPORT_POWER_LIMIT, watts)]


def _set_slot_endpoint(hr: int, t: dt_time | None) -> list[TransparentRequest]:
    """Write a single slot-endpoint register: HHMM-encoded time, or 0 to clear."""
    return [WriteHoldingRegisterRequest(hr, int(t.strftime("%H%M")) if t else 0)]


def _resolve_slot_registers(discharge: bool, idx: int, slot_map: SlotMap) -> tuple[int, int]:
    idx = _as_int(idx, "idx")  # True == 1 would silently select slot 1's registers
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
    if dt.year < 2000:
        # The year register stores `year - 2000`; a pre-2000 year underflows to a negative
        # value and a confusing encode-time InvalidPduState. Reject it clearly up front (L6).
        raise ValueError(f"System date year ({dt.year}) must be >= 2000")
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
    slot_map: SlotMap = SINGLE_PHASE_SLOTS,
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
    ret.extend(set_discharge_slot(1, discharge_slot_1, slot_map))
    if discharge_slot_2:
        ret.extend(set_discharge_slot(2, discharge_slot_2, slot_map))
    else:
        ret.extend(reset_discharge_slot(2, slot_map))
    return ret


# ---------------------------------------------------------------------------
# Installer-tier command helpers
# These return WriteHoldingRegisterRequest instances with installer=True.
# Pass them to Client.installer_command(), never to one_shot_command().
# Destructive wrappers require an explicit confirm=True.
# ---------------------------------------------------------------------------


def set_battery_nominal_power(power: int) -> list[WriteHoldingRegisterRequest]:
    """Set battery nominal power (HR308). Installer-tier.

    No explicit app range — accepts any uint16. Consult battery hardware spec.
    """
    return [WriteHoldingRegisterRequest(RegisterMap.BATTERY_NOMINAL_POWER, _as_int(power, "power"), installer=True)]


def set_battery_nominal_current(current: int) -> list[WriteHoldingRegisterRequest]:
    """Set battery nominal current (HR309). Installer-tier.

    No explicit app range — accepts any uint16. Consult battery hardware spec.
    """
    val = _as_int(current, "current")
    return [WriteHoldingRegisterRequest(RegisterMap.BATTERY_NOMINAL_CURRENT, val, installer=True)]


def set_battery_max_charge_pct(pct: int) -> list[WriteHoldingRegisterRequest]:
    """Set battery maximum charge percentage (HR310). Installer-tier. App range: 20–100."""
    val = _as_int(pct, "pct")
    if not (20 <= val <= 100):
        raise ValueError(f"Battery max charge % must be 20–100, got {val}")
    return [WriteHoldingRegisterRequest(RegisterMap.BATTERY_MAX_CHARGE_PCT, val, installer=True)]


def set_anti_islanding_detection(enabled: bool) -> list[WriteHoldingRegisterRequest]:
    """Enable or disable anti-islanding detection (HR115). Installer-tier."""
    return [WriteHoldingRegisterRequest(RegisterMap.ANTI_ISLANDING_DETECTION, 1 if enabled else 0, installer=True)]


def set_grid_import_limit_enabled(enabled: bool) -> list[WriteHoldingRegisterRequest]:
    """Enable or disable the grid import limit (HR102). Installer-tier."""
    return [WriteHoldingRegisterRequest(RegisterMap.GRID_IMPORT_LIMIT_ENABLED, 1 if enabled else 0, installer=True)]


def set_enable_plant_mode(enabled: bool) -> list[WriteHoldingRegisterRequest]:
    """Enable or disable plant mode (HR300). Installer-tier."""
    return [WriteHoldingRegisterRequest(RegisterMap.ENABLE_PLANT_MODE, 1 if enabled else 0, installer=True)]


def set_enable_micro_grid(enabled: bool) -> list[WriteHoldingRegisterRequest]:
    """Enable or disable micro grid mode (HR332). Installer-tier."""
    return [WriteHoldingRegisterRequest(RegisterMap.ENABLE_MICRO_GRID, 1 if enabled else 0, installer=True)]


def set_enable_ev_charger(enabled: bool) -> list[WriteHoldingRegisterRequest]:
    """Enable or disable the EV charger (HR333). Installer-tier."""
    return [WriteHoldingRegisterRequest(RegisterMap.ENABLE_EV_CHARGER, 1 if enabled else 0, installer=True)]


def set_ev_charger_soc_limit(soc: int) -> list[WriteHoldingRegisterRequest]:
    """Set EV charger SOC limit (HR336). Installer-tier. Range: 0–100 %."""
    val = _as_int(soc, "soc")
    if not (0 <= val <= 100):
        raise ValueError(f"EV charger SOC limit must be 0–100, got {val}")
    return [WriteHoldingRegisterRequest(RegisterMap.EV_CHARGER_SOC_LIMIT, val, installer=True)]


def set_enable_generator(enabled: bool) -> list[WriteHoldingRegisterRequest]:
    """Enable or disable the generator (HR343). Installer-tier."""
    return [WriteHoldingRegisterRequest(RegisterMap.ENABLE_GENERATOR, 1 if enabled else 0, installer=True)]


def set_generator_start_soc(soc: int) -> list[WriteHoldingRegisterRequest]:
    """Set generator start SOC threshold (HR344). Installer-tier. Range: 0–100 %."""
    val = _as_int(soc, "soc")
    if not (0 <= val <= 100):
        raise ValueError(f"Generator start SOC must be 0–100, got {val}")
    return [WriteHoldingRegisterRequest(RegisterMap.GENERATOR_START_SOC, val, installer=True)]


def set_generator_stop_soc(soc: int) -> list[WriteHoldingRegisterRequest]:
    """Set generator stop SOC threshold (HR345). Installer-tier. Range: 0–100 %."""
    val = _as_int(soc, "soc")
    if not (0 <= val <= 100):
        raise ValueError(f"Generator stop SOC must be 0–100, got {val}")
    return [WriteHoldingRegisterRequest(RegisterMap.GENERATOR_STOP_SOC, val, installer=True)]


def set_enable_smart_load(enabled: bool) -> list[WriteHoldingRegisterRequest]:
    """Enable or disable smart load (HR540). Installer-tier."""
    return [WriteHoldingRegisterRequest(RegisterMap.ENABLE_SMART_LOAD, 1 if enabled else 0, installer=True)]


def set_smart_load_control_soc(soc: int) -> list[WriteHoldingRegisterRequest]:
    """Set smart load control SOC (HR541). Installer-tier. App range: 50–100 %."""
    val = _as_int(soc, "soc")
    if not (50 <= val <= 100):
        raise ValueError(f"Smart load control SOC must be 50–100, got {val}")
    return [WriteHoldingRegisterRequest(RegisterMap.SMART_LOAD_CONTROL_SOC, val, installer=True)]


def set_general_load_control_soc(soc: int) -> list[WriteHoldingRegisterRequest]:
    """Set general load control SOC (HR543). Installer-tier. App range: 50–100 %."""
    val = _as_int(soc, "soc")
    if not (50 <= val <= 100):
        raise ValueError(f"General load control SOC must be 50–100, got {val}")
    return [WriteHoldingRegisterRequest(RegisterMap.GENERAL_LOAD_CONTROL_SOC, val, installer=True)]


def set_generator_control_soc(soc: int) -> list[WriteHoldingRegisterRequest]:
    """Set generator control SOC (HR544). Installer-tier. App range: 10–90 %."""
    val = _as_int(soc, "soc")
    if not (10 <= val <= 90):
        raise ValueError(f"Generator control SOC must be 10–90, got {val}")
    return [WriteHoldingRegisterRequest(RegisterMap.GENERATOR_CONTROL_SOC, val, installer=True)]


def set_enable_export_limit_3ph(enabled: bool) -> list[WriteHoldingRegisterRequest]:
    """Enable or disable export limit on three-phase inverters (HR1103). Installer-tier."""
    return [WriteHoldingRegisterRequest(RegisterMap.ENABLE_EXPORT_LIMIT_3PH, 1 if enabled else 0, installer=True)]


def set_enable_import_limit_3ph(enabled: bool) -> list[WriteHoldingRegisterRequest]:
    """Enable or disable import limit on three-phase inverters (HR1131). Installer-tier."""
    return [WriteHoldingRegisterRequest(RegisterMap.ENABLE_IMPORT_LIMIT_3PH, 1 if enabled else 0, installer=True)]


def set_peak_shaving_export_limit_enabled(enabled: bool) -> list[WriteHoldingRegisterRequest]:
    """Enable or disable peak-shaving grid export limit (HR20000). Installer-tier."""
    val = 1 if enabled else 0
    return [WriteHoldingRegisterRequest(RegisterMap.PEAK_SHAVING_EXPORT_LIMIT_ENABLED, val, installer=True)]


def set_peak_shaving_enabled(enabled: bool) -> list[WriteHoldingRegisterRequest]:
    """Enable or disable peak shaving (HR20002). Installer-tier."""
    return [WriteHoldingRegisterRequest(RegisterMap.PEAK_SHAVING_ENABLED, 1 if enabled else 0, installer=True)]


# --- Grid protection setters — installer-tier, require confirm=True ---
# These registers govern trip/reconnect/grid-band thresholds for G98/G99/G100 compliance.
# Incorrect values can cause loss of grid-code certification. An installer is responsible
# for verifying that settings comply with the applicable grid code before writing.


def _grid_confirm(fn_name: str, confirm: bool) -> None:
    if not confirm:
        raise ValueError(
            f"{fn_name}() modifies a grid-protection register — pass confirm=True to proceed. "
            "Verify the new value complies with G98/G99/G100 (or the applicable grid code) "
            "before writing."
        )


def set_v_ac_low_limit_trip(voltage: float, *, confirm: bool = False) -> list[WriteHoldingRegisterRequest]:
    """Set AC under-voltage trip threshold (HR63). Installer-tier. Range 0.0–500.0 V.

    Part of the G98/G99/G100 trip band. Pass confirm=True after verifying grid-code compliance.
    Value is written as deci (int(voltage × 10)).
    """
    _grid_confirm("set_v_ac_low_limit_trip", confirm)
    val = _as_int(voltage * 10, "voltage × 10")
    if not (0 <= val <= 5000):
        raise ValueError(f"v_ac_low_limit_trip must be 0.0–500.0 V, got {voltage}")
    return [WriteHoldingRegisterRequest(RegisterMap.V_AC_LOW_LIMIT_TRIP, val, installer=True)]


def set_v_ac_high_limit_trip(voltage: float, *, confirm: bool = False) -> list[WriteHoldingRegisterRequest]:
    """Set AC over-voltage trip threshold (HR64). Installer-tier. Range 0.0–500.0 V.

    Part of the G98/G99/G100 trip band. Pass confirm=True after verifying grid-code compliance.
    Value is written as deci (int(voltage × 10)).
    """
    _grid_confirm("set_v_ac_high_limit_trip", confirm)
    val = _as_int(voltage * 10, "voltage × 10")
    if not (0 <= val <= 5000):
        raise ValueError(f"v_ac_high_limit_trip must be 0.0–500.0 V, got {voltage}")
    return [WriteHoldingRegisterRequest(RegisterMap.V_AC_HIGH_LIMIT_TRIP, val, installer=True)]


def set_f_ac_low_limit_trip(freq: float, *, confirm: bool = False) -> list[WriteHoldingRegisterRequest]:
    """Set AC under-frequency trip threshold (HR65). Installer-tier. Range 40.0–70.0 Hz.

    Part of the G98/G99/G100 trip band. Pass confirm=True after verifying grid-code compliance.
    Value is written as centi (int(freq × 100)).
    """
    _grid_confirm("set_f_ac_low_limit_trip", confirm)
    val = _as_int(freq * 100, "freq × 100")
    if not (4000 <= val <= 7000):
        raise ValueError(f"f_ac_low_limit_trip must be 40.0–70.0 Hz, got {freq}")
    return [WriteHoldingRegisterRequest(RegisterMap.F_AC_LOW_LIMIT_TRIP, val, installer=True)]


def set_f_ac_high_limit_trip(freq: float, *, confirm: bool = False) -> list[WriteHoldingRegisterRequest]:
    """Set AC over-frequency trip threshold (HR66). Installer-tier. Range 40.0–70.0 Hz.

    Part of the G98/G99/G100 trip band. Pass confirm=True after verifying grid-code compliance.
    Value is written as centi (int(freq × 100)).
    """
    _grid_confirm("set_f_ac_high_limit_trip", confirm)
    val = _as_int(freq * 100, "freq × 100")
    if not (4000 <= val <= 7000):
        raise ValueError(f"f_ac_high_limit_trip must be 40.0–70.0 Hz, got {freq}")
    return [WriteHoldingRegisterRequest(RegisterMap.F_AC_HIGH_LIMIT_TRIP, val, installer=True)]


def set_t_ac_low_voltage_trip(seconds: float, *, confirm: bool = False) -> list[WriteHoldingRegisterRequest]:
    """Set AC under-voltage trip time (HR67). Installer-tier. Value in seconds (centi-scaled).

    Part of the G98/G99/G100 trip band. Pass confirm=True after verifying grid-code compliance.
    Value is written as centi (int(seconds × 100)).
    """
    _grid_confirm("set_t_ac_low_voltage_trip", confirm)
    val = _as_int(seconds * 100, "seconds × 100")
    if val < 0:
        raise ValueError(f"t_ac_low_voltage_trip must be non-negative, got {seconds}")
    return [WriteHoldingRegisterRequest(RegisterMap.T_AC_LOW_VOLTAGE_TRIP, val, installer=True)]


def set_t_ac_high_voltage_trip(seconds: float, *, confirm: bool = False) -> list[WriteHoldingRegisterRequest]:
    """Set AC over-voltage trip time (HR68). Installer-tier. Value in seconds (centi-scaled).

    Part of the G98/G99/G100 trip band. Pass confirm=True after verifying grid-code compliance.
    Value is written as centi (int(seconds × 100)).
    """
    _grid_confirm("set_t_ac_high_voltage_trip", confirm)
    val = _as_int(seconds * 100, "seconds × 100")
    if val < 0:
        raise ValueError(f"t_ac_high_voltage_trip must be non-negative, got {seconds}")
    return [WriteHoldingRegisterRequest(RegisterMap.T_AC_HIGH_VOLTAGE_TRIP, val, installer=True)]


def set_t_ac_low_freq_trip(seconds: float, *, confirm: bool = False) -> list[WriteHoldingRegisterRequest]:
    """Set AC under-frequency trip time (HR69). Installer-tier. Value in seconds (centi-scaled).

    Part of the G98/G99/G100 trip band. Pass confirm=True after verifying grid-code compliance.
    Value is written as centi (int(seconds × 100)).
    """
    _grid_confirm("set_t_ac_low_freq_trip", confirm)
    val = _as_int(seconds * 100, "seconds × 100")
    if val < 0:
        raise ValueError(f"t_ac_low_freq_trip must be non-negative, got {seconds}")
    return [WriteHoldingRegisterRequest(RegisterMap.T_AC_LOW_FREQ_TRIP, val, installer=True)]


def set_t_ac_high_freq_trip(seconds: float, *, confirm: bool = False) -> list[WriteHoldingRegisterRequest]:
    """Set AC over-frequency trip time (HR70). Installer-tier. Value in seconds (centi-scaled).

    Part of the G98/G99/G100 trip band. Pass confirm=True after verifying grid-code compliance.
    Value is written as centi (int(seconds × 100)).
    """
    _grid_confirm("set_t_ac_high_freq_trip", confirm)
    val = _as_int(seconds * 100, "seconds × 100")
    if val < 0:
        raise ValueError(f"t_ac_high_freq_trip must be non-negative, got {seconds}")
    return [WriteHoldingRegisterRequest(RegisterMap.T_AC_HIGH_FREQ_TRIP, val, installer=True)]


def set_v_ac_low_limit_reconnect(voltage: float, *, confirm: bool = False) -> list[WriteHoldingRegisterRequest]:
    """Set AC under-voltage reconnect threshold (HR71). Installer-tier. Range 0.0–500.0 V.

    Part of the G98/G99/G100 reconnect band. Pass confirm=True after verifying grid-code compliance.
    Value is written as deci (int(voltage × 10)).
    """
    _grid_confirm("set_v_ac_low_limit_reconnect", confirm)
    val = _as_int(voltage * 10, "voltage × 10")
    if not (0 <= val <= 5000):
        raise ValueError(f"v_ac_low_limit_reconnect must be 0.0–500.0 V, got {voltage}")
    return [WriteHoldingRegisterRequest(RegisterMap.V_AC_LOW_LIMIT_RECONNECT, val, installer=True)]


def set_v_ac_high_limit_reconnect(voltage: float, *, confirm: bool = False) -> list[WriteHoldingRegisterRequest]:
    """Set AC over-voltage reconnect threshold (HR72). Installer-tier. Range 0.0–500.0 V.

    Part of the G98/G99/G100 reconnect band. Pass confirm=True after verifying grid-code compliance.
    Value is written as deci (int(voltage × 10)).
    """
    _grid_confirm("set_v_ac_high_limit_reconnect", confirm)
    val = _as_int(voltage * 10, "voltage × 10")
    if not (0 <= val <= 5000):
        raise ValueError(f"v_ac_high_limit_reconnect must be 0.0–500.0 V, got {voltage}")
    return [WriteHoldingRegisterRequest(RegisterMap.V_AC_HIGH_LIMIT_RECONNECT, val, installer=True)]


def set_f_ac_low_limit_reconnect(freq: float, *, confirm: bool = False) -> list[WriteHoldingRegisterRequest]:
    """Set AC under-frequency reconnect threshold (HR73). Installer-tier. Range 40.0–70.0 Hz.

    Part of the G98/G99/G100 reconnect band. Pass confirm=True after verifying grid-code compliance.
    Value is written as centi (int(freq × 100)).
    """
    _grid_confirm("set_f_ac_low_limit_reconnect", confirm)
    val = _as_int(freq * 100, "freq × 100")
    if not (4000 <= val <= 7000):
        raise ValueError(f"f_ac_low_limit_reconnect must be 40.0–70.0 Hz, got {freq}")
    return [WriteHoldingRegisterRequest(RegisterMap.F_AC_LOW_LIMIT_RECONNECT, val, installer=True)]


def set_f_ac_high_limit_reconnect(freq: float, *, confirm: bool = False) -> list[WriteHoldingRegisterRequest]:
    """Set AC over-frequency reconnect threshold (HR74). Installer-tier. Range 40.0–70.0 Hz.

    Part of the G98/G99/G100 reconnect band. Pass confirm=True after verifying grid-code compliance.
    Value is written as centi (int(freq × 100)).
    """
    _grid_confirm("set_f_ac_high_limit_reconnect", confirm)
    val = _as_int(freq * 100, "freq × 100")
    if not (4000 <= val <= 7000):
        raise ValueError(f"f_ac_high_limit_reconnect must be 40.0–70.0 Hz, got {freq}")
    return [WriteHoldingRegisterRequest(RegisterMap.F_AC_HIGH_LIMIT_RECONNECT, val, installer=True)]


def set_t_ac_low_voltage_reconnect(seconds: float, *, confirm: bool = False) -> list[WriteHoldingRegisterRequest]:
    """Set AC under-voltage reconnect time (HR75). Installer-tier. Value in seconds (centi-scaled).

    Part of the G98/G99/G100 reconnect band. Pass confirm=True after verifying grid-code compliance.
    Value is written as centi (int(seconds × 100)).
    """
    _grid_confirm("set_t_ac_low_voltage_reconnect", confirm)
    val = _as_int(seconds * 100, "seconds × 100")
    if val < 0:
        raise ValueError(f"t_ac_low_voltage_reconnect must be non-negative, got {seconds}")
    return [WriteHoldingRegisterRequest(RegisterMap.T_AC_LOW_VOLTAGE_RECONNECT, val, installer=True)]


def set_t_ac_high_voltage_reconnect(seconds: float, *, confirm: bool = False) -> list[WriteHoldingRegisterRequest]:
    """Set AC over-voltage reconnect time (HR76). Installer-tier. Value in seconds (centi-scaled).

    Part of the G98/G99/G100 reconnect band. Pass confirm=True after verifying grid-code compliance.
    Value is written as centi (int(seconds × 100)).
    """
    _grid_confirm("set_t_ac_high_voltage_reconnect", confirm)
    val = _as_int(seconds * 100, "seconds × 100")
    if val < 0:
        raise ValueError(f"t_ac_high_voltage_reconnect must be non-negative, got {seconds}")
    return [WriteHoldingRegisterRequest(RegisterMap.T_AC_HIGH_VOLTAGE_RECONNECT, val, installer=True)]


def set_t_ac_low_freq_reconnect(seconds: float, *, confirm: bool = False) -> list[WriteHoldingRegisterRequest]:
    """Set AC under-frequency reconnect time (HR77). Installer-tier. Value in seconds (centi-scaled).

    Part of the G98/G99/G100 reconnect band. Pass confirm=True after verifying grid-code compliance.
    Value is written as centi (int(seconds × 100)).
    """
    _grid_confirm("set_t_ac_low_freq_reconnect", confirm)
    val = _as_int(seconds * 100, "seconds × 100")
    if val < 0:
        raise ValueError(f"t_ac_low_freq_reconnect must be non-negative, got {seconds}")
    return [WriteHoldingRegisterRequest(RegisterMap.T_AC_LOW_FREQ_RECONNECT, val, installer=True)]


def set_t_ac_high_freq_reconnect(seconds: float, *, confirm: bool = False) -> list[WriteHoldingRegisterRequest]:
    """Set AC over-frequency reconnect time (HR78). Installer-tier. Value in seconds (centi-scaled).

    Part of the G98/G99/G100 reconnect band. Pass confirm=True after verifying grid-code compliance.
    Value is written as centi (int(seconds × 100)).
    """
    _grid_confirm("set_t_ac_high_freq_reconnect", confirm)
    val = _as_int(seconds * 100, "seconds × 100")
    if val < 0:
        raise ValueError(f"t_ac_high_freq_reconnect must be non-negative, got {seconds}")
    return [WriteHoldingRegisterRequest(RegisterMap.T_AC_HIGH_FREQ_RECONNECT, val, installer=True)]


def set_v_ac_low_limit_grid(voltage: float, *, confirm: bool = False) -> list[WriteHoldingRegisterRequest]:
    """Set AC under-voltage grid-band threshold (HR79). Installer-tier. Range 0.0–500.0 V.

    Part of the G98/G99/G100 grid band. Pass confirm=True after verifying grid-code compliance.
    Value is written as deci (int(voltage × 10)).
    """
    _grid_confirm("set_v_ac_low_limit_grid", confirm)
    val = _as_int(voltage * 10, "voltage × 10")
    if not (0 <= val <= 5000):
        raise ValueError(f"v_ac_low_limit_grid must be 0.0–500.0 V, got {voltage}")
    return [WriteHoldingRegisterRequest(RegisterMap.V_AC_LOW_LIMIT_GRID, val, installer=True)]


def set_v_ac_high_limit_grid(voltage: float, *, confirm: bool = False) -> list[WriteHoldingRegisterRequest]:
    """Set AC over-voltage grid-band threshold (HR80). Installer-tier. Range 0.0–500.0 V.

    Part of the G98/G99/G100 grid band. Pass confirm=True after verifying grid-code compliance.
    Value is written as deci (int(voltage × 10)).
    """
    _grid_confirm("set_v_ac_high_limit_grid", confirm)
    val = _as_int(voltage * 10, "voltage × 10")
    if not (0 <= val <= 5000):
        raise ValueError(f"v_ac_high_limit_grid must be 0.0–500.0 V, got {voltage}")
    return [WriteHoldingRegisterRequest(RegisterMap.V_AC_HIGH_LIMIT_GRID, val, installer=True)]


def set_f_ac_low_limit_grid(freq: float, *, confirm: bool = False) -> list[WriteHoldingRegisterRequest]:
    """Set AC under-frequency grid-band threshold (HR81). Installer-tier. Range 40.0–70.0 Hz.

    Part of the G98/G99/G100 grid band. Pass confirm=True after verifying grid-code compliance.
    Value is written as centi (int(freq × 100)).
    """
    _grid_confirm("set_f_ac_low_limit_grid", confirm)
    val = _as_int(freq * 100, "freq × 100")
    if not (4000 <= val <= 7000):
        raise ValueError(f"f_ac_low_limit_grid must be 40.0–70.0 Hz, got {freq}")
    return [WriteHoldingRegisterRequest(RegisterMap.F_AC_LOW_LIMIT_GRID, val, installer=True)]


def set_f_ac_high_limit_grid(freq: float, *, confirm: bool = False) -> list[WriteHoldingRegisterRequest]:
    """Set AC over-frequency grid-band threshold (HR82). Installer-tier. Range 40.0–70.0 Hz.

    Part of the G98/G99/G100 grid band. Pass confirm=True after verifying grid-code compliance.
    Value is written as centi (int(freq × 100)).
    """
    _grid_confirm("set_f_ac_high_limit_grid", confirm)
    val = _as_int(freq * 100, "freq × 100")
    if not (4000 <= val <= 7000):
        raise ValueError(f"f_ac_high_limit_grid must be 40.0–70.0 Hz, got {freq}")
    return [WriteHoldingRegisterRequest(RegisterMap.F_AC_HIGH_LIMIT_GRID, val, installer=True)]


def set_v_ac_10min_protect(voltage: float, *, confirm: bool = False) -> list[WriteHoldingRegisterRequest]:
    """Set 10-minute mean AC voltage protection threshold (HR83). Installer-tier. Range 0.0–500.0 V.

    G98/G99/G100 10-minute mean voltage protection. Pass confirm=True after verifying grid-code compliance.
    Value is written as deci (int(voltage × 10)).
    """
    _grid_confirm("set_v_ac_10min_protect", confirm)
    val = _as_int(voltage * 10, "voltage × 10")
    if not (0 <= val <= 5000):
        raise ValueError(f"v_ac_10min_protect must be 0.0–500.0 V, got {voltage}")
    return [WriteHoldingRegisterRequest(RegisterMap.V_AC_10MIN_PROTECT, val, installer=True)]


# --- Destructive installer commands — require confirm=True ---


def reset_energy_totals(*, confirm: bool = False) -> list[WriteHoldingRegisterRequest]:
    """Reset all lifetime energy counters (HR162). Irreversible.

    This clears the lifetime import/export/charge/discharge totals stored in
    the inverter. Cannot be undone. Pass confirm=True to proceed.
    """
    if not confirm:
        raise ValueError("reset_energy_totals() is irreversible — pass confirm=True to proceed")
    return [WriteHoldingRegisterRequest(RegisterMap.RESET_ENERGY_TOTALS, 1, installer=True)]


def three_phase_factory_reset(*, confirm: bool = False) -> list[WriteHoldingRegisterRequest]:
    """Trigger three-phase factory reset without meter reset (HR1016). Irreversible.

    Resets inverter configuration to factory defaults, excluding meter data.
    Pass confirm=True to proceed.
    """
    if not confirm:
        raise ValueError("three_phase_factory_reset() is irreversible — pass confirm=True to proceed")
    return [WriteHoldingRegisterRequest(RegisterMap.THREE_PHASE_FACTORY_RESET, 1, installer=True)]


def enable_black_start(*, confirm: bool = False) -> list[WriteHoldingRegisterRequest]:
    """Enable EPS black-start mode (HR5003). Use with care.

    Activates black-start capability on EPS-capable inverters. Incorrect use can
    cause the inverter to energise an island without grid synchronisation.
    Pass confirm=True to proceed.
    """
    if not confirm:
        raise ValueError("enable_black_start() requires confirm=True")
    return [WriteHoldingRegisterRequest(RegisterMap.ENABLE_BLACK_START, 1, installer=True)]


def restore_factory_defaults(*, confirm: bool = False) -> list[WriteHoldingRegisterRequest]:
    """Restore factory defaults (HR5004). Irreversible — wipes all installer config.

    Resets the inverter to factory defaults, including all installer-configured
    grid-safety limits, battery settings, and operating modes. Pass confirm=True
    to proceed.
    """
    if not confirm:
        raise ValueError("restore_factory_defaults() is irreversible — pass confirm=True to proceed")
    return [WriteHoldingRegisterRequest(RegisterMap.RESTORE_FACTORY_DEFAULTS, 1, installer=True)]


# HR(300-359) AC-output config-block writes that are gated on capabilities.has_ac_config_block
# rather than the model-class allowlist — one_shot_command unions these into the safe set only when
# the detected model exposes the block (Model.AC / All-in-One), never for a DC-coupled hybrid or an
# undetected client (#295/#296 review). Currently just the AC charge/discharge limits; HR311/317
# (also HR300-359) predate the gate and stay in the universal set pending a separate cleanup.
_AC_CONFIG_WRITE_SAFE_REGISTERS: frozenset[int] = frozenset(
    {
        RegisterMap.BATTERY_CHARGE_LIMIT_AC,  # 313
        RegisterMap.BATTERY_DISCHARGE_LIMIT_AC,  # 314
    }
)


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
    # Single-phase shape: contains HR(96/110/116) and single-phase slot pairs (94/95,
    # 31/32 charge; 56/57, 44/45 discharge). ThreePhaseInverter replaces these via
    # _ThreePhaseCommands.WRITE_SAFE_REGISTERS (defined below, overrides this per MRO).
    # Excludes 313/314 (BATTERY_*_LIMIT_AC): these belong to the HR(300-359) AC-output config
    # block, absent (reads time out) on DC-coupled hybrids, so they are gated on
    # capabilities.has_ac_config_block at the client boundary instead — one_shot_command unions
    # _AC_CONFIG_WRITE_SAFE_REGISTERS in for Model.AC/AIO only, never a DC hybrid or an undetected
    # client (#295/#296 review). (HR311/317 are also HR300-359 registers but predate this and stay
    # in the universal set; folding them into the same gate is a separate cleanup.) Also excludes
    # 318-320 (pause mode, firmware-gated), 1078/1109/1111-1123 (native three-phase), and
    # 2040/2062-2069 (EMS).
    WRITE_SAFE_REGISTERS: ClassVar[frozenset[int]] = frozenset(
        {
            20,  # ENABLE_CHARGE_TARGET
            27,  # BATTERY_POWER_MODE
            311,  # EXPORT_PRIORITY (AC-coupled; confirmed writable via hass#52 portal observations)
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
            317,  # ENABLE_EPS (AC-coupled; confirmed writable via hass#52 portal observations)
        }
    )

    # --- charge target -------------------------------------------------------

    def disable_charge_target(self) -> list[TransparentRequest]:
        """Disable use of a charge target so the battery charges to 100%."""
        return disable_charge_target()

    def set_charge_target_enabled(self, target_soc: int) -> list[TransparentRequest]:
        """Enable charging and stop once SOC reaches target_soc (4-100)."""
        return set_charge_target_enabled(target_soc)

    @deprecated("use set_charge_target_enabled(target_soc) instead")
    def set_charge_target(self, target_soc: int) -> list[TransparentRequest]:
        """Deprecated: use set_charge_target_enabled(target_soc)."""
        return set_charge_target_enabled(target_soc)

    def set_charge_target_soc(self, target_soc: int) -> list[TransparentRequest]:
        """Adjust the charge target SOC (4-100) without touching the charge / charge-target enable bits."""
        return set_charge_target_soc(target_soc)

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

    def set_export_priority(self, priority: ExportPriority) -> list[TransparentRequest]:
        """Set surplus-power dispatch priority on AC-coupled inverters (BATTERY_FIRST, GRID_FIRST, LOAD_FIRST)."""
        return set_export_priority(priority)

    def set_enable_eps(self, enabled: bool) -> list[TransparentRequest]:
        """Enable or disable Emergency Power Supply (EPS) mode on AC-coupled inverters."""
        return set_enable_eps(enabled)

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
        """Set the battery charge power limit as a percentage of the rated charge power (0-100)."""
        return set_battery_charge_limit(val)

    def set_battery_discharge_limit(self, val: int) -> list[TransparentRequest]:
        """Set the battery discharge power limit as a percentage of the rated discharge power (0-100)."""
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
        return set_mode_storage(discharge_slot_1, discharge_slot_2, discharge_for_export, self.slot_map)


class _ThreePhaseCommands:
    """Commands that apply to three-phase inverters, composed onto `ThreePhaseInverter`.

    Overrides several `_InverterCommands` methods that hardcode single-phase registers:
    - `set_enable_charge()` → AC_CHARGE_ENABLE HR(1112) instead of HR(96)
    - `set_battery_soc_reserve()` → HR(1109) instead of HR(110)
    - `set_mode_dynamic()` → HR(1109) for the SOC reserve step instead of HR(110)
    - `set_charge_target_enabled()` → HR(1112)+HR(1111) instead of HR(96)+HR(116)
    - `set_battery_reserve_soc()` relocated here (three-phase only, HR 1078)

    MRO puts `_ThreePhaseCommands` before `_InverterCommands` on `ThreePhaseInverter`,
    so these overrides take precedence.

    The `WRITE_SAFE_REGISTERS` frozenset reflects the correct three-phase register
    addresses: single-phase slot pairs (94/95, 31/32, 56/57, 44/45) and the
    single-phase-only scalars (96, 110, 116) are replaced by their three-phase
    counterparts (1113-1116, 1118-1121, 1112, 1109, 1111).
    """

    # Three-phase allowlist: derived from _InverterCommands.WRITE_SAFE_REGISTERS with
    # single-phase slot pairs and scalar registers swapped out for three-phase equivalents.
    WRITE_SAFE_REGISTERS: ClassVar[frozenset[int]] = frozenset(
        (
            _InverterCommands.WRITE_SAFE_REGISTERS
            # remove single-phase slot pairs and scalars
            - {94, 95, 31, 32}  # charge slots 1-2
            - {56, 57, 44, 45}  # discharge slots 1-2
            - {96, 110, 116}  # ENABLE_CHARGE, BATTERY_SOC_RESERVE, CHARGE_TARGET_SOC
        )
        | {
            1078,  # BATTERY_RESERVE_SOC (three-phase only)
            1109,  # BATTERY_SOC_RESERVE_3PH (shadows HR 110)
            1111,  # CHARGE_TARGET_SOC_3PH (shadows HR 116)
            1112,  # AC_CHARGE_ENABLE (three-phase; replaces ENABLE_CHARGE HR 96)
            1113,
            1114,  # charge slot 1 (three-phase)
            1115,
            1116,  # charge slot 2 (three-phase)
            1118,
            1119,  # discharge slot 1 (three-phase)
            1120,
            1121,  # discharge slot 2 (three-phase)
            1122,  # FORCE_DISCHARGE_ENABLE
            1123,  # FORCE_CHARGE_ENABLE
        }
    )

    # --- three-phase-only enables --------------------------------------------

    def set_ac_charge(self, enabled: bool) -> list[TransparentRequest]:
        """Enable or disable AC charging (three-phase only)."""
        return set_ac_charge(enabled)

    def set_force_charge(self, enabled: bool) -> list[TransparentRequest]:
        """Force battery charging (three-phase only)."""
        return set_force_charge(enabled)

    def set_force_discharge(self, enabled: bool) -> list[TransparentRequest]:
        """Force battery discharging (three-phase only)."""
        return set_force_discharge(enabled)

    # --- three-phase-only reserve --------------------------------------------

    def set_battery_reserve_soc(self, val: int) -> list[TransparentRequest]:
        """Set the battery reserve SOC on three-phase inverters (HR 1078, "Battery Reserve %", 4-100)."""
        return set_battery_reserve_soc(val)

    # --- overrides: correct register selection for three-phase ---------------

    def set_enable_charge(self, enabled: bool) -> list[TransparentRequest]:
        """Enable or disable battery charging (three-phase: AC_CHARGE_ENABLE HR 1112, shadows single-phase HR 96)."""
        return set_ac_charge(enabled)

    def set_battery_soc_reserve(self, val: int) -> list[TransparentRequest]:
        """Set the minimum SOC reserve (three-phase: HR 1109, shadows single-phase HR 110)."""
        return set_battery_soc_reserve_3ph(val)

    def set_mode_dynamic(self) -> list[TransparentRequest]:
        """Set system to Dynamic / Eco mode (three-phase: HR 1109 for SOC reserve, shadows single-phase HR 110)."""
        return set_discharge_mode_to_match_demand() + set_battery_soc_reserve_3ph(4) + set_enable_discharge(False)

    def disable_charge_target(self) -> list[TransparentRequest]:
        """Remove SOC limit and target 100% charging (three-phase: HR 1111, shadows single-phase HR 116)."""
        return disable_charge_target_3ph()

    def set_charge_target_enabled(self, target_soc: int) -> list[TransparentRequest]:
        """Enable AC charging and set the charge target (three-phase HR 1111/1112, shadows single-phase HR 116)."""
        return set_charge_target_enabled_3ph(target_soc)

    @deprecated("use set_charge_target_enabled(target_soc) instead")
    def set_charge_target(self, target_soc: int) -> list[TransparentRequest]:
        """Deprecated: use set_charge_target_enabled(target_soc)."""
        return set_charge_target_enabled_3ph(target_soc)

    def set_charge_target_soc(self, target_soc: int) -> list[TransparentRequest]:
        """Adjust the charge target SOC, no enable side effects (three-phase HR 1111, shadows single-phase HR 116)."""
        return set_charge_target_soc_3ph(target_soc)


class _EmsCommands:
    """Commands that target the EMS plant controller.

    Composed onto `Ems`. Does *not* inherit from `_InverterCommands` — EMS is a
    peer device of the inverter(s) it manages, not an inverter itself, so the
    inverter-level allowlist and slot setters do not apply. EMS slot primitives
    use the `EMS_SLOTS` constant internally so there's no `self.slot_map`
    dependency.

    The EMS register block (HR 2040, 2044–2071) is decoded in
    `givenergy_modbus.model.ems`; write-safety for those registers is enforced
    both here and at the PDU level (`pdu.write_registers.WRITE_SAFE_REGISTERS`).
    """

    WRITE_SAFE_REGISTERS: ClassVar[frozenset[int]] = frozenset({2040, *range(2044, 2072)})

    # --- plant master enable -------------------------------------------------

    def set_ems_plant(self, enabled: bool) -> list[TransparentRequest]:
        """Enable or disable plant-level EMS ("Flexi EMS") control."""
        return set_ems_plant(enabled)

    # --- export slots (HR 2062–2070) ----------------------------------------

    def set_export_slot(self, idx: int, slot: TimeSlot | None) -> list[TransparentRequest]:
        """Set export slot start & end times by index (1–3), or clear if `slot` is None."""
        return set_export_slot(idx, slot)

    def set_export_slot_start(self, idx: int, t: dt_time | None) -> list[TransparentRequest]:
        """Set just the start of export slot `idx` (1–3), or clear it if `t` is None."""
        return set_export_slot_start(idx, t)

    def set_export_slot_end(self, idx: int, t: dt_time | None) -> list[TransparentRequest]:
        """Set just the end of export slot `idx` (1–3), or clear it if `t` is None."""
        return set_export_slot_end(idx, t)

    # --- EMS-named aliases for export slots ---------------------------------

    def set_ems_export_slot(self, idx: int, timeslot: TimeSlot | None) -> list[TransparentRequest]:
        """Set an EMS plant export slot `idx` (1–3), or clear it if None."""
        return set_ems_export_slot(idx, timeslot)

    def set_ems_export_slot_start(self, idx: int, t: dt_time | None) -> list[TransparentRequest]:
        """Set just the start of EMS export slot `idx` (1–3), or clear it if None."""
        return set_ems_export_slot_start(idx, t)

    def set_ems_export_slot_end(self, idx: int, t: dt_time | None) -> list[TransparentRequest]:
        """Set just the end of EMS export slot `idx` (1–3), or clear it if None."""
        return set_ems_export_slot_end(idx, t)

    # --- EMS charge slots (HR 2053–2061) ------------------------------------

    def set_ems_charge_slot(self, idx: int, timeslot: TimeSlot | None) -> list[TransparentRequest]:
        """Set an EMS plant charge slot `idx` (1–3), or clear it if None."""
        return set_ems_charge_slot(idx, timeslot)

    def set_ems_charge_slot_start(self, idx: int, t: dt_time | None) -> list[TransparentRequest]:
        """Set just the start of EMS charge slot `idx` (1–3), or clear it if None."""
        return set_ems_charge_slot_start(idx, t)

    def set_ems_charge_slot_end(self, idx: int, t: dt_time | None) -> list[TransparentRequest]:
        """Set just the end of EMS charge slot `idx` (1–3), or clear it if None."""
        return set_ems_charge_slot_end(idx, t)

    # --- EMS discharge slots (HR 2044–2052) ---------------------------------

    def set_ems_discharge_slot(self, idx: int, timeslot: TimeSlot | None) -> list[TransparentRequest]:
        """Set an EMS plant discharge slot `idx` (1–3), or clear it if None."""
        return set_ems_discharge_slot(idx, timeslot)

    def set_ems_discharge_slot_start(self, idx: int, t: dt_time | None) -> list[TransparentRequest]:
        """Set just the start of EMS discharge slot `idx` (1–3), or clear it if None."""
        return set_ems_discharge_slot_start(idx, t)

    def set_ems_discharge_slot_end(self, idx: int, t: dt_time | None) -> list[TransparentRequest]:
        """Set just the end of EMS discharge slot `idx` (1–3), or clear it if None."""
        return set_ems_discharge_slot_end(idx, t)

    # --- per-slot target SoC ------------------------------------------------

    def set_ems_charge_target_soc(self, idx: int, target_soc: int) -> list[TransparentRequest]:
        """Set the SoC target (0–100%) for EMS charge slot `idx` (1–3)."""
        return set_ems_charge_target_soc(idx, target_soc)

    def set_ems_discharge_target_soc(self, idx: int, target_soc: int) -> list[TransparentRequest]:
        """Set the SoC target (0–100%) for EMS discharge slot `idx` (1–3)."""
        return set_ems_discharge_target_soc(idx, target_soc)

    def set_ems_export_target_soc(self, idx: int, target_soc: int) -> list[TransparentRequest]:
        """Set the SoC target (0–100%) for EMS export slot `idx` (1–3)."""
        return set_ems_export_target_soc(idx, target_soc)

    # --- plant export power limit -------------------------------------------

    def set_ems_export_power_limit(self, watts: int) -> list[TransparentRequest]:
        """Set the EMS plant export power limit in watts."""
        return set_ems_export_power_limit(watts)
