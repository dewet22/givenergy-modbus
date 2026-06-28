"""Tests for model-aware write safety at the Client boundary.

one_shot_command() validates every WriteHoldingRegisterRequest against the
model-specific WRITE_SAFE_REGISTERS set before transmitting. A caller who
bypasses the command mixins and hand-builds a WriteHoldingRegisterRequest still
gets rejected if the register is not valid for the detected inverter model.

Uses dry_run=True throughout so no network transport is needed.
"""

import pytest

from givenergy_modbus.client.client import Client
from givenergy_modbus.client.commands import _EmsCommands, _InverterCommands, _ThreePhaseCommands
from givenergy_modbus.exceptions import InvalidPduState
from givenergy_modbus.model.inverter import Model
from givenergy_modbus.model.plant import PlantCapabilities
from givenergy_modbus.pdu.write_registers import INSTALLER_WRITE_REGISTERS as PDU_INSTALLER_WRITE_REGISTERS
from givenergy_modbus.pdu.write_registers import WRITE_SAFE_REGISTERS as PDU_WRITE_SAFE_REGISTERS
from givenergy_modbus.pdu.write_registers import WriteHoldingRegisterRequest

# HR 96 = ENABLE_CHARGE — in _InverterCommands.WRITE_SAFE_REGISTERS (single-phase)
# HR 1112 = AC_CHARGE_ENABLE — in _ThreePhaseCommands.WRITE_SAFE_REGISTERS only
_SINGLE_PHASE_REG = 96
_THREE_PHASE_REG = 1112
# HR 1078 = BATTERY_RESERVE_SOC — three-phase-only; not in base _InverterCommands set
_THREE_PHASE_ONLY_REG = 1078
# HR 2040 = EMS_PLANT_ENABLE — EMS-only
_EMS_REG = 2040


def _client(caps: PlantCapabilities | None) -> Client:
    c = Client("localhost", 8899)
    c.plant.capabilities = caps
    return c


def _caps(model: Model) -> PlantCapabilities:
    return PlantCapabilities(device_type=model)


# ---------------------------------------------------------------------------
# Single-phase model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_phase_accepts_single_phase_register():
    client = _client(_caps(Model.HYBRID_GEN1))
    req = WriteHoldingRegisterRequest(_SINGLE_PHASE_REG, 1)
    await client.one_shot_command([req], dry_run=True)  # must not raise


@pytest.mark.asyncio
async def test_single_phase_rejects_three_phase_register():
    client = _client(_caps(Model.HYBRID_GEN1))
    req = WriteHoldingRegisterRequest(_THREE_PHASE_REG, 1)
    with pytest.raises(InvalidPduState, match=r"HR\(1112\)"):
        await client.one_shot_command([req], dry_run=True)


# HR 313/314 = BATTERY_*_LIMIT_AC — HR(300-359) AC-output config-block registers (#295). Gated on
# capabilities.has_ac_config_block at the client boundary, NOT the model-class allowlist: accepted
# only on a model that exposes the block (AC / All-in-One) and is not three-phase.
_AC_LIMIT_REGS = (313, 314)


@pytest.mark.asyncio
@pytest.mark.parametrize("model", [Model.AC, Model.ALL_IN_ONE])
async def test_ac_config_models_accept_battery_limit_ac_writes(model):
    """Models that expose the HR(300-359) block (AC, AIO) may write HR313/314 (#295)."""
    client = _client(_caps(model))
    for reg in _AC_LIMIT_REGS:
        await client.one_shot_command([WriteHoldingRegisterRequest(reg, 50)], dry_run=True)  # must not raise


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model",
    [
        Model.HYBRID_GEN1,  # DC-coupled hybrid — lacks the AC-config block (reads time out)
        Model.AC_3PH,  # has the block but is three-phase → remaps to HR1110/1108 (not routed yet)
        Model.HYBRID_3PH,  # three-phase, no AC-config block
    ],
)
async def test_non_ac_config_models_reject_battery_limit_ac_writes(model):
    """HR313/314 must be rejected unless has_ac_config_block and not three-phase (#296 review)."""
    client = _client(_caps(model))
    for reg in _AC_LIMIT_REGS:
        with pytest.raises(InvalidPduState, match=rf"HR\({reg}\)"):
            await client.one_shot_command([WriteHoldingRegisterRequest(reg, 50)], dry_run=True)


@pytest.mark.asyncio
async def test_undetected_rejects_battery_limit_ac_writes():
    """An undetected client (no capabilities) must reject HR313/314 — conservative fallback (#296 review)."""
    client = _client(None)
    for reg in _AC_LIMIT_REGS:
        with pytest.raises(InvalidPduState, match=rf"HR\({reg}\)"):
            await client.one_shot_command([WriteHoldingRegisterRequest(reg, 50)], dry_run=True)


def test_battery_limit_ac_commands_encode():
    """The battery AC-limit command builders produce requests that encode cleanly (Gemini #296 review)."""
    from givenergy_modbus.client.commands import set_battery_charge_limit_ac, set_battery_discharge_limit_ac

    for req in set_battery_charge_limit_ac(50):
        req.encode()
    for req in set_battery_discharge_limit_ac(50):
        req.encode()


# ---------------------------------------------------------------------------
# Three-phase model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_three_phase_accepts_three_phase_register():
    client = _client(_caps(Model.HYBRID_3PH))
    req = WriteHoldingRegisterRequest(_THREE_PHASE_REG, 1)
    await client.one_shot_command([req], dry_run=True)  # must not raise


@pytest.mark.asyncio
async def test_three_phase_rejects_single_phase_register():
    client = _client(_caps(Model.HYBRID_3PH))
    req = WriteHoldingRegisterRequest(_SINGLE_PHASE_REG, 1)
    with pytest.raises(InvalidPduState, match=r"HR\(96\)"):
        await client.one_shot_command([req], dry_run=True)


# ---------------------------------------------------------------------------
# Undetected model (capabilities not set) — conservative fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_undetected_accepts_single_phase_register():
    client = _client(None)
    req = WriteHoldingRegisterRequest(_SINGLE_PHASE_REG, 1)
    await client.one_shot_command([req], dry_run=True)  # must not raise


@pytest.mark.asyncio
async def test_undetected_rejects_three_phase_only_register():
    client = _client(None)
    req = WriteHoldingRegisterRequest(_THREE_PHASE_ONLY_REG, 1)
    with pytest.raises(InvalidPduState, match=r"HR\(1078\)"):
        await client.one_shot_command([req], dry_run=True)


# ---------------------------------------------------------------------------
# EMS model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ems_accepts_ems_register():
    client = _client(_caps(Model.EMS))
    req = WriteHoldingRegisterRequest(_EMS_REG, 1)
    await client.one_shot_command([req], dry_run=True)  # must not raise


@pytest.mark.asyncio
async def test_ems_rejects_inverter_register():
    client = _client(_caps(Model.EMS))
    req = WriteHoldingRegisterRequest(_SINGLE_PHASE_REG, 1)
    with pytest.raises(InvalidPduState, match=r"HR\(96\)"):
        await client.one_shot_command([req], dry_run=True)


# ---------------------------------------------------------------------------
# dry_run=False path still validates (just also transmits, so we only test
# the synchronous validation part; actual transmission would need a live socket)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validation_fires_before_transmit():
    """Rejected register raises immediately — before any network I/O."""
    client = _client(_caps(Model.HYBRID_GEN1))
    req = WriteHoldingRegisterRequest(_THREE_PHASE_REG, 1)
    # Even without dry_run, InvalidPduState must be raised (no network needed
    # because the raise happens before execute() is called).
    with pytest.raises(InvalidPduState):
        await client.one_shot_command([req])


@pytest.mark.asyncio
async def test_dry_run_validates_value_bounds():
    """A model-allowed register with an out-of-range value is rejected in dry_run.

    dry_run must run the same PDU validation (ensure_valid_state) the live encode
    path runs, otherwise a dry run can pass for a request real execution rejects.
    """
    client = _client(_caps(Model.HYBRID_GEN1))
    # HR 96 is model-allowed, but 70000 > 0xFFFF — only ensure_valid_state catches it.
    req = WriteHoldingRegisterRequest(_SINGLE_PHASE_REG, 70000)
    with pytest.raises(InvalidPduState, match=r"16-bit"):
        await client.one_shot_command([req], dry_run=True)


@pytest.mark.asyncio
async def test_dry_run_false_calls_execute(monkeypatch):
    """When dry_run=False and all registers are valid, execute() is called."""
    client = _client(_caps(Model.HYBRID_GEN1))
    req = WriteHoldingRegisterRequest(_SINGLE_PHASE_REG, 1)
    calls = []

    async def fake_execute(requests, timeout, retries, retry_delay):
        calls.append(requests)

    monkeypatch.setattr(client, "execute", fake_execute)
    await client.one_shot_command([req])
    assert len(calls) == 1 and calls[0] == [req]


# ---------------------------------------------------------------------------
# Sanity: register sets are consistent with expectations
# ---------------------------------------------------------------------------


def test_single_phase_reg_in_base_set():
    assert _SINGLE_PHASE_REG in _InverterCommands.WRITE_SAFE_REGISTERS


def test_three_phase_reg_not_in_base_set():
    assert _THREE_PHASE_REG not in _InverterCommands.WRITE_SAFE_REGISTERS


def test_three_phase_reg_in_three_phase_set():
    assert _THREE_PHASE_REG in _ThreePhaseCommands.WRITE_SAFE_REGISTERS


def test_single_phase_reg_not_in_three_phase_set():
    assert _SINGLE_PHASE_REG not in _ThreePhaseCommands.WRITE_SAFE_REGISTERS


def test_ems_reg_in_ems_set():
    assert _EMS_REG in _EmsCommands.WRITE_SAFE_REGISTERS


def test_ems_reg_not_in_base_set():
    assert _EMS_REG not in _InverterCommands.WRITE_SAFE_REGISTERS


def test_ems_set_covers_full_range():
    assert _EmsCommands.WRITE_SAFE_REGISTERS == frozenset({2040, *range(2044, 2072)})


# ---------------------------------------------------------------------------
# Encode-path drift guard: every model command set must be a subset of the PDU
# allowlist, else ensure_valid_state()/encode() would reject a model-"safe"
# register at transmit time. Encoding an EMS request exercises that path directly.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command_set",
    [
        _InverterCommands.WRITE_SAFE_REGISTERS,
        _ThreePhaseCommands.WRITE_SAFE_REGISTERS,
        _EmsCommands.WRITE_SAFE_REGISTERS,
    ],
)
def test_model_command_set_subset_of_pdu_allowlist(command_set):
    assert command_set <= PDU_WRITE_SAFE_REGISTERS


def test_ems_write_request_encodes():
    """An EMS write encodes cleanly — ensure_valid_state() accepts the register."""
    WriteHoldingRegisterRequest(_EMS_REG, 1).encode()


# ---------------------------------------------------------------------------
# Installer tier
# ---------------------------------------------------------------------------

# HR 308 = Battery Nominal Power — in INSTALLER_WRITE_REGISTERS, not WRITE_SAFE_REGISTERS
_INSTALLER_REG = 308
# HR 5004 = Restore Factory Defaults — destructive installer register
_INSTALLER_DESTRUCTIVE_REG = 5004


@pytest.mark.asyncio
async def test_installer_command_accepts_installer_register():
    """installer_command() admits installer-flagged requests for installer registers."""
    client = _client(_caps(Model.HYBRID_GEN1))
    req = WriteHoldingRegisterRequest(_INSTALLER_REG, 5000, installer=True)
    await client.installer_command([req], dry_run=True)  # must not raise


@pytest.mark.asyncio
async def test_one_shot_command_rejects_installer_flagged_request():
    """one_shot_command() always rejects installer-flagged requests."""
    client = _client(_caps(Model.HYBRID_GEN1))
    req = WriteHoldingRegisterRequest(_INSTALLER_REG, 5000, installer=True)
    with pytest.raises(InvalidPduState, match="installer_command"):
        await client.one_shot_command([req], dry_run=True)


@pytest.mark.asyncio
async def test_installer_command_rejects_non_installer_register_without_installer_flag():
    """installer_command() still rejects a non-installer register not in model_safe."""
    client = _client(_caps(Model.HYBRID_GEN1))
    # HR 1112 = AC_CHARGE_ENABLE — three-phase only; not in single-phase model_safe
    req = WriteHoldingRegisterRequest(1112, 1)
    with pytest.raises(InvalidPduState, match=r"HR\(1112\)"):
        await client.installer_command([req], dry_run=True)


def test_installer_flag_excluded_from_eq():
    """Installer flag is excluded from __eq__ — two requests differing only in installer compare equal."""
    req_normal = WriteHoldingRegisterRequest(_SINGLE_PHASE_REG, 1)
    req_installer = WriteHoldingRegisterRequest(_SINGLE_PHASE_REG, 1, installer=True)
    assert req_normal == req_installer


def test_installer_request_encodes_same_as_normal(monkeypatch):
    """Installer flag is non-wire — encoded bytes are identical to a normal request."""
    monkeypatch.setattr(WriteHoldingRegisterRequest, "ensure_valid_state", lambda self: None)
    req_normal = WriteHoldingRegisterRequest(_INSTALLER_REG, 5000, installer=False)
    req_installer = WriteHoldingRegisterRequest(_INSTALLER_REG, 5000, installer=True)
    assert req_normal.encode() == req_installer.encode()


def test_request_defaults_to_installer_false():
    """WriteHoldingRegisterRequest defaults to installer=False (wire decode path)."""
    req = WriteHoldingRegisterRequest(_SINGLE_PHASE_REG, 1)
    assert not req.installer


def test_installer_write_safe_disjoint():
    """INSTALLER_WRITE_REGISTERS and WRITE_SAFE_REGISTERS must be disjoint."""
    assert PDU_INSTALLER_WRITE_REGISTERS.isdisjoint(PDU_WRITE_SAFE_REGISTERS)


def test_installer_reg_not_in_write_safe():
    assert _INSTALLER_REG not in PDU_WRITE_SAFE_REGISTERS


def test_installer_reg_in_installer_set():
    assert _INSTALLER_REG in PDU_INSTALLER_WRITE_REGISTERS


def test_destructive_reg_in_installer_set():
    assert _INSTALLER_DESTRUCTIVE_REG in PDU_INSTALLER_WRITE_REGISTERS


# --- Bounds-validating wrapper tests ---


def test_set_battery_max_charge_pct_valid():
    from givenergy_modbus.client.commands import set_battery_max_charge_pct

    reqs = set_battery_max_charge_pct(80)
    assert len(reqs) == 1 and reqs[0].installer and reqs[0].value == 80


def test_set_battery_max_charge_pct_out_of_range():
    from givenergy_modbus.client.commands import set_battery_max_charge_pct

    with pytest.raises(ValueError, match="20"):
        set_battery_max_charge_pct(10)


def test_set_smart_load_control_soc_valid():
    from givenergy_modbus.client.commands import set_smart_load_control_soc

    reqs = set_smart_load_control_soc(75)
    assert reqs[0].installer and reqs[0].value == 75


def test_set_smart_load_control_soc_out_of_range():
    from givenergy_modbus.client.commands import set_smart_load_control_soc

    with pytest.raises(ValueError, match="50"):
        set_smart_load_control_soc(40)


def test_set_generator_control_soc_valid():
    from givenergy_modbus.client.commands import set_generator_control_soc

    reqs = set_generator_control_soc(50)
    assert reqs[0].installer and reqs[0].value == 50


def test_set_generator_control_soc_out_of_range():
    from givenergy_modbus.client.commands import set_generator_control_soc

    with pytest.raises(ValueError, match="10"):
        set_generator_control_soc(5)


# --- Destructive wrapper tests ---


def test_reset_energy_totals_requires_confirm():
    from givenergy_modbus.client.commands import reset_energy_totals

    with pytest.raises(ValueError, match="confirm=True"):
        reset_energy_totals()


def test_reset_energy_totals_with_confirm():
    from givenergy_modbus.client.commands import reset_energy_totals

    reqs = reset_energy_totals(confirm=True)
    assert len(reqs) == 1 and reqs[0].installer and reqs[0].value == 1


def test_restore_factory_defaults_requires_confirm():
    from givenergy_modbus.client.commands import restore_factory_defaults

    with pytest.raises(ValueError, match="confirm=True"):
        restore_factory_defaults()


def test_restore_factory_defaults_with_confirm():
    from givenergy_modbus.client.commands import restore_factory_defaults

    reqs = restore_factory_defaults(confirm=True)
    assert reqs[0].installer and reqs[0].value == 1


def test_enable_black_start_requires_confirm():
    from givenergy_modbus.client.commands import enable_black_start

    with pytest.raises(ValueError, match="confirm=True"):
        enable_black_start()


def test_three_phase_factory_reset_requires_confirm():
    from givenergy_modbus.client.commands import three_phase_factory_reset

    with pytest.raises(ValueError, match="confirm=True"):
        three_phase_factory_reset()


def test_three_phase_factory_reset_with_confirm():
    from givenergy_modbus.client.commands import three_phase_factory_reset

    reqs = three_phase_factory_reset(confirm=True)
    assert len(reqs) == 1 and reqs[0].installer and reqs[0].value == 1


def test_enable_black_start_with_confirm():
    from givenergy_modbus.client.commands import enable_black_start

    reqs = enable_black_start(confirm=True)
    assert len(reqs) == 1 and reqs[0].installer and reqs[0].value == 1


# --- Boolean enable installer wrappers ---


@pytest.mark.parametrize(
    "fn_name,reg",
    [
        ("set_anti_islanding_detection", 115),
        ("set_grid_import_limit_enabled", 102),
        ("set_enable_plant_mode", 300),
        ("set_enable_micro_grid", 332),
        ("set_enable_ev_charger", 333),
        ("set_enable_generator", 343),
        ("set_enable_smart_load", 540),
        ("set_enable_export_limit_3ph", 1103),
        ("set_enable_import_limit_3ph", 1131),
        ("set_peak_shaving_export_limit_enabled", 20000),
        ("set_peak_shaving_enabled", 20002),
    ],
)
def test_boolean_enable_installer_wrappers(fn_name, reg):
    import givenergy_modbus.client.commands as cmds

    fn = getattr(cmds, fn_name)
    for enabled in (True, False):
        reqs = fn(enabled)
        assert len(reqs) == 1
        assert reqs[0].installer
        assert reqs[0].value == int(enabled)
        assert reqs[0].register == reg


# --- Integer installer wrappers ---


def test_set_battery_nominal_power():
    from givenergy_modbus.client.commands import set_battery_nominal_power

    reqs = set_battery_nominal_power(5000)
    assert len(reqs) == 1 and reqs[0].installer and reqs[0].value == 5000


def test_set_battery_nominal_current():
    from givenergy_modbus.client.commands import set_battery_nominal_current

    reqs = set_battery_nominal_current(100)
    assert len(reqs) == 1 and reqs[0].installer and reqs[0].value == 100


# --- Bounded installer wrappers not yet covered ---


def test_set_ev_charger_soc_limit_valid():
    from givenergy_modbus.client.commands import set_ev_charger_soc_limit

    reqs = set_ev_charger_soc_limit(80)
    assert reqs[0].installer and reqs[0].value == 80


def test_set_ev_charger_soc_limit_out_of_range():
    from givenergy_modbus.client.commands import set_ev_charger_soc_limit

    with pytest.raises(ValueError, match="0"):
        set_ev_charger_soc_limit(101)


def test_set_generator_start_soc_valid():
    from givenergy_modbus.client.commands import set_generator_start_soc

    reqs = set_generator_start_soc(20)
    assert reqs[0].installer and reqs[0].value == 20


def test_set_generator_start_soc_out_of_range():
    from givenergy_modbus.client.commands import set_generator_start_soc

    with pytest.raises(ValueError, match="0"):
        set_generator_start_soc(101)


def test_set_generator_stop_soc_valid():
    from givenergy_modbus.client.commands import set_generator_stop_soc

    reqs = set_generator_stop_soc(80)
    assert reqs[0].installer and reqs[0].value == 80


def test_set_generator_stop_soc_out_of_range():
    from givenergy_modbus.client.commands import set_generator_stop_soc

    with pytest.raises(ValueError, match="0"):
        set_generator_stop_soc(101)


def test_set_general_load_control_soc_valid():
    from givenergy_modbus.client.commands import set_general_load_control_soc

    reqs = set_general_load_control_soc(75)
    assert reqs[0].installer and reqs[0].value == 75


def test_set_general_load_control_soc_out_of_range():
    from givenergy_modbus.client.commands import set_general_load_control_soc

    with pytest.raises(ValueError, match="50"):
        set_general_load_control_soc(40)


# --- installer_command() model-variant paths ---


@pytest.mark.asyncio
async def test_installer_command_ems_model():
    """installer_command() uses EMS register set for EMS model."""
    client = _client(_caps(Model.EMS))
    req = WriteHoldingRegisterRequest(_INSTALLER_REG, 5000, installer=True)
    await client.installer_command([req], dry_run=True)  # must not raise


@pytest.mark.asyncio
async def test_installer_command_three_phase_model():
    """installer_command() uses three-phase register set for three-phase models."""
    client = _client(_caps(Model.HYBRID_3PH))
    req = WriteHoldingRegisterRequest(_INSTALLER_REG, 5000, installer=True)
    await client.installer_command([req], dry_run=True)  # must not raise


@pytest.mark.asyncio
async def test_installer_command_ac_config_model():
    """installer_command() unions AC-config registers for AC-capable non-three-phase models."""
    client = _client(_caps(Model.AC))
    req = WriteHoldingRegisterRequest(_INSTALLER_REG, 5000, installer=True)
    await client.installer_command([req], dry_run=True)  # must not raise


@pytest.mark.asyncio
async def test_installer_command_dry_run_false_calls_execute(monkeypatch):
    """When dry_run=False and all registers valid, execute() is called."""
    client = _client(_caps(Model.HYBRID_GEN1))
    req = WriteHoldingRegisterRequest(_INSTALLER_REG, 5000, installer=True)
    calls = []

    async def fake_execute(requests, timeout, retries, retry_delay):
        calls.append(requests)

    monkeypatch.setattr(client, "execute", fake_execute)
    await client.installer_command([req])
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_installer_command_rejects_installer_register_without_flag():
    """installer_command() rejects an installer register if installer=True is not set.

    Without the flag, effective_safe = model_safe (which lacks HR308), so the
    request is rejected before any PDU validation.
    """
    client = _client(_caps(Model.HYBRID_GEN1))
    req = WriteHoldingRegisterRequest(_INSTALLER_REG, 5000)  # installer=False (default)
    with pytest.raises(InvalidPduState, match=r"HR\(308\)"):
        await client.installer_command([req], dry_run=True)


# --- Grid protection setters (HR63-83) ---


@pytest.mark.parametrize(
    "fn_name,hr,good_voltage",
    [
        ("set_v_ac_low_limit_trip", 63, 200.0),
        ("set_v_ac_high_limit_trip", 64, 270.0),
        ("set_v_ac_low_limit_reconnect", 71, 185.0),
        ("set_v_ac_high_limit_reconnect", 72, 260.0),
        ("set_v_ac_low_limit_grid", 79, 175.0),
        ("set_v_ac_high_limit_grid", 80, 285.0),
        ("set_v_ac_10min_protect", 83, 270.0),
    ],
)
def test_grid_protection_voltage_setter(fn_name, hr, good_voltage):
    import importlib

    fn = getattr(importlib.import_module("givenergy_modbus.client.commands"), fn_name)

    # confirm=False (default) raises
    with pytest.raises(ValueError, match="confirm=True"):
        fn(good_voltage)

    # Mid-range value accepted, installer flag set, correct register, encodes cleanly
    reqs = fn(good_voltage, confirm=True)
    assert len(reqs) == 1
    assert reqs[0].installer
    assert reqs[0].register == hr
    assert reqs[0].value == round(good_voltage * 10)
    assert reqs[0].encode()

    # Bool inputs rejected before scaling (True * 10 == 10 would otherwise slip through)
    with pytest.raises(ValueError, match="must be a number"):
        fn(True, confirm=True)

    # Out-of-range raises (above 500.0 V)
    with pytest.raises(ValueError):
        fn(501.0, confirm=True)


@pytest.mark.parametrize(
    "fn_name,hr,good_freq",
    [
        ("set_f_ac_low_limit_trip", 65, 47.0),
        ("set_f_ac_high_limit_trip", 66, 51.5),
        ("set_f_ac_low_limit_reconnect", 73, 47.5),
        ("set_f_ac_high_limit_reconnect", 74, 52.0),
        ("set_f_ac_low_limit_grid", 81, 47.0),
        ("set_f_ac_high_limit_grid", 82, 52.0),
    ],
)
def test_grid_protection_freq_setter(fn_name, hr, good_freq):
    import importlib

    fn = getattr(importlib.import_module("givenergy_modbus.client.commands"), fn_name)

    with pytest.raises(ValueError, match="confirm=True"):
        fn(good_freq)

    reqs = fn(good_freq, confirm=True)
    assert len(reqs) == 1
    assert reqs[0].installer
    assert reqs[0].register == hr
    assert reqs[0].value == round(good_freq * 100)
    assert reqs[0].encode()

    # Bool inputs rejected before scaling
    with pytest.raises(ValueError, match="must be a number"):
        fn(True, confirm=True)

    # Out-of-range raises (above 70.0 Hz)
    with pytest.raises(ValueError):
        fn(71.0, confirm=True)


@pytest.mark.parametrize(
    "fn_name,hr",
    [
        ("set_t_ac_low_voltage_trip", 67),
        ("set_t_ac_high_voltage_trip", 68),
        ("set_t_ac_low_freq_trip", 69),
        ("set_t_ac_high_freq_trip", 70),
        ("set_t_ac_low_voltage_reconnect", 75),
        ("set_t_ac_high_voltage_reconnect", 76),
        ("set_t_ac_low_freq_reconnect", 77),
        ("set_t_ac_high_freq_reconnect", 78),
    ],
)
def test_grid_protection_time_setter(fn_name, hr):
    import importlib

    fn = getattr(importlib.import_module("givenergy_modbus.client.commands"), fn_name)

    with pytest.raises(ValueError, match="confirm=True"):
        fn(1.0)

    reqs = fn(2.5, confirm=True)
    assert len(reqs) == 1
    assert reqs[0].installer
    assert reqs[0].register == hr
    assert reqs[0].value == 250  # 2.5s × 100
    assert reqs[0].encode()

    # round() absorbs IEEE 754 artefact (0.28 * 100 = 27.999... without rounding)
    assert fn(0.28, confirm=True)[0].value == 28

    # Bool inputs rejected before scaling
    with pytest.raises(ValueError, match="must be a number"):
        fn(True, confirm=True)

    # Negative time is invalid
    with pytest.raises(ValueError):
        fn(-0.01, confirm=True)

    # Over uint16 ceiling (655.35 s max)
    with pytest.raises(ValueError):
        fn(700.0, confirm=True)


# --- PDU: installer=True but register not in INSTALLER_WRITE_REGISTERS ---


def test_installer_request_wrong_register_raises():
    """ensure_valid_state raises if installer=True but register is not in INSTALLER_WRITE_REGISTERS."""
    # HR 96 is in WRITE_SAFE_REGISTERS, not INSTALLER_WRITE_REGISTERS
    req = WriteHoldingRegisterRequest(_SINGLE_PHASE_REG, 1, installer=True)
    with pytest.raises(InvalidPduState, match="installer register set"):
        req.ensure_valid_state()
