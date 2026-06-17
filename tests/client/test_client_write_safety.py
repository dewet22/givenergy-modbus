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
