import asyncio
import datetime
import logging
from asyncio import StreamReader
from unittest.mock import AsyncMock, MagicMock

import pytest

from givenergy_modbus.client.client import Client
from givenergy_modbus.model import TimeSlot
from givenergy_modbus.pdu.write_registers import WriteHoldingRegisterRequest, WriteHoldingRegisterResponse


async def test_expected_response():
    client = Client(host="foo", port=4321)
    assert client.expected_responses == {}
    req = WriteHoldingRegisterRequest(register=35, value=20)
    client.reader = StreamReader()
    network_consumer = asyncio.create_task(client._task_network_consumer())

    # enqueue the request
    send_and_wait = asyncio.create_task(client.send_request_and_await_response(req, timeout=0.1, retries=2))

    # simulate the message being transmitted
    tx_msg, tx_fut = await client.tx_queue.get()
    assert tx_msg == req.encode()
    client.tx_queue.task_done()
    tx_fut.set_result(True)

    # simulate receiving a response, which enables the consumer task to mark response_future as done
    client.reader.feed_data(WriteHoldingRegisterResponse(inverter_serial_number="", register=35, value=20).encode())
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


async def test_consumer_still_logs_critical_on_unexpected_eof(caplog):
    """When the reader hits EOF without a shutdown signal, CRITICAL is preserved."""
    client = Client(host="foo", port=4321)
    client.reader = StreamReader()
    client.reader.feed_eof()  # _shutting_down stays False

    with caplog.at_level(logging.DEBUG, logger="givenergy_modbus.client.client"):
        await client._task_network_consumer()

    assert any(r.levelno == logging.CRITICAL for r in caplog.records)


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


async def test_producer_still_logs_critical_on_unexpected_writer_close(caplog):
    """When the writer is closing without a shutdown signal, CRITICAL is preserved."""
    client = Client(host="foo", port=4321)
    writer = MagicMock()
    writer.is_closing.return_value = True
    client.writer = writer  # _shutting_down stays False

    with caplog.at_level(logging.DEBUG, logger="givenergy_modbus.client.client"):
        await client._task_network_producer()

    assert any(r.levelno == logging.CRITICAL for r in caplog.records)


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
