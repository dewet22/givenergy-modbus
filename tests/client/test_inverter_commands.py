"""Tests for the `_InverterCommands` mixin exposed via inverter instances.

The mixin lives in `givenergy_modbus.client.commands` and is composed onto
`SinglePhaseInverter` and `ThreePhaseInverter`. Consumers should be able to
call `inverter.set_*(...)` without threading `slot_map` through every slot
call. Lower-level callers still use `commands.*` directly (covered by
`test_commands.py`).
"""

from datetime import time as dt_time

import pytest

from givenergy_modbus.client.commands import RegisterMap, _InverterCommands
from givenergy_modbus.model import TimeSlot
from givenergy_modbus.model.inverter import SinglePhaseInverter
from givenergy_modbus.model.inverter_threephase import ThreePhaseInverter
from givenergy_modbus.model.register_cache import RegisterCache
from givenergy_modbus.model.slot_map import SINGLE_PHASE_SLOTS, THREE_PHASE_SLOTS
from givenergy_modbus.pdu import WriteHoldingRegisterRequest


def _single_phase() -> SinglePhaseInverter:
    return SinglePhaseInverter.from_register_cache(RegisterCache())


def _three_phase() -> ThreePhaseInverter:
    return ThreePhaseInverter.from_register_cache(RegisterCache())


# ---------------------------------------------------------------------------
# Mixin composition
# ---------------------------------------------------------------------------


def test_single_phase_inverter_inherits_mixin():
    assert issubclass(SinglePhaseInverter, _InverterCommands)


def test_three_phase_inverter_inherits_mixin():
    assert issubclass(ThreePhaseInverter, _InverterCommands)


def test_mixin_write_safe_registers_is_universal_subset():
    """Base allowlist should exclude registers that belong on model-specific mixins (three-phase, EMS, pause-mode)."""
    excluded = {313, 314, 318, 319, 320, 1112, 1122, 1123, 2040, 2062, 2063, 2065, 2066, 2068, 2069}
    assert excluded.isdisjoint(_InverterCommands.WRITE_SAFE_REGISTERS)
    # Sanity: still substantial, includes the bread-and-butter ones.
    assert 20 in _InverterCommands.WRITE_SAFE_REGISTERS  # ENABLE_CHARGE_TARGET
    assert 96 in _InverterCommands.WRITE_SAFE_REGISTERS  # ENABLE_CHARGE
    assert 116 in _InverterCommands.WRITE_SAFE_REGISTERS  # CHARGE_TARGET_SOC


def test_mixin_classvar_does_not_leak_into_model_dump():
    """`WRITE_SAFE_REGISTERS` is a ClassVar — must not appear as a model field."""
    inv = _single_phase()
    assert "WRITE_SAFE_REGISTERS" not in inv.model_dump()
    assert "WRITE_SAFE_REGISTERS" not in SinglePhaseInverter.model_fields


# ---------------------------------------------------------------------------
# Method delegation — confirms inverter.set_* matches commands.* primitives
# ---------------------------------------------------------------------------


def test_inverter_set_charge_target_emits_correct_writes():
    inv = _single_phase()
    assert inv.set_charge_target(80) == [
        WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE, True),
        WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE_TARGET, True),
        WriteHoldingRegisterRequest(RegisterMap.CHARGE_TARGET_SOC, 80),
    ]


def test_inverter_set_enable_charge_emits_single_write():
    assert _single_phase().set_enable_charge(False) == [
        WriteHoldingRegisterRequest(RegisterMap.ENABLE_CHARGE, False),
    ]


def test_inverter_set_battery_soc_reserve_validates():
    """Validation happens in the underlying primitive; mixin just delegates."""
    with pytest.raises(ValueError, match=r"\[4-100\]"):
        _single_phase().set_battery_soc_reserve(0)


# ---------------------------------------------------------------------------
# Slot setters use self.slot_map — no caller-side threading needed
# ---------------------------------------------------------------------------


def test_single_phase_set_charge_slot_uses_single_phase_slots():
    """An empty-cache single-phase inverter falls back to SINGLE_PHASE_SLOTS, so slot 1 hits HR(94)/HR(95)."""
    inv = _single_phase()
    assert inv.slot_map == SINGLE_PHASE_SLOTS
    ts = TimeSlot(start=dt_time(5, 0), end=dt_time(7, 0))
    requests = inv.set_charge_slot(1, ts)
    assert [(r.register, r.value) for r in requests] == [(94, 500), (95, 700)]


def test_three_phase_set_charge_slot_uses_three_phase_slots():
    """Three-phase slot 1 lives at HR(1113)/HR(1114) per THREE_PHASE_SLOTS."""
    inv = _three_phase()
    assert inv.slot_map == THREE_PHASE_SLOTS
    ts = TimeSlot(start=dt_time(5, 0), end=dt_time(7, 0))
    requests = inv.set_charge_slot(1, ts)
    assert [(r.register, r.value) for r in requests] == [(1113, 500), (1114, 700)]


def test_inverter_reset_discharge_slot_clears_both_endpoints():
    inv = _single_phase()
    requests = inv.reset_discharge_slot(1)
    assert [(r.register, r.value) for r in requests] == [(56, 0), (57, 0)]


# ---------------------------------------------------------------------------
# Negative: model-specific commands are NOT on the base mixin yet
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method_name",
    [
        "set_ac_charge",
        "set_force_charge",
        "set_force_discharge",
        "set_battery_charge_limit_ac",
        "set_battery_pause_mode",
        "set_ems_plant",
        "set_export_slot",
    ],
)
def test_model_specific_commands_not_on_base_mixin(method_name):
    """Commands belonging to not-yet-implemented mixins (three-phase, EMS, pause) must not appear on the base."""
    inv = _single_phase()
    assert not hasattr(inv, method_name), (
        f"{method_name!r} appeared on the base mixin — should be on a model-specific mixin instead"
    )


def test_frozen_still_enforced_after_mixin():
    """Mixin composition must not have weakened the frozen=True pydantic config."""
    inv = _single_phase()
    with pytest.raises(Exception):  # pydantic ValidationError
        inv.battery_soc = 50  # type: ignore[misc]
