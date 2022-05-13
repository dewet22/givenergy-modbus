import logging
import struct
from abc import ABC
from typing import Optional

from givenergy_modbus.codec import PayloadDecoder, PayloadEncoder
from givenergy_modbus.exceptions import InvalidFrame

_logger = logging.getLogger(__name__)


class BasePDU(ABC):
    """Base of the PDU Message handler class tree.

    The Protocol Data Unit (PDU) defines the basic unit of message exchange for Modbus. It is routed to devices with
    specific addresses, and targets specific operations through function codes. This tree defines the hierarchy of
    functions, along with the attributes they specify and how they are encoded.

    The tree branches at the top based on the directionality of the messages – either client-focused (messages a
    client should expect to receive and send) or server-focused (less important for this library, but messages that a
    server would emit and expect to receive). It is mirrored in that a Request message from a client would have a
    matching Response message the server should reply with.

    The PDU classes are also codecs – they know how to convert between binary network frames and instantiated objects
    that can be manipulated programmatically.
    """

    _builder: PayloadEncoder
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
        self.ensure_valid_state()
        self._builder = PayloadEncoder()
        self._builder.add_serial_number(self.data_adapter_serial_number)
        self._encode_function_data()
        # self._update_check_code()
        return self._builder.to_string()

    @classmethod
    def decode_bytes(cls, data: bytes) -> 'BasePDU':
        """Decode raw byte frame to populated PDU instance."""
        _logger.debug(f'{cls.__name__}.decode_bytes(0x{data.hex()})')
        attrs = {}
        decoder = PayloadDecoder(data)
        attrs['_tid'] = decoder.decode_16bit_uint()
        attrs['_pid'] = decoder.decode_16bit_uint()
        attrs['_len'] = decoder.decode_16bit_uint()
        remaining_bytes = decoder.remaining_bytes
        attrs['_uid'] = decoder.decode_8bit_uint()
        attrs['main_function_code'] = decoder.decode_8bit_uint()
        if attrs['_tid'] != 0x5959:
            raise InvalidFrame(f'Transaction ID != 0x5959, attrs: {attrs}', data)
        if attrs['_pid'] != 0x01:
            raise InvalidFrame(f'Protocol ID != 0x0001, attrs: {attrs}', data)
        if attrs['_len'] != remaining_bytes:
            raise InvalidFrame(
                f'Header length {attrs["_len"]} != remaining bytes {remaining_bytes}, attrs: {attrs}', data
            )
        if attrs['_uid'] != 0x01:
            raise InvalidFrame(f'Unit ID != 0x01, attrs: {attrs}', data)

        candidate_decoder_classes = cls.__subclasses__()
        _logger.debug(
            f'Candidate decoders for function code {attrs["main_function_code"]}: '
            f'{", ".join([c.__name__ for c in candidate_decoder_classes])}'
        )

        for c in candidate_decoder_classes:
            cls_main_function_code = getattr(c, 'main_function_code', None)
            if cls_main_function_code == attrs['main_function_code']:
                _logger.debug(f'Passing off to {c.__name__}.decode_main_function(0x{decoder.remaining_payload.hex()})')
                try:
                    pdu = c._decode_main_function(decoder, **attrs)
                except struct.error as e:
                    raise InvalidFrame(str(e), data)
                if not decoder.decoding_complete:
                    _logger.error(
                        f'Decoder did not fully consume frame for {pdu}: decoded {decoder.decoded_bytes}b but '
                        f'packet header specified length={decoder.payload_size}. '
                        f'Remaining payload: [{decoder.remaining_payload.hex()}]'
                    )
                pdu.ensure_valid_state()
                if not decoder.remaining_bytes == 0:
                    _logger.warning(
                        f'Decoder buffer not exhausted, {decoder.remaining_bytes} bytes remain: '
                        f'0x{decoder.remaining_payload.hex()}'
                    )
                return pdu
            _logger.debug(f'{c.__name__} disregarded, it handles function code {cls_main_function_code}')
        raise InvalidFrame(f'Found no decoder for function code {attrs["main_function_code"]}', data)

    @classmethod
    def _decode_main_function(cls, decoder: PayloadDecoder, **attrs) -> 'BasePDU':
        raise NotImplementedError()

    def _encode_function_data(self) -> None:
        """Complete function-specific encoding of the remainder of the PDU message."""
        raise NotImplementedError()

    def ensure_valid_state(self) -> None:
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
            return self.shape_hash() == o.shape_hash()
        return NotImplemented

    def shape_hash(self) -> int:
        """Calculates the "shape hash" for a given message."""
        return hash(self._shape_hash_keys())

    def _shape_hash_keys(self) -> tuple:
        """Defines which keys to compare to see if two messages have the same shape."""
        return (type(self), self.main_function_code) + self._extra_shape_hash_keys()

    def _extra_shape_hash_keys(self) -> tuple:
        """Allows extra message-specific keys to be mixed in."""
        raise NotImplementedError()


class ClientIncomingMessage(BasePDU, ABC):
    """Root of the hierarchy for PDUs clients are expected to receive and handle."""

    def expected_response(self) -> Optional['ClientOutgoingMessage']:
        """Create a template of a correctly shaped Response expected for this Request."""
        raise NotImplementedError()


class ClientOutgoingMessage(BasePDU, ABC):
    """Root of the hierarchy for PDUs clients are expected to send to servers."""

    def expected_response(self) -> Optional['ClientIncomingMessage']:
        """Create a template of a correctly shaped Response expected for this Request."""
        raise NotImplementedError()


ServerIncomingMessage = ClientOutgoingMessage
ServerOutgoingMessage = ClientIncomingMessage

__all__ = ()
