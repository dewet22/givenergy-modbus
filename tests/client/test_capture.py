"""Tests for client-side wire capture (FrameRedactor + LanConfigBroadcast)."""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from givenergy_modbus.client.client import Client, FrameRedactor

# ---------------------------------------------------------------------------
# FrameRedactor — frame-aware redaction
# ---------------------------------------------------------------------------


def _make_holding_response(serial: str, *, base: int = 0, values: list[int] | None = None) -> bytes:
    """Build a wire-level ReadHoldingRegistersResponse with the given serial and values."""
    from givenergy_modbus.pdu import ReadHoldingRegistersResponse

    values = values or ([0] * 60)
    pdu = ReadHoldingRegistersResponse(
        data_adapter_serial_number="WF1234G567",
        inverter_serial_number=serial,
        base_register=base,
        register_count=len(values),
        register_values=values,
        device_address=0x32,
        padding=0x8A,
        error=False,
    )
    return pdu.encode()


def _make_input_response(serial: str, *, base: int = 0, values: list[int] | None = None) -> bytes:
    """Build a wire-level ReadInputRegistersResponse with the given serial and values."""
    from givenergy_modbus.pdu import ReadInputRegistersResponse

    values = values or ([0] * 60)
    pdu = ReadInputRegistersResponse(
        data_adapter_serial_number="WF1234G567",
        inverter_serial_number=serial,
        base_register=base,
        register_count=len(values),
        register_values=values,
        device_address=0x32,
        padding=0x8A,
        error=False,
    )
    return pdu.encode()


def test_frame_redactor_tx_redacts_request_serial():
    """TX-direction FrameRedactor decodes outgoing requests and redacts their adapter serial.

    Regression for the bug found in review: using ClientIncomingMessage for TX frames
    caused them to fall through to intact-passthrough, leaking the serial in every request.
    """
    from givenergy_modbus.pdu import ClientOutgoingMessage, ReadHoldingRegistersRequest

    req = ReadHoldingRegistersRequest(
        base_register=0,
        register_count=60,
        device_address=0x11,
        data_adapter_serial_number="WF2125G047",
    )
    frame = req.encode()
    assert b"WF2125G047" in frame  # serial is in the raw bytes before redaction

    r = FrameRedactor("tx")
    out = r.feed(frame) + r.flush()

    pdu = ClientOutgoingMessage.decode_bytes(out)
    assert pdu.data_adapter_serial_number == "WF2125G000"  # unit digits zeroed
    assert b"WF2125G047" not in out


def test_frame_redactor_redacts_envelope_serial():
    """Adapter and inverter serials in the envelope are zeroed in the re-encoded output."""
    from givenergy_modbus.pdu import ClientIncomingMessage

    frame = _make_holding_response("CE2231G454")
    r = FrameRedactor()
    out = r.feed(frame) + r.flush()

    pdu = ClientIncomingMessage.decode_bytes(out)
    # inverter serial zeroed: CE2231G000 (prefix + date kept, unit digits → 000)
    assert pdu.inverter_serial_number == "CE2231G000"
    # adapter serial also zeroed
    assert pdu.data_adapter_serial_number == "WF1234G000"
    assert len(out) == len(frame)


def test_frame_redactor_redacts_payload_inverter_serial():
    """HR(13-17) register group (inverter serial) is redacted in the register payload."""
    from givenergy_modbus.pdu import ClientIncomingMessage

    # Put a serial into HR(13-17) — these are the inverter serial registers
    # "SA2114G047" encoded as 5 big-endian register values
    serial_str = "SA2114G047"
    serial_regs = [int.from_bytes(serial_str[i * 2 : i * 2 + 2].encode("latin1"), "big") for i in range(5)]
    # Build an HR(0-59) response with the serial in slots 13-17
    values = [0] * 60
    values[13:18] = serial_regs

    frame = _make_holding_response("ZZ0000H000", base=0, values=values)
    r = FrameRedactor()
    out = r.feed(frame) + r.flush()

    pdu = ClientIncomingMessage.decode_bytes(out)
    # Reconstruct the HR(13-17) string from the redacted values
    raw = b"".join(pdu.register_values[13 + i].to_bytes(2, "big") for i in range(5))
    redacted_serial = raw.decode("latin1").replace("\x00", "").upper()
    assert redacted_serial == "SA2114G000"  # date kept, unit digits zeroed
    assert len(out) == len(frame)


def test_frame_redactor_redacts_hr8_serial_register():
    """HR(8-12) is still redacted after first_battery_serial_number was removed (#191).

    The field was dropped from the LUT, but AIO firmware stores the unit serial here
    byte-swapped (recoverable to the real serial), so HR(8-12) must stay in the
    redaction set via an explicit group. Guards against a silent privacy regression.
    """
    from givenergy_modbus.pdu import ClientIncomingMessage

    serial_str = "HC2114G047"  # AIO-style byte-swapped copy lives at HR(8-12)
    serial_regs = [int.from_bytes(serial_str[i * 2 : i * 2 + 2].encode("latin1"), "big") for i in range(5)]
    values = [0] * 60
    values[8:13] = serial_regs

    frame = _make_holding_response("ZZ0000H000", base=0, values=values)
    r = FrameRedactor()
    out = r.feed(frame) + r.flush()

    pdu = ClientIncomingMessage.decode_bytes(out)
    raw = b"".join(pdu.register_values[8 + i].to_bytes(2, "big") for i in range(5))
    redacted_serial = raw.decode("latin1").replace("\x00", "").upper()
    assert redacted_serial == "HC2114G000"  # date kept, unit digits zeroed
    assert len(out) == len(frame)


def test_frame_redactor_redacts_bmu_module_serial():
    """HV BMU per-module serial at IR(114-118) is redacted in an HV-stack frame (#375).

    The BMU serial has no LUT Def (Bmu decodes it manually), so it is only covered by
    the explicit BMU serial groups in _get_serial_groups(). FrameRedactor previously
    used a divergent serial-group builder that omitted them, leaking every HV module
    serial (0x50-0x55 stacks) from shared captures.
    """
    from givenergy_modbus.pdu import ClientIncomingMessage

    serial_str = "HY2336G680"
    serial_regs = [int.from_bytes(serial_str[i * 2 : i * 2 + 2].encode("latin1"), "big") for i in range(5)]
    # HV BMU module read: IR(60,60); serial lives at IR(114-118) → offset 54 in the block
    values = [0] * 60
    values[54:59] = serial_regs

    frame = _make_input_response("ZZ0000H000", base=60, values=values)
    assert b"HY2336G680" in frame  # present before redaction

    r = FrameRedactor()
    out = r.feed(frame) + r.flush()

    pdu = ClientIncomingMessage.decode_bytes(out)
    raw = b"".join(pdu.register_values[54 + i].to_bytes(2, "big") for i in range(5))
    redacted_serial = raw.decode("latin1").replace("\x00", "").upper()
    assert redacted_serial == "HY2336G000"  # date kept, unit digits zeroed
    assert b"HY2336G680" not in out
    assert len(out) == len(frame)


def test_frame_redactor_invalid_frame_emitted_intact():
    """An undecodable frame (bad MBAP / unknown function) is emitted intact, not dropped."""
    # Build a syntactically valid GivEnergy MBAP wrapping an unknown function code
    import struct

    bad_inner = b"\x00" * 20  # garbage inner
    mbap = struct.pack(">HHHBB", 0x5959, 0x1, len(bad_inner) + 2, 0x1, 0x7F)
    bad_frame = mbap + bad_inner

    r = FrameRedactor()
    out = r.feed(bad_frame) + r.flush()
    # Intact — exact same bytes
    assert out == bad_frame


def test_frame_redactor_invalid_frame_logs_warning(caplog):
    """An undecodable frame causes a WARNING log entry."""
    import struct

    bad_inner = b"\x00" * 20
    mbap = struct.pack(">HHHBB", 0x5959, 0x1, len(bad_inner) + 2, 0x1, 0x7F)
    bad_frame = mbap + bad_inner

    r = FrameRedactor()
    with caplog.at_level(logging.WARNING, logger="givenergy_modbus.client.client"):
        r.feed(bad_frame)
        r.flush()
    assert any("undecodable" in rec.message.lower() or "intact" in rec.message.lower() for rec in caplog.records)


def test_frame_redactor_partial_frame_held_then_emitted():
    """A frame split across two chunks is correctly reassembled before redaction."""
    frame = _make_holding_response("CE2231G454")
    # Split the frame in half — first feed returns nothing (partial), second returns the redacted frame
    r = FrameRedactor()
    mid = len(frame) // 2
    out1 = r.feed(frame[:mid])
    out2 = r.feed(frame[mid:])
    tail = r.flush()
    out = out1 + out2 + tail

    from givenergy_modbus.pdu import ClientIncomingMessage

    pdu = ClientIncomingMessage.decode_bytes(out)
    assert pdu.inverter_serial_number == "CE2231G000"
    assert len(out) == len(frame)


def test_frame_redactor_garbage_before_marker_emitted_intact():
    """Garbage bytes before a valid frame marker are emitted intact."""
    garbage = b"\x00\x01\x02\x03garbage"
    frame = _make_holding_response("WF1234G567")
    r = FrameRedactor()
    out = r.feed(garbage + frame) + r.flush()
    # Garbage preserved, followed by the redacted frame
    assert out[: len(garbage)] == garbage
    assert len(out) > len(garbage)


def test_frame_redactor_lan_config_broadcast_redacted():
    """The 70-byte LAN-config broadcast from the fixture round-trips with IPs zeroed."""
    # The frame from the ems_2_inv_3_bat_a fixture (already IP-zeroed in the fixture)
    inner_hex = (
        "574f3030303047303030000000000000002c3030302e3030302e302e30302c"
        "3030302e3030302e3030302e302c3030302e3030302e302e300d0a0d0ab4f2"
    )
    full_frame = bytes.fromhex("5959000100400102") + bytes.fromhex(inner_hex)

    r = FrameRedactor()
    out = r.feed(full_frame) + r.flush()

    from givenergy_modbus.pdu.lan_config import LanConfigBroadcast, _zero_ip

    pdu = ClientIncomingMessage.decode_bytes(out)
    assert isinstance(pdu, LanConfigBroadcast)
    # IPs already zeroed in the fixture; verify idempotent
    assert pdu.ip == _zero_ip(pdu.ip)
    assert len(out) == len(full_frame)
    # The trailing 2-byte check field (0xb4f2) is preserved verbatim.
    # Its derivation does not follow the CRC16/Modbus(payload[18:], byte-swapped)
    # formula used by all other GivEnergy frames — no candidate span produces a
    # match — so it is opaque and cannot be recomputed.  The fixture was captured
    # with IPs already zeroed, so the check is already consistent with the current
    # CSV bytes; redacting a live frame with real IPs would leave the check
    # inconsistent with the rewritten CSV, but this is unavoidable without
    # understanding the dongle-firmware-private derivation.
    assert out[-2:] == full_frame[-2:]  # check bytes pass through unchanged


# ---------------------------------------------------------------------------
# Client.capture_frames integration
# ---------------------------------------------------------------------------


async def test_capture_frames_tees_rx_to_sink_redacted():
    """The RX capture path redacts a valid frame's serial before passing to the sink."""
    from givenergy_modbus.pdu import ClientIncomingMessage

    client = Client(host="foo", port=4321)
    # Wire up a mock reader that yields one frame then EOF
    frame = _make_holding_response("CE2231G454")

    reader = MagicMock()
    reader.at_eof.side_effect = [False, True]
    reader.read = AsyncMock(side_effect=[frame, b""])
    client.reader = reader
    client.framer = MagicMock()
    client.framer.decode = MagicMock(return_value=_aiter([]))

    captured: list[tuple[str, bytes]] = []
    capture = asyncio.create_task(client.capture_frames(lambda d, f: captured.append((d, f)), duration=0.05))
    await asyncio.sleep(0)

    consumer = asyncio.create_task(client._task_network_consumer())
    try:
        await asyncio.sleep(0.1)
        await capture
    finally:
        consumer.cancel()
        try:
            await consumer
        except asyncio.CancelledError:
            pass

    rx_frames = [f for d, f in captured if d == "rx"]
    if rx_frames:
        out = b"".join(rx_frames)
        pdu = ClientIncomingMessage.decode_bytes(out)
        assert pdu.inverter_serial_number == "CE2231G000"

    assert client._capture_sink is None


async def test_capture_frames_refuses_concurrent_capture():
    """A second capture started while one is in flight raises immediately."""
    client = Client(host="foo", port=4321)
    client._capture_sink = lambda _d, _f: None
    with pytest.raises(RuntimeError, match="already running"):
        await client.capture_frames(lambda _d, _f: None, duration=0.01)


async def test_capture_frames_releases_sink_on_cancellation():
    """If the capture task is cancelled mid-sleep, the sink slot is freed."""
    client = Client(host="foo", port=4321)
    capture = asyncio.create_task(client.capture_frames(lambda _d, _f: None, duration=10.0))
    await asyncio.sleep(0)
    assert client._capture_sink is not None
    capture.cancel()
    try:
        await capture
    except asyncio.CancelledError:
        pass
    assert client._capture_sink is None


def test_emit_to_sink_swallows_sink_exceptions(caplog):
    """A sink callback that raises must not propagate out of the network tasks."""
    client = Client(host="foo", port=4321)

    def boom(_direction, _data):
        raise RuntimeError("sink blew up")

    client._capture_sink = boom
    with caplog.at_level(logging.ERROR, logger="givenergy_modbus.client.client"):
        client._emit_to_sink("rx", b"some redacted bytes")
    assert any("capture sink raised" in r.message for r in caplog.records)


def test_emit_to_sink_noops_without_sink_or_data():
    """No active sink, or empty data, is a silent no-op."""
    client = Client(host="foo", port=4321)
    calls = []
    client._emit_to_sink("rx", b"data")
    client._capture_sink = lambda d, f: calls.append((d, f))
    client._emit_to_sink("tx", b"")
    assert calls == []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _aiter(items):
    for item in items:
        yield item


def _aiter_wrap(items):
    async def _gen():
        for item in items:
            yield item

    return _gen()


from givenergy_modbus.pdu import ClientIncomingMessage  # noqa: E402 — used in test body


def test_frame_redactor_recovers_from_oversized_length_field():
    """A false marker whose length field exceeds 300 is emitted intact, not buffered (audit M3).

    Without a cap the redactor would wait for up to ~64 KB to complete a frame that never
    will, stalling the stream and (on flush) emitting the *unredacted* real frame behind it.
    The fix mirrors the framer's `hdr_len > 300` guard: skip the false marker and resume.
    """
    real = _make_holding_response("CE2231G454")
    bogus = bytes.fromhex("59590001") + b"\xff\xff"  # frame marker + length 0xFFFF (> 300)

    r = FrameRedactor()
    out = r.feed(bogus + real) + r.flush()

    assert b"CE2231G454" not in out, "redactor must recover and still redact the real frame"
    assert out.startswith(bogus), "the false-marker junk must pass through intact"
    assert len(out) == len(bogus) + len(real), "no bytes lost or stalled in the buffer"


# ---------------------------------------------------------------------------
# capture_frames() orchestration — setup, flush-on-close, single-capture guard
# ---------------------------------------------------------------------------


async def test_capture_frames_resets_state_on_completion():
    """capture_frames installs the sink/redactors for its duration and tears them all down."""
    client = Client(host="foo", port=4321)
    captured: list[tuple[str, bytes]] = []

    # duration=0 returns from the internal sleep immediately, then runs the finally block.
    await client.capture_frames(lambda d, f: captured.append((d, f)), duration=0)

    # The finally block must clear every capture handle so a later capture starts clean.
    assert client._capture_sink is None
    assert client._capture_redactor_rx is None
    assert client._capture_redactor_tx is None


async def test_capture_frames_flushes_held_tail_on_close(monkeypatch):
    """On close, each direction's redactor tail is flushed to the sink so trailing bytes aren't lost."""
    client = Client(host="foo", port=4321)
    emitted: list[tuple[str, bytes]] = []
    monkeypatch.setattr(client, "_emit_to_sink", lambda direction, data: emitted.append((direction, data)))

    # Force both redactors to yield a non-empty tail when flushed at close.
    monkeypatch.setattr(FrameRedactor, "flush", lambda self: b"tail-" + self._direction.encode())

    await client.capture_frames(lambda d, f: None, duration=0)

    assert ("rx", b"tail-rx") in emitted
    assert ("tx", b"tail-tx") in emitted
