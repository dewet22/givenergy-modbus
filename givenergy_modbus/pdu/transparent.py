import logging
from abc import ABC

from givenergy_modbus.codec import PayloadDecoder
from givenergy_modbus.exceptions import InvalidFrame
from givenergy_modbus.pdu.base import BasePDU, ClientIncomingMessage, ClientOutgoingMessage

_logger = logging.getLogger(__name__)


class TransparentMessage(BasePDU, ABC):
    """Root of the hierarchy for 2/Transparent PDUs."""

    main_function_code = 2
    padding: int = 0x8
    slave_address: int = 0x32  # 0x11 is the inverter but the cloud systems interfere, use 0x32+
    inner_function_code: int
    error: bool = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._set_attribute_if_present('padding', **kwargs)
        self._set_attribute_if_present('slave_address', **kwargs)
        self._set_attribute_if_present('error', **kwargs)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        _logger.info(f'TransparentMessage.__init_subclass__({cls.__name__})')

    def __str__(self) -> str:
        def format_kv(key, val):
            if val is None:
                val = '?'
            elif key in ('slave_address',):
                val = f'0x{val:02x}'
            elif key in ('check', 'padding'):
                val = f'0x{val:04x}'
            elif key == 'error' and val:
                return 'ERROR'
            elif key == 'nulls':
                return f'nulls=[0]*{len(val)}'
            return f'{key}={val}'

        filtered_keys = (
            'error',
            'check',
            'register_values',
            'inverter_serial_number',
            'data_adapter_serial_number',
            'padding',
            '_builder',
        )
        if self.error:
            filtered_args = [format_kv(k, v) for k, v in vars(self).items()]
        else:
            filtered_args = [format_kv(k, v) for k, v in vars(self).items() if k not in filtered_keys]

        return (
            f"{self.main_function_code}:{getattr(self, 'inner_function_code', '_')}/"
            f"{self.__class__.__name__}({' '.join(filtered_args)})"
        )

    def _encode_function_data(self):
        self._builder.add_64bit_uint(self.padding)
        self._builder.add_8bit_uint(self.slave_address)
        self._builder.add_8bit_uint(self.inner_function_code)
        # self._update_check_code()

    @classmethod
    def _decode_main_function(cls, decoder: PayloadDecoder, **attrs) -> 'TransparentMessage':
        attrs['data_adapter_serial_number'] = decoder.decode_serial_number()
        attrs['padding'] = decoder.decode_64bit_uint()
        attrs['slave_address'] = decoder.decode_8bit_uint()
        inner_function_code = decoder.decode_8bit_uint()
        if inner_function_code & 0x80:
            error = True
            inner_function_code &= 0x7F
        else:
            error = False
        attrs['error'] = error

        if issubclass(cls, TransparentResponse):
            attrs['inverter_serial_number'] = decoder.decode_serial_number()

        candidate_decoder_classes = cls.__subclasses__()
        for c in candidate_decoder_classes:
            candidate_decoder_classes.extend(c.__subclasses__())
        _logger.debug(
            f'Candidate decoders for inner function code {inner_function_code}: '
            f'{", ".join([c.__name__ for c in candidate_decoder_classes])}'
        )

        for c in candidate_decoder_classes:
            cls_inner_function_code = getattr(c, 'inner_function_code', None)
            if cls_inner_function_code == inner_function_code:
                _logger.debug(
                    f'Passing off to {c.__name__}.decode_inner_function(0x{decoder.remaining_payload.hex()}, {attrs})'
                )
                return c._decode_inner_function(decoder, **attrs)
            _logger.debug(f'{c.__name__} disregarded, it handles function code {cls_inner_function_code}')
        raise InvalidFrame(
            f'No known decoder for inner function code {inner_function_code} (attrs={attrs})',
            frame=decoder.remaining_payload,
        )

    @classmethod
    def _decode_inner_function(cls, decoder: PayloadDecoder, **attrs) -> 'TransparentMessage':
        raise NotImplementedError()

    def ensure_valid_state(self) -> None:  # flake8: D102
        """Sanity check our internal state."""
        # if self.padding != 0x8A:
        #     _logger.debug(f'Expected padding 0x8a, found 0x{self.padding:02x} instead')

    def _update_check_code(self) -> None:
        """Recalculate CRC of the PDU message."""
        raise NotImplementedError()

    def _extra_shape_hash_keys(self):
        return (self.slave_address,)


class TransparentRequest(TransparentMessage, ClientOutgoingMessage, ABC):
    """Root of the hierarchy for Transparent Request PDUs."""


class TransparentResponse(TransparentMessage, ClientIncomingMessage, ABC):
    """Root of the hierarchy for Transparent Response PDUs."""

    inverter_serial_number: str

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._set_attribute_if_present('inverter_serial_number', **kwargs)

    def _encode_function_data(self):
        super()._encode_function_data()
        self._builder.add_serial_number(self.inverter_serial_number)

    def _update_check_code(self):
        if hasattr(self, 'check'):
            # Until we know how Responses' CRCs are calculated there's nothing we can do here; self.check stays 0x0000
            _logger.warning('Unable to recalculate checksum, using whatever value was set')
            self._builder.add_16bit_uint(self.check)


__all__ = ()
