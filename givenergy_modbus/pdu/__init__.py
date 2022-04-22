"""Package for the tree of PDU messages."""

from __future__ import annotations

import logging
from abc import ABC

from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadBuilder, BinaryPayloadDecoder

_logger = logging.getLogger(__package__)


class PayloadDecoder(BinaryPayloadDecoder):
    """Provide a few convenience shortcuts to the provided BinaryPayloadDecoder."""

    def __init__(self, payload):
        super().__init__(payload, byteorder=Endian.Big, wordorder=Endian.Big)

    @property
    def decoding_complete(self) -> bool:
        """Returns whether the payload has been completely decoded."""
        return self._pointer == len(self._payload)

    @property
    def payload_size(self) -> int:
        """Return the number of bytes the payload consists of."""
        return len(self._payload)

    @property
    def decoded_bytes(self) -> int:
        """Return the number of bytes of the payload that have been decoded."""
        return self._pointer

    @property
    def remaining_bytes(self) -> int:
        """Return the number of bytes of the payload that have been decoded."""
        return self.payload_size - self._pointer

    @property
    def remaining_payload(self) -> bytes:
        """Return the unprocessed / remaining tail of the payload."""
        return self._payload[self._pointer :]


class BasePDU(ABC):
    """Base of the PDU handler tree. Defines the most common shared attributes and code."""

    _builder: BinaryPayloadBuilder
    data_adapter_serial_number: str = 'AB1234G567'  # for client requests this seems ignored
    main_function_code: int

    def _set_attribute_if_present(self, attr: str, **kwargs):
        if attr in kwargs:
            setattr(self, attr, kwargs[attr])

    def __init__(self, **kwargs):
        self._set_attribute_if_present('data_adapter_serial_number', **kwargs)
        self._set_attribute_if_present('padding', **kwargs)
        self._set_attribute_if_present('slave_address', **kwargs)
        self._set_attribute_if_present('check', **kwargs)

    def encode(self) -> bytes:
        """Encode PDU message from instance attributes."""
        self._ensure_valid_state()
        self._builder = BinaryPayloadBuilder(byteorder=Endian.Big)
        self._builder.add_string(f"{self.data_adapter_serial_number[-10:]:*>10}")  # ensure exactly 10 bytes
        self._encode_function_data()
        # self._update_check_code()
        return self._builder.to_string()

    def decode(self, data: bytes) -> None:
        """Decode PDU message and populate instance attributes."""
        decoder = PayloadDecoder(data)
        self.data_adapter_serial_number = decoder.decode_string(10).decode("ascii")
        self._decode_function_data(decoder)
        if not decoder.decoding_complete:
            _logger.error(
                f'Decoder did not fully consume frame for {self}: decoded {decoder.decoded_bytes}b but '
                f'packet header specified length={decoder.payload_size}. '
                f'Remaining payload: [{decoder.remaining_payload.hex()}]'
            )
        self._ensure_valid_state()
        _logger.debug(f"Successfully decoded {len(data)} bytes: {self}")

    def _encode_function_data(self) -> None:
        """Complete function-specific encoding of the remainder of the PDU message."""
        raise NotImplementedError()

    def _decode_function_data(self, decoder: PayloadDecoder) -> None:
        """Complete function-specific decoding of the remainder of the PDU message."""
        raise NotImplementedError()

    def _ensure_valid_state(self) -> None:
        """Sanity check our internal state."""
        raise NotImplementedError()

    def has_same_shape(self, o: object):
        """Calculates whether a given message has the "same shape".

        Messages are similarly shaped when they match message type (response, error state), location (slave device,
        register type, register indexes) etc. but not data / register values.

        This is not an identity check but could be used both for creating template expected responses from
        outgoing requests (to facilitate tracking future responses), but also allows incoming messages to be
        hashed consistently to avoid (e.g.) multiple messages of the same shape getting enqueued unnecessarily –
        the theory being that newer messages being enqueued might as well replace older ones of the same shape.
        """
        if isinstance(o, BasePDU):
            return self._shape_hash() == o._shape_hash()
        return NotImplemented

    def _shape_hash(self) -> int:
        """Calculates the "shape hash" for a given message."""
        return hash(self._shape_hash_keys())

    def _shape_hash_keys(self) -> tuple:
        """Defines which keys to compare to see if two messages have the same shape."""
        return (type(self), self.main_function_code) + self._extra_shape_hash_keys()

    def _extra_shape_hash_keys(self) -> tuple:
        """Allows extra message-specific keys to be mixed in."""
        raise NotImplementedError()


class Request(BasePDU, ABC):
    """Root of the hierarchy for Request PDUs."""

    def expected_response_pdu(self) -> Response:
        """Create a template of a correctly shaped Response expected for this Request."""
        raise NotImplementedError()


class Response(BasePDU, ABC):
    """Root of the hierarchy for Response PDUs."""
