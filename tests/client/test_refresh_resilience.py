"""Partial-failure contract for Client.refresh() / load_config().

A poll cycle fans out many register reads (inverter banks, per-battery,
per-meter, per-BCU). Historically ``execute()`` gathered them with
``return_exceptions=False``, so the *first* read that timed out aborted the
whole cycle and the caller got nothing — one offline battery discarded every
reading that *did* come back.

The contract these tests pin:

- **full success** → return the ``Plant`` as before;
- **partial** (some reads failed, some succeeded) → raise
  ``RefreshPartiallySucceeded`` carrying the partial ``plant`` (the consumer's
  one chance to use the data we did collect), the structured ``failures``, and
  the raw ``cause`` ExceptionGroup;
- **total** (every read failed — link effectively dead) → raise
  ``RefreshFailed``.

Raising on partial is deliberate: it's the most honest, hardest-to-ignore
signal, and the ``except`` block is exactly where consumer-domain policy
(counters, diagnostics, notifications, or a deliberate pass) belongs. Policy is
not the library's to assume.

The deprecated orchestrators ``refresh_plant()`` / ``watch_plant()`` emit a
``DeprecationWarning`` *and* propagate the same exceptions — a double signal to
migrate to the primitives.

Failures are keyed on battery address (refresh) and base register (load_config),
both stable across #119/#121's inverter-address rework. Resilience follow-up to
#119; see dewet22/givenergy-hass#52.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from givenergy_modbus.client.client import Client
from givenergy_modbus.exceptions import RefreshFailed, RefreshPartiallySucceeded
from givenergy_modbus.model.inverter import Model
from givenergy_modbus.model.plant import PlantCapabilities
from givenergy_modbus.pdu import ReadInputRegistersRequest

# 0x33/0x34 are LV battery pack addresses, unaffected by the inverter-address
# rework — keying the induced failure here keeps these tests stable across #121.
OFFLINE_BATTERY = 0x34


def _client_with_caps(model: Model, **kwargs) -> Client:
    client = Client("localhost", 8899)
    client.plant.capabilities = PlantCapabilities(device_type=model, **kwargs)
    return client


def _selective_send(should_fail):
    """A send_request_and_await_response stand-in.

    Raises ``TimeoutError`` for any request where ``should_fail(request)`` is
    truthy (an offline/slow device that has exhausted its retries), and returns
    a benign successful response otherwise.
    """

    def _side(request, *args, **kwargs):
        if should_fail(request):
            raise TimeoutError()
        return SimpleNamespace(error=False, device_address=request.device_address)

    return _side


def _fail_device(*addresses):
    """Predicate: fail reads aimed at any of these device addresses."""
    targets = set(addresses)
    return lambda req: req.device_address in targets


def _fail_base(*bases):
    """Predicate: fail reads at any of these base registers (address-agnostic)."""
    targets = set(bases)
    return lambda req: req.base_register in targets


def _patch_send(client, predicate):
    return patch.object(
        client,
        "send_request_and_await_response",
        new_callable=AsyncMock,
        side_effect=_selective_send(predicate),
    )


# ---------------------------------------------------------------------------
# Partial failure → RefreshPartiallySucceeded (carrying the data we did get)
# ---------------------------------------------------------------------------


async def test_refresh_partial_raises_partially_succeeded():
    """One offline battery: refresh() raises RefreshPartiallySucceeded, not bare TimeoutError.

    The partial plant rides on the exception so a caller doing ``except ...``
    never loses the tick's data.
    """
    client = _client_with_caps(Model.HYBRID, lv_battery_addresses=[0x33, OFFLINE_BATTERY])
    with _patch_send(client, _fail_device(OFFLINE_BATTERY)):
        with pytest.raises(RefreshPartiallySucceeded) as ei:
            await client.refresh()
    exc = ei.value
    assert exc.plant is client.plant
    assert any(f.device_address == OFFLINE_BATTERY for f in exc.failures)


async def test_load_config_partial_raises_partially_succeeded():
    """load_config() carries the same contract; here an inverter bank (base 120) drops.

    Keyed on base register so it's independent of which device address the
    inverter lands on after #121.
    """
    client = _client_with_caps(Model.HYBRID)
    with _patch_send(client, _fail_base(120)):
        with pytest.raises(RefreshPartiallySucceeded) as ei:
            await client.load_config()
    assert ei.value.plant is client.plant
    assert any(f.base_register == 120 for f in ei.value.failures)


async def test_partial_exception_carries_full_failure_detail():
    """Structured failures (device/type/base/count) plus a cause grouping the raw errors.

    No silent swallow: every dropped read is accounted for, both as a
    ReadFailure record and inside the ExceptionGroup.
    """
    client = _client_with_caps(Model.HYBRID, lv_battery_addresses=[0x33, OFFLINE_BATTERY])
    with _patch_send(client, _fail_device(OFFLINE_BATTERY)):
        with pytest.raises(RefreshPartiallySucceeded) as ei:
            await client.refresh()
    exc = ei.value
    fail = next(f for f in exc.failures if f.device_address == OFFLINE_BATTERY)
    assert fail.request_type == "ReadInputRegistersRequest"
    assert (fail.base_register, fail.register_count) == (60, 60)
    assert isinstance(exc.cause, ExceptionGroup)
    assert len(exc.cause.exceptions) == len(exc.failures)


# ---------------------------------------------------------------------------
# Total failure → RefreshFailed; full success → plain Plant
# ---------------------------------------------------------------------------


async def test_refresh_total_raises_failed():
    """Every read times out (dead link): refresh() raises RefreshFailed."""
    client = _client_with_caps(Model.HYBRID, lv_battery_addresses=[0x33, OFFLINE_BATTERY])
    with _patch_send(client, lambda req: True):
        with pytest.raises(RefreshFailed) as ei:
            await client.refresh()
    assert ei.value.failures
    assert isinstance(ei.value.cause, ExceptionGroup)


async def test_refresh_returns_plant_when_all_reads_succeed():
    """Happy path: with no timeouts, refresh() returns the plant and raises nothing."""
    client = _client_with_caps(Model.HYBRID, lv_battery_addresses=[0x33, OFFLINE_BATTERY])
    with _patch_send(client, _fail_device()):
        plant = await client.refresh()
    assert plant is client.plant


# ---------------------------------------------------------------------------
# Deprecated orchestrators: warn AND propagate the new contract
# ---------------------------------------------------------------------------


async def test_refresh_plant_deprecated():
    """refresh_plant() still works on the happy path but warns it's deprecated."""
    client = _client_with_caps(Model.HYBRID)
    with _patch_send(client, _fail_device()):
        with pytest.warns(DeprecationWarning):
            await client.refresh_plant()


async def test_refresh_plant_propagates_partial():
    """A consumer still on refresh_plant() gets the new exception too — explicit migration signal."""
    client = _client_with_caps(Model.HYBRID, lv_battery_addresses=[0x33, OFFLINE_BATTERY])
    with _patch_send(client, _fail_device(OFFLINE_BATTERY)):
        with pytest.warns(DeprecationWarning), pytest.raises(RefreshPartiallySucceeded):
            await client.refresh_plant()


async def test_refresh_plant_no_caps_detects_first():
    """refresh_plant() without capabilities runs detect() first, then polls (#105).

    The deprecated wrapper keeps the legacy connect()-then-refresh_plant() shape
    working — but by detecting (so the inverter address is model-correct, e.g. 0x11
    for an AIO) rather than the old blind 0x32 fallback that timed out.
    """
    client = _client_with_caps(Model.HYBRID)
    client.plant.capabilities = None  # simulate no prior detect()
    detected = PlantCapabilities(device_type=Model.HYBRID)
    # Record call order — detecting *before* polling is the whole regression (#105),
    # so pin the sequence rather than just asserting each was awaited.
    calls: list[str] = []
    with (
        patch.object(
            client,
            "detect",
            new_callable=AsyncMock,
            side_effect=lambda *a, **k: calls.append("detect") or detected,
        ) as mock_detect,
        patch.object(
            client, "load_config", new_callable=AsyncMock, side_effect=lambda *a, **k: calls.append("load_config")
        ) as mock_load,
        patch.object(
            client, "refresh", new_callable=AsyncMock, side_effect=lambda *a, **k: calls.append("refresh")
        ) as mock_refresh,
    ):
        with pytest.warns(DeprecationWarning):
            await client.refresh_plant()
    assert calls == ["detect", "load_config", "refresh"]
    mock_detect.assert_awaited_once()
    assert client.plant.capabilities is detected
    mock_load.assert_awaited_once()
    mock_refresh.assert_awaited_once()


async def test_refresh_plant_warns_on_ignored_max_batteries():
    """refresh_plant(max_batteries=...) now no-ops that arg — warn rather than silently ignore.

    Battery addresses come from detect()/capabilities; the old fixed-count poll is gone.
    """
    client = _client_with_caps(Model.HYBRID)
    with (
        patch.object(client, "load_config", new_callable=AsyncMock),
        patch.object(client, "refresh", new_callable=AsyncMock),
    ):
        with pytest.warns(DeprecationWarning, match="max_batteries"):
            await client.refresh_plant(max_batteries=3)


async def test_watch_plant_deprecated():
    """watch_plant() warns on entry (before doing any work)."""
    client = Client("localhost", 8899)
    with patch.object(client, "connect", new_callable=AsyncMock, side_effect=RuntimeError("stop")):
        with pytest.warns(DeprecationWarning), pytest.raises(RuntimeError):
            await client.watch_plant()


# ---------------------------------------------------------------------------
# _execute_reads edge cases
# ---------------------------------------------------------------------------


async def test_execute_reads_empty_is_noop():
    """No requests → returns without raising or touching the wire."""
    client = _client_with_caps(Model.HYBRID)
    assert await client._execute_reads([], timeout=1.0, retries=0, retry_delay=0.0) is None


async def test_execute_reads_reraises_cancellation():
    """A CancelledError result is re-raised, never collected as a failure."""
    client = _client_with_caps(Model.HYBRID)
    req = ReadInputRegistersRequest(base_register=0, register_count=60, device_address=0x11)
    with patch.object(client, "execute", new_callable=AsyncMock, return_value=[asyncio.CancelledError()]):
        with pytest.raises(asyncio.CancelledError):
            await client._execute_reads([req], timeout=1.0, retries=0, retry_delay=0.0)
