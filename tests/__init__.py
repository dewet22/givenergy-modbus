"""Top-level package for GivEnergy Modbus tests."""

import importlib
from typing import Callable

REQUEST_PDU_MESSAGES = [
    # [(pdu_fn, pdu_fn_kwargs, encoded_pdu, packet_head, packet_tail), (..), ..]
    (  # data0
        "ReadInputRegistersRequest",
        {"base_register": 0x10, "register_count": 6},
        b"AB1234G567" b"\x00\x00\x00\x00\x00\x00\x00\x08" b"\x32\x04" b"\x00\x10" b"\x00\x06",  # 24 bytes
        b"YY\x00\x01\x00\x1c\x01\x02",  # 8 bytes
        b"\x07T",  # 2 bytes
    ),
    (  # data1
        "ReadHoldingRegistersRequest",
        {"base_register": 0x5151, "register_count": 2000},
        b"AB1234G567" b"\x00\x00\x00\x00\x00\x00\x00\x08" b"\x32\x03" b"\x51\x51" b"\x07\xd0",
        b"YY\x00\x01\x00\x1c\x01\x02",
        b"\x81\x22",
    ),
    (  # data2
        "ReadHoldingRegistersRequest",
        {"base_register": 0x5151, "register_count": 2000},
        b"AB1234G567" b"\x00\x00\x00\x00\x00\x00\x00\x08" b"\x32\x03" b"\x51\x51" b"\x07\xd0",
        b"YY\x00\x01\x00\x1c\x01\x02",
        b"\x81\x22",
    ),
]


# RESPONSE_PDU_MESSAGES = [
#     # [(pdu_fn, pdu_fn_kwargs, encoded_pdu, packet_head, packet_tail), (..), ..]
#     (  # data0
#         "ReadInputRegistersResponse",
#         {"base_register": 0x10, "register_count": 6},
#         (
#             b"AB1234G567"
#             b"\x00\x00\x00\x00\x00\x00\x00\x08"
#             b"\x32\x04"
#             b"\x00\x10"
#             b"\x00\x06"
#         ),  # 24 bytes
#         b"YY\x00\x01\x00\x1c\x01\x02",  # 8 bytes
#         b"\x07T",  # 2 bytes
#     ),
# ]


def _lookup_pdu_class(pdu_fn: str) -> Callable:
    """Utility to retrieve a PDU function from string representation because pytest can't parametrize class names."""
    module = importlib.import_module('givenergy_modbus.pdu')
    return getattr(module, pdu_fn)
