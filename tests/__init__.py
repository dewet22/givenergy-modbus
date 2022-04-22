"""Top-level package for GivEnergy Modbus tests."""

import importlib
from typing import Callable, Dict, List, Optional, Tuple, Union

import pytest

from givenergy_modbus.pdu import BasePDU

PDUType = str
CtorKwargs = Dict[str, Union[int, str, List[int]]]
MbapHeader = bytes
InnerFrame = bytes
ExceptionThrown = Optional[Exception]
StrRepr = str
PduTestCase = Tuple[StrRepr, PDUType, CtorKwargs, MbapHeader, InnerFrame, ExceptionThrown]
PduTestCaseSig = 'str_repr, pdu_class_name, constructor_kwargs, mbap_header, inner_frame, ex'
PduTestCases = List[PduTestCase]


def _lookup_pdu_class(pdu_fn: str) -> Callable[..., BasePDU]:
    """Utility to retrieve a PDU function from string representation because pytest can't parametrize class names."""
    if pdu_fn.startswith('Read'):
        module = importlib.import_module('givenergy_modbus.pdu.read_registers')
    elif pdu_fn.startswith('Write'):
        module = importlib.import_module('givenergy_modbus.pdu.write_registers')
    elif pdu_fn.startswith('Heartbeat'):
        module = importlib.import_module('givenergy_modbus.pdu.heartbeat')
    elif pdu_fn.startswith('Null'):
        module = importlib.import_module('givenergy_modbus.pdu.null')
    else:
        raise ValueError(pdu_fn)
    return getattr(module, pdu_fn)


_h2b = bytes.fromhex


def _mbap_header(function_code: int, packet_length: int) -> MbapHeader:
    return bytes.fromhex(f'59590001{packet_length:04x}01{function_code:02x}')


# Messages a server should be expected to process (or, typical messages a client would send)
_server_messages: PduTestCases = [
    (
        '2:4/ReadInputRegistersRequest(base_register=16 register_count=6)',
        "ReadInputRegistersRequest",
        {"base_register": 0x10, "register_count": 6, "check": 0x0754},
        b"YY\x00\x01\x00\x1c\x01\x02",  # 8 bytes
        b"AB1234G567" b"\x00\x00\x00\x00\x00\x00\x00\x08" b"\x32\x04\x00\x10\x00\x06" b"\x07\x54",  # 26 bytes
        None,
    ),
    (
        '2:3/ReadHoldingRegistersRequest(base_register=20817 register_count=20)',
        "ReadHoldingRegistersRequest",
        {"base_register": 0x5151, "register_count": 20, "check": 0x2221},
        b"YY\x00\x01\x00\x1c\x01\x02",
        b"AB1234G567" b"\x00\x00\x00\x00\x00\x00\x00\x08" b"\x32\x03\x51\x51\x00\x14" b"\x22\x21",
        None,
    ),
    (
        '2:3/ReadHoldingRegistersRequest(base_register=20817 register_count=30)',
        "ReadHoldingRegistersRequest",
        {"base_register": 0x5151, "register_count": 30, "check": 0x25A1, "data_adapter_serial_number": "AB1234G567"},
        b"YY\x00\x01\x00\x1c\x01\x02",
        b"AB1234G567" b"\x00\x00\x00\x00\x00\x00\x00\x08" b"\x32\x03\x51\x51\x00\x1e" b"\x25\xa1",
        None,
    ),
    (
        '2:6/WriteHoldingRegisterRequest(register=20817 value=2000)',
        "WriteHoldingRegisterRequest",
        {"register": 0x5151, "value": 2000, "check": 0x81EE, "data_adapter_serial_number": "AB1234G567"},
        b"YY\x00\x01\x00\x1c\x01\x02",
        b"AB1234G567" b"\x00\x00\x00\x00\x00\x00\x00\x08" b"\x32\x06\x51\x51\x07\xd0" b"\x81\xee",
        ValueError('Register 20817 is not safe to write to'),
    ),
    (
        '2:6/WriteHoldingRegisterRequest(register=20 value=1)',
        "WriteHoldingRegisterRequest",
        {"register": 0x14, "value": 1, "check": 0xC42D, "data_adapter_serial_number": "AB1234G567"},
        b"YY\x00\x01\x00\x1c\x01\x02",
        b"AB1234G567" b"\x00\x00\x00\x00\x00\x00\x00\x08" b"\x32\x06\x00\x14\x00\x01" b"\xc4\x2d",
        None,
    ),
    (
        '1/HeartbeatResponse(data_adapter_serial_number=AB1234G567 data_adapter_type=32)',
        "HeartbeatResponse",
        {
            "data_adapter_serial_number": 'AB1234G567',
            "data_adapter_type": 32,
        },
        b'YY\x00\x01\x00\x0d\x01\x01',  # 8b MBAP header
        b'AB1234G567' b'\x20',
        None,
    ),
]

# Messages a client should be expected to process (or, typical messages a server would send)
_client_messages: PduTestCases = [
    (
        '2:4/ReadInputRegistersResponse(slave_address=0x32 base_register=0 register_count=60)',
        "ReadInputRegistersResponse",
        {
            "check": 0x8E4B,
            "inverter_serial_number": 'SA1234G567',
            "base_register": 0x0000,
            "register_count": 0x003C,
            # fmt: off
            "register_values": [
                0x0001, 0x0CB0, 0x0C78, 0x0F19, 0x0000, 0x095B, 0x0000, 0x05C5, 0x0001, 0x0002,
                0x0021, 0x0000, 0x008C, 0x138A, 0x0005, 0x0AA9, 0x2B34, 0x0008, 0x0041, 0x0008,
                0x003F, 0x0000, 0x0005, 0x0000, 0x0278, 0x0000, 0x0071, 0x0000, 0x02FF, 0x0000,
                0xFF75, 0x0000, 0x0000, 0x0BF5, 0x0000, 0x0057, 0x0054, 0x0049, 0x0000, 0x0000,
                0x0000, 0x0124, 0x0311, 0x0288, 0x004E, 0x0000, 0x02F7, 0x0000, 0x00B6, 0x0001,
                0x139E, 0x0467, 0x023C, 0x094B, 0x1389, 0x0121, 0x00BE, 0x0000, 0x00F8, 0x0011,
            ],
            # fmt: on
            "data_adapter_serial_number": 'WF1234G567',
            "padding": 0x008A,
            "slave_address": 0x0032,
        },
        b'YY\x00\x01\x00\x9e\x01\x02',  # 8b MBAP header
        # 154b total payload, starting with 34b of fields:
        b'WF1234G567' b'\x00\x00\x00\x00\x00\x00\x00\x8a' b'\x32\x04' b'SA1234G567' b'\x00\x00' b'\x00<'
        # 4x60b chunk, containing register values:
        b'\x00\x01\x0c\xb0\x0cx\x0f\x19\x00\x00\t[\x00\x00\x05\xc5\x00\x01\x00\x02\x00!\x00\x00\x00\x8c\x13\x8a\x00\x05'
        b'\n\xa9+4\x00\x08\x00A\x00\x08\x00?\x00\x00\x00\x05\x00\x00\x02x\x00\x00\x00q\x00\x00\x02\xff\x00\x00'
        b'\xffu\x00\x00\x00\x00\x0b\xf5\x00\x00\x00W\x00T\x00I\x00\x00\x00\x00\x00\x00\x01$\x03\x11\x02\x88\x00N'
        b'\x00\x00\x02\xf7\x00\x00\x00\xb6\x00\x01\x13\x9e\x04g\x02<\tK\x13\x89\x01!\x00\xbe\x00\x00\x00\xf8\x00\x11'
        b"\x8e\x4b",  # 2b crc
        None,
    ),
    (
        '2:3/ReadHoldingRegistersResponse(slave_address=0x32 base_register=0 register_count=60)',
        "ReadHoldingRegistersResponse",
        {
            "check": 0x153D,
            "inverter_serial_number": 'SA1234G567',
            "base_register": 0x0000,
            "register_count": 0x003C,
            # fmt: off
            "register_values": [
                0x2001, 0x0003, 0x0832, 0x0201, 0x0000, 0xC350, 0x0E10, 0x0001, 0x4247, 0x3132,
                0x3334, 0x4735, 0x3637, 0x5341, 0x3132, 0x3334, 0x4735, 0x3637, 0x0BBD, 0x01C1,
                0x0000, 0x01C1, 0x0002, 0x0000, 0x8000, 0x761B, 0x1770, 0x0001, 0x0000, 0x0000,
                0x0011, 0x0000, 0x0004, 0x0007, 0x008C, 0x0016, 0x0004, 0x0011, 0x0013, 0x0001,
                0x0001, 0x0001, 0x0002, 0x0000, 0x0000, 0x0000, 0x0065, 0x0001, 0x0000, 0x0000,
                0x0064, 0x0000, 0x0000, 0x0001, 0x0001, 0x00A0, 0x0640, 0x02BC, 0x0001, 0x0000,
            ],
            # fmt: on
            "data_adapter_serial_number": 'WF1234G567',
            "padding": 0x008A,
            "slave_address": 0x0032,
        },
        b'YY\x00\x01\x00\x9e\x01\x02',  # 8b MBAP header
        # 154b total payload, starting with 34b of fields:
        b'WF1234G567' b'\x00\x00\x00\x00\x00\x00\x00\x8a' b'\x32\x03' b'SA1234G567' b'\x00\x00' b'\x00<'
        # 4x60b chunk, containing register values:
        b' \x01\x00\x03\x082\x02\x01\x00\x00\xc3P\x0e\x10\x00\x01BG1234G567SA1234G567\x0b\xbd\x01\xc1\x00\x00\x01'
        b'\xc1\x00\x02\x00\x00\x80\x00v\x1b\x17p\x00\x01\x00\x00\x00\x00\x00\x11\x00\x00\x00\x04\x00\x07\x00\x8c'
        b'\x00\x16\x00\x04\x00\x11\x00\x13\x00\x01\x00\x01\x00\x01\x00\x02\x00\x00\x00\x00\x00\x00\x00e\x00\x01\x00'
        b'\x00\x00\x00\x00d\x00\x00\x00\x00\x00\x01\x00\x01\x00\xa0\x06@\x02\xbc\x00\x01\x00\x00'
        b'\x15=',  # 2b crc
        # b'\x00\x01\x0c\xb0\x0cx\x0f\x19\x00\x00\t[\x00\x00\x05\xc5\x00\x01\x00\x02\x00!\x00\x00\x00\x8c\x13\x8a\x00\x05'
        # b'\n\xa9+4\x00\x08\x00A\x00\x08\x00?\x00\x00\x00\x05\x00\x00\x02x\x00\x00\x00q\x00\x00\x02\xff\x00\x00'
        # b'\xffu\x00\x00\x00\x00\x0b\xf5\x00\x00\x00W\x00T\x00I\x00\x00\x00\x00\x00\x00\x01$\x03\x11\x02\x88\x00N'
        # b'\x00\x00\x02\xf7\x00\x00\x00\xb6\x00\x01\x13\x9e\x04g\x02<\tK\x13\x89\x01!\x00\xbe\x00\x00\x00\xf8\x00\x11'
        # b"\x8e\x4b",  # 2b crc
        None,
    ),
    (
        '2:6/WriteHoldingRegisterResponse(slave_address=0x32 register=35 value=8764)',
        "WriteHoldingRegisterResponse",
        {
            "check": 0x8E4B,
            "inverter_serial_number": 'SA1234G567',
            "register": 0x0023,
            "value": 0x223C,
            "data_adapter_serial_number": 'WF1234G567',
            "padding": 0x8A,
            "slave_address": 0x32,
        },
        b'YY\x00\x01\x00\x26\x01\x02',  # 8b MBAP header
        b'WF1234G567'
        b'\x00\x00\x00\x00\x00\x00\x00\x8a'
        b'\x32\x06'
        b'SA1234G567'
        b'\x00\x23'  # register
        b'\x22\x3c'  # value readback
        b"\x8e\x4b",  # 2b crc
        None,
    ),
    (
        '1/HeartbeatRequest(data_adapter_serial_number=WF1234G567 data_adapter_type=1)',
        "HeartbeatRequest",
        {"data_adapter_serial_number": "WF1234G567", "data_adapter_type": 1},
        _mbap_header(1, 0x0D),
        b"WF1234G567" + _h2b("01"),
        None,
    ),
    (
        '2:0/NullResponse(slave_address=0x22)',
        "NullResponse",
        {
            "check": 0x0,
            "inverter_serial_number": '\x00' * 10,
            "data_adapter_serial_number": 'KK4321H987',
            "padding": 0x8A,
            "slave_address": 0x22,
        },
        _mbap_header(2, 158),
        _h2b('4b4b3433323148393837000000000000008a2200' + '0000' * 68),
        None,
    ),
]

# 59590001009e010257463231323547333136000000000000008a320000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000

SERVER_MESSAGES = [pytest.param(*p, id=p[0]) for p in _server_messages]
CLIENT_MESSAGES = [pytest.param(*p, id=p[0]) for p in _client_messages]
ALL_MESSAGES = SERVER_MESSAGES + CLIENT_MESSAGES
