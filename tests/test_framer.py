"""Tests for GivEnergyModbusFramer."""
import logging
from typing import Any, Dict, Optional, Type, Union

import pytest

from givenergy_modbus.exceptions import ExceptionBase
from givenergy_modbus.framer import ClientFramer, Framer, ServerFramer
from givenergy_modbus.pdu import (
    BasePDU,
    HeartbeatRequest,
    NullResponse,
    ReadHoldingRegistersResponse,
    ReadInputRegistersResponse,
)
from tests.conftest import CLIENT_MESSAGES, SERVER_MESSAGES, PduTestCaseSig, _h2b

VALID_REQUEST_FRAME = (  # actual recorded request frame, look up 6 input registers starting at #0
    b'\x59\x59\x00\x01\x00\x1c\x01\x02'  # 7-byte MBAP header + function code
    b'\x41\x42\x31\x32\x33\x34\x47\x35\x36\x37'  # 10-byte serial number: AB1234G567
    b'\x00\x00\x00\x00\x00\x00\x00\x08'  # 8-byte padding / crc / check?
    b'\x32'  # slave address
    b'\x04'  # sub-function: query input registers
    b'\x00\x00'  # start register: 0
    b'\x00\x06'  # step: 6
    b'\xc2\x55'  # crc
)  # 34 bytes

VALID_RESPONSE_FRAME = (  # actual recorded response frame, to request above
    b'\x59\x59\x00\x01\x00\x32\x01\x02'  # 7-byte MBAP header + function code
    b'\x57\x46\x31\x32\x33\x34\x47\x35\x36\x37'  # 10-byte serial number WF1234G567
    b'\x00\x00\x00\x00\x00\x00\x00\x1e'  # 8-byte padding / crc / check?
    b'\x32'  # slave address
    b'\x04'  # sub-function
    b'\x53\x41\x31\x32\x33\x34\x45\x35\x36\x37'  # 10-byte serial number SA1234G567
    b'\x00\x00'  # start register: 0
    b'\x00\x06'  # step: 6
    b'\x00\x01'  # register 0: 1 (inverter status, == OK?)
    b'\x0b\xee'  # register 1: 3054 (V_pv1, with 0.1 scaling == 305.4V)
    b'\x0b\xd5'  # register 2: 3029 (V_pv2, with 0.1 scaling == 302.9V)
    b'\x0f\x29'  # register 3: 3881 (V_P-bus_inside, with 0.1 scaling == 388.1)
    b'\x00\x00'  # register 4: 0 (V_N-bus_inside, with 0.1 scaling == 0.0)
    b'\x09\x55'  # register 5: 2389 (V_grid (single-phase), with 0.1 scaling == 238.9)
    b'\xb5\xd2'  # crc
)  # 56 bytes

EXCEPTION_RESPONSE_FRAME = (  # actual recorded response frame, to request above
    b'\x59\x59\x00\x01\x00\x26\x01\x02'  # 7-byte MBAP header + function code
    b'\x57\x46\x31\x32\x33\x34\x47\x35\x36\x37'  # 10-byte serial number WF1234G567
    b'\x00\x00\x00\x00\x00\x00\x00\x12'  # 8-byte padding / crc / check?
    b'\x32'  # slave address
    b'\x84'  # sub-function
    b'\x53\x41\x31\x32\x33\x34\x45\x35\x36\x37'  # 10-byte serial number SA1234G567
    b'\x00\x00'  # start register: 0
    b'\x00\x78'  # step: 120 – GivEnergy protocol only supports up to 60.
    b'\xf1\x33'  # crc
)  # 44 bytes


async def validate_decoding(
    framer: Framer,
    raw_frame: bytes,
    pdu_class: Type[BasePDU],
    constructor_kwargs: Dict[str, Any],
    ex: Optional[ExceptionBase],
):
    results = []
    async for result in framer.decode(raw_frame):
        results.append(result)
    assert len(results) == 1
    pdu = results[0]

    if ex:
        assert isinstance(pdu, type(ex))
    else:
        assert isinstance(pdu, pdu_class)
        constructor_kwargs['raw_frame'] = raw_frame
        assert pdu.__dict__ == constructor_kwargs


@pytest.mark.parametrize(PduTestCaseSig, SERVER_MESSAGES)
async def test_server_decoding(
    str_repr: str,
    pdu_class: Type[BasePDU],
    constructor_kwargs: Dict[str, Any],
    mbap_header: bytes,
    inner_frame: bytes,
    ex: Optional[ExceptionBase],
):
    """Ensure Request PDU messages can be decoded from raw messages."""
    await validate_decoding(ServerFramer(), mbap_header + inner_frame, pdu_class, constructor_kwargs, ex)


@pytest.mark.parametrize(PduTestCaseSig, CLIENT_MESSAGES)
async def test_client_decoding(
    str_repr: str,
    pdu_class: Type[BasePDU],
    constructor_kwargs: Dict[str, Any],
    mbap_header: bytes,
    inner_frame: bytes,
    ex: Optional[ExceptionBase],
):
    """Ensure Response PDU messages can be decoded from raw messages."""
    await validate_decoding(ClientFramer(), mbap_header + inner_frame, pdu_class, constructor_kwargs, ex)


async def decode(framer_class: Type[Framer], buffer: str) -> Union[BasePDU, ExceptionBase]:
    results = []
    async for result in framer_class().decode(_h2b(buffer)):
        results.append(result)
    assert len(results) == 1
    return results[0]


async def test_process_heartbeat_request():
    response = await decode(ClientFramer, '5959 0001 000d 0101 5746 3132 3334 4735 3637 02')
    assert isinstance(response, HeartbeatRequest)
    assert response.function_code == 1
    assert response.data_adapter_serial_number == 'WF1234G567'
    assert response.data_adapter_type == 2


async def test_process_null_response():
    response = await decode(
        ClientFramer,
        '5959 0001 009e 0102 5746 3132 3334 4735 3637 0000 0000 0000 008a 3200 0000 '
        '0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 '
        '0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 '
        '0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 '
        '0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 '
        '0000 0000 0000 0000 0000 0000 0000',
    )
    assert isinstance(response, NullResponse)
    assert response.function_code == 2
    assert response.data_adapter_serial_number == 'WF1234G567'


async def test_process_short_buffer():
    """Test a buffer with a truncated message."""
    framer = ClientFramer()
    buffer = _h2b(
        '5959 0001 009e 0102 5746 3231 3235 4733 3136 0000 0000 0000 008a 1103 5341'
        '3231 3134 4730 3437 0000 003c 2001 0003 0832 0201 0000 c350 0e10 0001 4247'
        '3231 3334 4730 3037 5341 3231 3134 4730 3437 0bbd 01c1 0000 01c1 0002 0000'
        '8000 761b 1770 0001 0000 0000 0011 0000 0004 0007 008c 0016 0001 000b 000e'
        '000c 0034 0001 0002 0000 0000 0000 0065 0001 0000 0000 0064 00'
    )
    results = []

    async for result in framer.decode(buffer):
        results.append(result)

    assert len(results) == 0

    async for result in framer.decode(buffer):
        results.append(result)
    assert len(results) == 1
    response = results[0]
    assert isinstance(response, ReadHoldingRegistersResponse)
    assert response.base_register == 0
    assert response.register_count == 60
    assert len(response.register_values) == 60
    assert response.error is False
    assert response.transparent_function_code == 3
    assert response.raw_frame.hex() == (buffer + buffer[:19]).hex()
    assert framer._buffer == buffer[19:]


@pytest.mark.parametrize('buffer', [VALID_RESPONSE_FRAME], ids=['VALID_RESPONSE_FRAME'])
async def test_various_short_message_buffers(caplog, buffer):
    """Try all lengths of incomplete messages to flush out bugs in framing logic."""
    framer = ClientFramer()
    results = []

    for i in range(len(buffer)):
        with caplog.at_level(logging.DEBUG, logger='givenergy_modbus.framer'):
            async for result in framer.decode(buffer[:i]):
                results.append(result)
        assert results == []
        if i < 18:
            assert len(caplog.records) == 0, i
        else:
            assert len(caplog.records) == 2, i
            assert caplog.records[0].message == f'Found next frame: 0x{buffer[:8].hex()}..., buffer_len={i}'
            assert caplog.records[1].message == f'Buffer ({i}b) insufficient for frame of length 56b, await more data'
        caplog.clear()
        assert framer._buffer == buffer[:i]
        framer._buffer = b''


async def test_process_stream_good():
    """Test a buffer of good messages without noise."""
    framer = ClientFramer()
    buffer = EXCEPTION_RESPONSE_FRAME + VALID_RESPONSE_FRAME
    results = []

    async for result in framer.decode(buffer):
        results.append(result)

    assert len(results) == 2

    response = results[0]
    assert isinstance(response, ReadInputRegistersResponse)
    assert response.base_register == 0
    assert response.register_count == 120
    assert response.register_values == []
    assert response.error is True
    assert response.transparent_function_code == 0x04

    response = results[1]
    assert isinstance(response, ReadInputRegistersResponse)
    assert response.base_register == 0
    assert response.register_count == 6
    assert response.register_values == [1, 3054, 3029, 3881, 0, 2389]
    assert response.error is False
    assert response.transparent_function_code == 0x04


async def test_process_stream_good_but_noisy():
    """Test a buffer of good messages without noise."""
    buffer = b'\x01\x02asdf' + EXCEPTION_RESPONSE_FRAME + b'foobarbaz' + VALID_RESPONSE_FRAME + b'\x00\x99\xff'
    results = []

    async for result in ClientFramer().decode(buffer):
        results.append(result)

    assert len(results) == 2

    response = results[0]
    assert isinstance(response, ReadInputRegistersResponse)
    assert response.base_register == 0
    assert response.register_count == 120
    assert response.register_values == []
    assert response.error is True
    assert response.transparent_function_code == 0x04
    assert response.raw_frame == EXCEPTION_RESPONSE_FRAME

    response = results[1]
    assert isinstance(response, ReadInputRegistersResponse)
    assert response.base_register == 0
    assert response.register_count == 6
    assert response.register_values == [1, 3054, 3029, 3881, 0, 2389]
    assert response.error is False
    assert response.transparent_function_code == 0x04
    assert response.raw_frame == VALID_RESPONSE_FRAME


async def test_decode_frames_bulk(caplog):
    caplog.set_level(logging.DEBUG)

    buffer = b''
    for message in CLIENT_MESSAGES:
        buffer += b'foo'
        buffer += message[0][3] + message[0][4]
        buffer += b'bar'

    i = 0
    framer = ClientFramer()
    async for message in framer.decode(buffer):
        assert str(message) == CLIENT_MESSAGES[i][0][0]
        assert isinstance(message, CLIENT_MESSAGES[i][0][1])
        assert len(caplog.records) >= 2
        if i == 0:
            assert caplog.records[0].message == (
                'Candidate frame found 3 bytes into buffer, discarding leading garbage: 0x666f6f'
            )
        else:
            assert caplog.records[0].message == (
                'Candidate frame found 6 bytes into buffer, discarding leading garbage: 0x626172666f6f'
            )

        assert caplog.records[1].message.startswith('Found next frame: 0x')
        caplog.clear()
        i += 1
    assert i == len(CLIENT_MESSAGES)
    assert framer._buffer == b'bar'
