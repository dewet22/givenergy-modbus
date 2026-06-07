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
        "set_battery_reserve_soc",  # three-phase only (HR 1078)
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
# #203 — three-phase model-aware routing
# ---------------------------------------------------------------------------


def test_three_phase_set_mode_storage_uses_three_phase_slots():
    """set_mode_storage on a ThreePhaseInverter writes discharge slot 1 to HR(1118/1119)."""
    inv = _three_phase()
    slot = TimeSlot(start=dt_time(16, 0), end=dt_time(7, 0))
    requests = inv.set_mode_storage(slot)
    regs = {r.register: r.value for r in requests}
    assert 1118 in regs, "three-phase discharge slot 1 start should be HR(1118)"
    assert 1119 in regs, "three-phase discharge slot 1 end should be HR(1119)"
    assert 56 not in regs, "single-phase HR(56) must not appear on three-phase"
    assert 57 not in regs, "single-phase HR(57) must not appear on three-phase"
    for r in requests:
        r.encode()


def test_single_phase_set_mode_storage_still_uses_single_phase_slots():
    """Regression: set_mode_storage on SinglePhaseInverter must still use HR(56/57)."""
    inv = _single_phase()
    slot = TimeSlot(start=dt_time(16, 0), end=dt_time(7, 0))
    requests = inv.set_mode_storage(slot)
    regs = {r.register: r.value for r in requests}
    assert 56 in regs
    assert 57 in regs
    assert 1118 not in regs


def test_three_phase_set_battery_soc_reserve_writes_correct_register():
    """set_battery_soc_reserve on three-phase must write HR(1109), not HR(110)."""
    requests = _three_phase().set_battery_soc_reserve(20)
    assert len(requests) == 1
    assert requests[0].register == RegisterMap.BATTERY_SOC_RESERVE_3PH
    requests[0].encode()


def test_single_phase_set_battery_soc_reserve_still_writes_hr110():
    """Regression: single-phase must still write HR(110) = BATTERY_SOC_RESERVE."""
    requests = _single_phase().set_battery_soc_reserve(20)
    assert len(requests) == 1
    assert requests[0].register == RegisterMap.BATTERY_SOC_RESERVE


def test_three_phase_set_battery_reserve_soc_available():
    """set_battery_reserve_soc (HR 1078) is reachable on three-phase."""
    requests = _three_phase().set_battery_reserve_soc(10)
    assert len(requests) == 1
    assert requests[0].register == RegisterMap.BATTERY_RESERVE_SOC
    requests[0].encode()


def test_three_phase_set_charge_target_uses_correct_registers():
    """set_charge_target on three-phase emits HR(1112) AC_CHARGE_ENABLE + HR(1111) charge target."""
    requests = _three_phase().set_charge_target(80)
    regs = {r.register: r.value for r in requests}
    assert RegisterMap.AC_CHARGE_ENABLE in regs, "three-phase must enable AC charge (HR 1112)"
    assert RegisterMap.CHARGE_TARGET_SOC_3PH in regs, "three-phase must write charge target to HR(1111)"
    assert regs[RegisterMap.CHARGE_TARGET_SOC_3PH] == 80
    assert RegisterMap.CHARGE_TARGET_SOC not in regs, "single-phase HR(116) must not appear"
    assert RegisterMap.ENABLE_CHARGE not in regs, "single-phase HR(96) must not appear"
    for r in requests:
        r.encode()


def test_single_phase_set_charge_target_unchanged():
    """Regression: single-phase set_charge_target must still use HR(96) and HR(116)."""
    requests = _single_phase().set_charge_target(80)
    regs = {r.register: r.value for r in requests}
    assert RegisterMap.ENABLE_CHARGE in regs
    assert RegisterMap.CHARGE_TARGET_SOC in regs
    assert regs[RegisterMap.CHARGE_TARGET_SOC] == 80
    assert RegisterMap.CHARGE_TARGET_SOC_3PH not in regs


def test_three_phase_write_safe_registers_contains_three_phase_entries():
    """_ThreePhaseCommands.WRITE_SAFE_REGISTERS must include three-phase-specific registers."""
    wsr = _ThreePhaseCommands.WRITE_SAFE_REGISTERS
    assert RegisterMap.CHARGE_TARGET_SOC_3PH in wsr  # 1111
    assert RegisterMap.BATTERY_SOC_RESERVE_3PH in wsr  # 1109
    assert RegisterMap.BATTERY_RESERVE_SOC in wsr  # 1078
    assert RegisterMap.AC_CHARGE_ENABLE in wsr  # 1112
    assert RegisterMap.FORCE_DISCHARGE_ENABLE in wsr  # 1122
    assert RegisterMap.FORCE_CHARGE_ENABLE in wsr  # 1123


def test_three_phase_disable_charge_target_uses_correct_register():
    """disable_charge_target on three-phase must write HR(1111), not single-phase HR(116)."""
    requests = _three_phase().disable_charge_target()
    regs = {r.register: r.value for r in requests}
    assert RegisterMap.ENABLE_CHARGE_TARGET in regs
    assert regs[RegisterMap.ENABLE_CHARGE_TARGET] is False
    assert regs.get(RegisterMap.CHARGE_TARGET_SOC_3PH) == 100
    assert RegisterMap.CHARGE_TARGET_SOC not in regs, "single-phase HR(116) must not appear"
    for r in requests:
        r.encode()


def test_three_phase_set_battery_soc_reserve_validates():
    """Out-of-range values must raise ValueError via the 3ph primitive."""
    with pytest.raises(ValueError, match=r"\[4-100\]"):
        _three_phase().set_battery_soc_reserve(0)


def test_three_phase_set_charge_target_validates():
    """Out-of-range charge target must raise ValueError via the 3ph primitive."""
    with pytest.raises(ValueError, match=r"\[4-100\]"):
        _three_phase().set_charge_target(101)


def test_three_phase_set_charge_target_100_disables_charge_target():
    """set_charge_target(100) on three-phase disables ENABLE_CHARGE_TARGET and writes HR(1111)=100."""
    requests = _three_phase().set_charge_target(100)
    regs = {r.register: r.value for r in requests}
    assert RegisterMap.ENABLE_CHARGE_TARGET in regs
    assert regs[RegisterMap.ENABLE_CHARGE_TARGET] is False
    assert regs.get(RegisterMap.CHARGE_TARGET_SOC_3PH) == 100
    for r in requests:
        r.encode()


def test_three_phase_write_safe_registers_excludes_single_phase_entries():
    """Single-phase-only registers must be absent from the three-phase allowlist."""
    wsr = _ThreePhaseCommands.WRITE_SAFE_REGISTERS
    assert RegisterMap.CHARGE_TARGET_SOC not in wsr  # 116 — replaced by 1111
    assert RegisterMap.BATTERY_SOC_RESERVE not in wsr  # 110 — replaced by 1109
    assert RegisterMap.ENABLE_CHARGE not in wsr  # 96 — replaced by AC_CHARGE_ENABLE
    # single-phase slot pairs 1-2
    assert 94 not in wsr and 95 not in wsr  # charge slot 1
    assert 31 not in wsr and 32 not in wsr  # charge slot 2
    assert 56 not in wsr and 57 not in wsr  # discharge slot 1
    assert 44 not in wsr and 45 not in wsr  # discharge slot 2


# ---------------------------------------------------------------------------
# set_enable_charge — three-phase routing
# ---------------------------------------------------------------------------


def test_three_phase_set_enable_charge_routes_to_ac_charge_enable():
    """set_enable_charge on ThreePhaseInverter must write AC_CHARGE_ENABLE (HR 1112), not HR 96."""
    requests = _three_phase().set_enable_charge(True)
    regs = {r.register: r.value for r in requests}
    assert RegisterMap.AC_CHARGE_ENABLE in regs
    assert RegisterMap.ENABLE_CHARGE not in regs, "single-phase HR(96) must not appear on three-phase"
    for r in requests:
        r.encode()


def test_single_phase_set_enable_charge_unchanged():
    """Regression: set_enable_charge on SinglePhaseInverter must still write HR(96)."""
    requests = _single_phase().set_enable_charge(True)
    regs = {r.register: r.value for r in requests}
    assert RegisterMap.ENABLE_CHARGE in regs


# ---------------------------------------------------------------------------
# set_mode_dynamic — three-phase routing
# ---------------------------------------------------------------------------


def test_three_phase_set_mode_dynamic_uses_three_phase_soc_reserve():
    """set_mode_dynamic on ThreePhaseInverter must write HR(1109), not single-phase HR(110)."""
    requests = _three_phase().set_mode_dynamic()
    regs = {r.register: r.value for r in requests}
    assert RegisterMap.BATTERY_SOC_RESERVE_3PH in regs
    assert RegisterMap.BATTERY_SOC_RESERVE not in regs, "single-phase HR(110) must not appear on three-phase"
    for r in requests:
        r.encode()


def test_single_phase_set_mode_dynamic_unchanged():
    """Regression: set_mode_dynamic on SinglePhaseInverter must still write HR(110)."""
    requests = _single_phase().set_mode_dynamic()
    regs = {r.register: r.value for r in requests}
    assert RegisterMap.BATTERY_SOC_RESERVE in regs


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
