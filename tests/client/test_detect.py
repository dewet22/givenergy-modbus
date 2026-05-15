"""Tests for Client.detect() and PlantCapabilities."""

from unittest.mock import AsyncMock, patch

import pytest

from givenergy_modbus.client.client import Client
from givenergy_modbus.exceptions import CommunicationError
from givenergy_modbus.model.inverter import Model
from givenergy_modbus.model.plant import PlantCapabilities
from givenergy_modbus.model.register import HR, IR


def _make_client() -> Client:
    client = Client("localhost", 8899)
    return client


def _prime_cache(client: Client, device_address: int, registers: dict) -> None:
    """Pre-populate a device's register cache as if plant.update() had been called."""
    from givenergy_modbus.model.register_cache import RegisterCache

    if device_address not in client.plant.register_caches:
        client.plant.register_caches[device_address] = RegisterCache()
    client.plant.register_caches[device_address].update(registers)


async def _mock_probe_success(request, *, timeout, retries):
    """Stub that always succeeds without touching the network."""
    return object()


async def _mock_probe_timeout(request, *, timeout, retries):
    raise TimeoutError


# ---------------------------------------------------------------------------
# PlantCapabilities serialisation
# ---------------------------------------------------------------------------


def test_plant_capabilities_round_trip():
    caps = PlantCapabilities(
        device_type=Model.HYBRID,
        inverter_address=0x32,
        meter_addresses=[1, 2],
        lv_battery_addresses=[0x33, 0x34],
        bcu_stacks=[],
    )
    assert PlantCapabilities.from_dict(caps.to_dict()) == caps


def test_plant_capabilities_round_trip_with_bcus():
    caps = PlantCapabilities(
        device_type=Model.ALL_IN_ONE,
        inverter_address=0x32,
        meter_addresses=[],
        lv_battery_addresses=[],
        bcu_stacks=[(0, 3), (1, 2)],
    )
    restored = PlantCapabilities.from_dict(caps.to_dict())
    assert restored == caps
    assert restored.bcu_stacks == [(0, 3), (1, 2)]


def test_plant_capabilities_is_hv():
    assert PlantCapabilities(device_type=Model.ALL_IN_ONE).is_hv is True
    assert PlantCapabilities(device_type=Model.HYBRID_HV_GEN3).is_hv is True
    assert PlantCapabilities(device_type=Model.ALL_IN_ONE_HYBRID).is_hv is True
    assert PlantCapabilities(device_type=Model.HYBRID_3PH).is_hv is True
    assert PlantCapabilities(device_type=Model.AC_3PH).is_hv is True
    assert PlantCapabilities(device_type=Model.HYBRID).is_hv is False
    assert PlantCapabilities(device_type=Model.HYBRID_GEN3).is_hv is False
    assert PlantCapabilities(device_type=Model.EMS).is_hv is False


# ---------------------------------------------------------------------------
# Client.detect()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_resolves_model_from_hr0_hr21():
    client = _make_client()
    # DTC 0x2001 → "2001" prefix "20", arm_fw=300 → century 3 → HYBRID_GEN3
    _prime_cache(client, 0x32, {HR(0): 0x2001, HR(21): 300})

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = object()
        with patch.object(client, "_probe", new=AsyncMock(return_value=False)):
            caps = await client.detect()

    assert caps.device_type == Model.HYBRID_GEN3
    assert client.plant.capabilities is caps


def _prime_battery_serial(client: Client, device_address: int) -> None:
    """Prime a device cache with a valid battery serial number (IR 110–114)."""
    # "SA1234A567" encoded as five big-endian 16-bit register values.
    _prime_cache(
        client,
        device_address,
        {IR(110): 0x5341, IR(111): 0x3132, IR(112): 0x3334, IR(113): 0x4135, IR(114): 0x3637},
    )


@pytest.mark.asyncio
async def test_detect_no_peripherals_returns_empty_lists():
    client = _make_client()
    _prime_cache(client, 0x32, {HR(0): 0x2001, HR(21): 0})
    # No battery serial primed at 0x32 → Battery.is_valid() returns False → no battery devices.

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", new=AsyncMock(return_value=False)):
            caps = await client.detect()

    assert caps.meter_addresses == []
    assert caps.lv_battery_addresses == []
    assert caps.bcu_stacks == []


@pytest.mark.asyncio
async def test_detect_finds_lv_batteries():
    client = _make_client()
    _prime_cache(client, 0x32, {HR(0): 0x2001, HR(21): 0})
    # Battery #1 shares the inverter cache at 0x32; #2 is at 0x33.
    _prime_battery_serial(client, 0x32)
    _prime_battery_serial(client, 0x33)

    # 0x33 responds; 0x34 times out → stop there.
    probe_results = {0x33: True, 0x34: False}

    async def _probe_side_effect(request, *, timeout, retries):
        return probe_results.get(request.device_address, False)

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", side_effect=_probe_side_effect):
            caps = await client.detect()

    assert caps.lv_battery_addresses == [0x32, 0x33]


@pytest.mark.asyncio
async def test_detect_finds_meters():
    client = _make_client()
    _prime_cache(client, 0x32, {HR(0): 0x2001, HR(21): 0})

    meter_addresses = {0x01, 0x03}

    async def _probe_side_effect(request, *, timeout, retries):
        return request.device_address in meter_addresses

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", side_effect=_probe_side_effect):
            caps = await client.detect()

    assert caps.meter_addresses == [0x01, 0x03]


@pytest.mark.asyncio
async def test_detect_hv_probes_bcus():
    client = _make_client()
    # ALL_IN_ONE → is_hv=True
    _prime_cache(client, 0x32, {HR(0): 0x8000, HR(21): 0})
    # BMS at 0xA0 reports 2 BCUs via IR(61)
    _prime_cache(client, 0xA0, {IR(61): 2})
    # BCU 0 has 3 modules (IR(64)=3), BCU 1 has 2 modules
    _prime_cache(client, 0x70, {IR(64): 3})
    _prime_cache(client, 0x71, {IR(64): 2})

    bams_and_bcus = {0xA0, 0x70, 0x71}

    async def _probe_side_effect(request, *, timeout, retries):
        return request.device_address in bams_and_bcus

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", side_effect=_probe_side_effect):
            caps = await client.detect()

    assert caps.is_hv is True
    assert caps.bcu_stacks == [(0, 3), (1, 2)]
    assert caps.lv_battery_addresses == []


@pytest.mark.asyncio
async def test_detect_hv_skips_lv_battery_probing():
    client = _make_client()
    _prime_cache(client, 0x32, {HR(0): 0x8000, HR(21): 0})
    _prime_cache(client, 0xA0, {IR(61): 0})

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", new=AsyncMock(return_value=False)):
            caps = await client.detect()

    assert caps.is_hv is True
    assert caps.lv_battery_addresses == []


@pytest.mark.asyncio
async def test_detect_raises_when_hr0_missing():
    """If HR(0) is absent after reading device 0x11, detect raises CommunicationError."""
    client = _make_client()
    # Don't prime any cache — HR(0) will be absent.

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", new=AsyncMock(return_value=False)):
            with pytest.raises(CommunicationError, match="HR\\(0\\)"):
                await client.detect()
