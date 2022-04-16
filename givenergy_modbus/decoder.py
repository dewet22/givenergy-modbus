from __future__ import annotations

import abc
import logging
from typing import Mapping, Sequence

from pymodbus.interfaces import IModbusDecoder

from givenergy_modbus.pdu import (
    HeartbeatRequest,
    ModbusPDU,
    ReadHoldingRegistersRequest,
    ReadHoldingRegistersResponse,
    ReadInputRegistersRequest,
    ReadInputRegistersResponse,
    WriteHoldingRegisterRequest,
    WriteHoldingRegisterResponse,
    NullResponse,
)
from givenergy_modbus.util import hexlify

_logger = logging.getLogger(__package__)


class GivEnergyDecoder(IModbusDecoder, metaclass=abc.ABCMeta):
    """GivEnergy Modbus Decoder factory base class.

    This is to enable efficient decoding of unencapsulated messages (i.e. having the Modbus-specific framing
    stripped) and creating populated matching PDU DTO instances. Two factories are created, dealing with messages
    traveling in a particular direction (Request/Client vs. Response/Server) since implementations generally know
    what side of the conversation they'll be on. It does allow for more general ideas like being able to decode
    arbitrary streams of messages (i.e. captured from a network interface) where these classes may be intermixed.

    The Decoder's job is to do the bare minimum inspecting of the raw message to determine its type,
    instantiate a concrete PDU handler to decode it, and pass it on.
    """

    _function_table: Sequence[type[ModbusPDU]]  # contains all the decoder functions this factory will consider
    _lookup: Mapping[int, type[ModbusPDU]]  # lookup table mapping function code to decoder type

    def __init__(self):
        # build the lookup table at instantiation time
        self._lookup = {f.function_code: f for f in self._function_table}

    def lookupPduClass(self, fn_code: int) -> type[ModbusPDU] | None:
        """Attempts to find the ModbusPDU handler class that can handle a given function code."""
        # strip the error bit for lookup; the PDU class will handle the error condition on decoding
        return self._lookup.get(fn_code & 0x7F, None)

    def decode(self, data: bytes) -> ModbusPDU | None:
        """Create an appropriately populated PDU message object from a valid Modbus message.

        Extracts the `function code` from the raw message and looks up the matching ModbusPDU handler class
        that claims that function. This handler is instantiated and passed the raw message, which then proceeds
        to decode its attributes from the bytestream.
        """
        main_fn = data[0]
        data = data[1:]
        if main_fn == 0x1:  # heartbeat
            pdu = HeartbeatRequest()
            pdu.decode(data)
            return pdu
        elif main_fn == 0x2:  # "transparent": pass-through to the inverter behind the data collector
            if len(data) <= 19:
                raise ValueError(f"Data is too short to find a valid function id: len={len(data)}")
            fn_code = data[19]
            response = self.lookupPduClass(fn_code)
            if response:
                _logger.debug(f"About to decode data [{hexlify(data)}]")
                r = response(function_code=fn_code)
                r.decode(data)
                return r
            raise ValueError(f"No decoder for inner function code {fn_code}")
        raise ValueError(f"Unknown function code {hex(main_fn)}")


class GivEnergyRequestDecoder(GivEnergyDecoder):
    """Factory class to decode GivEnergy Request PDU messages. Typically used by servers processing inbound requests."""

    _function_table = [
        ReadHoldingRegistersRequest,
        ReadInputRegistersRequest,
        WriteHoldingRegisterRequest,
    ]


class GivEnergyResponseDecoder(GivEnergyDecoder):
    """Factory class to decode GivEnergy Response PDU messages. Typically used by clients to process responses."""

    _function_table = [
        NullResponse,
        ReadHoldingRegistersResponse,
        ReadInputRegistersResponse,
        WriteHoldingRegisterResponse,
    ]
