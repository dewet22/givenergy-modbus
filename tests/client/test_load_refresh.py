"""Tests for Client.load_config() and Client.refresh() request dispatch."""

from unittest.mock import AsyncMock, patch

from givenergy_modbus.client.client import Client
from givenergy_modbus.model.inverter import Model
from givenergy_modbus.model.plant import PlantCapabilities


def _client_with_caps(model: Model, **kwargs) -> Client:
    client = Client("localhost", 8899)
    client.plant.capabilities = PlantCapabilities(device_type=model, **kwargs)
    return client


def _sig(req) -> tuple:
    """Comparable signature for a register request: (type, slave, base, count)."""
    return (type(req).__name__, req.slave_address, req.base_register, req.register_count)


def _hr(base, count, slave=0x32) -> tuple:
    return ("ReadHoldingRegistersRequest", slave, base, count)


def _ir(base, count, slave=0x32) -> tuple:
    return ("ReadInputRegistersRequest", slave, base, count)


def _reqs(mock_execute) -> list[tuple]:
    return [_sig(r) for r in mock_execute.call_args[0][0]]


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


async def test_load_config_no_caps():
    """Without capabilities, only the four base blocks are requested."""
    client = Client("localhost", 8899)
    with patch.object(client, "execute", new_callable=AsyncMock) as mock_exec:
        await client.load_config()
    assert _reqs(mock_exec) == [_hr(0, 60), _hr(60, 60), _hr(120, 60), _ir(120, 60)]


async def test_load_config_single_phase():
    """Standard single-phase HYBRID requests the four base blocks only."""
    client = _client_with_caps(Model.HYBRID)
    with patch.object(client, "execute", new_callable=AsyncMock) as mock_exec:
        await client.load_config()
    assert _reqs(mock_exec) == [_hr(0, 60), _hr(60, 60), _hr(120, 60), _ir(120, 60)]


async def test_load_config_three_phase():
    """Three-phase models add HR 1000–1124 as three reads (60 + 60 + 5)."""
    client = _client_with_caps(Model.HYBRID_3PH)
    with patch.object(client, "execute", new_callable=AsyncMock) as mock_exec:
        await client.load_config()
    assert _reqs(mock_exec) == [
        _hr(0, 60),
        _hr(60, 60),
        _hr(120, 60),
        _ir(120, 60),
        _hr(1000, 60),
        _hr(1060, 60),
        _hr(1120, 5),
    ]


async def test_load_config_extended_slots():
    """Extended-slot models add HR 240–299."""
    client = _client_with_caps(Model.HYBRID_GEN3)
    with patch.object(client, "execute", new_callable=AsyncMock) as mock_exec:
        await client.load_config()
    assert _reqs(mock_exec) == [_hr(0, 60), _hr(60, 60), _hr(120, 60), _ir(120, 60), _hr(240, 60)]


async def test_load_config_ems():
    """EMS models add HR 2040–2075."""
    client = _client_with_caps(Model.EMS)
    with patch.object(client, "execute", new_callable=AsyncMock) as mock_exec:
        await client.load_config()
    assert _reqs(mock_exec) == [_hr(0, 60), _hr(60, 60), _hr(120, 60), _ir(120, 60), _hr(2040, 36)]


# ---------------------------------------------------------------------------
# refresh
# ---------------------------------------------------------------------------


async def test_refresh_no_caps_falls_back_to_refresh_plant():
    """Without capabilities, refresh() delegates to refresh_plant(full_refresh=False)."""
    client = Client("localhost", 8899)
    with patch.object(client, "refresh_plant", new_callable=AsyncMock) as mock_rp:
        await client.refresh()
    mock_rp.assert_awaited_once_with(full_refresh=False)


async def test_refresh_single_phase_no_peripherals():
    """Standard single-phase with no peripherals: two base IR blocks only."""
    client = _client_with_caps(Model.HYBRID)
    with patch.object(client, "execute", new_callable=AsyncMock) as mock_exec:
        await client.refresh()
    assert _reqs(mock_exec) == [_ir(0, 60), _ir(180, 60)]


async def test_refresh_three_phase():
    """Three-phase adds IR 1000–1413 as seven reads."""
    client = _client_with_caps(Model.HYBRID_3PH)
    with patch.object(client, "execute", new_callable=AsyncMock) as mock_exec:
        await client.refresh()
    expected_3ph = [
        _ir(1000, 60),
        _ir(1060, 60),
        _ir(1120, 60),
        _ir(1180, 60),
        _ir(1240, 60),
        _ir(1300, 60),
        _ir(1360, 54),
    ]
    assert _reqs(mock_exec) == [_ir(0, 60), _ir(180, 60)] + expected_3ph


async def test_refresh_ems():
    """EMS adds IR 2040–2094 as one read of 55 registers."""
    client = _client_with_caps(Model.EMS)
    with patch.object(client, "execute", new_callable=AsyncMock) as mock_exec:
        await client.refresh()
    assert _reqs(mock_exec) == [_ir(0, 60), _ir(180, 60), _ir(2040, 55)]


async def test_refresh_gateway():
    """Gateway adds IR 1600–1859 as five reads."""
    client = _client_with_caps(Model.GATEWAY)
    with patch.object(client, "execute", new_callable=AsyncMock) as mock_exec:
        await client.refresh()
    expected_gw = [_ir(1600, 60), _ir(1660, 60), _ir(1720, 60), _ir(1780, 60), _ir(1840, 20)]
    assert _reqs(mock_exec) == [_ir(0, 60), _ir(180, 60)] + expected_gw


async def test_refresh_lv_batteries():
    """LV battery slaves each add an IR 60+60 read at their slave address."""
    client = _client_with_caps(Model.HYBRID, lv_battery_slaves=[0x33, 0x34])
    with patch.object(client, "execute", new_callable=AsyncMock) as mock_exec:
        await client.refresh()
    reqs = _reqs(mock_exec)
    assert _ir(60, 60, slave=0x33) in reqs
    assert _ir(60, 60, slave=0x34) in reqs


async def test_refresh_meter_slaves():
    """Meter slaves each add an IR 60+30 read."""
    client = _client_with_caps(Model.HYBRID, meter_slaves=[0x01, 0x02])
    with patch.object(client, "execute", new_callable=AsyncMock) as mock_exec:
        await client.refresh()
    reqs = _reqs(mock_exec)
    assert _ir(60, 30, slave=0x01) in reqs
    assert _ir(60, 30, slave=0x02) in reqs


async def test_refresh_bcu_slaves():
    """BCU slaves each add an IR 60+60 read at 0x70 + offset."""
    # Use HYBRID_HV_GEN3 which is three-phase + HV; check BCU reads are present
    client = _client_with_caps(Model.HYBRID_HV_GEN3, bcu_slaves=[(0, 3), (1, 2)])
    with patch.object(client, "execute", new_callable=AsyncMock) as mock_exec:
        await client.refresh()
    reqs = _reqs(mock_exec)
    assert _ir(60, 60, slave=0x70) in reqs
    assert _ir(60, 60, slave=0x71) in reqs
