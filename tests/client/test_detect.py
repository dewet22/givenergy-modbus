"""Tests for Client.detect() and PlantCapabilities."""

from unittest.mock import AsyncMock, MagicMock, patch

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


def test_plant_capabilities_round_trip_with_aio_modules():
    caps = PlantCapabilities(
        device_type=Model.ALL_IN_ONE,
        inverter_address=0x11,
        bcu_stacks=[(0, 4)],
        aio_battery_module_addresses=[0x50, 0x51, 0x52, 0x53],
    )
    restored = PlantCapabilities.from_dict(caps.to_dict())
    assert restored == caps
    assert restored.aio_battery_module_addresses == [0x50, 0x51, 0x52, 0x53]


def test_plant_capabilities_round_trip_with_hv_bmu_modules():
    caps = PlantCapabilities(
        device_type=Model.HYBRID_HV_GEN3,
        inverter_address=0x11,
        bcu_stacks=[(0, 2)],
        hv_bmu_addresses=[0x50, 0x51],
    )
    restored = PlantCapabilities.from_dict(caps.to_dict())
    assert restored == caps
    assert restored.hv_bmu_addresses == [0x50, 0x51]


def test_plant_capabilities_round_trip_with_lv_bcu():
    caps = PlantCapabilities(
        device_type=Model.HYBRID,
        inverter_address=0x11,
        lv_battery_addresses=[0x32, 0x33],
        lv_bcu_address=0x31,
    )
    assert caps.to_dict()["lv_bcu_address"] == "0x31"
    restored = PlantCapabilities.from_dict(caps.to_dict())
    assert restored == caps
    assert restored.lv_bcu_address == 0x31


def test_plant_capabilities_lv_bcu_defaults_none_and_survives_round_trip():
    """Payloads persisted before the field existed must load with lv_bcu_address=None."""
    caps = PlantCapabilities(device_type=Model.HYBRID)
    assert caps.lv_bcu_address is None
    payload = caps.to_dict()
    assert payload["lv_bcu_address"] is None
    assert PlantCapabilities.from_dict(payload).lv_bcu_address is None
    # Pre-field payload shape (no key at all):
    del payload["lv_bcu_address"]
    assert PlantCapabilities.from_dict(payload).lv_bcu_address is None


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


def test_plant_capabilities_derives_inverter_address_from_model():
    """Without an explicit address, inverter_address derives from the model (issue #119)."""
    assert PlantCapabilities(device_type=Model.HYBRID).inverter_address == 0x11
    assert PlantCapabilities(device_type=Model.EMS).inverter_address == 0x11
    assert PlantCapabilities(device_type=Model.ALL_IN_ONE).inverter_address == 0x11
    assert PlantCapabilities(device_type=Model.AC).inverter_address == 0x11
    assert PlantCapabilities(device_type=Model.HYBRID_GEN1).inverter_address == 0x11


def test_plant_capabilities_explicit_address_overrides_derivation():
    """An explicitly supplied address always wins over the model-derived default.

    This is what lets a persisted pre-#119 capability (inverter_address=0x32) round-trip
    through from_dict() unchanged, surfacing as a PlantTopologyMismatch on the next detect()
    rather than being silently rewritten.
    """
    assert PlantCapabilities(device_type=Model.ALL_IN_ONE, inverter_address=0x32).inverter_address == 0x32
    persisted = {
        "schema_version": 1,
        "device_type": "ALL_IN_ONE",
        "inverter_address": "0x32",
        "meter_addresses": [],
        "lv_battery_addresses": [],
        "bcu_stacks": [],
    }
    assert PlantCapabilities.from_dict(persisted).inverter_address == 0x32


# ---------------------------------------------------------------------------
# Client.detect()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_resolves_model_from_hr0_hr21():
    client = _make_client()
    # DTC 0x2001 → "2001" prefix "20", arm_fw=300 → century 3 → HYBRID_GEN3
    _prime_cache(client, 0x11, {HR(0): 0x2001, HR(21): 300})

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


def _prime_meter_voltage(client: Client, device_address: int, raw_v_phase_1: int = 2386) -> None:
    """Prime a device cache so Meter.is_valid() returns True.

    is_valid() checks v_phase_1 = IR(60), expecting a non-zero deci-volt reading.
    Default 2386 = 238.6 V (typical UK domestic mains, taken from the wire capture in #86).
    """
    _prime_cache(client, device_address, {IR(60): raw_v_phase_1})


def _pack_serial_into_registers(serial: str, base: int) -> dict:
    """Pack a 10-char serial string into 5 consecutive 16-bit IR registers at `base`.

    Mirrors how the EMS rollup encodes per-inverter serial strings in IR(2066..2070)
    etc. Used to prime register caches for the EMS rollup cross-check tests.
    """
    assert len(serial) == 10, f"GE serials are 10 chars, got {len(serial)}: {serial!r}"
    return {IR(base + i): (ord(serial[i * 2]) << 8) | ord(serial[i * 2 + 1]) for i in range(5)}


def _prime_ems_rollup(
    client: Client,
    inverter_count: int = 2,
    serials: tuple[str, ...] = ("CE0000G000", "CE0000G000"),
    meter_count: int = 2,
) -> None:
    """Prime IR(2040+) on the EMS cache with a plausible rollup payload.

    Mirrors a real EMS plant: status NORMAL, the given inverter and meter counts,
    serials packed into their canonical register slots. `serials` is a tuple of up
    to four 10-char strings; each is packed into 5 consecutive IR registers
    starting at IR(2066) for inverter_1, IR(2071) for inverter_2, etc.
    """
    rollup = {
        IR(2040): 1,  # ems_status = NORMAL
        IR(2041): meter_count,
        IR(2044): inverter_count,
    }
    for slot, serial in enumerate(serials):
        rollup.update(_pack_serial_into_registers(serial, 2066 + slot * 5))
    # EMS serves all its data, including the IR(2040+) rollup, at 0x11 (issue #119).
    _prime_cache(client, 0x11, rollup)


@pytest.mark.asyncio
async def test_detect_no_peripherals_returns_empty_lists():
    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x2001, HR(21): 0})
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
    _prime_cache(client, 0x11, {HR(0): 0x2001, HR(21): 0})
    # Battery pack #1 is at 0x32, #2 at 0x33 (the inverter is at 0x11 — issue #119).
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
async def test_detect_enumerates_battery_held_on_first_frame():
    """detect() must enumerate a battery whose first probe is cold-start-held (#233/#289).

    The #289 cold-start guard holds the first bank against an empty cache (the cache stays empty,
    pending a corroborating re-read). detect() probes each address once, so without a confirming
    read the address is dropped at the ``register_caches`` gate and refresh() never re-polls it — a
    permanent hold for a recovered/returned pack (hass#233). The confirming re-read corroborates a
    healthy bank so the returned battery re-enumerates within a single detect pass.

    Unlike test_detect_finds_lv_batteries, this drives the response through the REAL guard via
    plant.update() rather than pre-priming the cache — that is what exercises the cold-start hold.
    """
    from tests.model.test_plant import _coherent_battery_bank, _make_ir_pdu

    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x2001, HR(21): 0})
    _prime_battery_serial(client, 0x32)  # primary pack commits first-read via the inverter getter
    probes: list[int] = []

    async def _probe_side_effect(request, *, timeout, retries):
        addr = request.device_address
        if addr != 0x33:
            return False
        probes.append(addr)
        # First call: the guard holds it (cache stays empty). The confirming re-read feeds the same
        # healthy bank, which corroborates and commits.
        client.plant.update(
            _make_ir_pdu(_coherent_battery_bank(), device_address=0x33, base_register=60, register_count=60)
        )
        return True

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", side_effect=_probe_side_effect):
            caps = await client.detect()

    assert 0x33 in caps.lv_battery_addresses, "a cold-start-held battery must still be enumerated"
    assert probes.count(0x33) == 2, "detect must issue one confirming re-read when the first frame is held"


@pytest.mark.asyncio
async def test_detect_does_not_enumerate_flapping_battery():
    """A battery that responds but never corroborates is NOT enumerated (#289 safety at detect layer).

    The confirming re-read must not enumerate a pack whose two reads disagree by >=2 physics-impossible
    deltas (a sub-bus splice / flapping BMS) — it stays held with an empty cache, exactly as a transient
    splice should.
    """
    from tests.model.test_plant import _coherent_battery_bank, _make_ir_pdu

    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x2001, HR(21): 0})
    _prime_battery_serial(client, 0x32)
    # Two disagreeing reads: healthy, then the temp-zero corruption cohort (4 temps 250→0 = >=2 physics).
    banks = [_coherent_battery_bank(), _coherent_battery_bank({76 + i: 0 for i in range(4)})]
    calls = {"n": 0}

    async def _probe_side_effect(request, *, timeout, retries):
        if request.device_address != 0x33:
            return False
        bank = banks[min(calls["n"], len(banks) - 1)]
        calls["n"] += 1
        client.plant.update(_make_ir_pdu(bank, device_address=0x33, base_register=60, register_count=60))
        return True

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", side_effect=_probe_side_effect):
            caps = await client.detect()

    assert 0x33 not in caps.lv_battery_addresses, "a flapping/uncorroborated battery must not enumerate"


async def test_detect_finds_lv_bcu():
    """A populated BCU block at 0x31 sets lv_bcu_address (#241)."""
    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x2001, HR(21): 0})
    _prime_battery_serial(client, 0x32)
    # The field-observed BCU shape: status words zero, request currents 167/167.
    _prime_cache(client, 0x31, {IR(60): 0, IR(61): 0, IR(62): 167, IR(63): 167})

    async def _probe_side_effect(request, *, timeout, retries):
        return request.device_address == 0x31

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", side_effect=_probe_side_effect):
            caps = await client.detect()

    assert caps.lv_bcu_address == 0x31


async def test_detect_all_zero_lv_bcu_block_means_absent():
    """An all-zero block at 0x31 leaves lv_bcu_address=None (firmware-gated, #241).

    Units without the block still answer the probe — with zeros — so the probe
    succeeding is necessary but not sufficient.
    """
    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x2001, HR(21): 0})
    _prime_battery_serial(client, 0x32)
    _prime_cache(client, 0x31, {IR(60): 0, IR(61): 0, IR(62): 0, IR(63): 0})

    async def _probe_side_effect(request, *, timeout, retries):
        return request.device_address == 0x31

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", side_effect=_probe_side_effect):
            caps = await client.detect()

    assert caps.lv_bcu_address is None


async def test_detect_hinted_reconfirms_lv_bcu():
    """Hinted mode re-probes a prior lv_bcu_address and keeps it when still valid."""
    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x2001, HR(21): 0})
    _prime_battery_serial(client, 0x32)
    _prime_cache(client, 0x31, {IR(60): 0, IR(61): 0, IR(62): 167, IR(63): 167})
    prior = PlantCapabilities(device_type=Model.HYBRID_GEN1, lv_battery_addresses=[0x32], lv_bcu_address=0x31)

    async def _probe_side_effect(request, *, timeout, retries):
        return request.device_address == 0x31

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", side_effect=_probe_side_effect):
            caps = await client.detect(prior=prior)

    assert caps.lv_bcu_address == 0x31


async def test_detect_hinted_absent_lv_bcu_skips_probe():
    """Hinted mode trusts a prior None — no 0x31 probe is dispatched.

    Follows the meter convention: hinted detect only re-checks addresses the
    prior captured, so a firmware upgrade that adds the block needs a cold
    detect to notice.
    """
    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x2001, HR(21): 0})
    _prime_battery_serial(client, 0x32)
    prior = PlantCapabilities(device_type=Model.HYBRID_GEN1, lv_battery_addresses=[0x32])

    probed_addresses = []

    async def _probe_side_effect(request, *, timeout, retries):
        probed_addresses.append(request.device_address)
        return False

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", side_effect=_probe_side_effect):
            caps = await client.detect(prior=prior)

    assert caps.lv_bcu_address is None
    assert 0x31 not in probed_addresses


@pytest.mark.asyncio
async def test_detect_lv_bcu_probe_succeeds_but_cache_absent():
    """Probe returns True but no data landed in the cache — gracefully leaves lv_bcu_address=None."""
    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x2001, HR(21): 0})
    _prime_battery_serial(client, 0x32)
    # No cache at 0x31 — probe "succeeds" but no registers were stored.

    async def _probe_succeed_at_0x31(request, *, timeout, retries):
        return request.device_address == 0x31

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", side_effect=_probe_succeed_at_0x31):
            caps = await client.detect()

    assert caps.lv_bcu_address is None


@pytest.mark.asyncio
async def test_detect_lv_bcu_decode_error_is_swallowed():
    """A decoding error in the BCU probe is logged and leaves lv_bcu_address=None."""
    from unittest.mock import patch as _patch

    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x2001, HR(21): 0})
    _prime_battery_serial(client, 0x32)
    _prime_cache(client, 0x31, {IR(60): 1, IR(61): 0, IR(62): 0, IR(63): 0})

    async def _probe_succeed_at_0x31(request, *, timeout, retries):
        return request.device_address == 0x31

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", side_effect=_probe_succeed_at_0x31):
            with _patch("givenergy_modbus.model.plant.LvBcu.from_register_cache", side_effect=ValueError("corrupt")):
                caps = await client.detect()

    assert caps.lv_bcu_address is None


def _prime_aio_module_serial(client: Client, device_address: int, serial: str = "HX2414G832") -> None:
    """Prime an AIO module cache with a valid module serial (IR 114-118)."""
    regs = {IR(114 + i): int.from_bytes(serial[i * 2 : i * 2 + 2].encode("latin1"), "big") for i in range(5)}
    _prime_cache(client, device_address, regs)


@pytest.mark.asyncio
async def test_detect_finds_aio_battery_modules():
    """An AIO with a 4-module BCU records its per-module addresses at 0x50-0x53 (#192)."""
    client = _make_client()
    # DTC 0x8001 + fw 612 → Model.ALL_IN_ONE (HV, single-phase).
    _prime_cache(client, 0x11, {HR(0): 0x8001, HR(21): 612})
    # BMS at 0xA0 reports 1 BCU; BCU at 0x70 reports 4 modules.
    _prime_cache(client, 0xA0, {IR(61): 1})
    _prime_cache(client, 0x70, {IR(64): 4})
    for addr in (0x50, 0x51, 0x52, 0x53):
        _prime_aio_module_serial(client, addr, serial=f"HX2414G83{addr - 0x50}")

    responders = {0xA0, 0x70, 0x50, 0x51, 0x52, 0x53}

    async def _probe_side_effect(request, *, timeout, retries):
        return request.device_address in responders

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", side_effect=_probe_side_effect):
            caps = await client.detect()

    assert caps.device_type is Model.ALL_IN_ONE
    assert caps.bcu_stacks == [(0, 4)]
    assert caps.aio_battery_module_addresses == [0x50, 0x51, 0x52, 0x53]
    # AIO modules must not also be detected via the HV BMU path — that's gated to non-AIO (#265).
    assert caps.hv_bmu_addresses == []


@pytest.mark.asyncio
async def test_detect_aio_skips_modules_with_no_serial():
    """An AIO module that responds but has no serial is not recorded (ghost guard)."""
    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x8001, HR(21): 612})
    _prime_cache(client, 0xA0, {IR(61): 1})
    _prime_cache(client, 0x70, {IR(64): 2})
    _prime_aio_module_serial(client, 0x50)  # 0x51 responds but has no serial primed

    responders = {0xA0, 0x70, 0x50, 0x51}

    async def _probe_side_effect(request, *, timeout, retries):
        return request.device_address in responders

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", side_effect=_probe_side_effect):
            caps = await client.detect()

    assert caps.aio_battery_module_addresses == [0x50]


@pytest.mark.asyncio
async def test_detect_aio_module_decode_error_skips_address(monkeypatch):
    """A ValidationError during AIO module decode skips the address without crashing detect()."""
    from givenergy_modbus.model.aio_battery import AioBatteryModule

    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x8001, HR(21): 612})
    _prime_cache(client, 0xA0, {IR(61): 1})
    _prime_cache(client, 0x70, {IR(64): 1})
    _prime_aio_module_serial(client, 0x50)

    def _raise(cache, addr):
        raise ValueError("simulated decode failure")

    monkeypatch.setattr(AioBatteryModule, "from_register_cache", staticmethod(_raise))

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", new=AsyncMock(return_value=True)):
            caps = await client.detect()

    assert caps.aio_battery_module_addresses == []
    assert client.plant.block_present(0x50, "IR", 60, 60) is False  # decode exception → ABSENT


@pytest.mark.asyncio
async def test_detect_aio_hinted_probes_only_prior_addresses():
    """Hinted detect() for AIO modules sweeps only the prior addresses, not a fresh BCU count.

    If prior has [0x50, 0x51] but the BCU now reports 4 modules, the hinted pass must
    probe only 0x50 and 0x51 — consistent with the confirm-only contract for meters and
    batteries.
    """
    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x8001, HR(21): 612})
    # BCU now reports 4 modules, but prior only knew about 2.
    _prime_cache(client, 0x70, {IR(64): 4})
    for addr in (0x50, 0x51):
        _prime_aio_module_serial(client, addr, serial=f"HX2414G83{addr - 0x50}")
    # 0x52 and 0x53 are present on hardware but were not in prior.
    for addr in (0x52, 0x53):
        _prime_aio_module_serial(client, addr, serial=f"HX2414G83{addr - 0x50}")

    prior = PlantCapabilities(
        device_type=Model.ALL_IN_ONE,
        inverter_address=0x11,
        bcu_stacks=[(0, 2)],
        aio_battery_module_addresses=[0x50, 0x51],
    )
    probed: list[int] = []

    async def _probe_side_effect(request, *, timeout, retries):
        probed.append(request.device_address)
        return True

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", side_effect=_probe_side_effect):
            from givenergy_modbus.exceptions import PlantTopologyMismatch

            try:
                await client.detect(prior=prior)
            except PlantTopologyMismatch:
                pass  # topology changed (BCU count 2→4) — that's expected; we only care what was probed

    aio_probed = [a for a in probed if 0x50 <= a <= 0x53]
    assert aio_probed == [0x50, 0x51], f"hinted AIO sweep must not probe 0x52/0x53; got {aio_probed}"


@pytest.mark.asyncio
async def test_detect_aio_cold_clamps_module_count_to_max():
    """Cold detect() clamps a corrupt/large BCU module count to _AIO_MAX_MODULES (4)."""
    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x8001, HR(21): 612})
    _prime_cache(client, 0xA0, {IR(61): 1})
    # BCU reports 6 modules — should be clamped to 4.
    _prime_cache(client, 0x70, {IR(64): 6})
    for addr in range(0x50, 0x56):
        _prime_aio_module_serial(client, addr, serial=f"HX2414G8{addr:02x}")

    probed: list[int] = []

    async def _probe_side_effect(request, *, timeout, retries):
        probed.append(request.device_address)
        return True

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", side_effect=_probe_side_effect):
            caps = await client.detect()

    aio_probed = [a for a in probed if 0x50 <= a <= 0x5F]
    assert all(a <= 0x53 for a in aio_probed), f"must not probe beyond 0x53; got {aio_probed}"
    assert len(caps.aio_battery_module_addresses) <= 4


@pytest.mark.asyncio
async def test_detect_battery_decode_value_error_stops_probe(monkeypatch):
    """A battery register-decode ValueError stops the probe rather than propagating.

    An out-of-range enum value while decoding a battery must be swallowed and treated
    as "no valid battery" — it must not propagate out of detect().
    """
    from givenergy_modbus.model.battery import Battery

    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x2001, HR(21): 0})
    _prime_battery_serial(client, 0x32)  # battery #1 present at 0x32

    def _raise(cache):
        raise ValueError("11 is not a valid BatteryState")

    monkeypatch.setattr(Battery, "from_register_cache", staticmethod(_raise))

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", new=AsyncMock(return_value=False)):
            caps = await client.detect()

    # The decode error at 0x32 is treated as "no valid battery" — probe stops, no raise.
    assert caps.lv_battery_addresses == []


@pytest.mark.asyncio
async def test_detect_finds_meters():
    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x2001, HR(21): 0})
    # Prime IR(60) on the responding meters so Meter.is_valid() passes.
    _prime_meter_voltage(client, 0x01)
    _prime_meter_voltage(client, 0x03)

    meter_addresses = {0x01, 0x03}

    async def _probe_side_effect(request, *, timeout, retries):
        return request.device_address in meter_addresses

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", side_effect=_probe_side_effect):
            caps = await client.detect()

    assert caps.meter_addresses == [0x01, 0x03]


@pytest.mark.asyncio
async def test_detect_cold_filters_empty_meter_slots():
    """EMS firmwares can ACK every slot in 0x01..0x08 even when no meter is wired.

    Real meters report a non-zero v_phase_1; empty slots ACK but report zeros. The
    filter should drop the empty slots so they don't end up as ghost Meter objects
    in plant.meters. Regression: #95 item 1 (wire evidence in #86).
    """
    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x2001, HR(21): 0})
    # Real meters at 0x01 and 0x03 (mirrors Nick's grid + load CTs).
    _prime_meter_voltage(client, 0x01)
    _prime_meter_voltage(client, 0x03)
    # Empty-but-ACK'd slots at 0x07 and 0x08 — primed with zeros explicitly.
    _prime_cache(client, 0x07, {IR(60): 0})
    _prime_cache(client, 0x08, {IR(60): 0})

    # All four addresses respond to the probe; only the valid pair survives the filter.
    responding = {0x01, 0x03, 0x07, 0x08}

    async def _probe_side_effect(request, *, timeout, retries):
        return request.device_address in responding

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", side_effect=_probe_side_effect):
            caps = await client.detect()

    assert caps.meter_addresses == [0x01, 0x03]


@pytest.mark.asyncio
async def test_detect_cold_handles_non_contiguous_meters():
    """The meter filter is per-slot, not break-on-fail.

    Meters can be non-contiguous (Nick's installation has 0x01 and 0x03 populated
    with 0x02 absent). A real meter following an empty slot must still be discovered.
    """
    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x2001, HR(21): 0})
    # Real meters at 0x01 and 0x05 — non-contiguous.
    _prime_meter_voltage(client, 0x01)
    _prime_meter_voltage(client, 0x05)
    # Empty-but-ACK'd at 0x06–0x08.
    for addr in (0x06, 0x07, 0x08):
        _prime_cache(client, addr, {IR(60): 0})

    # 0x02–0x04 don't respond at all; 0x01, 0x05, 0x06, 0x07, 0x08 all ACK.
    responding = {0x01, 0x05, 0x06, 0x07, 0x08}

    async def _probe_side_effect(request, *, timeout, retries):
        return request.device_address in responding

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", side_effect=_probe_side_effect):
            caps = await client.detect()

    assert caps.meter_addresses == [0x01, 0x05]


@pytest.mark.asyncio
async def test_detect_hinted_drops_ghost_meter_with_mismatch():
    """Prior caps carrying a ghost address get cleaned up on next hinted detect.

    Migration path for any user whose persisted prior was captured before #95
    landed — the empty slot drops out of caps and PlantTopologyMismatch is raised,
    which the consumer (givenergy-hass#62) auto-accepts and re-persists.
    """
    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x2001, HR(21): 0})
    _prime_battery_serial(client, 0x32)
    _prime_meter_voltage(client, 0x01)
    _prime_meter_voltage(client, 0x03)
    # 0x07 is the ghost: cached, probes ACK, but v_phase_1 = 0.
    _prime_cache(client, 0x07, {IR(60): 0})

    prior = PlantCapabilities(
        device_type=Model.HYBRID_GEN1,
        meter_addresses=[0x01, 0x03, 0x07],
        lv_battery_addresses=[0x32],
    )

    # All hinted meter addresses respond to the probe.
    async def _probe_side_effect(request, *, timeout, retries):
        return request.device_address in {0x01, 0x03, 0x07}

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", side_effect=_probe_side_effect):
            with pytest.raises(PlantTopologyMismatch) as exc_info:
                await client.detect(prior=prior)

    assert exc_info.value.prior is prior
    assert exc_info.value.actual.meter_addresses == [0x01, 0x03]
    assert client.plant.capabilities is None


@pytest.mark.asyncio
async def test_detect_hinted_drops_meter_with_transient_zero_voltage():
    """A previously-valid meter reading v_phase_1=0 at the instant of hinted detect is dropped.

    This is the trade-off documented in the design discussion for #95: a real meter
    that has lost AC reference (e.g. warm restart during a grid outage) will fail
    is_valid() at detect time. We deliberately surface this as PlantTopologyMismatch
    rather than carrying the meter through with a transient zero — symmetry with the
    Battery path, and the consumer (givenergy-hass#62) handles the auto-accept and
    advisory Repairs note. Documented as a test so the choice is visible to future
    readers rather than buried in commit history.
    """
    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x2001, HR(21): 0})
    _prime_battery_serial(client, 0x32)
    # 0x01 probes ACK but v_phase_1 == 0 — the transient-zero case.
    _prime_cache(client, 0x01, {IR(60): 0})

    prior = PlantCapabilities(
        device_type=Model.HYBRID_GEN1,
        meter_addresses=[0x01],
        lv_battery_addresses=[0x32],
    )

    async def _probe_side_effect(request, *, timeout, retries):
        return request.device_address == 0x01

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", side_effect=_probe_side_effect):
            with pytest.raises(PlantTopologyMismatch) as exc_info:
                await client.detect(prior=prior)

    assert exc_info.value.prior is prior
    assert exc_info.value.actual.meter_addresses == []
    assert client.plant.capabilities is None


@pytest.mark.asyncio
async def test_detect_hv_probes_bcus():
    client = _make_client()
    # ALL_IN_ONE → is_hv=True
    _prime_cache(client, 0x11, {HR(0): 0x8000, HR(21): 0})
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
async def test_detect_bcu_stacks_bms_timeout_marks_absent():
    """Cold path BMS probe timeout stamps 0xA0 IR(60,5) ABSENT."""
    client = _make_client()
    caps = PlantCapabilities(device_type=Model.ALL_IN_ONE, inverter_address=0x11)
    with patch.object(client, "_probe", new=AsyncMock(return_value=False)):
        await client._detect_bcu_stacks(caps, None, 1.0, 1)
    assert caps.bcu_stacks == []
    assert client.plant.block_present(0xA0, "IR", 60, 5) is False


@pytest.mark.asyncio
async def test_detect_bcu_stacks_cold_bcu_timeout_marks_absent():
    """Cold path: a BCU probe timeout stamps that BCU address ABSENT."""
    client = _make_client()
    _prime_cache(client, 0xA0, {IR(61): 2})
    _prime_cache(client, 0x70, {IR(64): 3})
    caps = PlantCapabilities(device_type=Model.ALL_IN_ONE, inverter_address=0x11)

    async def _probe_side_effect(request, *, timeout, retries):
        return request.device_address != 0x71

    with patch.object(client, "_probe", side_effect=_probe_side_effect):
        await client._detect_bcu_stacks(caps, None, 1.0, 1)

    assert caps.bcu_stacks[0][0] == 0
    assert client.plant.block_present(0x71, "IR", 60, 60) is False


@pytest.mark.asyncio
async def test_detect_bcu_stacks_hinted_bcu_timeout_marks_absent():
    """Hinted path: a BCU probe timeout stamps that BCU address ABSENT."""
    client = _make_client()
    _prime_cache(client, 0x70, {IR(64): 3})
    caps = PlantCapabilities(device_type=Model.ALL_IN_ONE, inverter_address=0x11)
    prior = PlantCapabilities(device_type=Model.ALL_IN_ONE, bcu_stacks=[(0, 3), (1, 2)])

    async def _probe_side_effect(request, *, timeout, retries):
        return request.device_address == 0x70

    with patch.object(client, "_probe", side_effect=_probe_side_effect):
        await client._detect_bcu_stacks(caps, prior, 1.0, 1)

    assert caps.bcu_stacks == [(0, 3)]
    assert client.plant.block_present(0x71, "IR", 60, 5) is False


@pytest.mark.asyncio
async def test_detect_hv_skips_lv_battery_probing():
    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x8000, HR(21): 0})
    _prime_cache(client, 0xA0, {IR(61): 0})

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", new=AsyncMock(return_value=False)):
            caps = await client.detect()

    assert caps.is_hv is True
    assert caps.lv_battery_addresses == []


@pytest.mark.asyncio
async def test_detect_ems_skips_lv_battery_probing():
    """EMS plant controllers skip the LV battery probe.

    They don't expose IR at the inverter address — the unconditional read at
    IR(60,60) on 0x32 would time out every detect(). See #86.
    """
    client = _make_client()
    # DTC 0x5001 → Model.EMS (first-digit prefix "5")
    _prime_cache(client, 0x11, {HR(0): 0x5001, HR(21): 0})
    # Prime a plausible EMS rollup so the cross-check at the end of detect() is happy.
    _prime_ems_rollup(client)

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock) as mock_send:
        with patch.object(client, "_probe", new=AsyncMock(return_value=False)):
            caps = await client.detect()

    assert caps.is_ems is True
    assert caps.lv_battery_addresses == []
    # No IR(60,60) at 0x32 — the LV battery probe is skipped for EMS.
    sent = [call.args[0] for call in mock_send.call_args_list]
    assert not any(req.device_address == 0x32 for req in sent), (
        f"detect() should not read from 0x32 for EMS; got {sent}"
    )


@pytest.mark.asyncio
async def test_detect_ems_reads_rollup_at_detect_time():
    """EMS detect issues an IR(2040,55) read to populate the rollup early.

    Consumers don't need to wait for the first refresh cycle to see the per-managed-
    inverter and per-meter rollup data.
    """
    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x5001, HR(21): 0})
    _prime_ems_rollup(client)

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock) as mock_send:
        with patch.object(client, "_probe", new=AsyncMock(return_value=False)):
            await client.detect()

    sent = [call.args[0] for call in mock_send.call_args_list]
    rollup_reads = [
        req for req in sent if req.base_register == 2040 and req.register_count == 55 and req.device_address == 0x11
    ]
    assert len(rollup_reads) == 1, f"expected exactly one IR(2040,55) at 0x11; got {sent}"


@pytest.mark.asyncio
async def test_detect_ems_warns_on_implausible_inverter_count(caplog):
    """If the rollup decodes with inverter_count outside [1, 4], log a warning rather than raise."""
    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x5001, HR(21): 0})
    # IR(2040) signals the rollup actually populated; without it the validator
    # short-circuits on the "no rollup data" path before reaching inverter_count.
    _prime_cache(client, 0x11, {IR(2040): 1, IR(2044): 7})  # ems_status NORMAL, inverter_count = 7 — implausible

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", new=AsyncMock(return_value=False)):
            with caplog.at_level("WARNING", logger="givenergy_modbus.client.client"):
                await client.detect()

    assert any(
        "implausible inverter_count" in rec.message and "inverter_count=7" in rec.message for rec in caplog.records
    ), f"expected implausible-inverter_count warning; got {[r.message for r in caplog.records]}"


@pytest.mark.asyncio
async def test_detect_ems_tolerates_rollup_read_timeout(caplog):
    """A timeout on the IR(2040,55) read is logged and detect() still returns caps.

    The cross-check is documented as best-effort end-to-end — the read itself
    needs to be wrapped, otherwise `send_request_and_await_response` would
    raise `TimeoutError` before the validation helper ever ran. See #109 review.
    """
    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x5001, HR(21): 0})

    async def _send_or_timeout(request, *, timeout, retries):
        if request.base_register == 2040 and request.register_count == 55:
            raise TimeoutError

    with patch.object(client, "send_request_and_await_response", side_effect=_send_or_timeout):
        with patch.object(client, "_probe", new=AsyncMock(return_value=False)):
            with caplog.at_level("WARNING", logger="givenergy_modbus.client.client"):
                caps = await client.detect()

    assert caps.is_ems is True  # detection still succeeded despite the rollup timing out
    assert any("EMS rollup read at IR(2040,55) timed out" in rec.message for rec in caplog.records), (
        f"expected timeout warning; got {[r.message for r in caplog.records]}"
    )


@pytest.mark.asyncio
async def test_detect_ems_warns_on_missing_rollup_registers(caplog):
    """If the cache at 0x11 has HR data but no IR rollup registers, log and continue.

    Realistic shape — Step 1's HR(0,60) always populates the cache for 0x11, so the
    "cache is None" branch is unreachable at runtime. The actual failure mode is the
    rollup read silently returning no IR data: the cache exists but IR(2040+) is
    absent, in which case the defaultdict-shaped `RegisterCache` would otherwise
    decode missing keys as 0 and produce a misleading "implausible inverter_count=0"
    warning.
    """
    client = _make_client()
    # HR(0)/(21) prime the EMS resolution; we deliberately don't prime IR(2040+) to
    # simulate the rollup read happening but yielding no data into the cache.
    _prime_cache(client, 0x11, {HR(0): 0x5001, HR(21): 0})

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", new=AsyncMock(return_value=False)):
            with caplog.at_level("WARNING", logger="givenergy_modbus.client.client"):
                await client.detect()

    assert any("returned no data at 0x11" in rec.message for rec in caplog.records), (
        f"expected no-data warning; got {[r.message for r in caplog.records]}"
    )
    # Specifically should NOT log the implausible-count message — the early-out
    # catches the missing-rollup case before reaching that branch.
    assert not any("implausible inverter_count" in rec.message for rec in caplog.records), (
        f"unexpected implausible-count warning: {[r.message for r in caplog.records]}"
    )


@pytest.mark.asyncio
async def test_detect_ems_warns_on_rollup_decode_failure(caplog):
    """A decode exception during the rollup parse is caught and logged, not raised."""
    client = _make_client()
    # IR(2040) signals the rollup populated; without it the validator short-circuits
    # before reaching EmsRegisterGetter.build() and the patched failure never fires.
    _prime_cache(client, 0x11, {HR(0): 0x5001, HR(21): 0, IR(2040): 1})

    # Force EmsRegisterGetter(...).build() to raise — simulates a parser regression.
    with patch("givenergy_modbus.client.client.EmsRegisterGetter") as MockGetter:
        MockGetter.return_value.build.side_effect = RuntimeError("simulated decode failure")
        with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
            with patch.object(client, "_probe", new=AsyncMock(return_value=False)):
                with caplog.at_level("WARNING", logger="givenergy_modbus.client.client"):
                    await client.detect()

    assert any(
        "rollup decode failed" in rec.message and "simulated decode failure" in rec.message for rec in caplog.records
    ), f"expected decode-failure warning; got {[r.message for r in caplog.records]}"


@pytest.mark.asyncio
async def test_detect_ems_warns_on_malformed_serial(caplog):
    """If a per-slot serial string doesn't match the GE 10-char format, log a warning."""
    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x5001, HR(21): 0})
    # Inverter slot 1 has a malformed serial (junk bytes), slot 2 is a normal redacted form.
    _prime_ems_rollup(client, inverter_count=2, serials=("!!!garbage", "CE0000G000"))

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", new=AsyncMock(return_value=False)):
            with caplog.at_level("WARNING", logger="givenergy_modbus.client.client"):
                await client.detect()

    assert any(
        "inverter_1_serial_number" in rec.message and "doesn't match GE serial format" in rec.message
        for rec in caplog.records
    ), f"expected malformed-serial warning for slot 1; got {[r.message for r in caplog.records]}"
    # Slot 2 is well-formed — no warning for it.
    assert not any(
        "inverter_2_serial_number" in rec.message and "doesn't match GE serial format" in rec.message
        for rec in caplog.records
    )


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
    _prime_cache(client, 0x11, {HR(0): 0x2001, HR(21): 0})
    _prime_battery_serial(client, 0x32)
    _prime_battery_serial(client, 0x33)
    _prime_meter_voltage(client, 0x01)

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
    _prime_cache(client, 0x11, {HR(0): 0x2001, HR(21): 0})
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
    _prime_cache(client, 0x11, {HR(0): 0x2001, HR(21): 0})
    _prime_battery_serial(client, 0x32)
    _prime_meter_voltage(client, 0x01)

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
    _prime_cache(client, 0x11, {HR(0): 0x8000, HR(21): 0})
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
    _prime_cache(client, 0x11, {HR(0): 0x8000, HR(21): 0})
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


@pytest.mark.asyncio
async def test_detect_lv_batteries_non_contiguous():
    """Non-contiguous battery addresses (e.g. 0x32 + 0x34, gap at 0x33) are all detected.

    Regression for break-on-first-absent: a gap at 0x33 must not prevent 0x34 from
    being found. Mirrors the meter sweep which already uses per-slot continue (#95).
    """
    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x2001, HR(21): 0})
    _prime_battery_serial(client, 0x32)
    # 0x33 is absent; 0x34 is present and valid.
    _prime_battery_serial(client, 0x34)

    async def _probe_side_effect(request, *, timeout, retries):
        return request.device_address in {0x34}  # 0x33 absent, 0x34 present

    with (
        patch.object(client, "send_request_and_await_response", new_callable=AsyncMock),
        patch.object(client, "_probe", side_effect=_probe_side_effect),
    ):
        caps = await client.detect()

    assert 0x32 in caps.lv_battery_addresses
    assert 0x33 not in caps.lv_battery_addresses
    assert 0x34 in caps.lv_battery_addresses


@pytest.mark.asyncio
async def test_detect_lv_batteries_transient_failure_mid_range():
    """A transient probe failure on one battery slot does not drop all subsequent slots."""
    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x2001, HR(21): 0})
    _prime_battery_serial(client, 0x32)
    # 0x33 times out transiently; 0x34 is present and valid.
    _prime_battery_serial(client, 0x34)

    call_count = {}

    async def _probe_side_effect(request, *, timeout, retries):
        addr = request.device_address
        call_count[addr] = call_count.get(addr, 0) + 1
        return addr == 0x34  # 0x33 fails, 0x34 succeeds

    with (
        patch.object(client, "send_request_and_await_response", new_callable=AsyncMock),
        patch.object(client, "_probe", side_effect=_probe_side_effect),
    ):
        caps = await client.detect()

    assert 0x32 in caps.lv_battery_addresses
    assert 0x33 not in caps.lv_battery_addresses
    assert 0x34 in caps.lv_battery_addresses
    # 0x34 must have been probed (not short-circuited after 0x33 failed)
    assert call_count.get(0x34, 0) >= 1


@pytest.mark.asyncio
async def test_detect_lv_batteries_invalid_slot_skipped_not_aborted():
    """A ghost slot that ACKs but fails Battery.is_valid() is skipped; later slots still found."""
    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x2001, HR(21): 0})
    _prime_battery_serial(client, 0x32)
    # 0x33 responds but has no valid serial → is_valid()=False (ghost).
    _prime_cache(client, 0x33, {})  # no serial registers → is_valid False
    _prime_battery_serial(client, 0x34)

    async def _probe_side_effect(request, *, timeout, retries):
        return request.device_address in {0x33, 0x34}

    with (
        patch.object(client, "send_request_and_await_response", new_callable=AsyncMock),
        patch.object(client, "_probe", side_effect=_probe_side_effect),
    ):
        caps = await client.detect()

    assert 0x32 in caps.lv_battery_addresses
    assert 0x33 not in caps.lv_battery_addresses  # ghost — skipped
    assert 0x34 in caps.lv_battery_addresses


# ---------------------------------------------------------------------------
# connect()+detect() atomicity (#274): a connection-level detect() failure must
# tear the connection down so connect()+detect() is atomic. A PlantTopologyMismatch
# is raised on a healthy connection, so it must leave `connected` untouched.
# ---------------------------------------------------------------------------


def _prime_live_connection(client: Client) -> MagicMock:
    """Put the client in a post-connect() state so the real close() can run.

    Mirrors the mock-socket setup in tests/client/test_client.py — a MagicMock
    writer whose wait_closed is awaitable, a reader, both background tasks, and
    connected=True. Returns the writer for teardown assertions.
    """
    writer = MagicMock()
    writer.wait_closed = AsyncMock()
    client.writer = writer
    client.reader = MagicMock()
    client.network_producer_task = MagicMock()
    client.network_consumer_task = MagicMock()
    client.connected = True
    return writer


@pytest.mark.asyncio
async def test_detect_timeout_closes_connection():
    """A TimeoutError during detect() tears the connection down (connected=False)."""
    client = _make_client()
    writer = _prime_live_connection(client)

    with patch.object(client, "send_request_and_await_response", side_effect=TimeoutError):
        with patch.object(client, "_probe", new=AsyncMock(return_value=False)):
            with pytest.raises(TimeoutError):
                await client.detect()

    assert client.connected is False
    writer.close.assert_called_once()


@pytest.mark.asyncio
async def test_detect_teardown_error_does_not_mask_original():
    """If close() raises during teardown, the original detect() error still propagates."""
    client = _make_client()
    _prime_live_connection(client)

    with patch.object(client, "send_request_and_await_response", side_effect=TimeoutError):
        with patch.object(client, "_probe", new=AsyncMock(return_value=False)):
            with patch.object(client, "close", new=AsyncMock(side_effect=RuntimeError("teardown boom"))):
                with pytest.raises(TimeoutError):  # not RuntimeError
                    await client.detect()


@pytest.mark.asyncio
async def test_detect_missing_hr0_closes_connection():
    """A CommunicationError ("HR(0) not populated") tears the connection down."""
    client = _make_client()
    _prime_live_connection(client)
    # Don't prime any cache — HR(0) will be absent → CommunicationError.

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", new=AsyncMock(return_value=False)):
            with pytest.raises(CommunicationError, match="HR\\(0\\)"):
                await client.detect()

    assert client.connected is False


@pytest.mark.asyncio
async def test_detect_topology_mismatch_keeps_connection():
    """A PlantTopologyMismatch is raised on a healthy connection — leave it up.

    The hint was wrong, not the link; capabilities is cleared, but the caller can
    retry a cold detect() on the same live socket, so connected must stay True.
    """
    client = _make_client()
    _prime_live_connection(client)
    _prime_cache(client, 0x11, {HR(0): 0x2001, HR(21): 0})
    _prime_battery_serial(client, 0x32)
    _prime_meter_voltage(client, 0x01)

    prior = PlantCapabilities(
        device_type=Model.HYBRID_GEN1,
        meter_addresses=[0x01, 0x02],  # 0x02 won't confirm → mismatch
        lv_battery_addresses=[0x32],
    )

    async def _probe_side_effect(request, *, timeout, retries):
        return request.device_address == 0x01

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", side_effect=_probe_side_effect):
            with pytest.raises(PlantTopologyMismatch):
                await client.detect(prior=prior)

    assert client.connected is True
    assert client.plant.capabilities is None


@pytest.mark.asyncio
async def test_detect_stale_cache_not_admitted_on_probe_failure_meter():
    """A stale meter cache from a prior detect must not re-appear when the probe now times out.

    Regression for the probe-then-validate split: _probe_ranges marks the address absent but
    previously left the stale RegisterCache entry in place, so _derive_capabilities re-admitted
    the device from stale data. Cold detect (no prior) avoids the topology-mismatch raise.
    """
    from givenergy_modbus.model.register_cache import RegisterCache

    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x2001, HR(21): 0})
    _prime_battery_serial(client, 0x32)
    # Stale valid-looking meter cache at 0x02 — a previous detect run left it there.
    client.plant.register_caches[0x02] = RegisterCache({IR(60): 1})

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", new=AsyncMock(return_value=False)):
            caps = await client.detect()

    assert 0x02 not in caps.meter_addresses, "stale meter cache must be evicted when probe fails"
    assert client.plant.block_present(0x02, "IR", 60, 30) is False


@pytest.mark.asyncio
async def test_detect_stale_cache_not_admitted_on_probe_failure_battery():
    """A stale battery cache from a prior detect must not re-appear when the probe now times out.

    Same regression as the meter case, but through _detect_lv_batteries's imperative probe loop.
    0x32 is always found via the known-tier preamble; 0x33's stale cache must be evicted.
    """
    from givenergy_modbus.model.register_cache import RegisterCache

    client = _make_client()
    _prime_cache(client, 0x11, {HR(0): 0x2001, HR(21): 0})
    _prime_battery_serial(client, 0x32)
    # Stale valid-looking battery cache at 0x33 — a previous detect run left it there.
    client.plant.register_caches[0x33] = RegisterCache({IR(60): 1})

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", new=AsyncMock(return_value=False)):
            caps = await client.detect()

    assert 0x33 not in caps.lv_battery_addresses, "stale battery cache must be evicted when probe fails"
    assert client.plant.block_present(0x33, "IR", 60, 60) is False


@pytest.mark.asyncio
async def test_detect_success_leaves_connected():
    """A successful detect() leaves the connection up (regression guard)."""
    client = _make_client()
    _prime_live_connection(client)
    _prime_cache(client, 0x11, {HR(0): 0x2001, HR(21): 0})
    _prime_battery_serial(client, 0x32)

    with patch.object(client, "send_request_and_await_response", new_callable=AsyncMock):
        with patch.object(client, "_probe", new=AsyncMock(return_value=False)):
            caps = await client.detect()

    assert client.connected is True
    assert client.plant.capabilities is caps
