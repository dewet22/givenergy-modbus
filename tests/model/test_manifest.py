"""Tests for the declarative capability manifest (Slice A: register semantics, #293)."""

import pytest

from givenergy_modbus.model.inverter import Model
from givenergy_modbus.model.manifest import (
    WRITE_SAFE_AC_CONFIG,
    WRITE_SAFE_EMS,
    WRITE_SAFE_SINGLE_PHASE,
    WRITE_SAFE_THREE_PHASE,
    battery_energy_source,
    has_capability,
    has_extended_slots,
    ir44_is_inverter_output,
    write_safe_registers,
)


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


def test_has_capability_is_hv():
    """Relocated verbatim from plant.py's _HV_MODELS (#293 Slice B)."""
    for m in (Model.HYBRID_3PH, Model.AC_3PH, Model.ALL_IN_ONE, Model.HYBRID_HV_GEN3, Model.ALL_IN_ONE_HYBRID):
        assert has_capability("is_hv", m) is True
    for m in (Model.HYBRID_GEN1, Model.AC, Model.EMS):
        assert has_capability("is_hv", m) is False


def test_has_capability_is_three_phase():
    """Relocated from BOTH plant.py and inverter_threephase.py.

    These were independently-maintained duplicates (#293 Slice B).
    """
    for m in (Model.HYBRID_3PH, Model.AC_3PH, Model.AIO_COMMERCIAL, Model.ALL_IN_ONE_HYBRID, Model.HYBRID_HV_GEN3):
        assert has_capability("is_three_phase", m) is True
    assert has_capability("is_three_phase", Model.ALL_IN_ONE) is False  # HV but single-phase (#105)


def test_has_capability_is_ac_coupled():
    """Relocated from inverter.py's AC_COUPLED_MODELS (#293 Slice B)."""
    assert has_capability("is_ac_coupled", Model.AC) is True
    assert has_capability("is_ac_coupled", Model.AC_3PH) is True
    assert has_capability("is_ac_coupled", Model.HYBRID_GEN1) is False


def test_has_capability_has_ac_config_block():
    """Relocated from plant.py's _AC_CONFIG_BLOCK_MODELS (#293 Slice B)."""
    for m in (Model.AC, Model.AC_3PH, Model.ALL_IN_ONE):
        assert has_capability("has_ac_config_block", m) is True
    assert has_capability("has_ac_config_block", Model.HYBRID_GEN1) is False


def test_has_capability_empty_placeholder_facts():
    """Three empty placeholder capability sets from plant.py.

    No model has been confirmed to answer these blocks on real hardware yet (#293 Slice B).
    """
    for name in ("has_smart_load_block", "has_hv_cabinet_block", "has_peak_shaving_block"):
        assert has_capability(name, Model.HYBRID_GEN1) is False
        assert has_capability(name, Model.ALL_IN_ONE) is False


def test_has_capability_unknown_name_raises():
    """A typo in the fact name fails loudly, not silently (deliberate — see manifest.py)."""
    with pytest.raises(KeyError):
        has_capability("has_typo_block", Model.HYBRID_GEN1)


def test_has_extended_slots_unconditional_models():
    for m in (Model.HYBRID_GEN4, Model.ALL_IN_ONE, Model.ALL_IN_ONE_HYBRID, Model.HYBRID_HV_GEN3):
        assert has_extended_slots(m) is True
        assert has_extended_slots(m, arm_fw=1) is True  # unconditional — fw irrelevant


def test_has_extended_slots_hybrid_gen3_firmware_gate():
    """HYBRID_GEN3 extended slots gate at firmware 302.

    This task fixes the firmware-gating rule, matching slot_map.py (#293 Slice B).
    """
    assert has_extended_slots(Model.HYBRID_GEN3) is False  # arm_fw=None
    assert has_extended_slots(Model.HYBRID_GEN3, arm_fw=302) is False
    assert has_extended_slots(Model.HYBRID_GEN3, arm_fw=303) is True


def test_has_extended_slots_non_extended_models():
    for m in (Model.HYBRID_GEN1, Model.HYBRID_GEN2, Model.AC, Model.EMS):
        assert has_extended_slots(m) is False
        assert has_extended_slots(m, arm_fw=999) is False


def test_capabilities_gained_is_ems_and_is_gateway():
    """Extends Slice B's CAPABILITIES table — is_ems/is_gateway were never migrated (#293 Slice C1)."""
    assert has_capability("is_ems", Model.EMS) is True
    assert has_capability("is_ems", Model.EMS_COMMERCIAL) is True
    assert has_capability("is_ems", Model.HYBRID_GEN1) is False
    assert has_capability("is_gateway", Model.GATEWAY) is True
    assert has_capability("is_gateway", Model.HYBRID_GEN1) is False


def test_load_config_three_phase_ranges_exact_values():
    from givenergy_modbus.model.manifest import (
        LOAD_CONFIG_THREE_PHASE_RANGES,
        RegisterRange,
    )

    assert LOAD_CONFIG_THREE_PHASE_RANGES == [
        RegisterRange("HR", 1000, 60),
        RegisterRange("HR", 1060, 60),
        RegisterRange("HR", 1120, 5),
    ]


def test_load_config_ranges_exact_values():
    from givenergy_modbus.model.manifest import (
        LOAD_CONFIG_RANGES,
        RegisterRange,
    )

    assert LOAD_CONFIG_RANGES == {
        "has_smart_load_block": [RegisterRange("HR", 540, 60)],
        "has_hv_cabinet_block": [RegisterRange("HR", 499, 12)],
        "has_peak_shaving_block": [RegisterRange("HR", 20000, 52)],
        "has_ac_config_block": [RegisterRange("HR", 300, 60)],
        "is_ems": [RegisterRange("HR", 2040, 36)],
    }


def test_refresh_ir_ranges_exact_values():
    from givenergy_modbus.model.manifest import (
        REFRESH_IR_RANGES,
        RegisterRange,
    )

    assert REFRESH_IR_RANGES["is_ems"] == [RegisterRange("IR", 2040, 55)]
    assert REFRESH_IR_RANGES["is_three_phase"] == [
        RegisterRange("IR", 1000, 60),
        RegisterRange("IR", 1060, 60),
        RegisterRange("IR", 1120, 60),
        RegisterRange("IR", 1180, 60),
        RegisterRange("IR", 1240, 60),
        RegisterRange("IR", 1300, 60),
        RegisterRange("IR", 1360, 54),
    ]
    assert REFRESH_IR_RANGES["is_gateway"] == [
        RegisterRange("IR", 1600, 60),
        RegisterRange("IR", 1660, 60),
        RegisterRange("IR", 1720, 60),
        RegisterRange("IR", 1780, 60),
        RegisterRange("IR", 1840, 20),
    ]


def test_gated_ranges_returns_only_true_facts():
    """AC is has_ac_config_block + is_ems=False → exactly the HR(300,60) entry."""
    from givenergy_modbus.model.manifest import (
        LOAD_CONFIG_RANGES,
        RegisterRange,
        gated_ranges,
    )

    ranges = gated_ranges(LOAD_CONFIG_RANGES, Model.AC)
    assert ranges == [RegisterRange("HR", 300, 60)]


def test_gated_ranges_ems_model():
    from givenergy_modbus.model.manifest import (
        LOAD_CONFIG_RANGES,
        RegisterRange,
        gated_ranges,
    )

    ranges = gated_ranges(LOAD_CONFIG_RANGES, Model.EMS)
    assert ranges == [RegisterRange("HR", 2040, 36)]


def test_gated_ranges_no_facts_true():
    from givenergy_modbus.model.manifest import (
        LOAD_CONFIG_RANGES,
        gated_ranges,
    )

    ranges = gated_ranges(LOAD_CONFIG_RANGES, Model.HYBRID_GEN1)
    assert ranges == []


def test_gated_ranges_accepts_none_model():
    """Model | None consistent with has_capability's own None-safety (#293 Slice B)."""
    from givenergy_modbus.model.manifest import (
        LOAD_CONFIG_RANGES,
        gated_ranges,
    )

    assert gated_ranges(LOAD_CONFIG_RANGES, None) == []


def test_write_safe_ac_config_membership_and_disjointness():
    """Permanent #297 pins at the manifest level.

    The AC-config block is exactly HR311/313/314/317 and is in NEITHER base set
    (it only arrives via the union).
    """
    assert WRITE_SAFE_AC_CONFIG == frozenset({311, 313, 314, 317})
    assert WRITE_SAFE_AC_CONFIG.isdisjoint(WRITE_SAFE_SINGLE_PHASE)
    assert WRITE_SAFE_AC_CONFIG.isdisjoint(WRITE_SAFE_THREE_PHASE)
    assert WRITE_SAFE_AC_CONFIG.isdisjoint(WRITE_SAFE_EMS)


def test_write_safe_registers_model_matrix():
    """The base-set selection: EMS → EMS set, three-phase → 3ph set, else single-phase.

    AC/AIO additionally get the AC-config union (#295).
    """
    assert write_safe_registers(Model.EMS) == WRITE_SAFE_EMS
    assert write_safe_registers(Model.EMS_COMMERCIAL) == WRITE_SAFE_EMS
    assert write_safe_registers(Model.HYBRID_3PH) == WRITE_SAFE_THREE_PHASE
    assert write_safe_registers(Model.HYBRID_GEN1) == WRITE_SAFE_SINGLE_PHASE
    assert write_safe_registers(Model.AC) == WRITE_SAFE_SINGLE_PHASE | WRITE_SAFE_AC_CONFIG
    assert write_safe_registers(Model.ALL_IN_ONE) == WRITE_SAFE_SINGLE_PHASE | WRITE_SAFE_AC_CONFIG


def test_write_safe_registers_ac_3ph_no_ac_config_union():
    """The load-bearing guard: AC_3PH HAS has_ac_config_block but is three-phase.

    It remaps those controls to the 1000-range, so it must NOT get the HR300-359
    union (#295/#296; pinned behaviourally in test_client_write_safety.py too).
    """
    result = write_safe_registers(Model.AC_3PH)
    assert result == WRITE_SAFE_THREE_PHASE
    for reg in (311, 313, 314, 317):
        assert reg not in result


def test_write_safe_registers_undetected_falls_back_to_single_phase():
    """model=None (undetected client) → conservative single-phase base, no AC-config union.

    Falls out of has_capability's None→False contract, not a special case (#296).
    """
    assert write_safe_registers(None) == WRITE_SAFE_SINGLE_PHASE


def test_write_safe_registers_accepts_fw_param():
    """arm_fw column exists in the signature from day one.

    Unused — no write capability is firmware-gated today.
    """
    assert write_safe_registers(Model.HYBRID_GEN1, arm_fw=449) == WRITE_SAFE_SINGLE_PHASE
