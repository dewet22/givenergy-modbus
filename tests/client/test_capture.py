"""Tests for client-side wire capture."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from givenergy_modbus.client.client import Client, redact

# ---------------------------------------------------------------------------
# redact()
# ---------------------------------------------------------------------------


def test_redact_single_serial():
    """A standalone serial gets its digits zeroed; surrounding letters preserved."""
    frame = b"prefix EA1234B567 suffix"
    redacted = redact(frame)
    assert redacted == b"prefix EA0000B000 suffix"
    assert len(redacted) == len(frame)


def test_redact_dual_serial():
    """Both dongle and inverter serials in the same frame are rewritten."""
    frame = b"dongle SA1111R222 inverter SA3333A444"
    redacted = redact(frame)
    assert redacted == b"dongle SA0000R000 inverter SA0000A000"
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
    assert redacted == b"\x01\x02 SA0000X000 \x03\x04 SA0000Z000 \x05"


def test_redact_ems_serial():
    """EMS plant controller serials are redacted via a dedicated 3+7 pattern.

    EMS units use a 3-letter + 7-digit format that the standard pattern
    doesn't match (e.g. ``EMS2522018``). The dedicated pattern zeroes the
    seven trailing digits while preserving the prefix letters.
    """
    frame = b"prefix EMS2522018 suffix"
    redacted = redact(frame)
    assert redacted == b"prefix EMS0000000 suffix"
    assert len(redacted) == len(frame)


def test_redact_mixed_standard_and_ems_serials():
    """Standard and EMS serials in the same frame are each rewritten.

    Either pattern leaves the other's structure alone, so a single redact()
    call covers a frame that mentions both shapes.
    """
    frame = b"adapter FO2522G018 ems EMS2522018 inverter CE2231G454"
    redacted = redact(frame)
    assert redacted == b"adapter FO0000G000 ems EMS0000000 inverter CE0000G000"
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
    """A frame containing both serial-shaped runs and IPv4 gets both redacted in one pass."""
    frame = b"from FO2522G018 to 10.0.0.1 by EMS2522018"
    redacted = redact(frame)
    assert redacted == b"from FO0000G000 to 00.0.0.0 by EMS0000000"
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

    producer = asyncio.create_task(client._task_network_producer(tx_message_wait=0))
    try:
        await asyncio.wait_for(frame_sent, timeout=0.5)
        await capture
    finally:
        producer.cancel()
        try:
            await producer
        except asyncio.CancelledError:
            pass

    assert captured == [("tx", b"hello SA0000B000 frame")]
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
