from __future__ import annotations

import abc
import logging
from typing import Callable

from pymodbus.interfaces import IModbusDecoder
from pymodbus.pdu import ExceptionResponse, ModbusExceptions

from .pdu import REQUEST_PDUS, RESPONSE_PDUS, ModbusPDU
from .util import friendly_class_name, hexlify

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

    _function_table: list[Callable]  # contains all the decoder functions this factory will consider
    _lookup: dict[int, Callable]  # lookup table mapping function code to decoder type

    def __init__(self):
        """Constructor."""
        # build the lookup table at instantiation time
        self._lookup = {f.function_code: f for f in self._function_table}

    def lookupPduClass(self, fn_code: int) -> ModbusPDU | None:
        """Attempts to find the ModbusPDU handler class that can handle a given function code."""
        if fn_code in self._lookup:
            fn = self._lookup[fn_code]
            _logger.info(f"Identified incoming PDU as {fn_code}/{friendly_class_name(fn)}")
            return fn()
        return None

    def decode(self, data: bytes) -> ModbusPDU | None:
        """Create an appropriately populated PDU message object from a valid Modbus message.

        Extracts the `function code` from the raw message and looks up the matching ModbusPDU handler class
        that claims that function. This handler is instantiated and passed the raw message, which then proceeds
        to decode its attributes from the bytestream.
        """
        if len(data) <= 19:
            _logger.error(f"PDU data is too short to find a valid function id: {len(data)} [{hexlify(data)}]")
            return None
        fn_code = data[19]
        if fn_code > 0x80:
            code = fn_code & 0x7F  # strip error portion
            return ExceptionResponse(code, ModbusExceptions.IllegalFunction)

        response = self.lookupPduClass(fn_code)
        if response:
            _logger.debug(f"About to decode data [{hexlify(data)}]")
            response.decode(data)
            return response

        _logger.error(f"No decoder for function code {fn_code}")
        return None


class GivEnergyRequestDecoder(GivEnergyDecoder):
    """Factory class to decode GivEnergy Request PDU messages. Typically used by servers processing inbound requests."""

    _function_table = REQUEST_PDUS


class GivEnergyResponseDecoder(GivEnergyDecoder):
    """Factory class to decode GivEnergy Response PDU messages. Typically used by clients to process responses."""

    _function_table = RESPONSE_PDUS
