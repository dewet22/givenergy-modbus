"""High-level methods for interacting with a remote system."""

from typing import List, Optional

from arrow import Arrow

from givenergy_modbus.client import Timeslot
from givenergy_modbus.model.register import HoldingRegister
from givenergy_modbus.pdu import (
    ReadHoldingRegistersRequest,
    ReadInputRegistersRequest,
    TransparentRequest,
    WriteHoldingRegisterRequest,
)


def refresh_plant_data(complete: bool, number_batteries: int = 1, max_batteries: int = 5) -> List[TransparentRequest]:
    """Refresh plant data."""
    requests: List[TransparentRequest] = [
        ReadInputRegistersRequest(base_register=0, register_count=60, slave_address=0x32),
        ReadInputRegistersRequest(base_register=180, register_count=60, slave_address=0x32),
    ]
    if complete:
        requests.append(ReadHoldingRegistersRequest(base_register=0, register_count=60, slave_address=0x32))
        requests.append(ReadHoldingRegistersRequest(base_register=60, register_count=60, slave_address=0x32))
        requests.append(ReadHoldingRegistersRequest(base_register=120, register_count=60, slave_address=0x32))
        requests.append(ReadInputRegistersRequest(base_register=120, register_count=60, slave_address=0x32))
        number_batteries = max_batteries
    for i in range(number_batteries):
        requests.append(ReadInputRegistersRequest(base_register=60, register_count=60, slave_address=0x32 + i))
    return requests


def disable_charge_target() -> List[TransparentRequest]:
    """Removes SOC limit and target 100% charging."""
    return [
        WriteHoldingRegisterRequest(HoldingRegister.ENABLE_CHARGE_TARGET, False),
        WriteHoldingRegisterRequest(HoldingRegister.CHARGE_TARGET_SOC, 100),
    ]


def set_charge_target(target_soc: int) -> List[TransparentRequest]:
    """Sets inverter to stop charging when SOC reaches the desired level. Also referred to as "winter mode"."""
    if not 4 <= target_soc <= 100:
        raise ValueError(f'Charge Target SOC ({target_soc}) must be in [4-100]%')
    ret = enable_charge()
    if target_soc == 100:
        ret.extend(disable_charge_target())
    else:
        ret.append(WriteHoldingRegisterRequest(HoldingRegister.ENABLE_CHARGE_TARGET, True))
        ret.append(WriteHoldingRegisterRequest(HoldingRegister.CHARGE_TARGET_SOC, target_soc))
    return ret


def enable_charge() -> List[TransparentRequest]:
    """Enable the battery to charge, depending on the mode and slots set."""
    return [WriteHoldingRegisterRequest(HoldingRegister.ENABLE_CHARGE, True)]


def disable_charge() -> List[TransparentRequest]:
    """Prevent the battery from charging at all."""
    return [WriteHoldingRegisterRequest(HoldingRegister.ENABLE_CHARGE, False)]


def enable_discharge() -> List[TransparentRequest]:
    """Enable the battery to discharge, depending on the mode and slots set."""
    return [WriteHoldingRegisterRequest(HoldingRegister.ENABLE_DISCHARGE, True)]


def disable_discharge() -> List[TransparentRequest]:
    """Prevent the battery from discharging at all."""
    return [WriteHoldingRegisterRequest(HoldingRegister.ENABLE_DISCHARGE, False)]


def set_discharge_mode_max_power() -> List[TransparentRequest]:
    """Set the battery discharge mode to maximum power, exporting to the grid if it exceeds load demand."""
    return [WriteHoldingRegisterRequest(HoldingRegister.BATTERY_POWER_MODE, 0)]


def set_discharge_mode_to_match_demand() -> List[TransparentRequest]:
    """Set the battery discharge mode to match demand, avoiding exporting power to the grid."""
    return [WriteHoldingRegisterRequest(HoldingRegister.BATTERY_POWER_MODE, 1)]


def set_shallow_charge(val: int) -> List[TransparentRequest]:
    """Set the minimum level of charge to maintain."""
    # TODO what are valid values? 4-100?
    if not 4 <= val <= 100:
        raise ValueError(f'Minimum SOC / shallow charge ({val}) must be in [4-100]%')
    return [WriteHoldingRegisterRequest(HoldingRegister.BATTERY_SOC_RESERVE, val)]


def set_battery_charge_limit(val: int) -> List[TransparentRequest]:
    """Set the battery charge power limit as percentage. 50% (2.6 kW) is the maximum for most inverters."""
    if not 0 <= val <= 50:
        raise ValueError(f'Specified Charge Limit ({val}%) is not in [0-50]%')
    return [WriteHoldingRegisterRequest(HoldingRegister.BATTERY_CHARGE_LIMIT, val)]


def set_battery_discharge_limit(val: int) -> List[TransparentRequest]:
    """Set the battery discharge power limit as percentage. 50% (2.6 kW) is the maximum for most inverters."""
    if not 0 <= val <= 50:
        raise ValueError(f'Specified Discharge Limit ({val}%) is not in [0-50]%')
    return [WriteHoldingRegisterRequest(HoldingRegister.BATTERY_DISCHARGE_LIMIT, val)]


def set_battery_power_reserve(val: int) -> List[TransparentRequest]:
    """Set the battery power reserve to maintain."""
    # TODO what are valid values?
    if not 4 <= val <= 100:
        raise ValueError(f'Battery power reserve ({val}) must be in [4-100]%')
    return [WriteHoldingRegisterRequest(HoldingRegister.BATTERY_DISCHARGE_MIN_POWER_RESERVE, val)]


def _set_charge_slot(discharge: bool, idx: int, slot: Optional[Timeslot]) -> List[TransparentRequest]:
    hr_start, hr_end = (
        HoldingRegister[f'{"DIS" if discharge else ""}CHARGE_SLOT_{idx}_START'],
        HoldingRegister[f'{"DIS" if discharge else ""}CHARGE_SLOT_{idx}_END'],
    )
    if slot:
        return [
            WriteHoldingRegisterRequest(hr_start, int(slot.start.strftime('%H%M'))),
            WriteHoldingRegisterRequest(hr_end, int(slot.end.strftime('%H%M'))),
        ]
    else:
        return [
            WriteHoldingRegisterRequest(hr_start, 0),
            WriteHoldingRegisterRequest(hr_end, 0),
        ]


def set_charge_slot_1(timeslot: Timeslot) -> List[TransparentRequest]:
    """Set first charge slot start & end times."""
    return _set_charge_slot(False, 1, timeslot)


def reset_charge_slot_1() -> List[TransparentRequest]:
    """Reset first charge slot to zero/disabled."""
    return _set_charge_slot(False, 1, None)


def set_charge_slot_2(timeslot: Timeslot) -> List[TransparentRequest]:
    """Set second charge slot start & end times."""
    return _set_charge_slot(False, 2, timeslot)


def reset_charge_slot_2() -> List[TransparentRequest]:
    """Reset second charge slot to zero/disabled."""
    return _set_charge_slot(False, 2, None)


def set_discharge_slot_1(timeslot: Timeslot) -> List[TransparentRequest]:
    """Set first discharge slot start & end times."""
    return _set_charge_slot(True, 1, timeslot)


def reset_discharge_slot_1() -> List[TransparentRequest]:
    """Reset first discharge slot to zero/disabled."""
    return _set_charge_slot(True, 1, None)


def set_discharge_slot_2(timeslot: Timeslot) -> List[TransparentRequest]:
    """Set second discharge slot start & end times."""
    return _set_charge_slot(True, 2, timeslot)


def reset_discharge_slot_2() -> List[TransparentRequest]:
    """Reset second discharge slot to zero/disabled."""
    return _set_charge_slot(True, 2, None)


def set_system_date_time(dt: Arrow) -> List[TransparentRequest]:
    """Set the date & time of the inverter."""
    return [
        WriteHoldingRegisterRequest(HoldingRegister.SYSTEM_TIME_YEAR, dt.year - 2000),
        WriteHoldingRegisterRequest(HoldingRegister.SYSTEM_TIME_MONTH, dt.month),
        WriteHoldingRegisterRequest(HoldingRegister.SYSTEM_TIME_DAY, dt.day),
        WriteHoldingRegisterRequest(HoldingRegister.SYSTEM_TIME_HOUR, dt.hour),
        WriteHoldingRegisterRequest(HoldingRegister.SYSTEM_TIME_MINUTE, dt.minute),
        WriteHoldingRegisterRequest(HoldingRegister.SYSTEM_TIME_SECOND, dt.second),
    ]


def set_mode_dynamic() -> List[TransparentRequest]:
    """Set system to Dynamic / Eco mode.

    This mode is designed to maximise use of solar generation. The battery will charge from excess solar
    generation to avoid exporting power, and discharge to meet load demand when solar power is insufficient to
    avoid importing power. This mode is useful if you want to maximise self-consumption of renewable generation
    and minimise the amount of energy drawn from the grid.
    """
    # r27=1 r110=4 r59=0
    return set_discharge_mode_to_match_demand() + set_shallow_charge(4) + disable_discharge()


def set_mode_storage(
    discharge_slot_1: Timeslot = Timeslot.from_repr(1600, 700),
    discharge_slot_2: Optional[Timeslot] = None,
    discharge_for_export: bool = False,
) -> List[TransparentRequest]:
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
    ret.extend(set_shallow_charge(100))  # r110=100
    ret.extend(enable_discharge())  # r59=1
    ret.extend(set_discharge_slot_1(discharge_slot_1))  # r56=1600, r57=700
    if discharge_slot_2:
        ret.extend(set_discharge_slot_2(discharge_slot_2))  # r56=1600, r57=700
    else:
        ret.extend(reset_discharge_slot_2())
    return ret
