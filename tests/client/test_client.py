import asyncio
import datetime
import logging
from asyncio import StreamReader
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from givenergy_modbus.client.client import Client
from givenergy_modbus.exceptions import ConnectionLost
from givenergy_modbus.model import TimeSlot
from givenergy_modbus.pdu import HeartbeatRequest, ReadInputRegistersResponse
from givenergy_modbus.pdu.write_registers import WriteHoldingRegisterRequest, WriteHoldingRegisterResponse


async def test_expected_response():
    client = Client(host="foo", port=4321)
    assert client.expected_responses == {}
    req = WriteHoldingRegisterRequest(register=35, value=20)
    client.reader = StreamReader()
    network_consumer = asyncio.create_task(client._task_network_consumer())

    # enqueue the request
    send_and_wait = asyncio.create_task(
        client.send_request_and_await_response(req, timeout=0.1, retries=2, retry_delay=0)
    )

    # simulate the message being transmitted
    tx_msg, tx_fut, _ = await client.tx_queue.get()
    assert tx_msg == req.encode()
    client.tx_queue.task_done()
    tx_fut.set_result(True)

    # simulate receiving a response, which enables the consumer task to mark response_future as done
    client.reader.feed_data(WriteHoldingRegisterResponse(inverter_serial_number="", register=35, value=20).encode())
    client._shutting_down = True
    client.reader.feed_eof()

    # check the response
    res, _ = await asyncio.gather(send_and_wait, network_consumer)

    assert len(client.expected_responses) == 1
    assert res.shape_hash() in client.expected_responses.keys()
    expected_res_future = client.expected_responses[res.shape_hash()]
    assert expected_res_future._state == "FINISHED"
    expected_res = await expected_res_future
    assert expected_res.has_same_shape(res)
    assert expected_res == res


async def test_consumer_auto_responds_to_heartbeat_request():
    """An inbound HeartbeatRequest is answered automatically by queueing a HeartbeatResponse frame."""
    client = Client(host="foo", port=4321)
    client.reader = StreamReader()
    client.reader.feed_data(HeartbeatRequest(data_adapter_serial_number="AB1234G567", data_adapter_type=2).encode())
    client._shutting_down = True
    client.reader.feed_eof()

    await client._task_network_consumer()

    # The consumer enqueues the heartbeat reply (frame, None, None) on the tx queue.
    assert not client.tx_queue.empty()
    frame, frame_sent, response_future = client.tx_queue.get_nowait()
    assert frame_sent is None and response_future is None
    # The reply round-trips back to a HeartbeatResponse echoing the adapter type.
    from givenergy_modbus.pdu import ClientOutgoingMessage

    reply = ClientOutgoingMessage.decode_bytes(frame)
    assert reply.data_adapter_type == 2


async def test_consumer_logs_warning_on_write_error_response(caplog):
    """A WriteHoldingRegisterResponse flagged as an error is surfaced at WARNING."""
    client = Client(host="foo", port=4321)
    client.reader = StreamReader()
    client.reader.feed_data(
        WriteHoldingRegisterResponse(inverter_serial_number="", register=35, value=20, error=True).encode()
    )
    client.reader.feed_eof()

    with caplog.at_level(logging.WARNING, logger="givenergy_modbus.client.client"):
        await client._task_network_consumer()

    assert any("WriteHoldingRegisterResponse" in r.message and r.levelno == logging.WARNING for r in caplog.records), (
        f"expected a WARNING for the errored write response, got: {[(r.levelname, r.message) for r in caplog.records]}"
    )


def test_timeslot():
    ts = TimeSlot(datetime.time(4, 5), datetime.time(9, 8))
    assert ts == TimeSlot(start=datetime.time(4, 5), end=datetime.time(9, 8))
    assert ts == TimeSlot(datetime.time(4, 5), datetime.time(9, 8))
    assert ts == TimeSlot.from_components(4, 5, 9, 8)
    assert ts == TimeSlot.from_repr(405, 908)
    assert ts == TimeSlot.from_repr("405", "908")
    assert TimeSlot(datetime.time(0, 2), datetime.time(0, 2)) == TimeSlot.from_repr(2, 2)
    with pytest.raises(ValueError, match="hour must be in 0..23"):
        TimeSlot.from_repr(999999, 999999)
    with pytest.raises(ValueError, match="minute must be in 0..59"):
        TimeSlot.from_repr(999, 888)
    with pytest.raises(ValueError, match="hour must be in 0..23"):
        TimeSlot.from_components(99, 88, 77, 66)
    with pytest.raises(ValueError, match="minute must be in 0..59"):
        TimeSlot.from_components(11, 22, 11, 66)

    ts = TimeSlot(datetime.time(12, 34), datetime.time(23, 45))
    assert ts == TimeSlot(start=datetime.time(12, 34), end=datetime.time(23, 45))
    assert ts == TimeSlot(datetime.time(12, 34), datetime.time(23, 45))
    assert ts == TimeSlot.from_components(12, 34, 23, 45)
    assert ts == TimeSlot.from_repr(1234, 2345)
    assert ts == TimeSlot.from_repr("1234", "2345")
    with pytest.raises(ValueError, match="hour must be in 0..23"):
        assert ts == TimeSlot.from_components(43, 21, 54, 32)
    with pytest.raises(ValueError, match="hour must be in 0..23"):
        assert ts == TimeSlot.from_repr(4321, 5432)
    with pytest.raises(ValueError, match="hour must be in 0..23"):
        assert ts == TimeSlot.from_repr("4321", "5432")


async def test_close_succeeds_when_connection_closed_cleanly():
    client = Client(host="foo", port=4321)
    writer = MagicMock()
    writer.wait_closed = AsyncMock()
    client.writer = writer
    client.reader = MagicMock()
    client.network_producer_task = MagicMock()
    client.network_consumer_task = MagicMock()

    await client.close()

    writer.close.assert_called_once()
    writer.wait_closed.assert_called_once()


async def test_close_handles_connection_reset_on_wait_closed():
    """close() must not propagate ConnectionResetError from wait_closed() when remote tears down first."""
    client = Client(host="foo", port=4321)
    writer = MagicMock()
    writer.wait_closed = AsyncMock(side_effect=ConnectionResetError)
    client.writer = writer
    client.reader = MagicMock()
    client.network_producer_task = MagicMock()
    client.network_consumer_task = MagicMock()

    await client.close()  # must not raise

    writer.close.assert_called_once()
    writer.wait_closed.assert_called_once()


def test_client_expected_responses_isolated_between_instances():
    """expected_responses must be per-instance, not shared at the class level."""
    client1 = Client(host="a", port=1)
    client2 = Client(host="b", port=2)
    client1.expected_responses[42] = "sentinel"
    assert 42 not in client2.expected_responses


async def test_consumer_logs_debug_not_critical_on_intentional_shutdown(caplog):
    """Regression for #50: when close() set _shutting_down, the consumer must exit at DEBUG, not CRITICAL."""
    client = Client(host="foo", port=4321)
    client.reader = StreamReader()
    client._shutting_down = True
    client.reader.feed_eof()

    with caplog.at_level(logging.DEBUG, logger="givenergy_modbus.client.client"):
        await client._task_network_consumer()

    assert not any(r.levelno >= logging.WARNING for r in caplog.records), (
        f"intentional shutdown should not emit WARNING+: {[(r.levelname, r.message) for r in caplog.records]}"
    )
    assert any("intentional shutdown" in r.message for r in caplog.records)


async def test_consumer_logs_warning_on_unexpected_eof(caplog):
    """A peer-initiated EOF (no shutdown signal) is a recoverable drop → WARNING, not CRITICAL."""
    client = Client(host="foo", port=4321)
    client.reader = StreamReader()
    client.reader.feed_eof()  # _shutting_down stays False

    with caplog.at_level(logging.DEBUG, logger="givenergy_modbus.client.client"):
        await client._task_network_consumer()

    assert any(r.levelno == logging.WARNING for r in caplog.records)
    assert not any(r.levelno >= logging.ERROR for r in caplog.records)  # a routine drop must not alarm


async def test_producer_logs_debug_not_critical_on_intentional_shutdown(caplog):
    """Regression for #50: when close() set _shutting_down, the producer must exit at DEBUG, not CRITICAL."""
    client = Client(host="foo", port=4321)
    writer = MagicMock()
    writer.is_closing.return_value = True
    client.writer = writer
    client._shutting_down = True

    with caplog.at_level(logging.DEBUG, logger="givenergy_modbus.client.client"):
        await client._task_network_producer()

    assert not any(r.levelno >= logging.WARNING for r in caplog.records), (
        f"intentional shutdown should not emit WARNING+: {[(r.levelname, r.message) for r in caplog.records]}"
    )
    assert any("intentional shutdown" in r.message for r in caplog.records)


async def test_producer_logs_warning_on_unexpected_writer_close(caplog):
    """A peer-initiated writer close (no shutdown signal) is a recoverable drop → WARNING, not CRITICAL."""
    client = Client(host="foo", port=4321)
    writer = MagicMock()
    writer.is_closing.return_value = True
    client.writer = writer  # _shutting_down stays False

    with caplog.at_level(logging.DEBUG, logger="givenergy_modbus.client.client"):
        await client._task_network_producer()

    assert any(r.levelno == logging.WARNING for r in caplog.records)
    assert not any(r.levelno >= logging.ERROR for r in caplog.records)  # a routine drop must not alarm


async def test_close_sets_shutting_down_flag():
    """close() must set _shutting_down so the task exit-paths take the quiet branch."""
    client = Client(host="foo", port=4321)
    writer = MagicMock()
    writer.wait_closed = AsyncMock()
    client.writer = writer
    client.reader = MagicMock()
    client.network_producer_task = MagicMock()
    client.network_consumer_task = MagicMock()

    assert client._shutting_down is False
    await client.close()
    assert client._shutting_down is True


def _stub_open_connection(reader=None, writer=None):
    """Build an AsyncMock for asyncio.open_connection returning a (reader, writer) pair."""
    reader = reader or MagicMock(spec=StreamReader)
    writer = writer or MagicMock()
    return AsyncMock(return_value=(reader, writer))


async def test_connect_resets_shutting_down_after_close():
    """Regression for #62: close() → connect() must clear _shutting_down so the new tasks log correctly on EOF."""
    client = Client(host="foo", port=4321)
    writer = MagicMock()
    writer.wait_closed = AsyncMock()
    client.writer = writer
    client.reader = MagicMock()
    client.network_producer_task = MagicMock()
    client.network_consumer_task = MagicMock()

    await client.close()
    assert client._shutting_down is True

    with patch("asyncio.open_connection", _stub_open_connection()):
        # Stub out the background tasks so we don't actually run the network loops.
        with patch.object(client, "_task_network_consumer", new=AsyncMock()):
            with patch.object(client, "_task_network_producer", new=AsyncMock()):
                await client.connect()

    assert client._shutting_down is False
    assert client.connected is True


async def test_connect_is_idempotent_on_already_connected_client():
    """Regression for #62: connect() on a live client must tear down the previous connection first."""
    client = Client(host="foo", port=4321)
    first_writer = MagicMock()
    first_writer.wait_closed = AsyncMock()
    client.writer = first_writer
    client.reader = MagicMock()
    client.network_producer_task = MagicMock()
    client.network_consumer_task = MagicMock()
    client.connected = True

    second_writer = MagicMock()
    second_reader = MagicMock(spec=StreamReader)

    with patch("asyncio.open_connection", _stub_open_connection(reader=second_reader, writer=second_writer)):
        with patch.object(client, "_task_network_consumer", new=AsyncMock()):
            with patch.object(client, "_task_network_producer", new=AsyncMock()):
                await client.connect()

    # The previous writer was closed as part of the teardown, and the new one is in place.
    first_writer.close.assert_called_once()
    assert client.writer is second_writer
    assert client.reader is second_reader
    assert client.connected is True
    assert client._shutting_down is False


async def test_connect_also_tears_down_leftover_resources_after_eof():
    """connect() must clean up leftover reader/writer/tasks even if connected=False.

    After an unexpected EOF the consumer sets connected=False but the
    writer/reader/producer-task can still exist. A subsequent connect() that
    only checks `connected` would skip the cleanup and start a second
    producer pair racing against the leftover state.
    """
    client = Client(host="foo", port=4321)
    leftover_writer = MagicMock()
    leftover_writer.wait_closed = AsyncMock()
    client.writer = leftover_writer
    client.reader = MagicMock()
    client.network_producer_task = MagicMock()
    client.network_consumer_task = MagicMock()
    client.connected = False  # ← EOF case: flag is already False, but resources remain

    new_writer = MagicMock()
    new_reader = MagicMock(spec=StreamReader)

    with patch("asyncio.open_connection", _stub_open_connection(reader=new_reader, writer=new_writer)):
        with patch.object(client, "_task_network_consumer", new=AsyncMock()):
            with patch.object(client, "_task_network_producer", new=AsyncMock()):
                await client.connect()

    leftover_writer.close.assert_called_once()
    assert client.writer is new_writer
    assert client.connected is True


async def test_consumer_does_not_resolve_future_for_crc_failed_frame():
    """A CRC-failed frame must leave the response future pending so retries fire."""
    client = Client(host="foo", port=4321)
    client.reader = StreamReader()

    msg = MagicMock(spec=ReadInputRegistersResponse)
    msg.error = False
    msg.crc_failed = True
    setattr(msg, "lenient_crc_commit", False)
    msg.device_address = 0x32
    msg.base_register = 0
    msg.shape_hash.return_value = 42

    future = asyncio.get_event_loop().create_future()
    client.expected_responses[42] = future

    async def fake_decode(frame):
        if frame:
            yield msg

    with patch.object(client.framer, "decode", new=fake_decode):
        client.reader.feed_data(b"\x00")
        client._shutting_down = True
        client.reader.feed_eof()
        await client._task_network_consumer()

    assert not future.done(), "future must stay pending for a CRC-failed frame"


async def test_consumer_clears_connected_on_unexpected_eof():
    """Bug fix: connected must be set to False when the consumer exits due to remote EOF."""
    client = Client(host="foo", port=4321)
    client.reader = StreamReader()
    client.reader.feed_eof()
    client.connected = True

    await client._task_network_consumer()

    assert client.connected is False  # nosec


async def test_producer_clears_connected_on_unexpected_writer_close():
    """Bug fix: connected must be set to False when the producer exits due to writer closing."""
    client = Client(host="foo", port=4321)
    writer = MagicMock()
    writer.is_closing.return_value = True
    client.writer = writer
    client.connected = True

    await client._task_network_producer()

    assert client.connected is False  # nosec


async def test_send_request_raises_timeout_when_tx_queue_is_full():
    """Bug fix: a full tx_queue must raise TimeoutError quickly, not block forever."""
    client = Client(host="foo", port=4321)
    # Fill the queue to capacity so the next put() will block.
    for _ in range(client.tx_queue.maxsize):
        client.tx_queue.put_nowait((b"", None, None))

    from givenergy_modbus.pdu.write_registers import WriteHoldingRegisterRequest

    req = WriteHoldingRegisterRequest(register=35, value=20)

    async def timeout_wait_for(awaitable, timeout):
        # Simulate the 5s timeout without leaking the Queue.put coroutine that
        # send_request_and_await_response passes into asyncio.wait_for().
        awaitable.close()
        raise TimeoutError

    # Patch wait_for to immediately raise TimeoutError, simulating the 5s timeout
    # elapsing without the producer draining the queue.
    with patch("givenergy_modbus.client.client.asyncio.wait_for", new=timeout_wait_for):
        with pytest.raises(TimeoutError, match="TX queue full"):
            await client.send_request_and_await_response(req, timeout=1.0, retries=0)


async def test_close_does_not_raise_when_tasks_were_never_created():
    """Bug fix: close() must not raise AttributeError when connect() failed before tasks were created."""
    client = Client(host="foo", port=4321)
    # Simulate a half-initialised client: writer exists, but no task attributes.
    writer = MagicMock()
    writer.wait_closed = AsyncMock()
    client.writer = writer
    client.reader = MagicMock()

    await client.close()  # must not raise


async def test_send_request_raises_timeout_after_all_retries_exhausted():
    """When all retry attempts time out, the final TimeoutError is raised."""
    client = Client(host="foo", port=4321)
    req = WriteHoldingRegisterRequest(register=35, value=20)

    async def drain_queue():
        while True:
            _, frame_sent, _ = await client.tx_queue.get()
            client.tx_queue.task_done()
            if frame_sent and not frame_sent.done():
                frame_sent.set_result(True)

    drainer = asyncio.create_task(drain_queue())
    try:
        with pytest.raises(TimeoutError):
            await client.send_request_and_await_response(req, timeout=0.02, retries=1, retry_delay=0)
    finally:
        drainer.cancel()


async def test_send_request_succeeds_after_timeout_retry():
    """When the first attempt times out but the retry receives a response, the result is returned."""
    client = Client(host="foo", port=4321)
    req = WriteHoldingRegisterRequest(register=35, value=20)
    expected_hash = req.expected_response().shape_hash()
    attempt = 0

    async def drain_and_respond():
        nonlocal attempt
        while True:
            _, frame_sent, _ = await client.tx_queue.get()
            client.tx_queue.task_done()
            if frame_sent and not frame_sent.done():
                frame_sent.set_result(True)
            attempt += 1
            if attempt >= 2:
                # First attempt times out; resolve the response on retry.
                await asyncio.sleep(0)
                future = client.expected_responses.get(expected_hash)
                if future and not future.done():
                    future.set_result(WriteHoldingRegisterResponse(inverter_serial_number="", register=35, value=20))

    drainer = asyncio.create_task(drain_and_respond())
    try:
        result = await client.send_request_and_await_response(req, timeout=0.02, retries=2, retry_delay=0)
        assert result.register == 35  # nosec
    finally:
        drainer.cancel()


async def test_send_request_retries_on_error_response():
    """When the response has error=True the request is retried, then gives up with TimeoutError."""
    client = Client(host="foo", port=4321)
    req = WriteHoldingRegisterRequest(register=35, value=20)
    expected_hash = req.expected_response().shape_hash()

    async def drain_and_error():
        while True:
            _, frame_sent, _ = await client.tx_queue.get()
            client.tx_queue.task_done()
            if frame_sent and not frame_sent.done():
                frame_sent.set_result(True)
            await asyncio.sleep(0)
            future = client.expected_responses.get(expected_hash)
            if future and not future.done():
                error_resp = WriteHoldingRegisterResponse(inverter_serial_number="", register=35, value=20)
                error_resp.error = True
                future.set_result(error_resp)

    drainer = asyncio.create_task(drain_and_error())
    try:
        with pytest.raises(TimeoutError):
            await client.send_request_and_await_response(req, timeout=0.02, retries=1, retry_delay=0)
    finally:
        drainer.cancel()


async def test_retry_count_increments_on_consumed_retry():
    """A consumed retry bumps the plant's per-device retry_count (#284)."""
    client = Client(host="foo", port=4321)
    req = WriteHoldingRegisterRequest(register=35, value=20)
    expected_hash = req.expected_response().shape_hash()
    attempt = 0

    async def drain_and_respond():
        nonlocal attempt
        while True:
            _, frame_sent, _ = await client.tx_queue.get()
            client.tx_queue.task_done()
            if frame_sent and not frame_sent.done():
                frame_sent.set_result(True)
            attempt += 1
            if attempt >= 2:  # first attempt times out; resolve on the retry
                await asyncio.sleep(0)
                future = client.expected_responses.get(expected_hash)
                if future and not future.done():
                    future.set_result(WriteHoldingRegisterResponse(inverter_serial_number="", register=35, value=20))

    drainer = asyncio.create_task(drain_and_respond())
    try:
        await client.send_request_and_await_response(req, timeout=0.02, retries=2, retry_delay=0)
    finally:
        drainer.cancel()
    assert client.plant.retry_count == {req.device_address: 1}


async def test_retry_count_excludes_probe_retries():
    """Absent-device probes (warn_timeout=False) must not pollute retry_count (#284)."""
    client = Client(host="foo", port=4321)
    req = WriteHoldingRegisterRequest(register=35, value=20)

    async def drain_queue():
        while True:
            _, frame_sent, _ = await client.tx_queue.get()
            client.tx_queue.task_done()
            if frame_sent and not frame_sent.done():
                frame_sent.set_result(True)

    drainer = asyncio.create_task(drain_queue())
    try:
        with pytest.raises(TimeoutError):
            await client.send_request_and_await_response(
                req, timeout=0.02, retries=1, retry_delay=0, warn_timeout=False
            )
    finally:
        drainer.cancel()
    assert client.plant.retry_count == {}


async def test_retry_count_excludes_probe_on_error_response_with_delay():
    """An error-response retry with warn_timeout=False and a retry delay still skips retry_count (#284)."""
    client = Client(host="foo", port=4321)
    req = WriteHoldingRegisterRequest(register=35, value=20)
    expected_hash = req.expected_response().shape_hash()

    async def drain_and_error():
        while True:
            _, frame_sent, _ = await client.tx_queue.get()
            client.tx_queue.task_done()
            if frame_sent and not frame_sent.done():
                frame_sent.set_result(True)
            await asyncio.sleep(0)
            future = client.expected_responses.get(expected_hash)
            if future and not future.done():
                error_resp = WriteHoldingRegisterResponse(inverter_serial_number="", register=35, value=20)
                error_resp.error = True
                future.set_result(error_resp)

    drainer = asyncio.create_task(drain_and_error())
    try:
        with pytest.raises(TimeoutError):
            await client.send_request_and_await_response(
                req, timeout=0.02, retries=1, retry_delay=0.01, warn_timeout=False
            )
    finally:
        drainer.cancel()
    assert client.plant.retry_count == {}


def test_client_forwards_splice_heal_seconds():
    """Client(splice_heal_seconds=…) overrides the plant's value only when explicitly given (#286)."""
    from givenergy_modbus.model.plant import Plant

    assert Client(host="foo", port=4321).plant.splice_heal_seconds == 900.0  # Plant default stands
    assert Client(host="foo", port=4321, splice_heal_seconds=42.0).plant.splice_heal_seconds == 42.0
    # An injected plant's own value is preserved when the Client param is omitted (not clobbered).
    injected = Plant(splice_heal_seconds=123.0)
    assert Client(host="foo", port=4321, plant=injected).plant.splice_heal_seconds == 123.0
    # An explicit Client param still wins over an injected plant's value.
    assert (
        Client(
            host="foo", port=4321, plant=Plant(splice_heal_seconds=123.0), splice_heal_seconds=7.0
        ).plant.splice_heal_seconds
        == 7.0
    )


def test_client_forwards_splice_reject_heal_seconds():
    """Client(splice_reject_heal_seconds=…) overrides the plant's value only when given (#299)."""
    from givenergy_modbus.model.plant import Plant

    assert Client(host="foo", port=4321).plant.splice_reject_heal_seconds is None  # default: disabled
    assert Client(host="foo", port=4321, splice_reject_heal_seconds=300.0).plant.splice_reject_heal_seconds == 300.0
    # An injected plant's own value is preserved when the Client param is omitted (not clobbered).
    injected = Plant(splice_reject_heal_seconds=600.0)
    assert Client(host="foo", port=4321, plant=injected).plant.splice_reject_heal_seconds == 600.0
    # An explicit Client param still wins over an injected plant's value.
    assert (
        Client(
            host="foo", port=4321, plant=Plant(splice_reject_heal_seconds=600.0), splice_reject_heal_seconds=300.0
        ).plant.splice_reject_heal_seconds
        == 300.0
    )


async def test_send_request_sleeps_between_retries_on_timeout():
    """A retry_delay > 0 must impose a sleep between a timed-out attempt and the next.

    This protects against the multi-second silent-window failure mode where firing
    the retry immediately would land it inside the same window as the original.
    """
    client = Client(host="foo", port=4321)
    req = WriteHoldingRegisterRequest(register=35, value=20)
    send_times: list[float] = []

    async def drain_queue():
        while True:
            _, frame_sent, _ = await client.tx_queue.get()
            client.tx_queue.task_done()
            send_times.append(asyncio.get_running_loop().time())
            if frame_sent and not frame_sent.done():
                frame_sent.set_result(True)

    drainer = asyncio.create_task(drain_queue())
    try:
        with pytest.raises(TimeoutError):
            # 20ms timeout, one retry, 80ms delay → second send happens ~100ms after first.
            await client.send_request_and_await_response(req, timeout=0.02, retries=1, retry_delay=0.08)
        assert len(send_times) == 2
        gap = send_times[1] - send_times[0]
        assert gap >= 0.08, f"expected gap of at least 80ms between retries, got {gap * 1000:.0f}ms"
    finally:
        drainer.cancel()


async def test_producer_skips_wire_send_when_response_already_resolved():
    """Producer must skip the wire write when response_future is already done.

    Models the late-arrival case where a response from a previous attempt
    resolved the future between enqueue and dequeue — no point writing a
    duplicate request whose answer we already have. frame_sent still gets
    released so the caller-side awaiter unblocks normally.
    """
    client = Client(host="foo", port=4321)
    writer = MagicMock()
    writer.is_closing.return_value = False
    writer.drain = AsyncMock()
    client.writer = writer

    loop = asyncio.get_running_loop()
    resolved_response = loop.create_future()
    resolved_response.set_result("already here")
    frame_sent = loop.create_future()
    await client.tx_queue.put((b"the-frame", frame_sent, resolved_response))

    client.tx_message_wait = 0
    client.tx_jitter = 0
    producer = asyncio.create_task(client._task_network_producer())
    try:
        await asyncio.wait_for(frame_sent, timeout=0.5)
    finally:
        producer.cancel()
        try:
            await producer
        except asyncio.CancelledError:
            pass

    writer.write.assert_not_called()
    assert frame_sent.result() is True


async def test_producer_sends_normally_when_response_future_pending():
    """Sanity check the inverse: when response_future is pending, the producer writes."""
    client = Client(host="foo", port=4321)
    writer = MagicMock()
    writer.is_closing.return_value = False
    writer.drain = AsyncMock()
    client.writer = writer

    loop = asyncio.get_running_loop()
    pending_response = loop.create_future()
    frame_sent = loop.create_future()
    await client.tx_queue.put((b"the-frame", frame_sent, pending_response))

    client.tx_message_wait = 0
    client.tx_jitter = 0
    producer = asyncio.create_task(client._task_network_producer())
    try:
        await asyncio.wait_for(frame_sent, timeout=0.5)
    finally:
        producer.cancel()
        try:
            await producer
        except asyncio.CancelledError:
            pass

    writer.write.assert_called_once_with(b"the-frame")
    assert frame_sent.result() is True


def test_client_tx_pacing_defaults_and_overrides():
    """tx_message_wait and tx_jitter expose the producer's pacing knobs (issue #71)."""
    default = Client(host="foo", port=4321)
    assert default.tx_message_wait == 0.25
    assert default.tx_jitter == 0.1

    custom = Client(host="foo", port=4321, tx_message_wait=0.5, tx_jitter=0.0)
    assert custom.tx_message_wait == 0.5
    assert custom.tx_jitter == 0.0


async def test_producer_inter_frame_sleep_includes_jitter_within_bounds():
    """Producer must sleep in [tx_message_wait, tx_message_wait + tx_jitter) between frames.

    Asymmetric-only jitter: the minimum gap stays at tx_message_wait so the
    historic 250ms floor isn't violated; the upper bound is tx_message_wait +
    tx_jitter so concurrent bursts disperse without unbounded growth.
    """
    client = Client(host="foo", port=4321, tx_message_wait=0.25, tx_jitter=0.1)
    writer = MagicMock()
    writer.is_closing.return_value = False
    writer.drain = AsyncMock()
    client.writer = writer

    loop = asyncio.get_running_loop()
    pending = loop.create_future()
    frame_sent = loop.create_future()
    await client.tx_queue.put((b"frame", frame_sent, pending))

    sleep_durations: list[float] = []

    async def capture_sleep(delay):
        # NB: must not call asyncio.sleep here — the patch is global to the
        # asyncio module, which would recurse. Returning without yielding is
        # fine because the producer's next loop iteration awaits tx_queue.get()
        # on an empty queue, which yields control naturally for cancellation.
        sleep_durations.append(delay)

    with patch("givenergy_modbus.client.client.asyncio.sleep", new=capture_sleep):
        producer = asyncio.create_task(client._task_network_producer())
        try:
            await asyncio.wait_for(frame_sent, timeout=0.5)
        finally:
            producer.cancel()
            try:
                await producer
            except asyncio.CancelledError:
                pass

    assert sleep_durations, "producer never called asyncio.sleep"
    pacing_sleep = sleep_durations[0]
    assert 0.25 <= pacing_sleep < 0.25 + 0.1


async def test_producer_inter_frame_sleep_is_deterministic_when_jitter_zero():
    """tx_jitter=0 must produce a fixed inter-frame sleep equal to tx_message_wait."""
    client = Client(host="foo", port=4321, tx_message_wait=0.25, tx_jitter=0.0)
    writer = MagicMock()
    writer.is_closing.return_value = False
    writer.drain = AsyncMock()
    client.writer = writer

    loop = asyncio.get_running_loop()
    pending = loop.create_future()
    frame_sent = loop.create_future()
    await client.tx_queue.put((b"frame", frame_sent, pending))

    sleep_durations: list[float] = []

    async def capture_sleep(delay):
        # See sibling test above re: not recursing into asyncio.sleep.
        sleep_durations.append(delay)

    with patch("givenergy_modbus.client.client.asyncio.sleep", new=capture_sleep):
        producer = asyncio.create_task(client._task_network_producer())
        try:
            await asyncio.wait_for(frame_sent, timeout=0.5)
        finally:
            producer.cancel()
            try:
                await producer
            except asyncio.CancelledError:
                pass

    assert sleep_durations[0] == 0.25


async def test_send_request_no_sleep_after_final_retry_exhausted():
    """retry_delay only applies between retries — no sleep after the last attempt fails.

    Otherwise every timed-out call would pay an extra retry_delay before raising,
    inflating wall-clock for callers that just want to fail fast.
    """
    client = Client(host="foo", port=4321)
    req = WriteHoldingRegisterRequest(register=35, value=20)

    async def drain_queue():
        while True:
            _, frame_sent, _ = await client.tx_queue.get()
            client.tx_queue.task_done()
            if frame_sent and not frame_sent.done():
                frame_sent.set_result(True)

    drainer = asyncio.create_task(drain_queue())
    try:
        start = asyncio.get_running_loop().time()
        with pytest.raises(TimeoutError):
            # retries=0, large retry_delay — should never sleep since we never retry.
            await client.send_request_and_await_response(req, timeout=0.02, retries=0, retry_delay=5.0)
        elapsed = asyncio.get_running_loop().time() - start
        assert elapsed < 0.1, f"expected fast fail (~20ms), took {elapsed * 1000:.0f}ms"
    finally:
        drainer.cancel()


async def test_frame_sent_timeout_cleans_up_stale_future(monkeypatch):
    """A stuck producer raises a clear TimeoutError and cleans up the stale response future.

    When the frame is never sent, the wait must remove the future from expected_responses so a
    late send can't resolve a stale request. Regression for the review finding on PR #225: the
    bare frame_sent wait left the future registered and uncancelled on timeout.
    """
    from givenergy_modbus.client import client as client_mod

    # Shrink the floor so the stuck path fires in ~20ms; zero inter-frame delay → no backlog term.
    monkeypatch.setattr(client_mod, "_FRAME_SENT_MIN_TIMEOUT", 0.02)
    client = Client(host="foo", port=4321, tx_message_wait=0, tx_jitter=0)
    req = WriteHoldingRegisterRequest(register=35, value=20)
    expected_hash = req.expected_response().shape_hash()

    # No producer task is running, so frame_sent is never resolved → stuck-producer path.
    with pytest.raises(TimeoutError, match="stuck"):
        await client.send_request_and_await_response(req, timeout=1.0, retries=0)

    assert expected_hash not in client.expected_responses, "stale response future must be cleaned up"


async def test_frame_sent_timeout_does_not_evict_newer_future(monkeypatch):
    """A timed-out call must not evict a newer same-shaped caller's response future (PR #225).

    Same-shaped requests deliberately replace one another. If call A is still waiting on
    frame_sent when call B installs its own future under the shared shape_hash, A's timeout
    cleanup must be identity-conditional — it must not delete B's mapping.
    """
    from givenergy_modbus.client import client as client_mod

    monkeypatch.setattr(client_mod, "_FRAME_SENT_MIN_TIMEOUT", 0.05)
    client = Client(host="foo", port=4321, tx_message_wait=0, tx_jitter=0)
    req = WriteHoldingRegisterRequest(register=35, value=20)
    shape_hash = req.expected_response().shape_hash()

    # Call A installs its future and blocks on frame_sent (no producer running).
    task_a = asyncio.create_task(client.send_request_and_await_response(req, timeout=1.0, retries=0))
    await asyncio.sleep(0.01)  # let A reach the frame_sent wait

    # Call B replaces the mapping under the same shape_hash.
    b_future: asyncio.Future = asyncio.get_running_loop().create_future()
    client.expected_responses[shape_hash] = b_future

    with pytest.raises(TimeoutError):
        await task_a  # A times out (~0.05s)

    assert client.expected_responses.get(shape_hash) is b_future, "A's cleanup must not evict B's future"
    b_future.cancel()


def test_connection_lost_is_communication_error_and_timeout():
    """Dual inheritance is the compat contract (#356): typed for new consumers.

    Still a TimeoutError so legacy `except TimeoutError` paths keep working.
    """
    from givenergy_modbus.exceptions import CommunicationError

    exc = ConnectionLost("connection dropped")
    assert isinstance(exc, CommunicationError)
    assert isinstance(exc, TimeoutError)


def test_connection_lost_caught_by_legacy_timeout_handler():
    """A consumer catching bare TimeoutError (e.g. released hass coordinator).

    Must catch it.
    """
    try:
        raise ConnectionLost("connection dropped")
    except TimeoutError as e:
        assert "connection dropped" in str(e)


async def test_abort_connection_fails_inflight_and_queued_with_connection_lost():
    """_abort_connection unblocks every waiter fast with the typed exception (#356)."""
    client = Client(host="foo", port=4321)
    inflight = asyncio.get_running_loop().create_future()
    client.expected_responses[1234] = inflight
    q_frame_sent = asyncio.get_running_loop().create_future()
    q_response = asyncio.get_running_loop().create_future()
    client.tx_queue.put_nowait((b"frame", q_frame_sent, q_response))

    client._abort_connection(ConnectionLost("test drop"))

    assert client._connection_lost is True
    assert client.connected is False
    assert isinstance(inflight.exception(), ConnectionLost)
    assert isinstance(q_frame_sent.exception(), ConnectionLost)
    assert isinstance(q_response.exception(), ConnectionLost)
    assert client.expected_responses == {}
    assert client.tx_queue.empty()


async def test_abort_connection_is_idempotent_and_respects_shutdown():
    """Second call is a no-op; a call during intentional close() is a no-op."""
    client = Client(host="foo", port=4321)
    client._abort_connection(ConnectionLost("first"))
    client._abort_connection(ConnectionLost("second"))  # must not raise (futures done, dict clear)
    assert client._connection_lost is True

    quiet = Client(host="bar", port=4321)
    quiet._shutting_down = True
    fut = asyncio.get_running_loop().create_future()
    quiet.expected_responses[1] = fut
    quiet._abort_connection(ConnectionLost("during close"))
    assert quiet._connection_lost is False  # early-returned
    assert not fut.done()  # close() owns intentional-shutdown cleanup


async def test_abort_connection_cancels_only_the_other_task():
    """The task NOT calling abort is cancelled; the caller is left to exit on its own."""
    client = Client(host="foo", port=4321)

    async def _sleeper():
        await asyncio.sleep(30)

    other = asyncio.create_task(_sleeper())
    client.network_consumer_task = other
    client.network_producer_task = None

    client._abort_connection(ConnectionLost("drop"))
    await asyncio.sleep(0)  # let cancellation propagate
    assert other.cancelled()


async def test_connect_resets_connection_lost_flag():
    """connect() re-arms the client after a prior abort (mirrors _shutting_down reset)."""
    client = Client(host="foo", port=4321)
    client._connection_lost = True
    reader, writer = MagicMock(spec=StreamReader), MagicMock()
    writer.wait_closed = AsyncMock()
    with patch("asyncio.open_connection", _stub_open_connection(reader, writer)):
        await client.connect()  # existing _stub_open_connection pattern; no wait_for patch needed
    assert client._connection_lost is False
    await client.close()


async def test_producer_drain_stall_aborts_connection(monkeypatch, caplog):
    """A wedged writer.drain() (half-open socket, hass#233) is bounded.

    The producer treats the stall as connection loss, fails the current frame's
    frame_sent, and tears down — instead of hanging until close().
    """
    monkeypatch.setattr("givenergy_modbus.client.client._DRAIN_TIMEOUT", 0.05)
    client = Client(host="foo", port=4321)
    writer = MagicMock()
    writer.is_closing.return_value = False
    never = asyncio.get_running_loop().create_future()  # drain() that never completes
    writer.drain = MagicMock(return_value=never)
    client.writer = writer

    frame_sent = asyncio.get_running_loop().create_future()
    response_future = asyncio.get_running_loop().create_future()
    client.expected_responses[99] = response_future
    client.tx_queue.put_nowait((b"frame", frame_sent, response_future))

    with caplog.at_level(logging.DEBUG, logger="givenergy_modbus.client.client"):
        await asyncio.wait_for(client._task_network_producer(), timeout=2.0)

    assert isinstance(frame_sent.exception(), ConnectionLost)  # current frame unblocked
    assert isinstance(response_future.exception(), ConnectionLost)
    assert client._connection_lost is True
    assert client.connected is False
    assert any("drain stalled" in r.message for r in caplog.records if r.levelno == logging.WARNING)


async def test_producer_unexpected_writer_close_aborts_connection():
    """The existing writer-closing exit path now also runs the shared teardown."""
    client = Client(host="foo", port=4321)
    writer = MagicMock()
    writer.is_closing.return_value = True
    client.writer = writer
    inflight = asyncio.get_running_loop().create_future()
    client.expected_responses[7] = inflight

    await client._task_network_producer()

    assert client._connection_lost is True
    assert isinstance(inflight.exception(), ConnectionLost)


async def test_consumer_unexpected_eof_aborts_connection():
    """Unexpected reader EOF runs the shared teardown.

    In-flight senders unblock immediately with ConnectionLost instead of
    burning their full timeouts.
    """
    client = Client(host="foo", port=4321)
    client.reader = StreamReader()
    inflight = asyncio.get_running_loop().create_future()
    client.expected_responses[11] = inflight
    client.reader.feed_eof()  # _shutting_down stays False

    await client._task_network_consumer()

    assert client._connection_lost is True
    assert isinstance(inflight.exception(), ConnectionLost)
