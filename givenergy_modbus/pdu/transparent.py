import logging
from abc import ABC

from givenergy_modbus.pdu import BasePDU, Request, Response

_logger = logging.getLogger(__package__)


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
            return f'{key}={val}'

        filtered_keys = (
            'error',
            'check',
            'register_values',
            'inverter_serial_number',
            'data_adapter_serial_number',
            'padding',
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

    def _decode_function_data(self, decoder):
        """Encode request PDU message and populate instance attributes."""
        self.padding = decoder.decode_64bit_uint()
        self.slave_address = decoder.decode_8bit_uint()
        inner_function_code = decoder.decode_8bit_uint()
        if inner_function_code & 0x80:
            self.error = True
            inner_function_code &= 0x7F
        if self.inner_function_code != inner_function_code:
            raise ValueError(
                f"Expected inner_function_code 0x{self.inner_function_code:02x}, "
                f"found 0x{inner_function_code:02x} instead.",
                self,
            )

    def _ensure_valid_state(self) -> None:
        if self.padding != 0x8A:
            _logger.warning(f'Expected padding 0x8a, found {hex(self.padding)} instead')

    def _update_check_code(self) -> None:
        """Recalculate CRC of the PDU message."""
        raise NotImplementedError()

    def _extra_shape_hash_keys(self):
        return (self.slave_address,)


class TransparentRequest(TransparentMessage, Request, ABC):
    """Root of the hierarchy for Transparent Request PDUs."""


class TransparentResponse(TransparentMessage, Response, ABC):
    """Root of the hierarchy for Transparent Response PDUs."""

    inverter_serial_number: str

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._set_attribute_if_present('inverter_serial_number', **kwargs)

    def _encode_function_data(self):
        super()._encode_function_data()
        self._builder.add_string(f"{self.inverter_serial_number[-10:]:*>10}")  # ensure exactly 10 bytes

    def _decode_function_data(self, decoder):
        super()._decode_function_data(decoder)
        self.inverter_serial_number = decoder.decode_string(10).decode("ascii")

    def _update_check_code(self):
        if hasattr(self, 'check'):
            # Until we know how Responses' CRCs are calculated there's nothing we can do here; self.check stays 0x0000
            _logger.warning('Unable to recalculate checksum, using whatever value was set')
            self._builder.add_16bit_uint(self.check)
