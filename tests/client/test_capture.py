"""Tests for client-side wire capture."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from givenergy_modbus.client.client import Client, StreamRedactor, redact

# ---------------------------------------------------------------------------
# redact()
# ---------------------------------------------------------------------------


def test_redact_single_serial():
    """A serial keeps its family prefix, YYWW date and middle letter; unit digits zeroed."""
    frame = b"prefix EA1234B567 suffix"
    redacted = redact(frame)
    assert redacted == b"prefix EA1234B000 suffix"
    assert len(redacted) == len(frame)


def test_redact_dual_serial():
    """Both dongle and inverter serials are rewritten, each keeping its YYWW date."""
    frame = b"dongle SA1111R222 inverter SA3333A444"
    redacted = redact(frame)
    assert redacted == b"dongle SA1111R000 inverter SA3333A000"
    assert len(redacted) == len(frame)


def test_redact_no_serial_unchanged():
    """A frame without serial-shaped runs comes through unchanged."""
    frame = b"\x00\x01\x02\x03 hello world \xff\xfe\xfd"
    assert redact(frame) == frame


def test_redact_preserves_length_with_mixed_content():
    """Length and offsets stay constant — important for CRC/length fields."""
    frame = b"\x01\x02 SA1234X567 \x03\x04 SA9999Z888 \x05"
    redacted = redact(frame)
    assert len(redacted) == len(frame)
    assert redacted == b"\x01\x02 SA1234X000 \x03\x04 SA9999Z000 \x05"


def test_redact_preserves_manufacture_date():
    """The YYWW manufacture-date digits survive redaction; only unit digits zero.

    The date is a coarse, diagnostically useful cohort marker (hardware
    revision / firmware-compatibility windows); the trailing three digits
    are the install-unique identifier. See #113.
    """
    # SA = family, 2114 = week 14 of 2021, G = middle letter, 047 = unit.
    frame = b"unit SA2114G047 here"
    redacted = redact(frame)
    assert redacted == b"unit SA2114G000 here"
    # Date digits unchanged; only the trailing three zeroed.
    assert b"2114" in redacted
    assert b"047" not in redacted


def test_redact_ems_serial():
    """EMS serials keep prefix + YYWW date; trailing unit digits zeroed.

    EMS units use a 3-letter + 7-digit format that the standard pattern
    doesn't match (e.g. ``EMS2522018``). The dedicated pattern preserves
    the prefix and the YYWW date (2522 → week 22 of 2025) while zeroing the
    trailing three unit digits.
    """
    frame = b"prefix EMS2522018 suffix"
    redacted = redact(frame)
    assert redacted == b"prefix EMS2522000 suffix"
    assert len(redacted) == len(frame)


def test_redact_mixed_standard_and_ems_serials():
    """Standard and EMS serials in the same frame are each rewritten.

    Either pattern leaves the other's structure alone, so a single redact()
    call covers a frame that mentions both shapes — each keeping its date.
    """
    frame = b"adapter FO2522G018 ems EMS2522018 inverter CE2231G454"
    redacted = redact(frame)
    assert redacted == b"adapter FO2522G000 ems EMS2522000 inverter CE2231G000"
    assert len(redacted) == len(frame)


def test_redact_ipv4_dotted_quad():
    """IPv4 dotted-quad gets its digits zeroed per-octet; dots preserved.

    Some inverter dongles emit network config as ASCII in protocol responses;
    see issue #100. Same-length substitution keeps frame offsets / lengths
    intact.
    """
    frame = b"prefix 192.168.4.47 suffix"
    redacted = redact(frame)
    assert redacted == b"prefix 000.000.0.00 suffix"
    assert len(redacted) == len(frame)


def test_redact_ipv4_csv_triplet():
    """The observed WO-heartbeat shape: ip,netmask,gateway as a CSV blob."""
    frame = b",192.168.4.47,255.255.252.0,192.168.4.1\r\n\r\n"
    redacted = redact(frame)
    assert redacted == b",000.000.0.00,000.000.000.0,000.000.0.0\r\n\r\n"
    assert len(redacted) == len(frame)


def test_redact_ipv4_mixed_with_serials():
    """A frame containing both serial-shaped runs and IPv4 gets both redacted in one pass.

    Serials keep their YYWW dates; the IPv4 is fully digit-zeroed (no date to keep).
    """
    frame = b"from FO2522G018 to 10.0.0.1 by EMS2522018"
    redacted = redact(frame)
    assert redacted == b"from FO2522G000 to 00.0.0.0 by EMS2522000"
    assert len(redacted) == len(frame)


def test_redact_is_idempotent():
    """Running redact() twice yields the same output as running it once.

    Important: future tooling that pipes capture data through redact() on
    re-export shouldn't accidentally double-substitute or lose information.
    """
    frame = b"FO2522G018 EMS2522018 192.168.4.47"
    once = redact(frame)
    twice = redact(once)
    assert once == twice


# ---------------------------------------------------------------------------
# Client.capture_frames integration
# ---------------------------------------------------------------------------


async def test_capture_frames_tees_tx_to_sink_redacted():
    """Producer task tees each written frame to the sink with redaction applied."""
    client = Client(host="foo", port=4321)
    writer = MagicMock()
    writer.is_closing.return_value = False
    writer.drain = AsyncMock()
    client.writer = writer

    captured: list[tuple[str, bytes]] = []

    capture = asyncio.create_task(client.capture_frames(lambda d, f: captured.append((d, f)), duration=0.05))
    # Yield once so capture_frames installs the sink before the producer runs.
    await asyncio.sleep(0)

    loop = asyncio.get_running_loop()
    frame_sent = loop.create_future()
    await client.tx_queue.put((b"hello SA1234B567 frame", frame_sent, None))

    client.tx_message_wait = 0
    client.tx_jitter = 0
    producer = asyncio.create_task(client._task_network_producer())
    try:
        await asyncio.wait_for(frame_sent, timeout=0.5)
        await capture
    finally:
        producer.cancel()
        try:
            await producer
        except asyncio.CancelledError:
            pass

    # The stream redactor may re-chunk the output (holds a trailing tail across
    # feeds, flushed at close), so reassemble before asserting. The joined stream
    # is identical-length to the raw frame with the serial's unit digits zeroed.
    assert all(d == "tx" for d, _ in captured)
    reassembled = b"".join(f for _, f in captured)
    assert reassembled == b"hello SA1234B000 frame"
    # Sink is detached after the capture completes.
    assert client._capture_sink is None


async def test_capture_frames_refuses_concurrent_capture():
    """A second capture started while one is in flight raises immediately."""
    client = Client(host="foo", port=4321)
    client._capture_sink = lambda _d, _f: None  # simulate an in-flight capture
    with pytest.raises(RuntimeError, match="already running"):
        await client.capture_frames(lambda _d, _f: None, duration=0.01)


async def test_capture_frames_releases_sink_on_cancellation():
    """If the capture task is cancelled mid-sleep, the sink slot is freed."""
    client = Client(host="foo", port=4321)
    capture = asyncio.create_task(client.capture_frames(lambda _d, _f: None, duration=10.0))
    await asyncio.sleep(0)  # let it install the sink
    assert client._capture_sink is not None
    capture.cancel()
    try:
        await capture
    except asyncio.CancelledError:
        pass
    assert client._capture_sink is None


# ---------------------------------------------------------------------------
# StreamRedactor — cross-chunk redaction (#117)
# ---------------------------------------------------------------------------


def _stream(chunks: list[bytes]) -> bytes:
    """Feed chunks through a StreamRedactor and reassemble the emitted output."""
    r = StreamRedactor()
    return b"".join(r.feed(c) for c in chunks) + r.flush()


def test_stream_redactor_catches_serial_split_across_chunks():
    """A serial split across two chunks is redacted (the leak the per-frame redact misses)."""
    # 'CE2242G612' split mid-serial: prefix in chunk 1, unit-bearing tail in chunk 2.
    out = _stream([b"pad CE22", b"42G612 pad"])
    assert b"CE2242G612" not in out
    assert b"CE2242G000" in out  # date kept, unit digits zeroed (#113)


def test_stream_redactor_reassembles_identically_to_whole_redact():
    """However the stream is chunked, the reassembled output equals redact(whole)."""
    whole = b"xx CE2242G612 yy EMS2522018 zz ,192.168.1.100, end"
    expected = redact(whole)
    for split in range(1, len(whole)):
        assert _stream([whole[:split], whole[split:]]) == expected
    # also multi-chunk
    assert _stream([whole[i : i + 3] for i in range(0, len(whole), 3)]) == expected


def test_stream_redactor_preserves_length_and_offsets():
    """The reassembled stream is byte-identical in length to the raw input."""
    raw = b"abc SA1234B567 def XY9876Z543 ghi"
    assert len(_stream([raw[:7], raw[7:20], raw[20:]])) == len(raw)


def test_stream_redactor_buffer_stays_bounded():
    """A long stream doesn't grow the internal buffer unbounded (prefix pruning)."""
    r = StreamRedactor()
    for _ in range(1000):
        r.feed(b"AB1234C567 some filler bytes ")
        assert len(r._buffer) < 100  # prunes to ~lookback regardless of stream length
    r.flush()


def test_stream_redactor_no_identifiers_passthrough():
    """Plain bytes with no identifiers reassemble unchanged."""
    raw = b"just some plain frame bytes with no serials at all"
    assert _stream([raw[:10], raw[10:]]) == raw


def test_emit_to_sink_swallows_sink_exceptions(caplog):
    """A sink callback that raises must not propagate out of the network tasks (#117 review)."""
    import logging

    client = Client(host="foo", port=4321)

    def boom(_direction, _data):
        raise RuntimeError("sink blew up")

    client._capture_sink = boom
    with caplog.at_level(logging.ERROR, logger="givenergy_modbus.client.client"):
        # Must not raise — the capture is a diagnostic tee, never load-bearing.
        client._emit_to_sink("rx", b"some redacted bytes")
    assert any("capture sink raised" in r.message for r in caplog.records)


def test_emit_to_sink_noops_without_sink_or_data():
    """No active sink, or empty data, is a silent no-op (doesn't call the sink)."""
    client = Client(host="foo", port=4321)
    calls = []
    # No sink installed → nothing happens even with data.
    client._emit_to_sink("rx", b"data")
    # Sink installed but empty data → not called (avoids spurious empty sink calls).
    client._capture_sink = lambda d, f: calls.append((d, f))
    client._emit_to_sink("tx", b"")
    assert calls == []
