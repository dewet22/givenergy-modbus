"""End-to-end integration: drive the real Client against MockPlant.

The golden-master tests (tests/model/test_fixture_golden_master.py) replay recorded
*responses* through decode. These instead exercise the client's own request *generation*
— connect → detect → refresh, over a real socket — against a server that synthesizes
correct-CRC responses from the same captures. That round-trip is what the passive replay
can't cover.
"""

import re
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from givenergy_modbus.client.client import Client
from givenergy_modbus.exceptions import RefreshPartiallySucceeded
from givenergy_modbus.model.inverter import Model
from givenergy_modbus.model.register import HR
from givenergy_modbus.model.register_cache import RegisterCache
from givenergy_modbus.pdu import (
    ClientIncomingMessage,
    ReadHoldingRegistersRequest,
    ReadInputRegistersRequest,
    WriteHoldingRegisterRequest,
)
from givenergy_modbus.testing import MockPlant
from givenergy_modbus.testing.mock_plant import _iter_capture_frames, plant_from_capture

_CAPTURES = Path(__file__).parents[1] / "fixtures" / "captures"


async def _connected_client(mock: MockPlant) -> tuple[Client, str, int]:
    host, port = await mock.start("127.0.0.1", 0)
    client = Client(host, port, tx_message_wait=0, tx_jitter=0)
    await client.connect()
    return client, host, port


async def _client_for(*relpaths: str) -> AsyncIterator[Client]:
    mock = MockPlant.from_capture(*[_CAPTURES / r for r in relpaths])
    client, _, _ = await _connected_client(mock)
    try:
        yield client
    finally:
        await client.close()
        await mock.aclose()


# Fast probe params: absent peripheral addresses time out, so keep them short.
_DETECT = dict(timeout=1.0, retries=0, probe_timeout=0.1, probe_retries=0)


@pytest.mark.timeout(30)
async def test_detect_and_refresh_aio():
    """All-in-One: detect → ALL_IN_ONE @ 0x11 with HV BCU stack; refresh completes."""
    async for client in _client_for("aio_a/aio_arm612_5min.log"):
        caps = await client.detect(**_DETECT)
        assert caps.device_type is Model.ALL_IN_ONE
        assert caps.inverter_address == 0x11
        assert caps.is_hv
        assert caps.bcu_stacks  # the integrated HV stack is detected
        plant = await client.refresh(timeout=1.0, retries=0)
        assert plant.capabilities.device_type is Model.ALL_IN_ONE


@pytest.mark.timeout(30)
async def test_detect_ems():
    """EMS controller: detect → Model.EMS @ 0x11, two managed inverters via the rollup."""
    async for client in _client_for("ems_2_inv_3_bat_a/ems_arm1036_60s.log"):
        caps = await client.detect(**_DETECT)
        assert caps.device_type is Model.EMS
        assert caps.is_ems


@pytest.mark.timeout(30)
async def test_detect_and_refresh_hybrid_gen1():
    """HYBRID_GEN1: detect → Model.HYBRID_GEN1 @ 0x11 (unified addressing, #189); refresh completes.

    Backed by the 0x11-polled capture — recorded by this library's own poll loop, so the
    mock serves full banks at 0x11 exactly as the live unit did. The older passive dongle
    capture only carries identity at 0x11 (the dongle polled the 0x31 facade) and can no
    longer satisfy a 0x11-addressed refresh.
    """
    async for client in _client_for("hybrid_2_bat_a/hybrid_gen1_arm449_0x11_poll_10min.log"):
        caps = await client.detect(**_DETECT)
        assert caps.device_type is Model.HYBRID_GEN1
        assert caps.inverter_address == 0x11
        plant = await client.refresh(timeout=1.0, retries=0)
        assert plant.capabilities.device_type is Model.HYBRID_GEN1


@pytest.mark.timeout(30)
async def test_aio_errors_on_absent_three_phase_bank():
    """A direct IR(1000+) read against the AIO mock returns an error response (#105).

    The AIO has no per-phase bank, so this is the faithful reproduction of the #105
    symptom — end-to-end over a real socket through the synthesizing mock.

    Uses a fresh raw connection rather than the Client's internal reader, because the
    Client's _task_network_consumer is already consuming the same StreamReader in the
    background — sharing it causes a race condition (Codex review).
    """
    import asyncio

    async with MockPlant.from_capture(_CAPTURES / "aio_a/aio_arm612_5min.log") as mock:
        _, port = await mock.start("127.0.0.1", 0)
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        req = ReadInputRegistersRequest(base_register=1000, register_count=60, device_address=0x11)
        writer.write(req.encode())
        await writer.drain()
        data = await reader.read(4096)
        pdu = ClientIncomingMessage.decode_bytes(data)
        assert pdu.error is True
        writer.close()


# ---------------------------------------------------------------------------
# Live full-cycle: detect → load_config → refresh over the socket, then assert the
# fully-decoded typed Plant. The offline golden-master
# (tests/model/test_fixture_golden_master.py) pins the same topology but bypasses
# the client/detect stack; these run the whole cycle live against MockPlant, so the
# manifest-driven detect/load_config/refresh routing (#293) is exercised end-to-end.
# Assertion values are lifted from the golden-master.
#
# three_phase_hv_a is intentionally absent: its capture is IR-only with no HR bank at
# 0x11, so detect()'s identity read errors and the live cycle can't start — a
# follow-up issue tracks recapturing a complete three-phase fixture.
# ---------------------------------------------------------------------------


async def _full_cycle(client, *, strict=False):
    """Run detect → load_config → refresh, tolerating partial captures unless strict.

    Some committed captures don't carry every HR/IR bank the cycle polls; MockPlant
    error-responds to an absent bank, which the client surfaces as
    RefreshPartiallySucceeded — carrying a Plant fully decoded from the banks that DID
    respond. Clean captures raise nothing; these fixtures never RefreshFailed.
    ``strict=True`` (captures known to carry every polled bank) lets the exception
    propagate, so a formerly-clean capture starting to miss banks fails loudly instead
    of silently degrading to whatever the topology assertions happen to touch.
    """
    # Fast, in-process timeouts throughout: MockPlant answers present banks instantly,
    # so these only bound waits on genuinely-absent device addresses (detect's meter/
    # peripheral probe sweeps) and absent banks. No network to be slow — don't raise them.
    await client.detect(timeout=0.3, retries=0, probe_timeout=0.05, probe_retries=0)
    for step in (client.load_config, client.refresh):
        try:
            await step(timeout=0.3, retries=0)
        except RefreshPartiallySucceeded:
            if strict:
                raise
    return client.plant


def _assert_ems_rollup(plant):
    caps = plant.capabilities
    assert caps.device_type is Model.EMS
    assert caps.is_ems
    ems = plant.ems
    assert ems is not None
    assert ems.inverter_count == 2
    managed = plant.inverters
    assert len(managed) == 2
    assert all(i.data_source == "ems_rollup" for i in managed)
    assert all(i.serial_number for i in managed)
    # load_config's HR(2040,36) EMS-config bank — the is_ems entry in the
    # LOAD_CONFIG_RANGES manifest table, read ONLY by load_config (not detect/refresh).
    # Pins that the table-driven load_config routing ran end-to-end (#293).
    assert ems.export_power_limit == 9500
    assert ems.plant_enabled is True


def _assert_ems_meters(plant):
    caps = plant.capabilities
    assert caps.device_type is Model.EMS
    # detect() derives meter_addresses live (unlike the offline golden-master, which
    # sets them by hand), so plant.meters is populated end-to-end (#246 pinned values).
    m1, m3 = plant.meters[0x01], plant.meters[0x03]
    assert m3.pf_total == 0.9998
    assert m3.p_apparent_total == 575.2
    assert m1.pf_total == -0.0866
    assert m1.p_apparent_total == 713.2


def _assert_aio(plant):
    caps = plant.capabilities
    assert caps.device_type is Model.ALL_IN_ONE
    assert caps.is_hv and not caps.is_ems
    assert caps.bcu_stacks  # integrated HV stack detected
    # HV stack separately addressed: BCU 0x70, BMS 0xA0.
    assert 0x70 in plant.register_caches
    assert 0xA0 in plant.register_caches
    inv = plant.inverter
    # IR44 is inverter output on ALL_IN_ONE, not PV (#293).
    assert inv.e_pv_generation_today is None
    assert inv.e_inverter_out_today == 1.8
    # load_config's HR(60,60) config bank — decoded ONLY when load_config polls it, not
    # by detect (HR(0,60) identity only) or refresh (IR measurement banks). Pins that the
    # load_config leg of the cycle actually ran and routed the HR banks (#293).
    assert inv.charge_target_soc == 100
    assert inv.enable_charge is False


def _assert_aio_redetect(plant):
    """The detect-inclusive direct-AIO capture (ARM 620): the first CLEAN AIO cycle.

    Unlike the May aio_arm612 capture (partial — missing banks tolerated), this one
    carries every bank the cycle polls, including HR(300,60) — the first live-cycle
    coverage of the AC-config block routing (has_ac_config_block, #293/#295).
    """
    caps = plant.capabilities
    assert caps.device_type is Model.ALL_IN_ONE
    assert caps.is_hv and not caps.is_ems
    assert caps.bcu_stacks == [(0, 4)]  # one integrated stack, 4 modules
    assert caps.arm_firmware_version == 620
    inv = plant.inverter
    assert inv.serial_number == "CH2414G000"
    # IR44 is inverter output on ALL_IN_ONE, not PV (#293 Slice A, live).
    assert inv.e_pv_generation_today is None
    assert inv.e_inverter_out_today == 8.4
    # load_config's HR(60,60) config bank (load_config-exclusive, #293).
    assert inv.charge_target_soc == 100
    assert inv.enable_charge is False
    assert inv.battery_charge_limit == 38
    # load_config's HR(300,60) AC-config bank — gated has_ac_config_block in
    # LOAD_CONFIG_RANGES and polled ONLY by load_config; first capture to carry it
    # live. Pins the capability-gated table entry end-to-end (#293/#295).
    assert inv.battery_charge_limit_ac == 50
    # Inverter-level v_battery (IR50) now admits the AIO's HV integrated-stack voltage
    # (~300 V) instead of clamping it to None under the old LV-calibrated 100 V bound —
    # so an AIO gets a real Battery Voltage rather than a permanently-Unknown entity.
    assert inv.v_battery == pytest.approx(312.78)
    # Each module's split serial's "HY" prefix lands on t_cell_21's register; the
    # bounds check (#379) suppresses that non-zero out-of-range raw to None rather than
    # surfacing a ~1852 °C phantom.
    for m in plant.aio_battery_modules:
        assert m.t_cell_21 is None
    # All 4 HV modules decode through the live cycle, with distinct serials. The
    # fixture's serials are prefixless placeholders ("2414G000"): this BMU firmware
    # (BAAA0013) stores serials SPLIT on the wire (prefix at IR110, tail at
    # IR115-118) — the #378 layout, on every module — and MockPlant disambiguates
    # identical serials per device address when serving (#288), so pin shape +
    # distinctness rather than exact values.
    modules = plant.aio_battery_modules
    assert len(modules) == 4
    serials = [m.serial_number for m in modules]
    assert all(isinstance(s, str) and re.fullmatch(r"2414G\d{3}", s.strip("\x00 ")) for s in serials), serials
    assert len(set(serials)) == 4


def _assert_hybrid_0x11(plant):
    caps = plant.capabilities
    assert caps.device_type is Model.HYBRID_GEN1
    assert caps.inverter_address == 0x11
    assert not caps.is_hv and not caps.is_ems
    assert plant.number_batteries == 2  # LV packs at 0x32/0x33
    inv = plant.inverter
    # IR44 stays PV on HYBRID_GEN1 — the #293 override doesn't fire.
    assert inv.e_pv_generation_today == 15.8
    assert inv.e_inverter_out_today is None
    # load_config's HR(60,60) config bank — decoded ONLY when load_config polls it, not
    # by detect (HR(0,60) identity only) or refresh (IR measurement banks). Pins that the
    # load_config leg of the cycle actually ran and routed the HR banks (#293).
    assert inv.charge_target_soc == 29
    assert inv.battery_charge_limit == 50


def _assert_hybrid_passive(plant):
    # Pre-#189 dongle capture: operational banks live at the 0x31 facade, so a
    # 0x11-addressed load_config/refresh can't reach them (hence partial). What the live
    # cycle CAN prove: detect() still classifies correctly and finds the LV battery
    # packs at 0x32/0x33 from their own banks — the partial path yields a coherent plant.
    caps = plant.capabilities
    assert caps.device_type is Model.HYBRID_GEN1
    assert caps.inverter_address == 0x11
    assert not caps.is_hv and not caps.is_ems
    assert plant.number_batteries == 2


def _assert_gateway(plant):
    from givenergy_modbus.model.gateway import GatewayV1

    caps = plant.capabilities
    assert caps.device_type is Model.GATEWAY
    assert not caps.is_hv and not caps.is_ems
    gw = plant.gateway
    assert isinstance(gw, GatewayV1)
    assert gw.software_version == "GAAA0014"
    assert gw.parallel_aio_num == 2
    # V1 word order: sane lifetime totals (#360 regression trap).
    assert gw.e_grid_import_total == 12710.8
    assert gw.e_pv_total == 5087.0
    assert gw.e_battery_charge_total == 8855.9
    assert gw.aio1_serial_number == "CH2414G000"
    assert gw.aio2_serial_number == "CH2542G000"


@pytest.mark.timeout(30)
@pytest.mark.parametrize(
    ("relpath", "assert_topology", "strict"),
    [
        ("ems_2_inv_3_bat_a/ems_arm1036_60s.log", _assert_ems_rollup, True),
        ("ems_2_inv_3_bat_a/ems_arm1036_30min.log", _assert_ems_meters, True),
        ("hybrid_2_bat_a/hybrid_gen1_arm449_0x11_poll_10min.log", _assert_hybrid_0x11, True),
        ("gateway_2aio_a/gateway_gaaa0014_10min_daylight.log", _assert_gateway, True),
        ("aio_a/aio_arm620_redetect_7min.log", _assert_aio_redetect, True),
        ("aio_a/aio_arm612_5min.log", _assert_aio, False),
        ("hybrid_2_bat_a/hybrid_gen1_arm449_givbat82_givbat95gen3_60min.log", _assert_hybrid_passive, False),
    ],
    ids=[
        "ems_rollup",
        "ems_meters",
        "hybrid_0x11",
        "gateway_v1",
        "aio_redetect_clean",
        "aio_partial",
        "hybrid_passive_partial",
    ],
)
async def test_full_cycle_instantiates_plant(relpath, assert_topology, strict):
    """Live detect → load_config → refresh yields a fully-decoded Plant (#293 regression fence).

    The strongest guard for the manifest series' detect/load_config/refresh routing: a
    real Client, over a real socket, against MockPlant seeded from a golden capture,
    ending in the same decoded topology the offline golden-master pins — but reached
    through the whole live stack. Assertion values are lifted from
    tests/model/test_fixture_golden_master.py.
    """
    async for client in _client_for(relpath):
        plant = await _full_cycle(client, strict=strict)
        assert_topology(plant)


# ---------------------------------------------------------------------------
# Unit tests for MockPlant internals (improve patch coverage)
# ---------------------------------------------------------------------------


def test_iter_capture_frames_skips_invalid_hex(tmp_path: Path):
    """Lines with malformed hex payloads are silently skipped."""
    log = tmp_path / "bad.log"
    log.write_text("2026-01-01T00:00:00Z rx notvalidhex\n")
    assert _iter_capture_frames(log) == []


def test_iter_capture_frames_skips_non_rx(tmp_path: Path):
    """TX lines are not included."""
    log = tmp_path / "tx.log"
    log.write_text("2026-01-01T00:00:00Z tx 5959000100060102ab0000003c000f\n")
    assert _iter_capture_frames(log) == []


def test_iter_capture_frames_tolerates_colon_rx_form(tmp_path: Path):
    """The integration capture's ``rx:/tx: <hex>`` form (no timestamp) is parsed; tx excluded (#322)."""
    good_frame = ReadHoldingRegistersRequest(base_register=0, register_count=60, device_address=0x11).encode()
    log = tmp_path / "colon.log"
    # Blank and single-token lines are skipped; only the rx line yields a frame (tx excluded).
    log.write_text(f"\nheader-line\ntx: {good_frame.hex()}\nrx: {good_frame.hex()}\n")
    frames = _iter_capture_frames(log)
    assert frames == [good_frame]  # only the rx line, decoded as one frame


def test_plant_from_capture_raises_on_zero_frames(tmp_path: Path):
    """A capture that parses to zero rx frames fails loudly rather than serving an empty plant (#322)."""
    log = tmp_path / "wrongformat.log"
    log.write_text("nothing here matches the expected line shape\n")
    with pytest.raises(ValueError, match="No rx frames parsed"):
        plant_from_capture(log)


def test_iter_capture_frames_handles_junk_before_marker(tmp_path: Path):
    """Bytes before the 5959 frame marker are silently skipped."""
    req = ReadHoldingRegistersRequest(base_register=0, register_count=60, device_address=0x11)
    good_frame = req.encode()
    payload = b"\x00\xff\xab" + good_frame
    log = tmp_path / "junk.log"
    log.write_text(f"2026-01-01T00:00:00Z rx {payload.hex()}\n")
    frames = _iter_capture_frames(log)
    assert len(frames) == 1
    assert frames[0] == good_frame


def test_iter_capture_frames_ignores_truncated_tail(tmp_path: Path):
    """A frame that ends mid-payload (truncated) is not returned."""
    log = tmp_path / "trunc.log"
    log.write_text("2026-01-01T00:00:00Z rx 595900010064010200\n")
    assert _iter_capture_frames(log) == []


def test_iter_capture_frames_skips_false_positive_marker(tmp_path: Path):
    """A 5959-marker with frame_len < 18 is a false positive; parsing continues past it."""
    req = ReadHoldingRegistersRequest(base_register=0, register_count=60, device_address=0x11)
    good_frame = req.encode()
    # frame_len = 6 + 0x05 = 11 < 18 → false positive; good_frame should still be found
    false_positive = bytes.fromhex("59590001000501")
    payload = false_positive + good_frame
    log = tmp_path / "fp.log"
    log.write_text(f"2026-01-01T00:00:00Z rx {payload.hex()}\n")
    frames = _iter_capture_frames(log)
    assert len(frames) == 1
    assert frames[0] == good_frame


async def test_context_manager_lifecycle():
    """Async with MockPlant starts and stops the server cleanly."""
    mock = MockPlant(devices={})
    async with mock:
        _, port = await mock.start("127.0.0.1", 0)
        assert port > 0
    assert mock._server is None


async def test_write_request_acknowledged():
    """A write request returns a valid ack response (Phase 1: no state mutation)."""
    import asyncio

    cache = RegisterCache({HR(94): 1380})  # CHARGE_SLOT_1_START — safe to write
    mock = MockPlant(devices={0x11: cache}, inverter_serial="SA2114G000")
    _, port = await mock.start("127.0.0.1", 0)
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        req = WriteHoldingRegisterRequest(register=94, value=1400, device_address=0x11)
        writer.write(req.encode())
        await writer.drain()
        data = await reader.read(4096)
        pdu = ClientIncomingMessage.decode_bytes(data)
        assert not pdu.error
        assert pdu.register == 94
        assert pdu.value == 1400
        writer.close()
    finally:
        await mock.aclose()


async def test_respond_returns_none_for_unknown_pdus():
    """_respond yields None (no reply) for PDU types that don't expect a response."""
    from givenergy_modbus.pdu.heartbeat import HeartbeatResponse

    mock = MockPlant(devices={})
    hb = HeartbeatResponse(data_adapter_serial_number="AB1234G567", data_adapter_type=0)
    assert mock._respond(hb) is None


# --- distinct device serials ------------------------------------------------


def test_serial_encode_decode_roundtrip():
    """`_encode_serial` is the inverse of `_decode_serial` over a 5-register IR serial."""
    from givenergy_modbus.model.register import IR
    from givenergy_modbus.testing.mock_plant import _decode_serial, _encode_serial

    regs = [IR(114 + i) for i in range(5)]
    cache = RegisterCache(dict(zip(regs, _encode_serial("HX2414G832", len(regs)))))
    assert _decode_serial(cache, regs) == "HX2414G832"


def test_make_device_serials_distinct_rewrites_all_in_a_colliding_group():
    """A re-tail must not recreate a collision with an already-distinct member (#288 review).

    When a group collides, every populated member is re-tailed by its unique suffix — not just the
    colliders — so the synthesized suffix can't land on a value an untouched member already holds.
    """
    from givenergy_modbus.model.battery import BatteryRegisterGetter
    from givenergy_modbus.model.plant import Plant
    from givenergy_modbus.testing.mock_plant import (
        _decode_serial,
        _encode_serial,
        _make_device_serials_distinct,
    )

    regs = BatteryRegisterGetter.registers_of("serial_number")  # IR(110-114)
    plant = Plant()
    for addr in (0x33, 0x34):  # collide on a redacted placeholder
        plant.register_caches[addr] = RegisterCache(dict(zip(regs, _encode_serial("BG0000G000", len(regs)))))
    # 0x35 is already distinct, but its serial ends in "34": re-tailing only 0x34 would mint
    # "BG0000G034" and recreate a collision with 0x35. Rewriting all populated members avoids that.
    plant.register_caches[0x35] = RegisterCache(dict(zip(regs, _encode_serial("BG0000G034", len(regs)))))

    _make_device_serials_distinct(plant)

    serials = [_decode_serial(plant.register_caches[a], regs) for a in (0x33, 0x34, 0x35)]
    assert serials == ["BG0000G033", "BG0000G034", "BG0000G035"]
    assert len(set(serials)) == 3  # crucially: no re-created collision


def test_make_device_serials_distinct_leaves_a_fully_distinct_group_untouched():
    """A group with no collision is left exactly as captured (#288)."""
    from givenergy_modbus.model.battery import BatteryRegisterGetter
    from givenergy_modbus.model.plant import Plant
    from givenergy_modbus.testing.mock_plant import (
        _decode_serial,
        _encode_serial,
        _make_device_serials_distinct,
    )

    regs = BatteryRegisterGetter.registers_of("serial_number")
    plant = Plant()
    plant.register_caches[0x33] = RegisterCache(dict(zip(regs, _encode_serial("BG0000G111", len(regs)))))
    plant.register_caches[0x34] = RegisterCache(dict(zip(regs, _encode_serial("BG0000G222", len(regs)))))

    _make_device_serials_distinct(plant)

    assert _decode_serial(plant.register_caches[0x33], regs) == "BG0000G111"  # untouched
    assert _decode_serial(plant.register_caches[0x34], regs) == "BG0000G222"


def test_aio_mock_serves_distinct_module_serials():
    """The AIO mock gives each battery module its own serial (was all `HX0000G000`)."""
    from givenergy_modbus.model.aio_battery import AioBatteryModule

    mock = MockPlant.from_capture(_CAPTURES / "aio_a" / "aio_arm612_5min.log")
    serials = {
        addr: AioBatteryModule.from_register_cache(mock.devices[addr], addr).serial_number
        for addr in (0x50, 0x51, 0x52, 0x53)
    }
    assert len(set(serials.values())) == 4, f"module serials must be distinct: {serials}"
    for addr in (0x50, 0x51, 0x52, 0x53):
        assert serials[addr].startswith("HX"), serials[addr]  # real prefix preserved
        assert serials[addr].endswith(f"{addr:02x}"), serials[addr]  # address-tailed, distinct


def test_make_device_serials_distinct_includes_0x32_under_unified_addressing():
    """With a 0x11 inverter present, pack #1 lives at 0x32 and must join the collision set (#283)."""
    from givenergy_modbus.model.battery import BatteryRegisterGetter
    from givenergy_modbus.model.plant import Plant
    from givenergy_modbus.testing.mock_plant import (
        _decode_serial,
        _encode_serial,
        _make_device_serials_distinct,
    )

    regs = BatteryRegisterGetter.registers_of("serial_number")
    plant = Plant()
    plant.register_caches[0x11] = RegisterCache()  # canonical inverter present → 0x32 is a pack
    for addr in (0x32, 0x33):  # both packs share the redacted placeholder → collision
        plant.register_caches[addr] = RegisterCache(dict(zip(regs, _encode_serial("BG0000G000", len(regs)))))

    _make_device_serials_distinct(plant)

    assert _decode_serial(plant.register_caches[0x32], regs) == "BG0000G032"
    assert _decode_serial(plant.register_caches[0x33], regs) == "BG0000G033"


def test_make_device_serials_distinct_leaves_legacy_inverter_at_0x32():
    """Without a canonical inverter address, 0x32 is the inverter facade and must not be rewritten."""
    from givenergy_modbus.model.battery import BatteryRegisterGetter
    from givenergy_modbus.model.plant import Plant
    from givenergy_modbus.testing.mock_plant import (
        _decode_serial,
        _encode_serial,
        _make_device_serials_distinct,
    )

    regs = BatteryRegisterGetter.registers_of("serial_number")
    plant = Plant()  # no 0x11/0x31 → legacy bare-plant addressing, 0x32 is the inverter
    plant.register_caches[0x32] = RegisterCache(dict(zip(regs, _encode_serial("SA0000G000", len(regs)))))
    for addr in (0x33, 0x34):  # the actual packs collide
        plant.register_caches[addr] = RegisterCache(dict(zip(regs, _encode_serial("BG0000G000", len(regs)))))

    _make_device_serials_distinct(plant)

    assert _decode_serial(plant.register_caches[0x32], regs) == "SA0000G000"  # inverter untouched
    assert _decode_serial(plant.register_caches[0x33], regs) == "BG0000G033"
    assert _decode_serial(plant.register_caches[0x34], regs) == "BG0000G034"


def test_make_device_serials_distinct_disambiguates_ems_managed_inverter_slots():
    """Colliding EMS managed-inverter slot serials (0x11 sub-slots) are re-tailed by slot index (#288)."""
    from givenergy_modbus.model.ems import EmsRegisterGetter
    from givenergy_modbus.model.plant import Plant
    from givenergy_modbus.testing.mock_plant import (
        _decode_serial,
        _encode_serial,
        _make_device_serials_distinct,
    )

    def slot_regs(i):
        return EmsRegisterGetter.registers_of(f"inverter_{i}_serial_number")

    plant = Plant()
    seed: dict = {}
    for i in (1, 2):  # slots 1 & 2 collide on a redacted placeholder
        seed.update(dict(zip(slot_regs(i), _encode_serial("CE0000G000", 5))))
    # slot 3 is distinct but ends in slot 1's index — re-tailing only the colliders would recreate a
    # collision (slot 1 → CE0000G001 == slot 3); rewriting all slots by index avoids it (#288 review).
    seed.update(dict(zip(slot_regs(3), _encode_serial("CE0000G001", 5))))
    # slot 4 is empty but *space-padded* — must NOT be mistaken for a colliding serial / phantom
    # inverter; decode strips whitespace → None (#288 review).
    seed.update(dict(zip(slot_regs(4), _encode_serial("          ", 5))))
    plant.register_caches[0x11] = RegisterCache(seed)

    _make_device_serials_distinct(plant)

    cache = plant.register_caches[0x11]
    serials = [_decode_serial(cache, slot_regs(i)) for i in (1, 2, 3)]
    assert serials == ["CE0000G001", "CE0000G002", "CE0000G003"]  # all slots re-tailed by index
    assert len(set(serials)) == 3  # slot 1 must not re-collide with slot 3
    assert _decode_serial(cache, slot_regs(4)) is None  # space-padded empty slot → not a phantom


def test_ems_mock_serves_distinct_managed_inverter_serials():
    """The EMS mock gives each managed-inverter slot its own serial (was both CE…G000) (#288)."""
    from givenergy_modbus.model.ems import Ems

    mock = MockPlant.from_capture(_CAPTURES / "ems_2_inv_3_bat_a" / "ems_arm1036_60s.log")
    serials = [inv.serial_number for inv in Ems.from_register_cache(mock.devices[0x11]).managed_inverters]
    assert len(serials) == 2  # the 2-managed-inverter fixture
    assert len(set(serials)) == 2, f"managed-inverter serials must be distinct: {serials}"
    assert all(s.startswith("CE") for s in serials)  # real prefix preserved


def test_main_serve_path_disambiguates_managed_inverter_serials(monkeypatch):
    """main() (the scripted serve path) disambiguates serials like from_capture, not collide them.

    Regression for the hass-reported gap: main() built MockPlant from plant_from_capture() directly and
    skipped _make_device_serials_distinct, so the served mock collided both managed inverters at CE…G000.
    Spy on construction and stub the server so we can inspect the built mock without binding a socket.
    """
    from givenergy_modbus.model.ems import Ems
    from givenergy_modbus.testing.mock_plant import MockPlant, main

    captured: dict = {}
    orig_init = MockPlant.__init__

    def _spy_init(self, devices, **kwargs):
        orig_init(self, devices, **kwargs)
        captured["mock"] = self

    async def _noop_start(self, host="127.0.0.1", port=0):
        return ("127.0.0.1", 0)

    async def _noop_serve(self):
        return

    monkeypatch.setattr(MockPlant, "__init__", _spy_init)
    monkeypatch.setattr(MockPlant, "start", _noop_start)
    monkeypatch.setattr(MockPlant, "serve_forever", _noop_serve)

    rc = main(["--capture", str(_CAPTURES / "ems_2_inv_3_bat_a" / "ems_arm1036_60s.log"), "--port", "0"])
    assert rc == 0
    serials = [inv.serial_number for inv in Ems.from_register_cache(captured["mock"].devices[0x11]).managed_inverters]
    assert len(serials) == 2 and len(set(serials)) == 2, f"main() must serve distinct serials, got {serials}"
