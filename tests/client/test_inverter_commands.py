"""Tests for the command mixins exposed via inverter / EMS instances.

The mixins live in `givenergy_modbus.client.commands`:
- `_InverterCommands` — composed onto `SinglePhaseInverter` and `ThreePhaseInverter`
- `_ThreePhaseCommands` — composed onto `ThreePhaseInverter` only
- `_EmsCommands` — composed onto `Ems` only

Consumers should be able to call `inverter.set_*(...)` / `ems.set_*(...)`
without threading `slot_map` through every slot call. Lower-level callers
still use `commands.*` directly (covered by `test_commands.py`).
"""

from datetime import time as dt_time

import pytest

from givenergy_modbus.client import commands
from givenergy_modbus.client.commands import (
    RegisterMap,
    _EmsCommands,
    _InverterCommands,
    _ThreePhaseCommands,
)
from givenergy_modbus.model import TimeSlot
from givenergy_modbus.model.battery import ExportPriority
from givenergy_modbus.model.ems import Ems
from givenergy_modbus.model.inverter import SinglePhaseInverter
from givenergy_modbus.model.inverter_threephase import ThreePhaseInverter
from givenergy_modbus.model.register_cache import RegisterCache
from givenergy_modbus.model.slot_map import SINGLE_PHASE_SLOTS, THREE_PHASE_SLOTS
from givenergy_modbus.pdu import WriteHoldingRegisterRequest


def _single_phase() -> SinglePhaseInverter:
    return SinglePhaseInverter.from_register_cache(RegisterCache())


def _three_phase() -> ThreePhaseInverter:
    return ThreePhaseInverter.from_register_cache(RegisterCache())


def _ems() -> Ems:
    return Ems.from_register_cache(RegisterCache())


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
# Negative: model-specific commands must not leak onto single-phase
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method_name",
    [
        # Three-phase commands live on _ThreePhaseCommands → ThreePhaseInverter only.
        "set_ac_charge",
        "set_force_charge",
        "set_force_discharge",
        # EMS commands live on _EmsCommands → Ems only.
        "set_ems_plant",
        "set_export_slot",
        # Still deferred pending wire data (HR 313/314 single-vs-three-phase write
        # semantics; HR 318–320 firmware-gated) — these stay on commands.* only.
        "set_battery_charge_limit_ac",
        "set_battery_pause_mode",
    ],
)
def test_model_specific_commands_isolated_from_single_phase(method_name):
    """Three-phase, EMS, and deferred pause/AC-limit commands must not appear on `SinglePhaseInverter`."""
    inv = _single_phase()
    assert not hasattr(inv, method_name), (
        f"{method_name!r} leaked onto single-phase — should be on a model-specific mixin or stay on commands.*"
    )


def test_frozen_still_enforced_after_mixin():
    """Mixin composition must not have weakened the frozen=True pydantic config."""
    inv = _single_phase()
    with pytest.raises(Exception):  # pydantic ValidationError
        inv.battery_soc = 50  # type: ignore[misc]


# ---------------------------------------------------------------------------
# `_InverterCommands` gap-fill: set_export_priority / set_enable_eps
# ---------------------------------------------------------------------------


def test_inverter_set_export_priority_emits_correct_write():
    assert _single_phase().set_export_priority(ExportPriority.LOAD_FIRST) == [
        WriteHoldingRegisterRequest(RegisterMap.EXPORT_PRIORITY, ExportPriority.LOAD_FIRST),
    ]


def test_inverter_set_enable_eps_emits_correct_write():
    assert _single_phase().set_enable_eps(True) == [
        WriteHoldingRegisterRequest(RegisterMap.ENABLE_EPS, True),
    ]


# ---------------------------------------------------------------------------
# `_ThreePhaseCommands` mixin
# ---------------------------------------------------------------------------


def test_three_phase_inverter_inherits_three_phase_commands():
    assert issubclass(ThreePhaseInverter, _ThreePhaseCommands)


def test_single_phase_does_not_inherit_three_phase_commands():
    assert not issubclass(SinglePhaseInverter, _ThreePhaseCommands)


def test_three_phase_write_safe_registers_is_superset_of_base():
    """Three-phase allowlist = base plus the native three-phase registers the inherited command surface writes."""
    assert _InverterCommands.WRITE_SAFE_REGISTERS.issubset(_ThreePhaseCommands.WRITE_SAFE_REGISTERS)
    # 1078 (set_battery_reserve_soc), 1113-1116 / 1118-1121 (charge/discharge slots 1-2 via
    # THREE_PHASE_SLOTS), 1112 / 1122 / 1123 (set_ac_charge / set_force_charge / set_force_discharge).
    assert {1078, 1112, 1113, 1114, 1115, 1116, 1118, 1119, 1120, 1121, 1122, 1123}.issubset(
        _ThreePhaseCommands.WRITE_SAFE_REGISTERS
    )
    # AC-limit / pause-mode / EMS registers are still excluded — those mixins haven't landed yet.
    assert {313, 314, 318, 319, 320, 2040, 2062}.isdisjoint(_ThreePhaseCommands.WRITE_SAFE_REGISTERS)


@pytest.mark.parametrize(
    ("method_name", "register"),
    [
        ("set_ac_charge", RegisterMap.AC_CHARGE_ENABLE),
        ("set_force_charge", RegisterMap.FORCE_CHARGE_ENABLE),
        ("set_force_discharge", RegisterMap.FORCE_DISCHARGE_ENABLE),
    ],
)
def test_three_phase_command_delegates_to_primitive(method_name, register):
    inv = _three_phase()
    requests = getattr(inv, method_name)(True)
    assert requests == [WriteHoldingRegisterRequest(register, True)]
    # Encode round-trip — catches a missing entry in pdu.write_registers.WRITE_SAFE_REGISTERS.
    requests[0].encode()


# ---------------------------------------------------------------------------
# `_EmsCommands` mixin
# ---------------------------------------------------------------------------


def test_ems_inherits_ems_commands():
    assert issubclass(Ems, _EmsCommands)


def test_ems_does_not_inherit_inverter_commands():
    """EMS is a peer device, not an inverter — must not pick up the inverter command surface."""
    assert not issubclass(Ems, _InverterCommands)


def test_single_phase_does_not_inherit_ems_commands():
    assert not issubclass(SinglePhaseInverter, _EmsCommands)


def test_ems_write_safe_registers_covers_ems_block():
    """The EMS allowlist must match the EMS HR block (2040, 2044–2071) and be disjoint from the inverter allowlist."""
    expected = {2040, *range(2044, 2072)}
    assert _EmsCommands.WRITE_SAFE_REGISTERS == expected
    assert _EmsCommands.WRITE_SAFE_REGISTERS.isdisjoint(_InverterCommands.WRITE_SAFE_REGISTERS)


def test_ems_set_ems_plant_emits_correct_write():
    requests = _ems().set_ems_plant(True)
    assert requests == [WriteHoldingRegisterRequest(RegisterMap.EMS_PLANT_ENABLE, True)]
    # Encode round-trip — catches a missing entry in pdu.write_registers.WRITE_SAFE_REGISTERS.
    requests[0].encode()


def test_ems_set_export_slot_emits_pair_of_writes():
    ts = TimeSlot(start=dt_time(11, 0), end=dt_time(15, 0))
    requests = _ems().set_export_slot(1, ts)
    assert [(r.register, r.value) for r in requests] == [
        (RegisterMap.EXPORT_SLOT_1_START, 1100),
        (RegisterMap.EXPORT_SLOT_1_END, 1500),
    ]


def test_ems_set_ems_charge_slot_uses_ems_slot_block():
    """EMS charge slot 1 lives at HR(2053)/HR(2054)."""
    ts = TimeSlot(start=dt_time(2, 0), end=dt_time(5, 30))
    requests = _ems().set_ems_charge_slot(1, ts)
    assert [(r.register, r.value) for r in requests] == [(2053, 200), (2054, 530)]


def test_ems_set_ems_discharge_slot_uses_ems_slot_block():
    """EMS discharge slot 1 lives at HR(2044)/HR(2045)."""
    ts = TimeSlot(start=dt_time(18, 0), end=dt_time(21, 0))
    requests = _ems().set_ems_discharge_slot(1, ts)
    assert [(r.register, r.value) for r in requests] == [(2044, 1800), (2045, 2100)]


def test_ems_set_ems_charge_target_soc_emits_correct_write():
    assert _ems().set_ems_charge_target_soc(2, 75) == [
        WriteHoldingRegisterRequest(RegisterMap.EMS_CHARGE_TARGET_SOC_2, 75),
    ]


def test_ems_set_ems_export_power_limit_validates():
    """Validation happens in the underlying primitive; mixin just delegates."""
    with pytest.raises(ValueError, match=r"\[0-65535\]"):
        _ems().set_ems_export_power_limit(70000)


def test_ems_mixin_delegates_to_underlying_primitive():
    """Spot-check: mixin output equals the module-level primitive output (no subtle divergence)."""
    em = _ems()
    assert em.set_ems_plant(True) == commands.set_ems_plant(True)
    assert em.set_ems_export_power_limit(5000) == commands.set_ems_export_power_limit(5000)


@pytest.mark.parametrize(
    ("method_name", "args"),
    [
        # Per-endpoint export-slot setters (HR 2062–2070).
        ("set_export_slot_start", (1, dt_time(9, 0))),
        ("set_export_slot_end", (1, dt_time(17, 0))),
        # EMS-named export-slot aliases.
        ("set_ems_export_slot", (1, TimeSlot(start=dt_time(11, 0), end=dt_time(15, 0)))),
        ("set_ems_export_slot_start", (1, dt_time(9, 0))),
        ("set_ems_export_slot_end", (1, dt_time(17, 0))),
        # EMS charge-slot endpoints (HR 2053–2061).
        ("set_ems_charge_slot_start", (1, dt_time(2, 0))),
        ("set_ems_charge_slot_end", (1, dt_time(5, 0))),
        # EMS discharge-slot endpoints (HR 2044–2052).
        ("set_ems_discharge_slot_start", (1, dt_time(18, 0))),
        ("set_ems_discharge_slot_end", (1, dt_time(21, 0))),
        # Per-slot target SoC.
        ("set_ems_discharge_target_soc", (2, 60)),
        ("set_ems_export_target_soc", (3, 40)),
    ],
)
def test_ems_command_delegates_to_primitive(method_name, args):
    """Every remaining thin `_EmsCommands` wrapper returns exactly what its module-level primitive does."""
    assert getattr(_ems(), method_name)(*args) == getattr(commands, method_name)(*args)


@pytest.mark.parametrize(
    "method_name",
    ["set_ems_charge_target_soc", "set_ems_discharge_target_soc", "set_ems_export_target_soc"],
)
def test_ems_target_soc_validation_holds_through_mixin(method_name):
    """The slot-index [1-3] and SoC [0-100] bounds enforced in the primitive must survive delegation."""
    em = _ems()
    with pytest.raises(ValueError, match=r"\[1-3\]"):
        getattr(em, method_name)(4, 50)  # index out of range
    with pytest.raises(ValueError, match=r"\[0-100\]"):
        getattr(em, method_name)(1, 150)  # SoC out of range
