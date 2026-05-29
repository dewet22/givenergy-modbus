"""Tests for Client.load_config() and Client.refresh() request dispatch."""

from unittest.mock import AsyncMock, patch

import pytest

from givenergy_modbus.client.client import Client
from givenergy_modbus.model.inverter import Model
from givenergy_modbus.model.plant import PlantCapabilities


def _client_with_caps(model: Model, **kwargs) -> Client:
    client = Client("localhost", 8899)
    client.plant.capabilities = PlantCapabilities(device_type=model, **kwargs)
    return client


def _sig(req) -> tuple:
    """Comparable signature for a register request: (type, device_address, base, count)."""
    return (type(req).__name__, req.device_address, req.base_register, req.register_count)


# 0x11 is the inverter's canonical address for every model except AC/HYBRID_GEN1
# (which use 0x31); battery/meter reads pass an explicit device= (issue #119).
def _hr(base, count, device=0x11) -> tuple:
    return ("ReadHoldingRegistersRequest", device, base, count)


def _ir(base, count, device=0x11) -> tuple:
    return ("ReadInputRegistersRequest", device, base, count)


def _reqs(mock_execute) -> list[tuple]:
    return [_sig(r) for r in mock_execute.call_args[0][0]]


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


async def test_load_config_no_caps():
    """Without capabilities, only the four base blocks are requested, at the legacy 0x32."""
    client = Client("localhost", 8899)
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
        await client.load_config()
    assert _reqs(mock_exec) == [
        _hr(0, 60, device=0x32),
        _hr(60, 60, device=0x32),
        _hr(120, 60, device=0x32),
        _ir(120, 60, device=0x32),
    ]


async def test_load_config_single_phase():
    """Standard single-phase HYBRID requests the four base blocks only, at 0x11."""
    client = _client_with_caps(Model.HYBRID)
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
        await client.load_config()
    assert _reqs(mock_exec) == [_hr(0, 60), _hr(60, 60), _hr(120, 60), _ir(120, 60)]


@pytest.mark.parametrize("model", [Model.AC, Model.HYBRID_GEN1])
async def test_load_config_ac_gen1_uses_0x31(model: Model):
    """AC and HYBRID_GEN1 both expose their registers at 0x31, not 0x11 (issue #119)."""
    client = _client_with_caps(model)
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
        await client.load_config()
    assert _reqs(mock_exec) == [
        _hr(0, 60, device=0x31),
        _hr(60, 60, device=0x31),
        _hr(120, 60, device=0x31),
        _ir(120, 60, device=0x31),
    ]


async def test_load_config_three_phase():
    """Three-phase models add HR 1000–1124 as three reads (60 + 60 + 5)."""
    client = _client_with_caps(Model.HYBRID_3PH)
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
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
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
        await client.load_config()
    assert _reqs(mock_exec) == [_hr(0, 60), _hr(60, 60), _hr(120, 60), _ir(120, 60), _hr(240, 60)]


async def test_load_config_ems():
    """EMS plant controllers expose HR(0,60) (identity/firmware/serial) and HR(2040,36) only.

    The inverter-style HR(60,60), HR(120,60) and IR(120,60) banks time out on EMS devices.
    Regression: #86. Wire capture confirmed via dewet22/givenergy-hass#52.
    """
    client = _client_with_caps(Model.EMS)
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
        await client.load_config()
    assert _reqs(mock_exec) == [_hr(0, 60), _hr(2040, 36)]


# ---------------------------------------------------------------------------
# refresh
# ---------------------------------------------------------------------------


async def test_refresh_no_caps_runs_legacy_path():
    """Without capabilities, refresh() runs the legacy capability-free fallback.

    It must NOT route through the deprecated refresh_plant() (that would warn);
    _refresh_no_caps() builds the legacy request list and dispatches it.
    """
    client = Client("localhost", 8899)
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
        plant = await client.refresh()
    assert plant is client.plant
    mock_exec.assert_awaited_once()


async def test_refresh_single_phase_no_peripherals():
    """Standard single-phase with no peripherals: two base IR blocks only."""
    client = _client_with_caps(Model.HYBRID)
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
        await client.refresh()
    assert _reqs(mock_exec) == [_ir(0, 60), _ir(180, 60)]


async def test_refresh_three_phase():
    """Three-phase adds IR 1000–1413 as seven reads."""
    client = _client_with_caps(Model.HYBRID_3PH)
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
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
    """EMS skips the inverter-style IR(0,60)/IR(180,60) reads — only IR 2040–2094 is requested.

    Regression: #86. The IR(2040,55) append matches what the library models for EMS today;
    the wire capture in dewet22/givenergy-hass#52 ran without populated capabilities so it
    can't independently confirm whether the EMS responds to that bank — revisit if a
    caps-populated capture shows otherwise.
    """
    client = _client_with_caps(Model.EMS)
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
        await client.refresh()
    assert _reqs(mock_exec) == [_ir(2040, 55)]


async def test_refresh_gateway():
    """Gateway adds IR 1600–1859 as five reads."""
    client = _client_with_caps(Model.GATEWAY)
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
        await client.refresh()
    expected_gw = [_ir(1600, 60), _ir(1660, 60), _ir(1720, 60), _ir(1780, 60), _ir(1840, 20)]
    assert _reqs(mock_exec) == [_ir(0, 60), _ir(180, 60)] + expected_gw


async def test_refresh_lv_batteries():
    """LV battery devices each add an IR 60+60 read at their device address."""
    client = _client_with_caps(Model.HYBRID, lv_battery_addresses=[0x33, 0x34])
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
        await client.refresh()
    reqs = _reqs(mock_exec)
    assert _ir(60, 60, device=0x33) in reqs
    assert _ir(60, 60, device=0x34) in reqs


async def test_refresh_meter_addresses():
    """Meter devices each add an IR 60+30 read."""
    client = _client_with_caps(Model.HYBRID, meter_addresses=[0x01, 0x02])
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
        await client.refresh()
    reqs = _reqs(mock_exec)
    assert _ir(60, 30, device=0x01) in reqs
    assert _ir(60, 30, device=0x02) in reqs


async def test_refresh_bcu_stacks():
    """BCU stacks each add an IR 60+60 read at 0x70 + offset."""
    # Use HYBRID_HV_GEN3 which is three-phase + HV; check BCU reads are present
    client = _client_with_caps(Model.HYBRID_HV_GEN3, bcu_stacks=[(0, 3), (1, 2)])
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
        await client.refresh()
    reqs = _reqs(mock_exec)
    assert _ir(60, 60, device=0x70) in reqs
    assert _ir(60, 60, device=0x71) in reqs


async def test_refresh_plant_forwards_timeout_retries_and_retry_delay_post_detect():
    """Once capabilities is set, refresh_plant() must thread timeout/retries/retry_delay through.

    load_config() and refresh() each accept these params; the capability-aware branch
    used to call them bare, silently dropping anything the caller passed in.
    """
    client = _client_with_caps(Model.HYBRID)
    with (
        patch.object(client, "load_config", new_callable=AsyncMock) as mock_lc,
        patch.object(client, "refresh", new_callable=AsyncMock) as mock_rf,
        pytest.warns(DeprecationWarning),
    ):
        await client.refresh_plant(full_refresh=True, timeout=3.5, retries=4, retry_delay=1.2)

    mock_lc.assert_awaited_once_with(timeout=3.5, retries=4, retry_delay=1.2)
    mock_rf.assert_awaited_once_with(timeout=3.5, retries=4, retry_delay=1.2)


async def test_refresh_plant_skips_load_config_when_not_full_refresh():
    """full_refresh=False on a capability-known client must call only refresh().

    The timeout/retries/retry_delay params still need to thread through to refresh().
    """
    client = _client_with_caps(Model.HYBRID)
    with (
        patch.object(client, "load_config", new_callable=AsyncMock) as mock_lc,
        patch.object(client, "refresh", new_callable=AsyncMock) as mock_rf,
        pytest.warns(DeprecationWarning),
    ):
        await client.refresh_plant(full_refresh=False, timeout=2.0, retries=1, retry_delay=0.3)

    mock_lc.assert_not_awaited()
    mock_rf.assert_awaited_once_with(timeout=2.0, retries=1, retry_delay=0.3)


async def test_probe_passes_zero_retry_delay():
    """_probe() must explicitly use retry_delay=0.

    Detect() does many speculative absent-device probes and most are expected to fail;
    a non-zero retry_delay there would add seconds to discovery for no diagnostic value.
    """
    client = Client("localhost", 8899)
    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock) as mock_send:
        from givenergy_modbus.pdu import ReadInputRegistersRequest

        await client._probe(
            ReadInputRegistersRequest(base_register=60, register_count=60, device_address=0x05),
            timeout=0.5,
            retries=1,
        )

    _, kwargs = mock_send.call_args
    assert kwargs["retry_delay"] == 0
