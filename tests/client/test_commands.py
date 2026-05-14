from datetime import datetime

import pytest

from givenergy_modbus.client import commands
from givenergy_modbus.client.commands import RegisterMap
from givenergy_modbus.model import TimeSlot
from givenergy_modbus.model.battery import BatteryPauseMode
from givenergy_modbus.model.inverter import SINGLE_PHASE_SLOTS
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


@pytest.mark.parametrize("action", ("charge", "discharge"))
@pytest.mark.parametrize("slot", (1, 2))
@pytest.mark.parametrize("hour1", (0, 23))
@pytest.mark.parametrize("min1", (0, 59))
@pytest.mark.parametrize("hour2", (0, 23))
@pytest.mark.parametrize("min2", (0, 59))
async def test_set_charge_slots(action: str, slot: int, hour1: int, min1: int, hour2: int, min2: int):
    """Ensure we can set charge time slots correctly."""
    # test set and reset functions for the relevant {action} and {slot}
    messages = getattr(commands, f"set_{action}_slot_{slot}")(TimeSlot.from_components(hour1, min1, hour2, min2))

    hr_start = getattr(RegisterMap, f"{'CHARGE' if action == 'charge' else 'DISCHARGE'}_SLOT_{slot}_START")
    hr_end = getattr(RegisterMap, f"{'CHARGE' if action == 'charge' else 'DISCHARGE'}_SLOT_{slot}_END")
    assert messages == [
        WriteHoldingRegisterRequest(hr_start, 100 * hour1 + min1),
        WriteHoldingRegisterRequest(hr_end, 100 * hour2 + min2),
    ]

    assert getattr(commands, f"reset_{action}_slot_{slot}")() == [
        WriteHoldingRegisterRequest(hr_start, 0),
        WriteHoldingRegisterRequest(hr_end, 0),
    ]


@pytest.mark.parametrize(
    "fn,ts_arg,discharge,idx",
    [
        ("set_charge_slot_1", TimeSlot.from_components(1, 0, 2, 0), False, 0),
        ("set_charge_slot_2", TimeSlot.from_components(1, 0, 2, 0), False, 1),
        ("set_discharge_slot_1", TimeSlot.from_components(16, 0, 7, 0), True, 0),
        ("set_discharge_slot_2", TimeSlot.from_components(16, 0, 7, 0), True, 1),
    ],
)
async def test_slot_setters_route_via_slot_map(fn, ts_arg, discharge, idx):
    slots = THREE_PHASE_SLOTS.discharge_slots if discharge else THREE_PHASE_SLOTS.charge_slots
    hr_start, hr_end = slots[idx]
    result = getattr(commands, fn)(ts_arg, slot_map=THREE_PHASE_SLOTS)
    assert result[0].register == hr_start
    assert result[1].register == hr_end


async def test_slot_setters_default_to_single_phase():
    result = commands.set_charge_slot_1(TimeSlot.from_components(0, 0, 1, 0))
    assert result[0].register == SINGLE_PHASE_SLOTS.charge_slots[0][0]
    assert result[1].register == SINGLE_PHASE_SLOTS.charge_slots[0][1]


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
        WriteHoldingRegisterRequest(RegisterMap.BATTERY_DISCHARGE_LIMIT, 50, slave_address=0x11),
    ]

    with pytest.raises(ValueError, match=r"Specified Charge Limit \(51%\) is not in \[0-50\]\%"):
        commands.set_battery_charge_limit(51)
    with pytest.raises(ValueError, match=r"Specified Discharge Limit \(51%\) is not in \[0-50\]\%"):
        commands.set_battery_discharge_limit(51)


async def test_set_system_time():
    """Ensure set_system_time emits the correct requests."""
    assert commands.set_system_date_time(datetime(2022, 11, 23, 4, 34, 59)) == [
        WriteHoldingRegisterRequest(RegisterMap.SYSTEM_TIME_YEAR, 22, slave_address=0x11),
        WriteHoldingRegisterRequest(RegisterMap.SYSTEM_TIME_MONTH, 11, slave_address=0x11),
        WriteHoldingRegisterRequest(RegisterMap.SYSTEM_TIME_DAY, 23, slave_address=0x11),
        WriteHoldingRegisterRequest(RegisterMap.SYSTEM_TIME_HOUR, 4, slave_address=0x11),
        WriteHoldingRegisterRequest(RegisterMap.SYSTEM_TIME_MINUTE, 34, slave_address=0x11),
        WriteHoldingRegisterRequest(RegisterMap.SYSTEM_TIME_SECOND, 59, slave_address=0x11),
    ]


async def test_set_inverter_reboot():
    """Ensure set_inverter_reboot emits the correct requests."""
    assert commands.set_inverter_reboot() == [
        WriteHoldingRegisterRequest(RegisterMap.REBOOT, 100, slave_address=0x11),
    ]


async def test_set_active_power_rate():
    assert commands.set_active_power_rate(100) == [WriteHoldingRegisterRequest(RegisterMap.ACTIVE_POWER_RATE, 100)]
    assert commands.set_active_power_rate(0) == [WriteHoldingRegisterRequest(RegisterMap.ACTIVE_POWER_RATE, 0)]


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
