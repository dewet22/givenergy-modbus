from __future__ import annotations

import logging
from typing import Mapping, Sequence

from givenergy_modbus.pdu import BasePDU
from givenergy_modbus.pdu.heartbeat import HeartbeatRequest
from givenergy_modbus.pdu.null import NullResponse
from givenergy_modbus.pdu.read_registers import (
    ReadHoldingRegistersRequest,
    ReadHoldingRegistersResponse,
    ReadInputRegistersRequest,
    ReadInputRegistersResponse,
)
from givenergy_modbus.pdu.transparent import TransparentMessage
from givenergy_modbus.pdu.write_registers import WriteHoldingRegisterRequest, WriteHoldingRegisterResponse

_logger = logging.getLogger(__name__)


class Decoder:
    """GivEnergy Modbus Decoder factory base class.

    This is to enable efficient decoding of unencapsulated messages (i.e. having the Modbus-specific framing
    stripped) and creating populated matching PDU DTO instances. Two factories are created, dealing with messages
    traveling in a particular direction (Request/Client vs. Response/Server) since implementations generally know
    what side of the conversation they'll be on. It does allow for more general ideas like being able to decode
    arbitrary streams of messages (i.e. captured from a network interface) where these classes may be intermixed.

    The Decoder's job is to do the bare minimum inspecting of the raw message to determine its type,
    instantiate a concrete PDU handler to decode it, and pass it on.
    """

    _function_table: Sequence[type[TransparentMessage]]  # contains all the decoder functions this factory will consider
    _lookup: Mapping[int, type[TransparentMessage]]  # lookup table mapping function code to decoder type

    def __init__(self):
        # build the lookup table at instantiation time
        self._lookup = {f.inner_function_code: f for f in self._function_table}

    def lookup_pdu_class(self, fn_code: int) -> type[TransparentMessage] | None:
        """Attempts to find the ModbusPDU handler class that can handle a given function code."""
        # strip the error bit for lookup; the PDU class will handle the error condition on decoding
        return self._lookup.get(fn_code & 0x7F, None)

    def decode(self, main_fn: int, data: bytes) -> BasePDU | None:
        """Create an appropriately populated PDU message object from a valid Modbus message.

        Extracts the `function code` from the raw message and looks up the matching ModbusPDU handler class
        that claims that function. This handler is instantiated and passed the raw message, which then proceeds
        to decode its attributes from the bytestream.
        """
        if main_fn == 1:
            pdu = HeartbeatRequest()
            pdu.decode(data)
            return pdu
        elif main_fn == 2:  # "transparent": pass-through to the inverter behind the data collector
            if len(data) <= 19:
                raise ValueError(f"Data is too short to find a valid function id: len={len(data)}")
            fn_code = data[19]
            response = self.lookup_pdu_class(fn_code & 0x7F)
            if response:
                _logger.debug(f"About to decode data [{data.hex()}]")
                r = response(error=bool(fn_code & 0x80))
                r.decode(data)
                return r
            raise ValueError(f"No decoder for inner function code {fn_code}")
        raise ValueError(f"Unknown function code {hex(main_fn)}")


class ServerDecoder(Decoder):
    """Decoder for incoming messages a server would typically expect."""

    _function_table = [
        ReadHoldingRegistersRequest,
        ReadInputRegistersRequest,
        WriteHoldingRegisterRequest,
    ]


class ClientDecoder(Decoder):
    """Decoder for incoming messages a client would typically expect."""

    _function_table = [
        NullResponse,
        ReadHoldingRegistersResponse,
        ReadInputRegistersResponse,
        WriteHoldingRegisterResponse,
    ]
