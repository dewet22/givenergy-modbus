"""Tests for the declarative capability manifest (Slice A: register semantics, #293)."""

from givenergy_modbus.model.inverter import Model
from givenergy_modbus.model.manifest import battery_energy_source, ir44_is_inverter_output


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


def test_ir44_identity_overrides():
    """IR44 = inverter output on exactly the evidence-backed models (#293)."""
    assert ir44_is_inverter_output(Model.AC) is True
    assert ir44_is_inverter_output(Model.ALL_IN_ONE) is True
    assert ir44_is_inverter_output(Model.HYBRID_GEN1) is False
    assert ir44_is_inverter_output(Model.HYBRID_GEN3) is False
    assert ir44_is_inverter_output(Model.GATEWAY) is False  # unlisted → status quo


def _inverter(dtc_hex: str, arm_fw: int, ir44: int = 77, ir45: int = 1, ir46: int = 17083):
    """Build a SinglePhaseInverter with identity registers primed."""
    from givenergy_modbus.model.inverter import SinglePhaseInverter
    from givenergy_modbus.model.register import HR, IR
    from givenergy_modbus.model.register_cache import RegisterCache

    cache = RegisterCache({HR(0): int(dtc_hex, 16), HR(21): arm_fw, IR(44): ir44, IR(45): ir45, IR(46): ir46})
    return SinglePhaseInverter.from_register_cache(cache)


def test_identity_matrix_hybrid_keeps_pv_generation():
    inv = _inverter("2001", 449)  # HYBRID_GEN1
    assert inv.e_pv_generation_today == 7.7
    assert inv.e_pv_generation_total == 8261.9  # uint32(1,17083)/10
    assert inv.e_inverter_out_today is None
    assert inv.e_inverter_out_total is None


def test_identity_matrix_ac_gets_inverter_out():
    inv = _inverter("3001", 282)  # Model.AC
    assert inv.e_inverter_out_today == 7.7
    assert inv.e_inverter_out_total == 8261.9
    assert inv.e_pv_generation_today is None
    assert inv.e_pv_generation_total is None


def test_identity_matrix_aio_gets_inverter_out():
    inv = _inverter("8001", 612)  # ALL_IN_ONE
    assert inv.e_inverter_out_today == 7.7
    assert inv.e_pv_generation_today is None


def test_identity_validator_is_idempotent_on_roundtrip():
    """model_validate(model_dump()) must not destroy the moved identity values (#293)."""
    from givenergy_modbus.model.inverter import SinglePhaseInverter

    inv = _inverter("3001", 282)  # Model.AC, live IR44/45/46
    again = SinglePhaseInverter.model_validate(inv.model_dump())
    assert again.e_inverter_out_today == inv.e_inverter_out_today
    assert again.e_inverter_out_total == inv.e_inverter_out_total
    assert again.e_pv_generation_today is None


def test_identity_unresolvable_keeps_status_quo():
    """No HR(0)/HR(21) → no override → e_pv_generation_* serves as today."""
    from givenergy_modbus.model.inverter import SinglePhaseInverter
    from givenergy_modbus.model.register import IR
    from givenergy_modbus.model.register_cache import RegisterCache

    inv = SinglePhaseInverter.from_register_cache(RegisterCache({IR(44): 77}))
    assert inv.e_pv_generation_today == 7.7
    assert inv.e_inverter_out_today is None
