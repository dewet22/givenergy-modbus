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
