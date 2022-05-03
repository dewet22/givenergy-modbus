"""Tests for GivEnergyModbusFramer."""
import logging
import sys
from unittest.mock import MagicMock, call

import pytest
from pymodbus.framer.socket_framer import ModbusSocketFramer

from givenergy_modbus.framer import ClientFramer, Framer, ServerFramer
from givenergy_modbus.pdu import BasePDU
from givenergy_modbus.pdu.heartbeat import HeartbeatRequest
from givenergy_modbus.pdu.null import NullResponse
from givenergy_modbus.pdu.read_registers import ReadHoldingRegistersResponse, ReadInputRegistersResponse
from tests import ALL_MESSAGES, CLIENT_MESSAGES, SERVER_MESSAGES, PduTestCaseSig, _lookup_pdu_class

VALID_REQUEST_FRAME = (  # actual recorded request frame, look up 6 input registers starting at #0
    b"\x59\x59\x00\x01\x00\x1c\x01\x02"  # 7-byte MBAP header + function code
    b"\x41\x42\x31\x32\x33\x34\x47\x35\x36\x37"  # 10-byte serial number: AB1234G567
    b"\x00\x00\x00\x00\x00\x00\x00\x08"  # 8-byte padding / crc / check?
    b"\x32"  # slave address
    b"\x04"  # sub-function: query input registers
    b"\x00\x00"  # start register: 0
    b"\x00\x06"  # step: 6
    b"\xc2\x55"  # crc
)  # 34 bytes

VALID_RESPONSE_FRAME = (  # actual recorded response frame, to request above
    b"\x59\x59\x00\x01\x00\x32\x01\x02"  # 7-byte MBAP header + function code
    b"\x57\x46\x31\x32\x33\x34\x47\x35\x36\x37"  # 10-byte serial number WF1234G567
    b"\x00\x00\x00\x00\x00\x00\x00\x1e"  # 8-byte padding / crc / check?
    b"\x32"  # slave address
    b"\x04"  # sub-function
    b"\x53\x41\x31\x32\x33\x34\x45\x35\x36\x37"  # 10-byte serial number SA1234G567
    b"\x00\x00"  # start register: 0
    b"\x00\x06"  # step: 6
    b"\x00\x01"  # register 0: 1 (inverter status, == OK?)
    b"\x0b\xee"  # register 1: 3054 (V_pv1, with 0.1 scaling == 305.4V)
    b"\x0b\xd5"  # register 2: 3029 (V_pv2, with 0.1 scaling == 302.9V)
    b"\x0f\x29"  # register 3: 3881 (V_P-bus_inside, with 0.1 scaling == 388.1)
    b"\x00\x00"  # register 4: 0 (V_N-bus_inside, with 0.1 scaling == 0.0)
    b"\x09\x55"  # register 5: 2389 (V_grid (single-phase), with 0.1 scaling == 238.9)
    b"\xb5\xd2"  # crc
)  # 56 bytes

EXCEPTION_RESPONSE_FRAME = (  # actual recorded response frame, to request above
    b"\x59\x59\x00\x01\x00\x26\x01\x02"  # 7-byte MBAP header + function code
    b"\x57\x46\x31\x32\x33\x34\x47\x35\x36\x37"  # 10-byte serial number WF1234G567
    b"\x00\x00\x00\x00\x00\x00\x00\x12"  # 8-byte padding / crc / check?
    b"\x32"  # slave address
    b"\x84"  # sub-function
    b"\x53\x41\x31\x32\x33\x34\x45\x35\x36\x37"  # 10-byte serial number SA1234G567
    b"\x00\x00"  # start register: 0
    b"\x00\x78"  # step: 120 – GivEnergy protocol only supports up to 60.
    b"\xf1\x33"  # crc
)  # 44 bytes


def test_framer_constructor():
    """Test constructor."""
    framer = Framer()
    assert not isinstance(framer, ModbusSocketFramer)
    framer.decoder = MagicMock()
    assert framer.FRAME_HEAD == ">HHHBB"
    assert framer.FRAME_HEAD_SIZE == 0x08
    assert framer._buffer == b""
    assert not hasattr(framer, '_length')
    assert framer.buffer_length == 0
    framer.decoder.assert_not_called()


@pytest.mark.parametrize(PduTestCaseSig, ALL_MESSAGES)
def test_encoding(str_repr, pdu_class_name, constructor_kwargs, mbap_header, inner_frame, ex):
    """Ensure message objects can be encoded to the correct wire format."""
    framer = Framer()
    pdu = _lookup_pdu_class(pdu_class_name)(**constructor_kwargs)
    if ex:
        with pytest.raises(type(ex), match=ex.message):
            framer.build_packet(pdu)
    else:
        packet = framer.build_packet(pdu)
        assert packet.hex() == (mbap_header + inner_frame).hex()


@pytest.mark.skipif(sys.version_info < (3, 8), reason="requires python3.8 or higher")
@pytest.mark.parametrize(PduTestCaseSig, SERVER_MESSAGES)
def test_server_decoding(str_repr, pdu_class_name, constructor_kwargs, mbap_header, inner_frame, ex):
    """Ensure Request PDU messages can be decoded from raw messages."""
    framer = ServerFramer()
    callback = MagicMock(return_value=None)

    framer.process_incoming_data(mbap_header + inner_frame, callback)

    if ex:
        assert callback.mock_calls == [call(None, mbap_header + inner_frame)]
    else:
        callback.assert_called_once()
        fn_kwargs = vars(callback.mock_calls[0].args[0])
        for (key, val) in constructor_kwargs.items():
            assert fn_kwargs[key] == val, f'{key} must match'
        assert fn_kwargs["data_adapter_serial_number"] == "AB1234G567"
        if hasattr(fn_kwargs, 'slave_address'):
            assert fn_kwargs["slave_address"] == 0x32
            assert fn_kwargs["check"] == int.from_bytes(inner_frame[-2:], "big")


@pytest.mark.skipif(sys.version_info < (3, 8), reason="requires python3.8 or higher")
@pytest.mark.parametrize(PduTestCaseSig, CLIENT_MESSAGES)
def test_client_decoding(str_repr, pdu_class_name, constructor_kwargs, mbap_header, inner_frame, ex):
    """Ensure Response PDU messages can be decoded from raw messages."""
    framer = ClientFramer()
    callback = MagicMock(return_value=None)
    framer.process_incoming_data(mbap_header + inner_frame, callback)
    callback.assert_called_once()
    fn_kwargs = vars(callback.mock_calls[0].args[0])
    for (key, val) in constructor_kwargs.items():
        assert fn_kwargs[key] == val, f'`{key}` attribute must match'
    if 'check' in fn_kwargs:
        assert fn_kwargs["check"] == int.from_bytes(inner_frame[-2:], "big")


def decode(framer_class: type[Framer], buffer: str) -> BasePDU:
    callback = MagicMock(return_value=None)
    framer_class().process_incoming_data(bytes.fromhex(buffer), callback)
    callback.assert_called_once()
    response = callback.call_args_list[0][0][0]
    return response


def test_process_heartbeat_request():
    response = decode(ClientFramer, '5959 0001 000d 0101 5746 3132 3334 4735 3637 02')
    assert isinstance(response, HeartbeatRequest)
    assert not hasattr(response, 'function_code')
    assert response.data_adapter_serial_number == 'WF1234G567'
    assert response.data_adapter_type == 2


def test_process_null_response():
    response = decode(
        ClientFramer,
        '5959 0001 009e 0102 5746 3132 3334 4735 3637 0000 0000 0000 008a 3200 0000 '
        '0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 '
        '0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 '
        '0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 '
        '0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 '
        '0000 0000 0000 0000 0000 0000 0000',
    )
    assert isinstance(response, NullResponse)
    assert not hasattr(response, 'function_code')
    assert response.data_adapter_serial_number == 'WF1234G567'


def test_process_short_buffer():
    """Test a buffer with a truncated message."""
    framer = ClientFramer()
    buffer = bytes.fromhex(
        '5959 0001 009e 0102 5746 3231 3235 4733 3136 0000 0000 0000 008a 1103 5341'
        '3231 3134 4730 3437 0000 003c 2001 0003 0832 0201 0000 c350 0e10 0001 4247'
        '3231 3334 4730 3037 5341 3231 3134 4730 3437 0bbd 01c1 0000 01c1 0002 0000'
        '8000 761b 1770 0001 0000 0000 0011 0000 0004 0007 008c 0016 0001 000b 000e'
        '000c 0034 0001 0002 0000 0000 0000 0065 0001 0000 0000 0064 00'
    )
    callback = MagicMock(return_value=None)

    framer.process_incoming_data(buffer, callback)

    callback.assert_not_called()

    framer.process_incoming_data(buffer, callback)
    assert len(callback.call_args_list) == 1
    callback_args = callback.call_args_list[0][0]
    response = callback_args[0]
    assert isinstance(response, ReadHoldingRegistersResponse)
    assert response.base_register == 0
    assert response.register_count == 60
    assert len(response.register_values) == 60
    assert response.error is False
    assert response.inner_function_code == 3
    assert callback_args[1] == buffer + buffer[:19]
    assert framer._buffer == buffer[19:]


@pytest.mark.parametrize("buffer", [VALID_RESPONSE_FRAME], ids=['VALID_RESPONSE_FRAME'])
def test_various_short_message_buffers(caplog, buffer):
    """Try all lengths of incomplete messages to flush out bugs in framing logic."""
    framer = ClientFramer()
    callback = MagicMock(return_value=None)

    for i in range(len(buffer)):
        with caplog.at_level(logging.DEBUG, logger='givenergy_modbus.framer'):
            framer.process_incoming_data(buffer[:i], callback)
        callback.assert_not_called()
        if i < 18:  # not framer.FRAME_HEAD_SIZE
            assert len(caplog.records) == 0, i
        else:
            assert len(caplog.records) == 4, i
            assert caplog.records[0].message == f"Found next header_start: 0, buffer_len={i}"
            assert caplog.records[1].message == "Candidate MBAP header 0x5959000100320102, parsing using format >HHHBB"
            assert caplog.records[2].message == "t_id=5959, p_id=0001, len=0032, u_id=01, f_id=02"
            assert caplog.records[3].message == f"Buffer too short ({i}) to complete frame (56)"
        caplog.clear()
        assert framer._buffer == buffer[:i]
        framer._buffer = b''


def test_process_stream_good():
    """Test a buffer of good messages without noise."""
    framer = ClientFramer()
    buffer = EXCEPTION_RESPONSE_FRAME + VALID_RESPONSE_FRAME
    callback = MagicMock(return_value=None)

    framer.process_incoming_data(buffer, callback)

    assert len(callback.call_args_list) == 2

    response = callback.call_args_list[0][0][0]
    assert isinstance(response, ReadInputRegistersResponse)
    assert response.base_register == 0
    assert response.register_count == 120
    assert response.register_values == []
    assert response.error is True
    assert response.inner_function_code == 0x04

    response = callback.call_args_list[1][0][0]
    assert isinstance(response, ReadInputRegistersResponse)
    assert response.base_register == 0
    assert response.register_count == 6
    assert response.register_values == [1, 3054, 3029, 3881, 0, 2389]
    assert response.error is False
    assert response.inner_function_code == 0x04


def test_process_stream_good_but_noisy():
    """Test a buffer of good messages without noise."""
    buffer = b'\x01\x02asdf' + EXCEPTION_RESPONSE_FRAME + b'foobarbaz' + VALID_RESPONSE_FRAME + b'\x00\x99\xff'
    callback = MagicMock(return_value=None)

    ClientFramer().process_incoming_data(buffer, callback)

    assert len(callback.call_args_list) == 2

    callback_args = callback.call_args_list[0][0]
    response = callback_args[0]
    assert isinstance(response, ReadInputRegistersResponse)
    assert response.base_register == 0
    assert response.register_count == 120
    assert response.register_values == []
    assert response.error is True
    assert response.inner_function_code == 0x04
    assert callback_args[1] == EXCEPTION_RESPONSE_FRAME

    callback_args = callback.call_args_list[1][0]
    response = callback_args[0]
    assert isinstance(response, ReadInputRegistersResponse)
    assert response.base_register == 0
    assert response.register_count == 6
    assert response.register_values == [1, 3054, 3029, 3881, 0, 2389]
    assert response.error is False
    assert response.inner_function_code == 0x04
    assert callback_args[1] == VALID_RESPONSE_FRAME
