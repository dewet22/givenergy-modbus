"""Tests for GivEnergyModbusFramer."""
from typing import Any
from unittest.mock import MagicMock

import pytest
from pymodbus.framer.socket_framer import ModbusSocketFramer

from givenergy_modbus.decoder import GivEnergyRequestDecoder, GivEnergyResponseDecoder
from givenergy_modbus.framer import GivEnergyModbusFramer

from . import REQUEST_PDU_MESSAGES, RESPONSE_PDU_MESSAGES, _lookup_pdu_class

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
    [  # list[tuple[bytes, bool, int, bytes]]
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
        (  # data4 - invalid frame, wrong fid is considered corruption and buffer will be reset
            b"\x59\x59\x00\x01\x00\x01\x01\xff",
            False,
            False,
            0,
            b"",
        ),
        (  # data5 - valid frame, length=5 with trailing buffer contents. invalid MBAP will reset the buffer
            b"YYYY\00\x05YYYYYAB",
            True,
            False,
            5,
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
    ],
)
def test_check_frame(requests_framer, data: tuple[bytes, bool, bool, dict[str, int], bytes]):
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
        with pytest.raises(ValueError) as e:
            requests_framer.checkFrame()
        assert e.value.args[0].startswith("Unexpected MBAP header")

    assert expected_remaining_buffer == requests_framer._buffer


@pytest.mark.parametrize("data", REQUEST_PDU_MESSAGES)
def test_request_wire_encoding(requests_framer, data: tuple[str, dict[str, Any], bytes, bytes]):
    """Ensure Request PDU messages can be encoded to the correct wire format."""
    pdu_fn, pdu_fn_kwargs, mbap_header, encoded_pdu = data

    pdu = _lookup_pdu_class(pdu_fn)(**pdu_fn_kwargs)
    packet = requests_framer.buildPacket(pdu)
    assert packet == mbap_header + encoded_pdu


@pytest.mark.parametrize("data", REQUEST_PDU_MESSAGES)
def test_request_wire_decoding(requests_framer, data: tuple[str, dict[str, Any], bytes, bytes]):
    """Ensure Request PDU messages can be decoded from raw messages."""
    pdu_fn, pdu_fn_kwargs, mbap_header, encoded_pdu = data

    callback = MagicMock(return_value=None)
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
def test_response_wire_encoding(responses_framer, data: tuple[str, dict[str, Any], bytes, bytes]):
    """Ensure Response PDU messages can be encoded to the correct wire format."""
    pdu_fn, pdu_fn_kwargs, mbap_header, encoded_pdu = data

    pdu = _lookup_pdu_class(pdu_fn)(**pdu_fn_kwargs)
    packet = responses_framer.buildPacket(pdu)
    assert packet == mbap_header + encoded_pdu


@pytest.mark.parametrize("data", RESPONSE_PDU_MESSAGES)
def test_client_wire_decoding(responses_framer, data: tuple[str, dict[str, Any], bytes, bytes]):
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
