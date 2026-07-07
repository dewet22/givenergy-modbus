"""Tests for the declarative capability manifest (Slice A: register semantics, #293)."""

from givenergy_modbus.model.inverter import Model
from givenergy_modbus.model.manifest import battery_energy_source


def test_battery_energy_source_migrated_rows():
    """The #184 routing rows relocated verbatim from _BATTERY_ENERGY_SOURCE."""
    assert battery_energy_source(Model.HYBRID_GEN1, "today") == "alt2"
    assert battery_energy_source(Model.HYBRID_GEN1, "total") == "alt1"
    assert battery_energy_source(Model.AC, "today") == "alt1"
    assert battery_energy_source(Model.ALL_IN_ONE, "today") == "alt1"


def test_battery_energy_source_absent_is_none():
    """Absent model or metric routes to None — the honest no-evidence posture."""
    assert battery_energy_source(Model.AC, "total") is None
    assert battery_energy_source(Model.GATEWAY, "today") is None


def test_battery_energy_source_accepts_fw_param():
    """The arm_fw column exists in the signature from day one (unused in Slice A)."""
    assert battery_energy_source(Model.HYBRID_GEN1, "today", arm_fw=449) == "alt2"
