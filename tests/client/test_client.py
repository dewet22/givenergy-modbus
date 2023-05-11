import asyncio
import datetime
from asyncio import StreamReader

import pytest

from givenergy_modbus.client.client import Client
from givenergy_modbus.model import TimeSlot
from givenergy_modbus.pdu.write_registers import WriteHoldingRegisterRequest, WriteHoldingRegisterResponse


async def test_expected_response():
    client = Client(host='foo', port=4321)
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
    client.reader.feed_data(WriteHoldingRegisterResponse(inverter_serial_number='', register=35, value=20).encode())
    client.reader.feed_eof()

    # check the response
    res, _ = await asyncio.gather(send_and_wait, network_consumer)

    assert len(client.expected_responses) == 1
    assert res.shape_hash() in client.expected_responses.keys()
    expected_res_future = client.expected_responses[res.shape_hash()]
    assert expected_res_future._state == 'FINISHED'
    expected_res = await expected_res_future
    assert expected_res.has_same_shape(res)
    assert expected_res == res


def test_timeslot():
    ts = TimeSlot(datetime.time(4, 5), datetime.time(9, 8))
    assert ts == TimeSlot(start=datetime.time(4, 5), end=datetime.time(9, 8))
    assert ts == TimeSlot(datetime.time(4, 5), datetime.time(9, 8))
    assert ts == TimeSlot.from_components(4, 5, 9, 8)
    assert ts == TimeSlot.from_repr(405, 908)
    assert ts == TimeSlot.from_repr('405', '908')
    assert TimeSlot(datetime.time(0, 2), datetime.time(0, 2)) == TimeSlot.from_repr(2, 2)
    with pytest.raises(ValueError, match='hour must be in 0..23'):
        TimeSlot.from_repr(999999, 999999)
    with pytest.raises(ValueError, match='minute must be in 0..59'):
        TimeSlot.from_repr(999, 888)
    with pytest.raises(ValueError, match='hour must be in 0..23'):
        TimeSlot.from_components(99, 88, 77, 66)
    with pytest.raises(ValueError, match='minute must be in 0..59'):
        TimeSlot.from_components(11, 22, 11, 66)

    ts = TimeSlot(datetime.time(12, 34), datetime.time(23, 45))
    assert ts == TimeSlot(start=datetime.time(12, 34), end=datetime.time(23, 45))
    assert ts == TimeSlot(datetime.time(12, 34), datetime.time(23, 45))
    assert ts == TimeSlot.from_components(12, 34, 23, 45)
    assert ts == TimeSlot.from_repr(1234, 2345)
    assert ts == TimeSlot.from_repr('1234', '2345')
    with pytest.raises(ValueError, match='hour must be in 0..23'):
        assert ts == TimeSlot.from_components(43, 21, 54, 32)
    with pytest.raises(ValueError, match='hour must be in 0..23'):
        assert ts == TimeSlot.from_repr(4321, 5432)
    with pytest.raises(ValueError, match='hour must be in 0..23'):
        assert ts == TimeSlot.from_repr('4321', '5432')
