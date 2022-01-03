"""Top-level package for GivEnergy Modbus tests."""

import importlib
from typing import Callable

# fmt: off
REQUEST_PDU_MESSAGES = [
    # [(pdu_fn, pdu_fn_kwargs, mbap_head, encoded_pdu), (..), ..]
    (   # data0
        "ReadInputRegistersRequest",
        {"base_register": 0x10, "register_count": 6, "check": 0x0754},
        b"YY\x00\x01\x00\x1c\x01\x02",  # 8 bytes
        b"AB1234G567" b"\x00\x00\x00\x00\x00\x00\x00\x08" b"\x32\x04\x00\x10\x00\x06" b"\x07\x54",  # 26 bytes
    ),
    (   # data1
        "ReadHoldingRegistersRequest",
        {"base_register": 0x5151, "register_count": 2000, "check": 0x8122},
        b"YY\x00\x01\x00\x1c\x01\x02",
        b"AB1234G567" b"\x00\x00\x00\x00\x00\x00\x00\x08" b"\x32\x03\x51\x51\x07\xd0" b"\x81\x22",
    ),
    (   # data2
        "ReadHoldingRegistersRequest",
        {"base_register": 0x5151, "register_count": 2000, "check": 0x8122, "data_adapter_serial_number": "AB1234G567"},
        b"YY\x00\x01\x00\x1c\x01\x02",
        b"AB1234G567" b"\x00\x00\x00\x00\x00\x00\x00\x08" b"\x32\x03\x51\x51\x07\xd0" b"\x81\x22",
    ),
    (   # data3
        "WriteHoldingRegisterRequest",
        {"register": 0x5151, "value": 2000, "check": 0x81ee, "data_adapter_serial_number": "AB1234G567"},
        b"YY\x00\x01\x00\x1c\x01\x02",
        b"AB1234G567" b"\x00\x00\x00\x00\x00\x00\x00\x08" b"\x32\x06\x51\x51\x07\xd0" b"\x81\xee",
    ),
    (  # data3
        "WriteHoldingRegisterRequest",
        {"register": 0x14, "value": 1, "check": 0xc42d, "data_adapter_serial_number": "AB1234G567"},
        b"YY\x00\x01\x00\x1c\x01\x02",
        b"AB1234G567" b"\x00\x00\x00\x00\x00\x00\x00\x08" b"\x32\x06\x00\x14\x00\x01" b"\xc4\x2d",
    ),
]

RESPONSE_PDU_MESSAGES = [
    # [(pdu_fn, pdu_fn_kwargs, mbap_head, encoded_pdu), (..), ..]
    (   # data0
        "ReadInputRegistersResponse",
        {
            "check": 0x8e4b,
            "inverter_serial_number": 'SA1234G567',
            "base_register": 0x0000,
            "register_count": 0x003C,
            "register_values": [
                0x0001, 0x0cb0, 0x0c78, 0x0f19, 0x0000, 0x095b, 0x0000, 0x05c5, 0x0001, 0x0002,
                0x0021, 0x0000, 0x008c, 0x138a, 0x0005, 0x0aa9, 0x2b34, 0x0008, 0x0041, 0x0008,
                0x003f, 0x0000, 0x0005, 0x0000, 0x0278, 0x0000, 0x0071, 0x0000, 0x02ff, 0x0000,
                0xff75, 0x0000, 0x0000, 0x0bf5, 0x0000, 0x0057, 0x0054, 0x0049, 0x0000, 0x0000,
                0x0000, 0x0124, 0x0311, 0x0288, 0x004e, 0x0000, 0x02f7, 0x0000, 0x00b6, 0x0001,
                0x139e, 0x0467, 0x023c, 0x094b, 0x1389, 0x0121, 0x00be, 0x0000, 0x00f8, 0x0011],
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

    ),
]
# fmt: on


def _lookup_pdu_class(pdu_fn: str) -> Callable:
    """Utility to retrieve a PDU function from string representation because pytest can't parametrize class names."""
    module = importlib.import_module('givenergy_modbus.pdu')
    return getattr(module, pdu_fn)
