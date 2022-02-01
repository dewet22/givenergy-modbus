"""Tests for GivEnergyModbusFramer."""
import sys
from typing import Any, Dict, Tuple
from unittest.mock import MagicMock

import pytest
from pymodbus.framer.socket_framer import ModbusSocketFramer

from givenergy_modbus.decoder import GivEnergyRequestDecoder, GivEnergyResponseDecoder
from givenergy_modbus.framer import GivEnergyModbusFramer
from givenergy_modbus.pdu import ErrorResponse, ReadInputRegistersResponse
from tests import REQUEST_PDU_MESSAGES, RESPONSE_PDU_MESSAGES, _lookup_pdu_class

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
    client_decoder = MagicMock()
    framer = GivEnergyModbusFramer(client_decoder)
    assert framer.client is None
    assert framer._buffer == b""
    assert framer.decoder == client_decoder
    assert framer._length == 0
    assert framer._hsize == 0x08
    client_decoder.assert_not_called()

    assert not isinstance(framer, ModbusSocketFramer)


@pytest.fixture
def requests_framer():
    """Yield a real framer for processing Request messages."""
    yield GivEnergyModbusFramer(GivEnergyRequestDecoder())


@pytest.fixture
def responses_framer():
    """Yield a real framer for processing Response messages."""
    yield GivEnergyModbusFramer(GivEnergyResponseDecoder())


@pytest.mark.parametrize(
    "data",  # [(input_buffer, complete, header_valid, expected_length, expected_remaining_buffer), (..), ..]
    [  # list[Tuple[bytes, bool, int, bytes]]
        (  # data0 - no data
            b"",
            False,
            True,
            0,
            b"",
        ),
        (  # data1 - incomplete frame, length=0xcc but not enough data follows
            b"\x02\x01\x01\x00Q\xcc",
            False,
            True,
            0,
            b"\x02\x01\x01\x00Q\xcc",
        ),
        (  # data2 - incomplete frame, length=0x9e but not enough data follows
            b"\x59\x59\x00\x01\x00\x9e\x01",
            False,
            True,
            0,
            b"\x59\x59\x00\x01\x00\x9e\x01",
        ),
        (  # data3 - invalid frame, length=1 is considered an error and frame will
            # be discarded silently when checkFrame() called
            b"\x59\x59\x00\x01\x00\x01\x01\x02",
            False,
            True,
            0,
            b"\x02",
        ),
        (  # data4 - valid frame, fid=0x1 is usually an error response?
            b"\x59\x59\x00\x01\x00\x0d\x01\x01\x57\x46\x32\x31\x32\x35\x47\x33\x31\x36\x01",
            True,
            True,
            13,
            b"",
        ),
        (  # data5 - invalid frame with leading & trailing trash, length=5. invalid MBAP, so reset the buffer
            b"YYYY\00\x05YYYYYAB",
            False,
            False,
            0,
            b"",
        ),
        (  # data6 - valid frame, length=2 with trailing buffer contents
            b"\x59\x59\x00\x01\x00\x02\x01\x02\xff\x01\x02\x03",
            True,
            True,
            2,
            b"\xff\x01\x02\x03",
        ),
        (  # data7 - invalid MBAP
            b"\x00\x01\x12\x34\x00\x04\xff\x02\x12\x34",
            True,
            False,
            4,
            b"",
        ),
        (  # data8 - VALID_REQUEST_FRAME with trailing data
            VALID_REQUEST_FRAME + b"\xde\xad\xbe\xef",
            True,
            True,
            28,
            b"\xde\xad\xbe\xef",
        ),
        (  # data9 - VALID_RESPONSE_FRAME with trailing data
            VALID_RESPONSE_FRAME + b"\x01\x02\x03",
            True,
            True,
            50,
            b"\x01\x02\x03",
        ),
        (  # data10 - exception response
            EXCEPTION_RESPONSE_FRAME,
            True,
            True,
            38,
            b"",
        ),
        (  # data11 - exception response + valid response
            EXCEPTION_RESPONSE_FRAME + VALID_RESPONSE_FRAME,
            True,
            True,
            38,
            VALID_RESPONSE_FRAME,
        ),
        (  # data12 - junk + valid response
            b'\x01\x02\x03\x04\x05\x06\x00\x01\x02\x03\x04\x05\x06\x00\x01\x02\x03\x04\x05\x06' + VALID_RESPONSE_FRAME,
            True,
            False,
            38,
            VALID_RESPONSE_FRAME,
        ),
    ],
)
def test_check_frame(requests_framer, data: Tuple[bytes, bool, bool, Dict[str, int], bytes]):
    """Validate the internal state of the framer as data gets processed."""
    input_buffer, is_complete_frame, is_valid_frame, expected_length, expected_remaining_buffer = data

    assert requests_framer.isFrameReady() is False
    assert requests_framer.checkFrame() is False
    assert requests_framer._length == 0

    requests_framer.addToFrame(input_buffer)

    if is_valid_frame:
        assert requests_framer.checkFrame() == is_complete_frame
        assert requests_framer._length == expected_length

        if is_complete_frame:
            requests_framer.advanceFrame()
    else:
        assert not requests_framer.checkFrame()

    # TODO do we need to care about this?
    # assert requests_framer._buffer == expected_remaining_buffer


@pytest.mark.parametrize("data", REQUEST_PDU_MESSAGES)
def test_request_wire_encoding(requests_framer, data: Tuple[str, Dict[str, Any], bytes, bytes, Exception]):
    """Ensure Request PDU messages can be encoded to the correct wire format."""
    pdu_fn, pdu_fn_kwargs, mbap_header, encoded_pdu, ex = data

    pdu = _lookup_pdu_class(pdu_fn)(**pdu_fn_kwargs)
    if ex:
        with pytest.raises(ex.__class__) as e:
            requests_framer.buildPacket(pdu)
        assert e.value.args == ex.args
    else:
        packet = requests_framer.buildPacket(pdu)
        assert packet == mbap_header + encoded_pdu


@pytest.mark.skipif(sys.version_info < (3, 8), reason="requires python3.8 or higher")
@pytest.mark.parametrize("data", REQUEST_PDU_MESSAGES)
def test_request_wire_decoding(requests_framer, data: Tuple[str, Dict[str, Any], bytes, bytes, Exception]):
    """Ensure Request PDU messages can be decoded from raw messages."""
    pdu_fn, pdu_fn_kwargs, mbap_header, encoded_pdu, ex = data

    callback = MagicMock(return_value=None)
    if ex:
        with pytest.raises(ex.__class__) as e:
            requests_framer.processIncomingPacket(mbap_header + encoded_pdu, callback)
        callback.assert_not_called()
        assert e.value.args == ex.args
    else:
        requests_framer.processIncomingPacket(mbap_header + encoded_pdu, callback)
        callback.assert_called_once()
        fn_kwargs = vars(callback.mock_calls[0].args[0])
        for (key, val) in pdu_fn_kwargs.items():
            assert fn_kwargs[key] == val
        assert fn_kwargs["transaction_id"] == 0x5959
        assert fn_kwargs["protocol_id"] == 0x1
        assert fn_kwargs["unit_id"] == 0x1
        assert fn_kwargs["skip_encode"]
        assert fn_kwargs["check"] == int.from_bytes(encoded_pdu[-2:], "big")
        assert fn_kwargs["data_adapter_serial_number"] == "AB1234G567"
        assert fn_kwargs["slave_address"] == 0x32


@pytest.mark.parametrize("data", RESPONSE_PDU_MESSAGES)
def test_response_wire_encoding(responses_framer, data: Tuple[str, Dict[str, Any], bytes, bytes]):
    """Ensure Response PDU messages can be encoded to the correct wire format."""
    pdu_fn, pdu_fn_kwargs, mbap_header, encoded_pdu = data

    pdu = _lookup_pdu_class(pdu_fn)(**pdu_fn_kwargs)
    packet = responses_framer.buildPacket(pdu)
    assert packet == mbap_header + encoded_pdu


@pytest.mark.skipif(sys.version_info < (3, 8), reason="requires python3.8 or higher")
@pytest.mark.parametrize("data", RESPONSE_PDU_MESSAGES)
def test_client_wire_decoding(responses_framer, data: Tuple[str, Dict[str, Any], bytes, bytes]):
    """Ensure Response PDU messages can be decoded from raw messages."""
    pdu_fn, pdu_fn_kwargs, mbap_header, encoded_pdu = data

    callback = MagicMock(return_value=None)
    responses_framer.processIncomingPacket(mbap_header + encoded_pdu, callback)
    callback.assert_called_once()
    fn_kwargs = vars(callback.mock_calls[0].args[0])
    for (key, val) in pdu_fn_kwargs.items():
        assert fn_kwargs[key] == val
    assert fn_kwargs["transaction_id"] == 0x5959
    assert fn_kwargs["protocol_id"] == 0x1
    assert fn_kwargs["unit_id"] == 0x1
    assert fn_kwargs["skip_encode"]
    assert fn_kwargs["check"] == int.from_bytes(encoded_pdu[-2:], "big")
    assert fn_kwargs["data_adapter_serial_number"] == "WF1234G567"
    assert fn_kwargs["slave_address"] == 0x32


def test_process_error_response(responses_framer):
    """Test error response processing."""
    buffer = bytes.fromhex('5959 0001 000d 0101 5746 3132 3334 4735 3637 01')

    callback = MagicMock(return_value=None)
    responses_framer.processIncomingPacket(buffer, callback)

    callback.assert_called_once()
    response = callback.call_args_list[0][0][0]
    assert isinstance(response, ErrorResponse)
    assert response.function_code == 0
    assert response.data_adapter_serial_number == 'WF1234G567'
    assert response.error_code == 0x1


def test_process_stream_short_frame(responses_framer):
    """Test a buffer with a truncated message."""
    buffer = bytes.fromhex(
        '59 5900 0100 9e01 0257 4632 3132 3547 3331 3600 0000 0000 0000 '
        '8a11 0353 4132 3131 3447 3034 3700 0000 3c20 0100 0308 3202 0100 00c3 500e 1000 0142 4732 3133 3447 3030 3753 '
        '4132 3131 3447 3034 370b bd01 c100 0001 c100 0200 0080 0076 1b17 7000 0100 0000 0000 1100 0000 0400 0700 8c00 '
        '1600 0100 0b00 0e00 0c00 3400 0100 0200 0000 0000 0000 6500 0100 0000 0000 6400'
    )

    callback = MagicMock(return_value=None)
    responses_framer.processIncomingPacket(buffer, callback)
    callback.assert_not_called()


def test_process_stream_good(responses_framer):
    """Test a buffer of good messages without noise."""
    buffer = EXCEPTION_RESPONSE_FRAME + VALID_RESPONSE_FRAME

    callback = MagicMock(return_value=None)
    responses_framer.processIncomingPacket(buffer, callback)

    assert len(callback.call_args_list) == 2

    response = callback.call_args_list[0][0][0]
    assert isinstance(response, ReadInputRegistersResponse)
    assert response.base_register == 0
    assert response.register_count == 120
    assert response.register_values == []
    assert response.error is True
    assert response.function_code == 0x04

    response = callback.call_args_list[1][0][0]
    assert isinstance(response, ReadInputRegistersResponse)
    assert response.base_register == 0
    assert response.register_count == 6
    assert response.register_values == [1, 3054, 3029, 3881, 0, 2389]
    assert response.error is False
    assert response.function_code == 0x04


@pytest.mark.skip('FIXME return to this some day')
def test_process_stream_good_but_noisy(responses_framer):
    """Test a buffer of good messages without noise."""
    buffer = b'\x01\x02asdf' + EXCEPTION_RESPONSE_FRAME + b'foobarbaz' + VALID_RESPONSE_FRAME + b'\x00\x99\xff'

    callback = MagicMock(return_value=None)
    responses_framer.processIncomingPacket(buffer, callback)

    assert len(callback.call_args_list) == 1

    response = callback.call_args_list[0][0][0]
    assert isinstance(response, ReadInputRegistersResponse)
    assert response.base_register == 0
    assert response.register_count == 120
    assert response.register_values == []
    assert response.error is True
    assert response.function_code == 0x04

    response = callback.call_args_list[1][0][0]
    assert isinstance(response, ReadInputRegistersResponse)
    assert response.base_register == 0
    assert response.register_count == 6
    assert response.register_values == [1, 3054, 3029, 3881, 0, 2389]
    assert response.error is False
    assert response.function_code == 0x04
