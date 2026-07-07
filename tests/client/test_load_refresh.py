"""Tests for Client.load_config() and Client.refresh() request dispatch."""

from unittest.mock import AsyncMock, PropertyMock, patch

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


async def test_load_config_single_phase():
    """Standard single-phase HYBRID requests the four base blocks only — no HR(300-359).

    HR(300-359) holds AC-coupled-only config; polling it on a DC-coupled/hybrid model
    causes a timeout → RefreshPartiallySucceeded → ConfigEntryNotReady in hass (#162).
    """
    client = _client_with_caps(Model.HYBRID)
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
        await client.load_config()
    assert _reqs(mock_exec) == [_hr(0, 60), _hr(60, 60), _hr(120, 60), _ir(120, 60)]


async def test_load_config_ac_polls_hr300():
    """AC-coupled model polls HR(300-359) at 0x11 (export priority, EPS, AC charge/discharge limits; #189)."""
    client = _client_with_caps(Model.AC)
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
        await client.load_config()
    assert _reqs(mock_exec) == [
        _hr(0, 60),
        _hr(60, 60),
        _hr(120, 60),
        _ir(120, 60),
        _hr(300, 60),
    ]


async def test_load_config_hybrid_gen1_at_0x11_no_hr300():
    """HYBRID_GEN1 reads at the unified 0x11 address (#189) and is DC-coupled — no HR(300-359) (#162)."""
    client = _client_with_caps(Model.HYBRID_GEN1)
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
        await client.load_config()
    assert _reqs(mock_exec) == [
        _hr(0, 60),
        _hr(60, 60),
        _hr(120, 60),
        _ir(120, 60),
    ]


async def test_load_config_hybrid_gen1_does_not_poll_smart_load():
    """HYBRID_GEN1 must not poll HR(540-599): the block times out on it (#179).

    The Smart Load gate (_SMART_LOAD_CAPABLE_MODELS) is currently empty, so no model
    polls it. Once a model is confirmed to answer the read, add it to that set and the
    HR(540) request returns for that model.
    """
    client = _client_with_caps(Model.HYBRID_GEN1)
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
        await client.load_config()
    assert _hr(540, 60) not in _reqs(mock_exec)


async def test_load_config_no_model_polls_hv_cabinet():
    """HR(499-510) HV cabinet topology block is never polled — gate set is empty.

    The block is defined from the GE app 4.0.7 binary but no model has been confirmed to
    respond to the read on real hardware. When a model is confirmed, add it to
    _HV_CABINET_MODELS; this test will need updating at that point.
    """
    for model in (Model.HYBRID_GEN1, Model.HYBRID_3PH, Model.AC, Model.ALL_IN_ONE, Model.EMS):
        client = _client_with_caps(model)
        with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
            await client.load_config()
        assert _hr(499, 12) not in _reqs(mock_exec), f"{model}: should not poll HV cabinet block"


async def test_load_config_no_model_polls_peak_shaving():
    """HR(20000-20051) peak-shaving block is never polled — gate set is empty.

    The block is defined from the GE app 4.0.7 binary but no model has been confirmed to
    respond to the read on real hardware. When a model is confirmed, add it to
    _PEAK_SHAVING_MODELS; this test will need updating at that point.
    """
    for model in (Model.HYBRID_GEN1, Model.HYBRID_3PH, Model.AC, Model.ALL_IN_ONE, Model.EMS):
        client = _client_with_caps(model)
        with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
            await client.load_config()
        assert _hr(20000, 52) not in _reqs(mock_exec), f"{model}: should not poll peak-shaving block"


async def test_load_config_polls_hv_cabinet_when_capable():
    """When has_hv_cabinet_block is True, HR(499-510) is included in load_config().

    Exercises the True branch of the gate; in production this fires once a real
    hardware capture confirms the block responds and a model is added to _HV_CABINET_MODELS.
    """
    client = _client_with_caps(Model.HYBRID_GEN1)
    caps_cls = type(client.plant.capabilities)
    with patch.object(caps_cls, "has_hv_cabinet_block", new_callable=PropertyMock, return_value=True):
        with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
            await client.load_config()
    assert _hr(499, 12) in _reqs(mock_exec)


async def test_load_config_polls_peak_shaving_when_capable():
    """When has_peak_shaving_block is True, HR(20000-20051) is included in load_config().

    Exercises the True branch of the gate; in production this fires once a real
    hardware capture confirms the block responds and a model is added to _PEAK_SHAVING_MODELS.
    """
    client = _client_with_caps(Model.HYBRID_GEN1)
    caps_cls = type(client.plant.capabilities)
    with patch.object(caps_cls, "has_peak_shaving_block", new_callable=PropertyMock, return_value=True):
        with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
            await client.load_config()
    assert _hr(20000, 52) in _reqs(mock_exec)


async def test_load_config_three_phase():
    """Three-phase DC-coupled models add HR 1000–1124 but not HR(300-359)."""
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
    """Extended-slot DC-coupled model adds HR 240–299 but not HR(300-359).

    HYBRID_GEN3 is extended-slot only above firmware 302 (#293 Slice B) — pin the
    firmware above the boundary so this test keeps exercising the extended-slot path.
    """
    client = _client_with_caps(Model.HYBRID_GEN3, arm_firmware_version=303)
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
        await client.load_config()
    assert _reqs(mock_exec) == [
        _hr(0, 60),
        _hr(60, 60),
        _hr(120, 60),
        _ir(120, 60),
        _hr(240, 60),
    ]


async def test_load_config_residential_aio_no_1000_range():
    """Residential ALL_IN_ONE: extended-slot + HR(300-359) AC-config, but no HR(1000+) bank.

    ALL_IN_ONE is HV + extended-slot + single-phase. It does NOT poll the three-phase
    HR(1000+) bank (#105), but it DOES carry the HR(300-359) AC-output config block
    (export priority/EPS/AC limits) and must keep polling it (#162).
    """
    client = _client_with_caps(Model.ALL_IN_ONE)
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
        await client.load_config()
    reqs = _reqs(mock_exec)
    assert reqs == [_hr(0, 60), _hr(60, 60), _hr(120, 60), _ir(120, 60), _hr(240, 60), _hr(300, 60)]
    assert all(base < 1000 for _, _, base, _ in reqs), "AIO must not poll the 1000-range bank"


async def test_load_config_hybrid_hv_gen3_three_phase_before_extended_slots():
    """HYBRID_HV_GEN3 has BOTH is_three_phase and has_extended_slots true (#293 Slice C1).

    The HR(1000+) three-phase block must appear BEFORE HR(240) — the relative order
    between these two facts is a real behaviour contract, preserved by keeping both
    as literal inline checks in load_config() rather than folding either into the
    generic capability-gated table (which would iterate in a different order).
    """
    client = _client_with_caps(Model.HYBRID_HV_GEN3)
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
        _hr(240, 60),
    ]


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


async def test_refresh_without_caps_raises_plant_not_detected():
    """refresh() refuses to guess an address when detect() hasn't run (#105).

    Previously it fell back to a hardcoded 0x32 poll, which silently timed out on
    models answering elsewhere (e.g. an All-in-One at 0x11). It now raises
    PlantNotDetected rather than dispatching a blind request.
    """
    from givenergy_modbus.exceptions import PlantNotDetected

    client = Client("localhost", 8899)
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
        with pytest.raises(PlantNotDetected, match="detect()"):
            await client.refresh()
    mock_exec.assert_not_awaited()


async def test_load_config_without_caps_raises_plant_not_detected():
    """load_config() likewise refuses without capabilities (#105)."""
    from givenergy_modbus.exceptions import PlantNotDetected

    client = Client("localhost", 8899)
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
        with pytest.raises(PlantNotDetected, match="detect()"):
            await client.load_config()
    mock_exec.assert_not_awaited()


async def test_refresh_single_phase_no_peripherals():
    """Standard single-phase with no peripherals: two base IR blocks only."""
    client = _client_with_caps(Model.HYBRID)
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
        await client.refresh()
    assert _reqs(mock_exec) == [_ir(0, 60), _ir(180, 60)]


async def test_refresh_hybrid_with_peripherals_golden_sequence():
    """Golden: HYBRID with meter + LV battery — full ordered sequence must not drift.

    Pins the relative order of inverter blocks, battery, and meter reads so that
    _refresh_ranges extraction in Slice 4 cannot accidentally reorder or drop a bank.
    """
    client = _client_with_caps(
        Model.HYBRID,
        meter_addresses=[0x01],
        lv_battery_addresses=[0x33, 0x34],
        lv_bcu_address=0x31,
    )
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
        await client.refresh()
    assert _reqs(mock_exec) == [
        _ir(0, 60),  # inverter live block
        _ir(180, 60),  # inverter second block
        _ir(60, 60, device=0x33),  # LV battery 1
        _ir(60, 60, device=0x34),  # LV battery 2
        _ir(60, 60, device=0x31),  # LV BCU
        _ir(60, 30, device=0x01),  # meter
    ]


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


async def test_refresh_residential_aio_no_1000_range():
    """Residential ALL_IN_ONE refreshes from IR(0)/IR(180) only — no per-phase IR(1000+) (#105)."""
    client = _client_with_caps(Model.ALL_IN_ONE)
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
        await client.refresh()
    reqs = _reqs(mock_exec)
    assert reqs == [_ir(0, 60), _ir(180, 60)]
    assert all(base < 1000 for _, _, base, _ in reqs), "AIO must not poll the 1000-range bank"


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


async def test_refresh_lv_bcu():
    """A detected LV BCU adds an IR 60+60 read at its page address (#241)."""
    client = _client_with_caps(Model.HYBRID, lv_battery_addresses=[0x32], lv_bcu_address=0x31)
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
        await client.refresh()
    reqs = _reqs(mock_exec)
    assert _ir(60, 60, device=0x31) in reqs


async def test_refresh_no_lv_bcu_read_when_absent():
    """No 0x31 read when the BCU block wasn't detected."""
    client = _client_with_caps(Model.HYBRID, lv_battery_addresses=[0x32])
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
        await client.refresh()
    assert _ir(60, 60, device=0x31) not in _reqs(mock_exec)


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


async def test_refresh_aio_battery_modules():
    """AIO battery modules each add an IR 60+60 read at their own device address (#192)."""
    client = _client_with_caps(Model.ALL_IN_ONE, aio_battery_module_addresses=[0x50, 0x51, 0x52, 0x53])
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
        await client.refresh()
    reqs = _reqs(mock_exec)
    for addr in (0x50, 0x51, 0x52, 0x53):
        assert _ir(60, 60, device=addr) in reqs


async def test_refresh_hv_bmu_modules():
    """Non-AIO HV BMU modules each add an IR 60+60 read at their own 0x50+ address (#265)."""
    client = _client_with_caps(Model.HYBRID_HV_GEN3, bcu_stacks=[(0, 2)], hv_bmu_addresses=[0x50, 0x51])
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_exec:
        await client.refresh()
    reqs = _reqs(mock_exec)
    for addr in (0x50, 0x51):
        assert _ir(60, 60, device=addr) in reqs


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


async def test_refresh_default_budget_tuned_for_contended_bus():
    """refresh() defaults to timeout=2.0s / retries=1 — the contended-bus tuning (#132).

    The hot poll path used to default to 1.0s / 0 retries, which produced spurious
    timeouts when other clients (GivTCP, the app, Predbat) share the inverter bus.
    """
    client = _client_with_caps(Model.HYBRID)
    with patch.object(client, "_execute_reads", new_callable=AsyncMock) as mock_reads:
        await client.refresh()
    _, kwargs = mock_reads.call_args
    assert kwargs["timeout"] == 2.0
    assert kwargs["retries"] == 1


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
