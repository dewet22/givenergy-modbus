import asyncio
import datetime

import pytest

from givenergy_modbus.client import Timeslot
from givenergy_modbus.client.coordinator import Coordinator
from givenergy_modbus.model.register import HoldingRegister
from givenergy_modbus.pdu.write_registers import WriteHoldingRegisterRequest, WriteHoldingRegisterResponse


async def test_expected_response():
    transmitted_frames = []

    async def mock_transmit_frame(frame: bytes):
        transmitted_frames.append(frame)

    async def mock_await_frames():
        yield WriteHoldingRegisterResponse(inverter_serial_number='', register=HoldingRegister(35), value=20).encode()

    client = Coordinator()
    assert client.expected_responses == {}
    req = WriteHoldingRegisterRequest(register=HoldingRegister(35), value=20)
    client.network_client.transmit_frame = mock_transmit_frame
    client.network_client.await_frames = mock_await_frames

    res, _ = await asyncio.gather(
        client.do_request(req, timeout=0.1, retries=2),
        client.process_incoming_data_loop(),
    )

    assert transmitted_frames == [req.encode()]
    assert len(client.expected_responses) == 1
    assert res.shape_hash() in client.expected_responses.keys()
    expected_res_future = client.expected_responses[res.shape_hash()]
    assert expected_res_future._state == 'FINISHED'
    expected_res = await expected_res_future
    assert expected_res.has_same_shape(res)
    assert expected_res == res


def test_timeslot():
    ts = Timeslot(datetime.time(4, 5), datetime.time(9, 8))
    assert ts == Timeslot(start=datetime.time(4, 5), end=datetime.time(9, 8))
    assert ts == Timeslot(datetime.time(4, 5), datetime.time(9, 8))
    assert ts == Timeslot.from_components(4, 5, 9, 8)
    assert ts == Timeslot.from_repr(405, 908)
    assert ts == Timeslot.from_repr('405', '908')
    with pytest.raises(ValueError, match='invalid literal'):
        Timeslot.from_repr(2, 2)
    with pytest.raises(ValueError, match='hour must be in 0..23'):
        Timeslot.from_repr(999999, 999999)
    with pytest.raises(ValueError, match='minute must be in 0..59'):
        Timeslot.from_repr(999, 888)
    with pytest.raises(ValueError, match='hour must be in 0..23'):
        Timeslot.from_components(99, 88, 77, 66)
    with pytest.raises(ValueError, match='minute must be in 0..59'):
        Timeslot.from_components(11, 22, 11, 66)

    ts = Timeslot(datetime.time(12, 34), datetime.time(23, 45))
    assert ts == Timeslot(start=datetime.time(12, 34), end=datetime.time(23, 45))
    assert ts == Timeslot(datetime.time(12, 34), datetime.time(23, 45))
    assert ts == Timeslot.from_components(12, 34, 23, 45)
    assert ts == Timeslot.from_repr(1234, 2345)
    assert ts == Timeslot.from_repr('1234', '2345')
    with pytest.raises(ValueError, match='hour must be in 0..23'):
        assert ts == Timeslot.from_components(43, 21, 54, 32)
    with pytest.raises(ValueError, match='hour must be in 0..23'):
        assert ts == Timeslot.from_repr(4321, 5432)
    with pytest.raises(ValueError, match='hour must be in 0..23'):
        assert ts == Timeslot.from_repr('4321', '5432')
