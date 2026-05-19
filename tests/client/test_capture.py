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
