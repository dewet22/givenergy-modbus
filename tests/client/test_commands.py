from datetime import datetime
from datetime import time as dt_time

import pytest

from givenergy_modbus.client import commands
from givenergy_modbus.client.commands import RegisterMap
from givenergy_modbus.model import TimeSlot
from givenergy_modbus.model.battery import BatteryPauseMode
from givenergy_modbus.model.inverter import EXTENDED_SLOTS, SINGLE_PHASE_SLOTS
from givenergy_modbus.model.inverter_threephase import THREE_PHASE_SLOTS
from givenergy_modbus.pdu import WriteHoldingRegisterRequest


async def test_configure_charge_target():
    """Ensure we can set and disable a charge target."""
    assert commands.set_charge_target(45) == [
        WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE, True),
        WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE_TARGET, True),
        WriteHoldingRegisterRequest(RegisterMap.CHARGE_TARGET_SOC, 45),
    ]
    assert commands.set_charge_target(100) == [
        WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE, True),
        WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE_TARGET, False),
        WriteHoldingRegisterRequest(RegisterMap.CHARGE_TARGET_SOC, 100),
    ]

    with pytest.raises(ValueError, match=r"Charge Target SOC \(0\) must be in \[4-100\]\%"):
        commands.set_charge_target(0)
    with pytest.raises(ValueError, match=r"Charge Target SOC \(1\) must be in \[4-100\]\%"):
        commands.set_charge_target(1)
    with pytest.raises(ValueError, match=r"Charge Target SOC \(101\) must be in \[4-100\]\%"):
        commands.set_charge_target(101)

    assert commands.disable_charge_target() == [
        WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE_TARGET, False),
        WriteHoldingRegisterRequest(RegisterMap.CHARGE_TARGET_SOC, 100),
    ]


async def test_set_charge():
    """Ensure we can toggle charging."""
    assert commands.set_enable_charge(True) == [WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE, True)]
    assert commands.set_enable_charge(False) == [WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE, False)]
    with pytest.warns(DeprecationWarning):
        assert commands.enable_charge() == [WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE, True)]
    with pytest.warns(DeprecationWarning):
        assert commands.disable_charge() == [WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE, False)]


async def test_set_discharge():
    """Ensure we can toggle discharging."""
    assert commands.set_enable_discharge(True) == [WriteHoldingRegisterRequest(RegisterMap.ENABLE_DISCHARGE, True)]
    assert commands.set_enable_discharge(False) == [WriteHoldingRegisterRequest(RegisterMap.ENABLE_DISCHARGE, False)]
    with pytest.warns(DeprecationWarning):
        assert commands.enable_discharge() == [WriteHoldingRegisterRequest(RegisterMap.ENABLE_DISCHARGE, True)]
    with pytest.warns(DeprecationWarning):
        assert commands.disable_discharge() == [WriteHoldingRegisterRequest(RegisterMap.ENABLE_DISCHARGE, False)]


async def test_set_battery_discharge_mode():
    """Ensure we can set a discharge mode."""
    assert commands.set_discharge_mode_max_power() == [WriteHoldingRegisterRequest(RegisterMap.BATTERY_POWER_MODE, 0)]
    assert commands.set_discharge_mode_to_match_demand() == [
        WriteHoldingRegisterRequest(RegisterMap.BATTERY_POWER_MODE, 1)
    ]


@pytest.mark.parametrize("discharge", (False, True))
@pytest.mark.parametrize("slot", (1, 2))
@pytest.mark.parametrize("hour1,min1,hour2,min2", [(0, 0, 23, 59), (16, 30, 7, 0)])
async def test_set_slot_single_phase(discharge: bool, slot: int, hour1: int, min1: int, hour2: int, min2: int):
    ts = TimeSlot.from_components(hour1, min1, hour2, min2)
    slot_map = SINGLE_PHASE_SLOTS
    slots = slot_map.discharge_slots if discharge else slot_map.charge_slots
    hr_start, hr_end = slots[slot - 1]
    fn = commands.set_discharge_slot if discharge else commands.set_charge_slot
    reset_fn = commands.reset_discharge_slot if discharge else commands.reset_charge_slot

    assert fn(slot, ts, slot_map) == [
        WriteHoldingRegisterRequest(hr_start, 100 * hour1 + min1),
        WriteHoldingRegisterRequest(hr_end, 100 * hour2 + min2),
    ]
    assert reset_fn(slot, slot_map) == [
        WriteHoldingRegisterRequest(hr_start, 0),
        WriteHoldingRegisterRequest(hr_end, 0),
    ]


@pytest.mark.parametrize("discharge", (False, True))
@pytest.mark.parametrize("slot", range(1, 11))
async def test_set_slot_extended(discharge: bool, slot: int):
    ts = TimeSlot.from_components(1, 0, 2, 0)
    slot_map = EXTENDED_SLOTS
    slots = slot_map.discharge_slots if discharge else slot_map.charge_slots
    hr_start, hr_end = slots[slot - 1]
    fn = commands.set_discharge_slot if discharge else commands.set_charge_slot

    result = fn(slot, ts, slot_map)
    assert isinstance(result[0], WriteHoldingRegisterRequest)
    assert isinstance(result[1], WriteHoldingRegisterRequest)
    assert result[0].register == hr_start
    assert result[1].register == hr_end


@pytest.mark.parametrize("discharge", (False, True))
@pytest.mark.parametrize("slot", range(1, 11))
async def test_set_slot_three_phase(discharge: bool, slot: int):
    ts = TimeSlot.from_components(1, 0, 2, 0)
    slot_map = THREE_PHASE_SLOTS
    slots = slot_map.discharge_slots if discharge else slot_map.charge_slots
    hr_start, hr_end = slots[slot - 1]
    fn = commands.set_discharge_slot if discharge else commands.set_charge_slot

    result = fn(slot, ts, slot_map)
    assert isinstance(result[0], WriteHoldingRegisterRequest)
    assert isinstance(result[1], WriteHoldingRegisterRequest)
    assert result[0].register == hr_start
    assert result[1].register == hr_end


async def test_slot_setters_require_explicit_slot_map():
    """The new-API slot setters must require `slot_map` rather than defaulting it.

    Per dewet22/givenergy-modbus#68 review: defaulting to EXTENDED_SLOTS silently
    wrote to the wrong registers on single-phase / three-phase hardware. Forcing
    callers to thread `inverter.slot_map` makes the dependency explicit and turns
    wrong-register writes into a TypeError at call time.
    """
    ts = TimeSlot.from_components(0, 0, 1, 0)
    setters_with_timeslot = (
        commands.set_charge_slot,
        commands.set_discharge_slot,
    )
    for fn in setters_with_timeslot:
        with pytest.raises(TypeError, match="slot_map"):
            fn(1, ts)  # type: ignore[call-arg]

    reset_setters = (commands.reset_charge_slot, commands.reset_discharge_slot)
    for fn in reset_setters:
        with pytest.raises(TypeError, match="slot_map"):
            fn(1)  # type: ignore[call-arg]

    endpoint_setters = (
        commands.set_charge_slot_start,
        commands.set_charge_slot_end,
        commands.set_discharge_slot_start,
        commands.set_discharge_slot_end,
    )
    for fn in endpoint_setters:
        with pytest.raises(TypeError, match="slot_map"):
            fn(1, dt_time(0, 0))  # type: ignore[call-arg]


async def test_set_slot_index_validation():
    ts = TimeSlot.from_components(0, 0, 1, 0)
    with pytest.raises(ValueError, match="Charge slot index"):
        commands.set_charge_slot(0, ts, SINGLE_PHASE_SLOTS)
    with pytest.raises(ValueError, match="Charge slot index"):
        commands.set_charge_slot(3, ts, SINGLE_PHASE_SLOTS)
    with pytest.raises(ValueError, match="Discharge slot index"):
        commands.reset_discharge_slot(0, EXTENDED_SLOTS)
    with pytest.raises(ValueError, match="Discharge slot index"):
        commands.reset_discharge_slot(11, EXTENDED_SLOTS)


@pytest.mark.parametrize("discharge", (False, True))
@pytest.mark.parametrize("slot", (1, 2))
async def test_set_slot_endpoint_single_phase(discharge: bool, slot: int):
    """Setting just one endpoint of a charge/discharge slot writes exactly one register."""
    slot_map = SINGLE_PHASE_SLOTS
    slots = slot_map.discharge_slots if discharge else slot_map.charge_slots
    hr_start, hr_end = slots[slot - 1]
    start_fn = commands.set_discharge_slot_start if discharge else commands.set_charge_slot_start
    end_fn = commands.set_discharge_slot_end if discharge else commands.set_charge_slot_end

    # Setting a time writes HHMM-encoded value
    assert start_fn(slot, dt_time(16, 30), slot_map) == [WriteHoldingRegisterRequest(hr_start, 1630)]
    assert end_fn(slot, dt_time(7, 0), slot_map) == [WriteHoldingRegisterRequest(hr_end, 700)]
    # Setting None clears just that end (other end untouched)
    assert start_fn(slot, None, slot_map) == [WriteHoldingRegisterRequest(hr_start, 0)]
    assert end_fn(slot, None, slot_map) == [WriteHoldingRegisterRequest(hr_end, 0)]


@pytest.mark.parametrize("discharge", (False, True))
async def test_set_slot_endpoint_index_validation(discharge: bool):
    """Endpoint setters share the same index validation as the whole-slot setters."""
    start_fn = commands.set_discharge_slot_start if discharge else commands.set_charge_slot_start
    end_fn = commands.set_discharge_slot_end if discharge else commands.set_charge_slot_end
    label = "Discharge" if discharge else "Charge"

    with pytest.raises(ValueError, match=f"{label} slot index"):
        start_fn(0, dt_time(1, 0), SINGLE_PHASE_SLOTS)
    with pytest.raises(ValueError, match=f"{label} slot index"):
        end_fn(11, dt_time(1, 0), EXTENDED_SLOTS)


async def test_set_pause_slot_endpoint():
    """Pause slot has its own endpoint setters that write a single register each."""
    assert commands.set_pause_slot_start(dt_time(13, 45)) == [
        WriteHoldingRegisterRequest(RegisterMap.BATTERY_PAUSE_SLOT_START, 1345)
    ]
    assert commands.set_pause_slot_end(dt_time(14, 0)) == [
        WriteHoldingRegisterRequest(RegisterMap.BATTERY_PAUSE_SLOT_END, 1400)
    ]
    assert commands.set_pause_slot_start(None) == [WriteHoldingRegisterRequest(RegisterMap.BATTERY_PAUSE_SLOT_START, 0)]
    assert commands.set_pause_slot_end(None) == [WriteHoldingRegisterRequest(RegisterMap.BATTERY_PAUSE_SLOT_END, 0)]


@pytest.mark.parametrize("idx", (1, 2, 3))
async def test_set_export_slot_endpoint(idx: int):
    """Export slot endpoint setters write a single register each."""
    hr_start = getattr(RegisterMap, f"EXPORT_SLOT_{idx}_START")
    hr_end = getattr(RegisterMap, f"EXPORT_SLOT_{idx}_END")

    assert commands.set_export_slot_start(idx, dt_time(10, 15)) == [WriteHoldingRegisterRequest(hr_start, 1015)]
    assert commands.set_export_slot_end(idx, dt_time(11, 30)) == [WriteHoldingRegisterRequest(hr_end, 1130)]
    assert commands.set_export_slot_start(idx, None) == [WriteHoldingRegisterRequest(hr_start, 0)]
    assert commands.set_export_slot_end(idx, None) == [WriteHoldingRegisterRequest(hr_end, 0)]


async def test_set_export_slot_endpoint_index_validation():
    with pytest.raises(ValueError, match="Export slot index"):
        commands.set_export_slot_start(0, dt_time(1, 0))
    with pytest.raises(ValueError, match="Export slot index"):
        commands.set_export_slot_end(4, dt_time(1, 0))


async def test_whole_slot_setters_defer_to_endpoint_setters():
    """Whole-slot setters must produce identical output to manually composing the endpoint setters."""
    ts = TimeSlot.from_components(8, 15, 18, 45)
    slot_map = SINGLE_PHASE_SLOTS

    composed_charge = commands.set_charge_slot_start(1, ts.start, slot_map) + commands.set_charge_slot_end(
        1, ts.end, slot_map
    )
    assert commands.set_charge_slot(1, ts, slot_map) == composed_charge

    composed_discharge = commands.set_discharge_slot_start(2, ts.start, slot_map) + commands.set_discharge_slot_end(
        2, ts.end, slot_map
    )
    assert commands.set_discharge_slot(2, ts, slot_map) == composed_discharge

    composed_pause = commands.set_pause_slot_start(ts.start) + commands.set_pause_slot_end(ts.end)
    assert commands.set_pause_slot(ts) == composed_pause

    composed_export = commands.set_export_slot_start(2, ts.start) + commands.set_export_slot_end(2, ts.end)
    assert commands.set_export_slot(2, ts) == composed_export


async def test_set_mode_dynamic():
    """Ensure we can set the inverter to dynamic mode."""
    assert commands.set_mode_dynamic() == [
        WriteHoldingRegisterRequest(RegisterMap.BATTERY_POWER_MODE, 1),
        WriteHoldingRegisterRequest(RegisterMap.BATTERY_SOC_RESERVE, 4),
        WriteHoldingRegisterRequest(RegisterMap.ENABLE_DISCHARGE, False),
    ]


async def test_set_mode_storage():
    """Ensure we can set the inverter to a storage mode with discharge slots."""
    assert commands.set_mode_storage(TimeSlot.from_components(1, 2, 3, 4)) == [
        WriteHoldingRegisterRequest(RegisterMap.BATTERY_POWER_MODE, 1),
        WriteHoldingRegisterRequest(RegisterMap.ENABLE_DISCHARGE, True),
        WriteHoldingRegisterRequest(RegisterMap.DISCHARGE_SLOT_1_START, 102),
        WriteHoldingRegisterRequest(RegisterMap.DISCHARGE_SLOT_1_END, 304),
        WriteHoldingRegisterRequest(RegisterMap.DISCHARGE_SLOT_2_START, 0),
        WriteHoldingRegisterRequest(RegisterMap.DISCHARGE_SLOT_2_END, 0),
    ]

    assert commands.set_mode_storage(TimeSlot.from_components(5, 6, 7, 8), TimeSlot.from_components(9, 10, 11, 12)) == [
        WriteHoldingRegisterRequest(RegisterMap.BATTERY_POWER_MODE, 1),
        WriteHoldingRegisterRequest(RegisterMap.ENABLE_DISCHARGE, True),
        WriteHoldingRegisterRequest(RegisterMap.DISCHARGE_SLOT_1_START, 506),
        WriteHoldingRegisterRequest(RegisterMap.DISCHARGE_SLOT_1_END, 708),
        WriteHoldingRegisterRequest(RegisterMap.DISCHARGE_SLOT_2_START, 910),
        WriteHoldingRegisterRequest(RegisterMap.DISCHARGE_SLOT_2_END, 1112),
    ]

    assert commands.set_mode_storage(TimeSlot.from_repr(1314, 1516), discharge_for_export=True) == [
        WriteHoldingRegisterRequest(RegisterMap.BATTERY_POWER_MODE, 0),
        WriteHoldingRegisterRequest(RegisterMap.ENABLE_DISCHARGE, True),
        WriteHoldingRegisterRequest(RegisterMap.DISCHARGE_SLOT_1_START, 1314),
        WriteHoldingRegisterRequest(RegisterMap.DISCHARGE_SLOT_1_END, 1516),
        WriteHoldingRegisterRequest(RegisterMap.DISCHARGE_SLOT_2_START, 0),
        WriteHoldingRegisterRequest(RegisterMap.DISCHARGE_SLOT_2_END, 0),
    ]


async def test_set_charge_and_discharge_limits():
    """Ensure we can set a charge limit."""
    assert commands.set_battery_charge_limit(1) == [
        WriteHoldingRegisterRequest(RegisterMap.BATTERY_CHARGE_LIMIT, 1),
    ]

    assert commands.set_battery_discharge_limit(1) == [
        WriteHoldingRegisterRequest(RegisterMap.BATTERY_DISCHARGE_LIMIT, 1),
    ]

    assert commands.set_battery_charge_limit(50) == [
        WriteHoldingRegisterRequest(RegisterMap.BATTERY_CHARGE_LIMIT, 50),
    ]

    assert commands.set_battery_discharge_limit(50) == [
        WriteHoldingRegisterRequest(RegisterMap.BATTERY_DISCHARGE_LIMIT, 50, device_address=0x11),
    ]

    with pytest.raises(ValueError, match=r"Specified Charge Limit \(51%\) is not in \[0-50\]\%"):
        commands.set_battery_charge_limit(51)
    with pytest.raises(ValueError, match=r"Specified Discharge Limit \(51%\) is not in \[0-50\]\%"):
        commands.set_battery_discharge_limit(51)


async def test_set_system_time():
    """Ensure set_system_time emits the correct requests."""
    assert commands.set_system_date_time(datetime(2022, 11, 23, 4, 34, 59)) == [
        WriteHoldingRegisterRequest(RegisterMap.SYSTEM_TIME_YEAR, 22, device_address=0x11),
        WriteHoldingRegisterRequest(RegisterMap.SYSTEM_TIME_MONTH, 11, device_address=0x11),
        WriteHoldingRegisterRequest(RegisterMap.SYSTEM_TIME_DAY, 23, device_address=0x11),
        WriteHoldingRegisterRequest(RegisterMap.SYSTEM_TIME_HOUR, 4, device_address=0x11),
        WriteHoldingRegisterRequest(RegisterMap.SYSTEM_TIME_MINUTE, 34, device_address=0x11),
        WriteHoldingRegisterRequest(RegisterMap.SYSTEM_TIME_SECOND, 59, device_address=0x11),
    ]


async def test_set_inverter_reboot():
    """Ensure set_inverter_reboot emits the correct requests."""
    assert commands.set_inverter_reboot() == [
        WriteHoldingRegisterRequest(RegisterMap.REBOOT, 100, device_address=0x11),
    ]


async def test_set_active_power_rate():
    assert commands.set_active_power_rate(100) == [WriteHoldingRegisterRequest(RegisterMap.ACTIVE_POWER_RATE, 100)]
    assert commands.set_active_power_rate(0) == [WriteHoldingRegisterRequest(RegisterMap.ACTIVE_POWER_RATE, 0)]
    with pytest.raises(ValueError, match=r"Active power rate \(-1\) must be in \[0-100\]%"):
        commands.set_active_power_rate(-1)
    with pytest.raises(ValueError, match=r"Active power rate \(101\) must be in \[0-100\]%"):
        commands.set_active_power_rate(101)


async def test_set_enable_rtc():
    assert commands.set_enable_rtc(True) == [WriteHoldingRegisterRequest(RegisterMap.ENABLE_RTC, True)]
    assert commands.set_enable_rtc(False) == [WriteHoldingRegisterRequest(RegisterMap.ENABLE_RTC, False)]


async def test_set_battery_charge_limit_ac():
    assert commands.set_battery_charge_limit_ac(50) == [
        WriteHoldingRegisterRequest(RegisterMap.BATTERY_CHARGE_LIMIT_AC, 50)
    ]
    with pytest.raises(ValueError, match="AC Charge Limit"):
        commands.set_battery_charge_limit_ac(0)
    with pytest.raises(ValueError, match="AC Charge Limit"):
        commands.set_battery_charge_limit_ac(101)


async def test_set_battery_discharge_limit_ac():
    assert commands.set_battery_discharge_limit_ac(50) == [
        WriteHoldingRegisterRequest(RegisterMap.BATTERY_DISCHARGE_LIMIT_AC, 50)
    ]
    with pytest.raises(ValueError, match="AC Discharge Limit"):
        commands.set_battery_discharge_limit_ac(0)
    with pytest.raises(ValueError, match="AC Discharge Limit"):
        commands.set_battery_discharge_limit_ac(101)


async def test_set_battery_pause_mode():
    assert commands.set_battery_pause_mode(BatteryPauseMode.DISABLED) == [
        WriteHoldingRegisterRequest(RegisterMap.BATTERY_PAUSE_MODE, BatteryPauseMode.DISABLED)
    ]
    assert commands.set_battery_pause_mode(BatteryPauseMode.PAUSE_BOTH) == [
        WriteHoldingRegisterRequest(RegisterMap.BATTERY_PAUSE_MODE, BatteryPauseMode.PAUSE_BOTH)
    ]


async def test_set_pause_slot():
    slot = TimeSlot.from_components(1, 30, 5, 0)
    assert commands.set_pause_slot(slot) == [
        WriteHoldingRegisterRequest(RegisterMap.BATTERY_PAUSE_SLOT_START, 130),
        WriteHoldingRegisterRequest(RegisterMap.BATTERY_PAUSE_SLOT_END, 500),
    ]
    assert commands.set_pause_slot(None) == [
        WriteHoldingRegisterRequest(RegisterMap.BATTERY_PAUSE_SLOT_START, 0),
        WriteHoldingRegisterRequest(RegisterMap.BATTERY_PAUSE_SLOT_END, 0),
    ]


async def test_set_ac_charge():
    assert commands.set_ac_charge(True) == [WriteHoldingRegisterRequest(RegisterMap.AC_CHARGE_ENABLE, True)]
    assert commands.set_ac_charge(False) == [WriteHoldingRegisterRequest(RegisterMap.AC_CHARGE_ENABLE, False)]


async def test_set_force_charge():
    assert commands.set_force_charge(True) == [WriteHoldingRegisterRequest(RegisterMap.FORCE_CHARGE_ENABLE, True)]


async def test_set_force_discharge():
    assert commands.set_force_discharge(True) == [WriteHoldingRegisterRequest(RegisterMap.FORCE_DISCHARGE_ENABLE, True)]


async def test_set_ems_plant():
    assert commands.set_ems_plant(True) == [WriteHoldingRegisterRequest(RegisterMap.EMS_PLANT_ENABLE, True)]
    assert commands.set_ems_plant(False) == [WriteHoldingRegisterRequest(RegisterMap.EMS_PLANT_ENABLE, False)]


@pytest.mark.parametrize("idx", [1, 2, 3])
async def test_set_export_slot(idx):
    slot = TimeSlot.from_components(16, 0, 20, 0)
    result = commands.set_export_slot(idx, slot)
    assert result[0].register == getattr(RegisterMap, f"EXPORT_SLOT_{idx}_START")
    assert result[1].register == getattr(RegisterMap, f"EXPORT_SLOT_{idx}_END")
    assert result[0].value == 1600
    assert result[1].value == 2000

    cleared = commands.set_export_slot(idx, None)
    assert cleared == [
        WriteHoldingRegisterRequest(getattr(RegisterMap, f"EXPORT_SLOT_{idx}_START"), 0),
        WriteHoldingRegisterRequest(getattr(RegisterMap, f"EXPORT_SLOT_{idx}_END"), 0),
    ]


async def test_set_export_slot_invalid_idx():
    with pytest.raises(ValueError, match="Export slot index"):
        commands.set_export_slot(0, None)
    with pytest.raises(ValueError, match="Export slot index"):
        commands.set_export_slot(4, None)


async def test_set_calibrate_battery_soc():
    assert commands.set_calibrate_battery_soc(0) == [WriteHoldingRegisterRequest(RegisterMap.SOC_FORCE_ADJUST, 0)]
    assert commands.set_calibrate_battery_soc(1) == [WriteHoldingRegisterRequest(RegisterMap.SOC_FORCE_ADJUST, 1)]
    assert commands.set_calibrate_battery_soc(3) == [WriteHoldingRegisterRequest(RegisterMap.SOC_FORCE_ADJUST, 3)]
    assert commands.set_calibrate_battery_soc() == [WriteHoldingRegisterRequest(RegisterMap.SOC_FORCE_ADJUST, 1)]
    with pytest.raises(ValueError, match="Battery calibration mode"):
        commands.set_calibrate_battery_soc(2)
    with pytest.raises(ValueError, match="Battery calibration mode"):
        commands.set_calibrate_battery_soc(4)
