from __future__ import annotations

import logging

from givenergy_modbus.pdu import PayloadDecoder
from givenergy_modbus.pdu.transparent import TransparentResponse

_logger = logging.getLogger(__name__)


class NullResponse(TransparentResponse):
    """Concrete PDU implementation for handling function #0/Null Response messages.

    This seems to be a quirk of the GivEnergy implementation – from time to time these responses will be sent
    unprompted by the remote device and this just handles it gracefully and allows further debugging. The function
    data payload seems to be invariably just a series of nulls.
    """

    inner_function_code = 0
    nulls = [0] * 62

    def _encode_function_data(self) -> None:
        super()._encode_function_data()
        [self._builder.add_16bit_uint(v) for v in self.nulls]
        self._update_check_code()

    def _decode_function_data(self, decoder: PayloadDecoder) -> None:
        super()._decode_function_data(decoder)
        self.nulls = [decoder.decode_16bit_uint() for _ in range(62)]
        self.check = decoder.decode_16bit_uint()

    def _ensure_valid_state(self) -> None:
        if self.inverter_serial_number != '\x00' * 10:
            if isinstance(self.inverter_serial_number, str):
                hex_str = self.inverter_serial_number.encode('ascii').hex()
            else:
                hex_str = bytes(self.inverter_serial_number).hex()
            _logger.warning(
                f'Unexpected non-null inverter serial number: {self.inverter_serial_number}/0x{hex_str}', self
            )
        if any(self.nulls):
            _logger.warning(
                f'Unexpected non-null "register" values: {dict(filter(lambda v: v[1] != 0, enumerate(self.nulls)))}',
                self,
            )

    def _extra_shape_hash_keys(self) -> tuple:
        return ()
