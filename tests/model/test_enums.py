import pytest

from givenergy_modbus.model.battery import BatteryMaintenance, BatteryPauseMode, State
from givenergy_modbus.model.inverter import Certification, Generation, InverterType, Phase, WorkMode
from givenergy_modbus.model.meter import MeterStatus


def test_work_mode():
    assert WorkMode(0) == WorkMode.INITIALISING
    assert WorkMode(2) == WorkMode.ON_GRID
    assert WorkMode(4) == WorkMode.UPDATE
    assert WorkMode(99) == WorkMode.INITIALISING  # _missing_


def test_state():
    assert State(0) == State.STATIC
    assert State(1) == State.CHARGE
    assert State(2) == State.DISCHARGE
    assert State(5) == State.STATIC  # _missing_


def test_meter_status():
    assert MeterStatus(0) == MeterStatus.DISABLED
    assert MeterStatus(1) == MeterStatus.ONLINE
    assert MeterStatus(2) == MeterStatus.OFFLINE
    assert MeterStatus(9) == MeterStatus.DISABLED  # _missing_


def test_certification():
    assert Certification(0) == Certification.UNKNOWN
    assert Certification(8) == Certification.G98
    assert Certification(12) == Certification.G99
    assert Certification(16) == Certification.G98_NI
    assert Certification(17) == Certification.G99_NI
    assert Certification(99) == Certification.UNKNOWN  # _missing_


def test_inverter_type():
    assert InverterType(0) == InverterType.SINGLE_PHASE_LV
    assert InverterType(1) == InverterType.SINGLE_PHASE_HV
    assert InverterType(2) == InverterType.THREE_PHASE_LV
    assert InverterType(3) == InverterType.THREE_PHASE_HV
    assert InverterType(9) == InverterType.SINGLE_PHASE_LV  # _missing_


def test_battery_pause_mode():
    assert BatteryPauseMode(0) == BatteryPauseMode.DISABLED
    assert BatteryPauseMode(1) == BatteryPauseMode.PAUSE_CHARGE
    assert BatteryPauseMode(2) == BatteryPauseMode.PAUSE_DISCHARGE
    assert BatteryPauseMode(3) == BatteryPauseMode.PAUSE_BOTH
    assert BatteryPauseMode(9) == BatteryPauseMode.DISABLED  # _missing_


def test_generation():
    assert Generation.GEN1 == "Gen 1"
    assert Generation.GEN3_PLUS == "Gen 3+"
    assert Generation.AIO2 == "AIO 2"
    assert Generation.UNKNOWN == "Unknown"


@pytest.mark.parametrize(
    "value, expected",
    [
        (1, Phase.ONE),
        (3, Phase.THREE),
        ("2001", Phase.ONE),  # DTC prefix "2" → single-phase
        ("4001", Phase.THREE),  # DTC prefix "4" → three-phase
        ("6001", Phase.THREE),  # DTC prefix "6" → three-phase
        ("3001", Phase.ONE),  # DTC prefix "3" → single-phase
        ("8001", Phase.ONE),  # DTC prefix "8" → single-phase
    ],
)
def test_phase(value, expected):
    assert Phase(value) == expected


def test_phase_unknown_dtc():
    with pytest.raises(ValueError):
        Phase("9001")


def test_battery_maintenance_missing():
    assert BatteryMaintenance(99) == BatteryMaintenance.OFF  # _missing_
