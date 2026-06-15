from datetime import datetime
from datetime import time as dt_time

import pytest

from givenergy_modbus.client import commands
from givenergy_modbus.client.commands import RegisterMap
from givenergy_modbus.model import TimeSlot
from givenergy_modbus.model.battery import BatteryPauseMode, ExportPriority
from givenergy_modbus.model.inverter import EXTENDED_SLOTS, SINGLE_PHASE_SLOTS
from givenergy_modbus.model.inverter_threephase import THREE_PHASE_SLOTS
from givenergy_modbus.pdu import WriteHoldingRegisterRequest


async def test_configure_charge_target():
    """Ensure we can set and disable a charge target."""
    assert commands.set_charge_target_enabled(45) == [
        WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE, 1),
        WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE_TARGET, 1),
        WriteHoldingRegisterRequest(RegisterMap.CHARGE_TARGET_SOC, 45),
    ]
    assert commands.set_charge_target_enabled(100) == [
        WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE, 1),
        WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE_TARGET, 0),
        WriteHoldingRegisterRequest(RegisterMap.CHARGE_TARGET_SOC, 100),
    ]

    with pytest.raises(ValueError, match=r"Charge Target SOC \(0\) must be in \[4-100\]\%"):
        commands.set_charge_target_enabled(0)
    with pytest.raises(ValueError, match=r"Charge Target SOC \(1\) must be in \[4-100\]\%"):
        commands.set_charge_target_enabled(1)
    with pytest.raises(ValueError, match=r"Charge Target SOC \(101\) must be in \[4-100\]\%"):
        commands.set_charge_target_enabled(101)

    assert commands.disable_charge_target() == [
        WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE_TARGET, 0),
        WriteHoldingRegisterRequest(RegisterMap.CHARGE_TARGET_SOC, 100),
    ]


async def test_set_charge_target_is_deprecated_alias():
    """set_charge_target is retained as a deprecated alias for set_charge_target_enabled (1ph + 3ph)."""
    with pytest.warns(DeprecationWarning):
        assert commands.set_charge_target(45) == commands.set_charge_target_enabled(45)
    with pytest.warns(DeprecationWarning):
        assert commands.set_charge_target_3ph(45) == commands.set_charge_target_enabled_3ph(45)


async def test_set_charge_target_soc_writes_only_the_target_register():
    """set_charge_target_soc adjusts the target SOC without touching any enable bit."""
    assert commands.set_charge_target_soc(45) == [
        WriteHoldingRegisterRequest(RegisterMap.CHARGE_TARGET_SOC, 45),
    ]
    assert commands.set_charge_target_soc_3ph(45) == [
        WriteHoldingRegisterRequest(RegisterMap.CHARGE_TARGET_SOC_3PH, 45),
    ]

    # The whole point: no enable side effects (unlike set_charge_target_enabled).
    for reqs in (commands.set_charge_target_soc(45), commands.set_charge_target_soc_3ph(45)):
        written = {r.register for r in reqs}
        assert RegisterMap.ENABLE_CHARGE not in written
        assert RegisterMap.ENABLE_CHARGE_TARGET not in written
        assert RegisterMap.AC_CHARGE_ENABLE not in written

    # 100 writes the register as-is — no special "disable" folding.
    assert commands.set_charge_target_soc(100) == [
        WriteHoldingRegisterRequest(RegisterMap.CHARGE_TARGET_SOC, 100),
    ]

    # Same [4-100] bound as set_charge_target_enabled.
    for fn in (commands.set_charge_target_soc, commands.set_charge_target_soc_3ph):
        with pytest.raises(ValueError, match=r"Charge Target SOC \(0\) must be in \[4-100\]\%"):
            fn(0)
        with pytest.raises(ValueError, match=r"Charge Target SOC \(101\) must be in \[4-100\]\%"):
            fn(101)


async def test_set_charge():
    """Ensure we can toggle charging."""
    assert commands.set_enable_charge(True) == [WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE, 1)]
    assert commands.set_enable_charge(False) == [WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE, 0)]
    with pytest.warns(DeprecationWarning):
        assert commands.enable_charge() == [WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE, 1)]
    with pytest.warns(DeprecationWarning):
        assert commands.disable_charge() == [WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE, 0)]


async def test_set_discharge():
    """Ensure we can toggle discharging."""
    assert commands.set_enable_discharge(True) == [WriteHoldingRegisterRequest(RegisterMap.ENABLE_DISCHARGE, 1)]
    assert commands.set_enable_discharge(False) == [WriteHoldingRegisterRequest(RegisterMap.ENABLE_DISCHARGE, 0)]
    with pytest.warns(DeprecationWarning):
        assert commands.enable_discharge() == [WriteHoldingRegisterRequest(RegisterMap.ENABLE_DISCHARGE, 1)]
    with pytest.warns(DeprecationWarning):
        assert commands.disable_discharge() == [WriteHoldingRegisterRequest(RegisterMap.ENABLE_DISCHARGE, 0)]


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
        WriteHoldingRegisterRequest(RegisterMap.ENABLE_DISCHARGE, 0),
    ]


async def test_set_mode_storage():
    """Ensure we can set the inverter to a storage mode with discharge slots."""
    assert commands.set_mode_storage(TimeSlot.from_components(1, 2, 3, 4)) == [
        WriteHoldingRegisterRequest(RegisterMap.BATTERY_POWER_MODE, 1),
        WriteHoldingRegisterRequest(RegisterMap.ENABLE_DISCHARGE, 1),
        WriteHoldingRegisterRequest(RegisterMap.DISCHARGE_SLOT_1_START, 102),
        WriteHoldingRegisterRequest(RegisterMap.DISCHARGE_SLOT_1_END, 304),
        WriteHoldingRegisterRequest(RegisterMap.DISCHARGE_SLOT_2_START, 0),
        WriteHoldingRegisterRequest(RegisterMap.DISCHARGE_SLOT_2_END, 0),
    ]

    assert commands.set_mode_storage(TimeSlot.from_components(5, 6, 7, 8), TimeSlot.from_components(9, 10, 11, 12)) == [
        WriteHoldingRegisterRequest(RegisterMap.BATTERY_POWER_MODE, 1),
        WriteHoldingRegisterRequest(RegisterMap.ENABLE_DISCHARGE, 1),
        WriteHoldingRegisterRequest(RegisterMap.DISCHARGE_SLOT_1_START, 506),
        WriteHoldingRegisterRequest(RegisterMap.DISCHARGE_SLOT_1_END, 708),
        WriteHoldingRegisterRequest(RegisterMap.DISCHARGE_SLOT_2_START, 910),
        WriteHoldingRegisterRequest(RegisterMap.DISCHARGE_SLOT_2_END, 1112),
    ]

    assert commands.set_mode_storage(TimeSlot.from_repr(1314, 1516), discharge_for_export=True) == [
        WriteHoldingRegisterRequest(RegisterMap.BATTERY_POWER_MODE, 0),
        WriteHoldingRegisterRequest(RegisterMap.ENABLE_DISCHARGE, 1),
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


async def test_set_system_time_rejects_pre_2000_year():
    """A pre-2000 year must be rejected with a clear ValueError (audit L6).

    Otherwise it underflows to a negative register and a confusing encode-time InvalidPduState.
    """
    with pytest.raises(ValueError, match="2000"):
        commands.set_system_date_time(datetime(1999, 12, 31, 23, 59, 59))


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
    assert commands.set_enable_rtc(True) == [WriteHoldingRegisterRequest(RegisterMap.ENABLE_RTC, 1)]
    assert commands.set_enable_rtc(False) == [WriteHoldingRegisterRequest(RegisterMap.ENABLE_RTC, 0)]


async def test_set_export_priority():
    assert commands.set_export_priority(ExportPriority.GRID_FIRST) == [
        WriteHoldingRegisterRequest(RegisterMap.EXPORT_PRIORITY, ExportPriority.GRID_FIRST)
    ]
    # Raw int that maps to a valid member is coerced.
    assert commands.set_export_priority(2) == [
        WriteHoldingRegisterRequest(RegisterMap.EXPORT_PRIORITY, ExportPriority.LOAD_FIRST)
    ]
    with pytest.raises(ValueError, match="Invalid export priority"):
        commands.set_export_priority(99)
    # HR311 must be in the lower-level PDU allowlist, or encode() raises InvalidPduState.
    commands.set_export_priority(ExportPriority.BATTERY_FIRST)[0].encode()


async def test_set_enable_eps():
    assert commands.set_enable_eps(True) == [WriteHoldingRegisterRequest(RegisterMap.ENABLE_EPS, 1)]
    assert commands.set_enable_eps(False) == [WriteHoldingRegisterRequest(RegisterMap.ENABLE_EPS, 0)]
    # HR317 must be in the lower-level PDU allowlist, or encode() raises InvalidPduState.
    commands.set_enable_eps(True)[0].encode()


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


def test_battery_ac_limit_single_phase_read_write_register_consistency():
    """Single-phase AC limit read-back reads the same register the write command targets.

    Pins read==write on single-phase so the model LUT and the command can't silently
    drift to different registers. The write target (RegisterMap) is the source of truth;
    reading that exact register back must surface on the model field.
    """
    from givenergy_modbus.model.inverter import SinglePhaseInverter
    from givenergy_modbus.model.register import HR
    from givenergy_modbus.model.register_cache import RegisterCache

    charge_reg = int(RegisterMap.BATTERY_CHARGE_LIMIT_AC)
    discharge_reg = int(RegisterMap.BATTERY_DISCHARGE_LIMIT_AC)
    inv = SinglePhaseInverter.from_register_cache(RegisterCache({HR(charge_reg): 55, HR(discharge_reg): 80}))
    assert inv.battery_charge_limit_ac == 55
    assert inv.battery_discharge_limit_ac == 80


def test_battery_ac_limit_three_phase_readback_diverges_from_write():
    """Pin the known three-phase read != write gap (#75): the divergence is intentional.

    The write command targets the single-phase HR313/314, but ThreePhaseInverter remaps
    the read-backs to HR1110/1108. Asserting both sides keeps the gap explicit and
    flagged until per-model command-register selection lands (#75).
    """
    from givenergy_modbus.model.inverter_threephase import ThreePhaseInverter
    from givenergy_modbus.model.register import HR
    from givenergy_modbus.model.register_cache import RegisterCache

    charge_reg = int(RegisterMap.BATTERY_CHARGE_LIMIT_AC)  # 313
    discharge_reg = int(RegisterMap.BATTERY_DISCHARGE_LIMIT_AC)  # 314
    # Single-phase write registers and the three-phase read-backs hold different values.
    tp = ThreePhaseInverter.from_register_cache(
        RegisterCache({HR(charge_reg): 11, HR(1110): 99, HR(discharge_reg): 22, HR(1108): 88})
    )
    # Three-phase reads its remapped registers, NOT the single-phase write target.
    assert tp.battery_charge_limit_ac == 99  # HR(1110), not HR(313)=11
    assert tp.battery_discharge_limit_ac == 88  # HR(1108), not HR(314)=22
    # Meanwhile the write command still targets the single-phase registers — the gap.
    assert commands.set_battery_charge_limit_ac(50) == [
        WriteHoldingRegisterRequest(RegisterMap.BATTERY_CHARGE_LIMIT_AC, 50)
    ]
    assert commands.set_battery_discharge_limit_ac(50) == [
        WriteHoldingRegisterRequest(RegisterMap.BATTERY_DISCHARGE_LIMIT_AC, 50)
    ]


def test_set_battery_reserve_soc():
    """set_battery_reserve_soc targets HR(1078) and enforces [4-100]% bounds."""
    assert commands.set_battery_reserve_soc(10) == [WriteHoldingRegisterRequest(RegisterMap.BATTERY_RESERVE_SOC, 10)]
    assert commands.set_battery_reserve_soc(100) == [WriteHoldingRegisterRequest(RegisterMap.BATTERY_RESERVE_SOC, 100)]
    with pytest.raises(ValueError, match="Battery reserve SOC"):
        commands.set_battery_reserve_soc(3)
    with pytest.raises(ValueError, match="Battery reserve SOC"):
        commands.set_battery_reserve_soc(101)


def test_battery_reserve_soc_three_phase_read_write_consistency():
    """ThreePhaseInverter reads battery_reserve_soc from the same register the command writes."""
    from givenergy_modbus.model.inverter_threephase import ThreePhaseInverter
    from givenergy_modbus.model.register import HR
    from givenergy_modbus.model.register_cache import RegisterCache

    reg = int(RegisterMap.BATTERY_RESERVE_SOC)  # 1078
    tph = ThreePhaseInverter.from_register_cache(RegisterCache({HR(reg): 15}))
    assert tph.battery_reserve_soc == 15
    assert commands.set_battery_reserve_soc(15) == [WriteHoldingRegisterRequest(RegisterMap.BATTERY_RESERVE_SOC, 15)]


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
    assert commands.set_ac_charge(True) == [WriteHoldingRegisterRequest(RegisterMap.AC_CHARGE_ENABLE, 1)]
    assert commands.set_ac_charge(False) == [WriteHoldingRegisterRequest(RegisterMap.AC_CHARGE_ENABLE, 0)]


async def test_set_force_charge():
    assert commands.set_force_charge(True) == [WriteHoldingRegisterRequest(RegisterMap.FORCE_CHARGE_ENABLE, 1)]


async def test_set_force_discharge():
    assert commands.set_force_discharge(True) == [WriteHoldingRegisterRequest(RegisterMap.FORCE_DISCHARGE_ENABLE, 1)]


async def test_set_ems_plant():
    assert commands.set_ems_plant(True) == [WriteHoldingRegisterRequest(RegisterMap.EMS_PLANT_ENABLE, 1)]
    assert commands.set_ems_plant(False) == [WriteHoldingRegisterRequest(RegisterMap.EMS_PLANT_ENABLE, 0)]


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


# --- EMS plant-level scheduling (#130) -----------------------------------


def test_set_ems_charge_slot_uses_ems_registers():
    ts = TimeSlot.from_components(2, 0, 5, 30)
    # EMS_SLOTS charge slot 1 = (2053, 2054)
    assert commands.set_ems_charge_slot(1, ts) == [
        WriteHoldingRegisterRequest(2053, 200),
        WriteHoldingRegisterRequest(2054, 530),
    ]
    # slot 3 = (2059, 2060)
    assert commands.set_ems_charge_slot(3, ts) == [
        WriteHoldingRegisterRequest(2059, 200),
        WriteHoldingRegisterRequest(2060, 530),
    ]


def test_set_ems_discharge_slot_uses_ems_registers():
    ts = TimeSlot.from_components(16, 0, 19, 0)
    # EMS_SLOTS discharge slot 1 = (2044, 2045)
    assert commands.set_ems_discharge_slot(1, ts) == [
        WriteHoldingRegisterRequest(2044, 1600),
        WriteHoldingRegisterRequest(2045, 1900),
    ]


def test_set_ems_slot_none_clears():
    assert commands.set_ems_charge_slot(2, None) == [
        WriteHoldingRegisterRequest(2056, 0),
        WriteHoldingRegisterRequest(2057, 0),
    ]
    assert commands.set_ems_discharge_slot(2, None) == [
        WriteHoldingRegisterRequest(2047, 0),
        WriteHoldingRegisterRequest(2048, 0),
    ]


def test_set_ems_slot_endpoints_write_single_registers():
    """Per-endpoint EMS setters write one register each.

    For consumers (HA) that model slot start/end as independent entities — parity
    with the inverter slot API.
    """
    # charge slot 1 = (2053, 2054)
    assert commands.set_ems_charge_slot_start(1, dt_time(2, 0)) == [WriteHoldingRegisterRequest(2053, 200)]
    assert commands.set_ems_charge_slot_end(1, dt_time(5, 30)) == [WriteHoldingRegisterRequest(2054, 530)]
    # discharge slot 3 = (2050, 2051)
    assert commands.set_ems_discharge_slot_start(3, dt_time(16, 0)) == [WriteHoldingRegisterRequest(2050, 1600)]
    assert commands.set_ems_discharge_slot_end(3, dt_time(19, 0)) == [WriteHoldingRegisterRequest(2051, 1900)]
    # None clears the single endpoint
    assert commands.set_ems_charge_slot_start(1, None) == [WriteHoldingRegisterRequest(2053, 0)]


def test_set_ems_slot_endpoints_compose_to_whole_slot():
    """Start + end endpoints together produce the same frames as the whole-slot setter."""
    ts = TimeSlot.from_components(1, 15, 6, 45)
    composed = commands.set_ems_charge_slot_start(2, ts.start) + commands.set_ems_charge_slot_end(2, ts.end)
    assert composed == commands.set_ems_charge_slot(2, ts)


def test_set_ems_slot_endpoint_index_validation():
    """EMS endpoint setters reject slot indices outside [1-3] (EMS_SLOTS has 3 slots)."""
    for fn in (
        commands.set_ems_charge_slot_start,
        commands.set_ems_charge_slot_end,
        commands.set_ems_discharge_slot_start,
        commands.set_ems_discharge_slot_end,
    ):
        with pytest.raises(ValueError, match="slot index"):
            fn(0, dt_time(1, 0))
        with pytest.raises(ValueError, match="slot index"):
            fn(4, dt_time(1, 0))


def test_set_ems_target_soc():
    assert commands.set_ems_charge_target_soc(1, 80) == [WriteHoldingRegisterRequest(2055, 80)]
    assert commands.set_ems_discharge_target_soc(3, 20) == [WriteHoldingRegisterRequest(2052, 20)]
    assert commands.set_ems_export_target_soc(2, 100) == [WriteHoldingRegisterRequest(2067, 100)]


def test_set_ems_export_power_limit():
    assert commands.set_ems_export_power_limit(3600) == [WriteHoldingRegisterRequest(2071, 3600)]


def test_set_ems_export_slot_uses_ems_registers():
    ts = TimeSlot.from_components(0, 0, 4, 30)
    # EMS export slot 1 = (2062, 2063), slot 3 = (2068, 2069)
    assert commands.set_ems_export_slot(1, ts) == [
        WriteHoldingRegisterRequest(2062, 0),
        WriteHoldingRegisterRequest(2063, 430),
    ]
    assert commands.set_ems_export_slot_start(3, dt_time(1, 0)) == [WriteHoldingRegisterRequest(2068, 100)]
    assert commands.set_ems_export_slot_end(3, dt_time(2, 0)) == [WriteHoldingRegisterRequest(2069, 200)]


def test_set_ems_export_slot_is_alias_of_export_slot():
    """The EMS-named export setters are aliases of set_export_slot_* (same EMS registers)."""
    ts = TimeSlot.from_components(1, 15, 6, 45)
    assert commands.set_ems_export_slot(2, ts) == commands.set_export_slot(2, ts)
    assert commands.set_ems_export_slot_start(2, ts.start) == commands.set_export_slot_start(2, ts.start)
    assert commands.set_ems_export_slot_end(2, ts.end) == commands.set_export_slot_end(2, ts.end)


def test_set_ems_export_slot_none_clears():
    assert commands.set_ems_export_slot(1, None) == [
        WriteHoldingRegisterRequest(2062, 0),
        WriteHoldingRegisterRequest(2063, 0),
    ]


def test_set_ems_export_slot_index_validation():
    for fn in (commands.set_ems_export_slot_start, commands.set_ems_export_slot_end):
        with pytest.raises(ValueError, match="slot index"):
            fn(0, dt_time(1, 0))
        with pytest.raises(ValueError, match="slot index"):
            fn(4, dt_time(1, 0))
    # whole-slot setter validates the index too (via set_export_slot)
    ts = TimeSlot.from_components(0, 0, 1, 0)
    with pytest.raises(ValueError, match="slot index"):
        commands.set_ems_export_slot(0, ts)
    with pytest.raises(ValueError, match="slot index"):
        commands.set_ems_export_slot(4, ts)


def test_set_ems_target_soc_validation():
    for fn in (
        commands.set_ems_charge_target_soc,
        commands.set_ems_discharge_target_soc,
        commands.set_ems_export_target_soc,
    ):
        with pytest.raises(ValueError, match="must be in"):
            fn(1, 101)
        with pytest.raises(ValueError, match="must be in"):
            fn(0, 50)  # bad slot index


def test_set_ems_export_power_limit_bounds():
    with pytest.raises(ValueError, match=r"\[0-65535\]"):
        commands.set_ems_export_power_limit(-1)
    with pytest.raises(ValueError, match=r"\[0-65535\]"):
        commands.set_ems_export_power_limit(70000)  # exceeds 16-bit register
    assert commands.set_ems_export_power_limit(65535) == [WriteHoldingRegisterRequest(2071, 65535)]


def test_ems_commands_are_write_safe():
    """Every EMS command's register must be in WRITE_SAFE_REGISTERS.

    Otherwise WriteHoldingRequest.ensure_valid_state() would reject it at send time.
    """
    from givenergy_modbus.pdu.write_registers import WRITE_SAFE_REGISTERS

    ts = TimeSlot.from_components(1, 0, 2, 0)
    reqs: list = []
    for idx in (1, 2, 3):
        reqs += commands.set_ems_charge_slot(idx, ts)
        reqs += commands.set_ems_discharge_slot(idx, ts)
        reqs += commands.set_ems_charge_target_soc(idx, 50)
        reqs += commands.set_ems_discharge_target_soc(idx, 50)
        reqs += commands.set_ems_export_target_soc(idx, 50)
        reqs += commands.set_export_slot(idx, ts)
    reqs += commands.set_ems_export_power_limit(2000)
    for r in reqs:
        assert r.register in WRITE_SAFE_REGISTERS, f"register {r.register} not write-safe"
        assert r.device_address == 0x11, f"EMS write to {r.register} should target 0x11"


def test_app_confirmed_registers_are_write_safe():
    """Registers GE exposes on the app's Direct Control (Control) tab are write-safe.

    The app listing each as user-editable is authoritative evidence they accept
    writes (see #48). Locks in the 2026-06-02 batch so they can't silently regress.
    """
    from givenergy_modbus.pdu.write_registers import WRITE_SAFE_REGISTERS

    app_confirmed = {
        104,
        172,
        199,
        299,
        331,  # standard block
        1005,
        1078,
        1108,
        1109,
        1110,
        1111,  # three-phase rates/limits
        1113,
        1114,
        1115,
        1116,
        1118,
        1119,
        1120,
        1121,  # three-phase slots
        5010,
        5014,  # hardware-control block
        *range(554, 574),  # SMART_LOAD_SLOT_1..10 start/end (HR554-573)
    }
    missing = app_confirmed - WRITE_SAFE_REGISTERS
    assert not missing, f"app-confirmed registers not write-safe: {sorted(missing)}"
    # HR479 (DC Wind CVT Voltage) is app-writable but held back — an unbounded
    # voltage setpoint with no range guard; admit only with a validating set_*.
    assert 479 not in WRITE_SAFE_REGISTERS
    # Each register must encode without raising — symmetric with the negative test
    # in conftest.py that verifies unsafe registers raise on encode().
    for reg in app_confirmed:
        req = WriteHoldingRegisterRequest(register=reg, value=0)
        assert req.encode(), f"encode() failed for app-confirmed register {reg}"


def test_refresh_plant_data_is_a_raising_stub():
    """The removed 0x32-poll builder is import-compatible but raises on call (#105/#156).

    Kept so external `from ...commands import refresh_plant_data` doesn't ImportError,
    but raises PlantNotDetected pointing at detect()/load_config()/refresh() rather
    than rebuilding the unsafe fixed-0x32 poll.
    """
    from givenergy_modbus.exceptions import PlantNotDetected

    with pytest.warns(DeprecationWarning):
        with pytest.raises(PlantNotDetected, match="detect()"):
            commands.refresh_plant_data(True)


@pytest.mark.parametrize(
    "helper",
    [
        commands.set_battery_soc_reserve,
        commands.set_battery_reserve_soc,
        commands.set_battery_charge_limit,
        commands.set_battery_discharge_limit,
        commands.set_battery_power_reserve,
        commands.set_active_power_rate,
        commands.set_battery_charge_limit_ac,
        commands.set_battery_discharge_limit_ac,
        commands.set_ems_export_power_limit,
    ],
)
def test_numeric_helpers_reject_bool(helper):
    """Numeric command helpers reject bool before their int() coercion (audit L1).

    These helpers coerce with int(value) before constructing the request, so the PDU-level
    bool guard never sees the bool — set_active_power_rate(True) would silently write 1.
    """
    with pytest.raises(ValueError, match="bool"):
        helper(True)
    with pytest.raises(ValueError, match="bool"):
        helper(False)


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(
            lambda: commands.set_charge_slot_start(True, dt_time(1, 0), SINGLE_PHASE_SLOTS), id="charge_slot_start"
        ),
        pytest.param(
            lambda: commands.set_discharge_slot_end(True, dt_time(1, 0), SINGLE_PHASE_SLOTS), id="discharge_slot_end"
        ),
        pytest.param(lambda: commands.set_export_slot_start(True, dt_time(1, 0)), id="export_slot_start"),
        pytest.param(lambda: commands.set_smart_load_slot_start(True, dt_time(1, 0)), id="smart_load_slot_start"),
        pytest.param(lambda: commands.set_smart_load_slot_end(True, dt_time(1, 0)), id="smart_load_slot_end"),
        pytest.param(lambda: commands.set_ems_charge_target_soc(True, 50), id="ems_charge_target_soc"),
        pytest.param(lambda: commands.set_ems_discharge_target_soc(True, 50), id="ems_discharge_target_soc"),
        pytest.param(lambda: commands.set_ems_export_target_soc(True, 50), id="ems_export_target_soc"),
    ],
)
def test_slot_index_arguments_reject_bool(call):
    """Slot/index selector arguments reject bool (audit L1 follow-up).

    True == 1 passes the `1 <= idx` bounds checks and silently selects slot 1's REGISTER —
    the same caller-error class as bool values, but worse on a write API: it picks the wrong
    register rather than the wrong value.
    """
    with pytest.raises(ValueError, match="bool"):
        call()


def test_numeric_arguments_reject_non_integral_and_str():
    """_as_int-guarded arguments reject non-integral floats and strings (fail loud, audit L1).

    2.9 as a slot index would silently truncate to slot 2 (wrong-register selection); "100"
    as a value is type confusion. Integral floats (50.0) stay accepted — they're unambiguous.
    """
    with pytest.raises(ValueError, match="integral"):
        commands.set_export_slot_start(2.9, dt_time(1, 0))
    with pytest.raises(ValueError, match="integral"):
        commands.set_battery_soc_reserve(50.5)
    with pytest.raises(ValueError, match="number"):
        commands.set_battery_soc_reserve("100")
    # Integral float remains accepted and resolves identically to the int.
    assert commands.set_battery_soc_reserve(50.0) == commands.set_battery_soc_reserve(50)


def test_set_export_priority_rejects_bool():
    """set_export_priority rejects bool before the enum conversion (audit L1 follow-up).

    ExportPriority(True) resolves to GRID_FIRST (1) and would pass as an IntEnum — silently
    selecting a write mode. A bool here is a caller error and must fail loudly. Valid enum
    members (and their int values) still work.
    """
    with pytest.raises(ValueError, match="bool"):
        commands.set_export_priority(True)
    with pytest.raises(ValueError, match="bool"):
        commands.set_export_priority(False)
    # Valid members / ints unaffected.
    assert commands.set_export_priority(ExportPriority.GRID_FIRST) == [
        WriteHoldingRegisterRequest(RegisterMap.EXPORT_PRIORITY, ExportPriority.GRID_FIRST)
    ]
    assert commands.set_export_priority(2) == [WriteHoldingRegisterRequest(RegisterMap.EXPORT_PRIORITY, 2)]


def test_set_battery_pause_mode_rejects_bool():
    """set_battery_pause_mode passes the raw value, so the PDU bool guard rejects True/False."""
    with pytest.raises(ValueError, match="bool|unacceptable"):
        commands.set_battery_pause_mode(True)
