"""Tests for Client.detect() and PlantCapabilities."""

from unittest.mock import AsyncMock, patch

import pytest

from givenergy_modbus.client.client import Client
from givenergy_modbus.exceptions import CommunicationError, PlantTopologyMismatch
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


def test_plant_capabilities_from_dict_accepts_v2_0_0_legacy_shape():
    """Regression: a v2.0.0-shaped payload must still parse after the v2.0.1 schema change.

    v2.0.0's to_dict() emitted no schema_version, used Model.value, and stored
    addresses as raw ints. v2.0.1 added schema_version=1, switched device_type
    to Model.name, and switched addresses to hex strings. Without a legacy
    parse path, a v2.0.0 → v2.0.1+ upgrade would crash with `ValueError:
    unsupported PlantCapabilities schema_version None`.

    The fixture below matches exactly what v2.0.0's `PlantCapabilities.to_dict()`
    would have produced for this configuration — captured by reading the v2.0.0
    tag's plant.py.
    """
    v2_0_0_payload = {
        "device_type": "2",  # Model.HYBRID.value, not .name
        "inverter_address": 0x32,  # integer, not hex string
        "meter_addresses": [0x01, 0x02],
        "lv_battery_addresses": [0x33, 0x34],
        "bcu_stacks": [],
    }
    caps = PlantCapabilities.from_dict(v2_0_0_payload)
    assert caps.device_type == Model.HYBRID
    assert caps.inverter_address == 0x32
    assert caps.meter_addresses == [0x01, 0x02]
    assert caps.lv_battery_addresses == [0x33, 0x34]
    assert caps.bcu_stacks == []


def test_plant_capabilities_from_dict_rejects_mismatched_schema_version():
    """A versioned payload with an unknown schema_version triggers ValueError.

    Distinct from missing-schema_version, which is now treated as v2.0.0 legacy.
    """
    with pytest.raises(ValueError, match="schema_version 99"):
        PlantCapabilities.from_dict({"schema_version": 99, "device_type": Model.HYBRID.name})


def test_plant_capabilities_from_dict_accepts_model_instance_device_type():
    """A `Model` instance passed directly is returned as-is, no string round-trip required."""
    caps = PlantCapabilities.from_dict(
        {
            "schema_version": 1,
            "device_type": Model.HYBRID_GEN1,  # Model instance, not a string
            "inverter_address": "0x32",
            "meter_addresses": [],
            "lv_battery_addresses": [],
            "bcu_stacks": [],
        }
    )
    assert caps.device_type is Model.HYBRID_GEN1


def test_plant_capabilities_from_dict_accepts_int_device_type():
    """A device_type that comes through as an unquoted int (sloppy JSON tooling) is coerced.

    `Model[v]` requires a string key, so an int input falls through to the
    value-lookup `Model(str(v))` rather than crashing with `ValueError: 2 is not
    a valid Model`. Same fallback that lets v2.0.0 string-value payloads parse.
    """
    caps = PlantCapabilities.from_dict(
        {
            "device_type": 2,  # int, not str — what unquoted JSON / sloppy YAML yields
            "inverter_address": 0x32,
            "meter_addresses": [],
            "lv_battery_addresses": [],
            "bcu_stacks": [],
        }
    )
    assert caps.device_type == Model.HYBRID


def test_plant_capabilities_from_dict_treats_null_list_fields_as_empty():
    """An explicit `null` for any of the optional list fields safely degrades to empty.

    Without the `or []` guard, `null` in JSON would surface as a `NoneType is not
    iterable` TypeError far from the parse site.
    """
    caps = PlantCapabilities.from_dict(
        {
            "schema_version": 1,
            "device_type": "HYBRID",
            "inverter_address": "0x32",
            "meter_addresses": None,
            "lv_battery_addresses": None,
            "bcu_stacks": None,
        }
    )
    assert caps.meter_addresses == []
    assert caps.lv_battery_addresses == []
    assert caps.bcu_stacks == []


def test_plant_capabilities_from_dict_coerces_bcu_stacks_ints():
    """A hand-edited payload with stringified bcu_stacks entries still loads cleanly.

    The address fields already tolerate hex-string-or-int via the `_addr()` helper, but
    `bcu_stacks` was passing entries through verbatim — strings here would only blow up
    later in `detect()` at `0x70 + offset` with `TypeError`, far from the parse site.
    Coercing to int at from_dict() time fails loud and immediately if the payload is
    malformed, and silently accepts the legitimate hand-edit case.
    """
    caps = PlantCapabilities.from_dict(
        {
            "schema_version": 1,
            "device_type": "ALL_IN_ONE",
            "inverter_address": "0x32",
            "meter_addresses": [],
            "lv_battery_addresses": [],
            "bcu_stacks": [["0", "3"], ["1", "2"]],
        }
    )
    assert caps.bcu_stacks == [(0, 3), (1, 2)]
    assert all(isinstance(o, int) and isinstance(n, int) for o, n in caps.bcu_stacks)


def test_plant_capabilities_from_dict_tolerates_legacy_key_aliases():
    """Pre-rename `*_slave(s)` keys are normalised so persisted state still loads cleanly."""
    legacy = {
        "schema_version": 1,
        "device_type": Model.HYBRID.name,
        "inverter_slave": "0x32",
        "meter_slaves": ["0x01"],
        "lv_battery_slaves": ["0x32", "0x33"],
        "bcu_slaves": [],
    }
    caps = PlantCapabilities.from_dict(legacy)
    assert caps.inverter_address == 0x32
    assert caps.meter_addresses == [0x01]
    assert caps.lv_battery_addresses == [0x32, 0x33]
    assert caps.bcu_stacks == []


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


# ---------------------------------------------------------------------------
# Client.detect(prior=...) — hinted mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_hinted_confirms_known_layout():
    """When prior matches reality, hinted detect returns equivalent caps and skips empty-slot probes."""
    client = _make_client()
    _prime_cache(client, 0x32, {HR(0): 0x2001, HR(21): 0})
    _prime_battery_serial(client, 0x32)
    _prime_battery_serial(client, 0x33)

    prior = PlantCapabilities(
        device_type=Model.HYBRID_GEN1,
        meter_addresses=[0x01],
        lv_battery_addresses=[0x32, 0x33],
    )

    confirmed = {0x01, 0x33}

    async def _probe_side_effect(request, *, timeout, retries):
        return request.device_address in confirmed

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", side_effect=_probe_side_effect) as mock_probe:
            caps = await client.detect(prior=prior)

    assert caps == prior
    # Only the hinted meter (0x01) and battery (0x33) get probed — not the full 0x01–0x08 / 0x32–0x37 sweep.
    probed = [call.args[0].device_address for call in mock_probe.call_args_list]
    assert probed == [0x01, 0x33]


@pytest.mark.asyncio
async def test_detect_hinted_raises_on_device_type_change():
    """If the inverter reports a different device_type than prior, raise and clear plant.capabilities."""
    client = _make_client()
    # Hardware now reports HYBRID_GEN1 (DTC 0x2001, arm_fw=0)
    _prime_cache(client, 0x32, {HR(0): 0x2001, HR(21): 0})
    # Caller's prior says ALL_IN_ONE_HYBRID — a different family entirely.
    prior = PlantCapabilities(device_type=Model.ALL_IN_ONE_HYBRID)

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", new=AsyncMock(return_value=False)):
            with pytest.raises(PlantTopologyMismatch) as exc_info:
                await client.detect(prior=prior)

    assert exc_info.value.prior is prior
    assert exc_info.value.actual.device_type == Model.HYBRID_GEN1
    assert client.plant.capabilities is None


@pytest.mark.asyncio
async def test_detect_hinted_raises_when_hinted_address_missing():
    """If a hinted meter doesn't confirm, raise PlantTopologyMismatch carrying both views."""
    client = _make_client()
    _prime_cache(client, 0x32, {HR(0): 0x2001, HR(21): 0})
    _prime_battery_serial(client, 0x32)

    prior = PlantCapabilities(
        device_type=Model.HYBRID_GEN1,
        meter_addresses=[0x01, 0x02],
        lv_battery_addresses=[0x32],
    )

    # 0x01 confirms, 0x02 doesn't.
    async def _probe_side_effect(request, *, timeout, retries):
        return request.device_address == 0x01

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", side_effect=_probe_side_effect):
            with pytest.raises(PlantTopologyMismatch) as exc_info:
                await client.detect(prior=prior)

    assert exc_info.value.prior is prior
    assert exc_info.value.actual.meter_addresses == [0x01]
    assert client.plant.capabilities is None


@pytest.mark.asyncio
async def test_detect_hinted_hv_skips_bms_read():
    """Hinted HV mode probes the BCUs (skipping BMS at 0xA0) and reads actual module counts."""
    client = _make_client()
    _prime_cache(client, 0x32, {HR(0): 0x8000, HR(21): 0})
    # Crucially: no cache primed at 0xA0 — if hinted mode tries to read it, it'll fail downstream.
    # Prime each BCU's IR(64) so the actual-module read returns the expected count.
    _prime_cache(client, 0x70, {IR(64): 3})
    _prime_cache(client, 0x71, {IR(64): 2})

    prior = PlantCapabilities(
        device_type=Model.ALL_IN_ONE,
        bcu_stacks=[(0, 3), (1, 2)],
    )

    # Only the BCUs themselves confirm; BMS at 0xA0 isn't queried.
    confirmed_bcus = {0x70, 0x71}

    async def _probe_side_effect(request, *, timeout, retries):
        assert request.device_address != 0xA0, "hinted mode must not probe the BMS"
        return request.device_address in confirmed_bcus

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", side_effect=_probe_side_effect):
            caps = await client.detect(prior=prior)

    assert caps.bcu_stacks == [(0, 3), (1, 2)]


@pytest.mark.asyncio
async def test_detect_hinted_raises_on_bcu_module_count_drift():
    """If a BCU now reports a different module count than prior, the final topology check raises."""
    client = _make_client()
    _prime_cache(client, 0x32, {HR(0): 0x8000, HR(21): 0})
    # Stack 0 originally had 3 modules; it now reports 2 (a module was removed).
    _prime_cache(client, 0x70, {IR(64): 2})
    _prime_cache(client, 0x71, {IR(64): 2})

    prior = PlantCapabilities(
        device_type=Model.ALL_IN_ONE,
        bcu_stacks=[(0, 3), (1, 2)],
    )

    async def _probe_side_effect(request, *, timeout, retries):
        return request.device_address in {0x70, 0x71}

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", side_effect=_probe_side_effect):
            with pytest.raises(PlantTopologyMismatch) as exc_info:
                await client.detect(prior=prior)

    assert exc_info.value.prior.bcu_stacks == [(0, 3), (1, 2)]
    assert exc_info.value.actual.bcu_stacks == [(0, 2), (1, 2)]
