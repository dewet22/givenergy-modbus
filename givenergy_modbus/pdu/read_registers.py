from __future__ import annotations

import logging
from abc import ABC

from crccheck.crc import CrcModbus
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadBuilder

from givenergy_modbus.exceptions import InvalidPduState
from givenergy_modbus.pdu.transparent import TransparentMessage, TransparentRequest, TransparentResponse

_logger = logging.getLogger(__package__)


class ReadRegisters(TransparentMessage, ABC):
    """Mixin for commands that specify base register and register count semantics."""

    base_register: int
    register_count: int

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.base_register = kwargs.get('base_register', 0)
        self.register_count = kwargs.get('register_count', 0)

    def _extra_shape_hash_keys(self) -> tuple:
        return super()._extra_shape_hash_keys() + (self.base_register, self.register_count)

    def _ensure_registers_spec_correct(self):
        if self.base_register is None:
            raise ValueError('Base register must be set', self)
        if self.base_register < 0 or 0xFFFF < self.base_register:
            raise ValueError('Base register must be an unsigned 16-bit int', self)

        if self.register_count is None:
            raise ValueError('Register count must be set', self)


class ReadRegistersRequest(ReadRegisters, TransparentRequest, ABC):
    """Handles all messages that request a range of registers."""

    def _encode_function_data(self):
        super()._encode_function_data()
        self._builder.add_16bit_uint(self.base_register)
        self._builder.add_16bit_uint(self.register_count)
        self._update_check_code()

    def _decode_function_data(self, decoder):
        super()._decode_function_data(decoder)
        self.base_register = decoder.decode_16bit_uint()
        self.register_count = decoder.decode_16bit_uint()
        self.check = decoder.decode_16bit_uint()

    def _update_check_code(self):
        crc_builder = BinaryPayloadBuilder(byteorder=Endian.Big)
        crc_builder.add_8bit_uint(self.inner_function_code)
        crc_builder.add_16bit_uint(self.base_register)
        crc_builder.add_16bit_uint(self.register_count)
        self.check = CrcModbus().process(crc_builder.to_string()).final()
        self._builder.add_16bit_uint(self.check)

    def _ensure_valid_state(self):
        self._ensure_registers_spec_correct()

        if self.register_count != 1 and self.base_register % 60 != 0:
            _logger.warning(f'Base register {self.base_register} not aligned on 60-byte boundary')
        if self.register_count <= 0 or 60 < self.register_count:
            raise ValueError('Register count must be in (0,60]', self)


class ReadRegistersResponse(ReadRegisters, TransparentResponse, ABC):
    """Handles all messages that respond with a range of registers."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.register_values: list[int] = kwargs.get('register_values', [])
        if self.register_count != len(self.register_values):
            raise ValueError(
                f'Expected to receive {self.register_count} register values, '
                f'instead received {len(self.register_values)}.',
                self,
            )

    def _encode_function_data(self):
        super()._encode_function_data()
        self._builder.add_16bit_uint(self.base_register)
        self._builder.add_16bit_uint(self.register_count)
        [self._builder.add_16bit_uint(v) for v in self.register_values]
        self._update_check_code()

    def _decode_function_data(self, decoder):
        super()._decode_function_data(decoder)
        self.base_register = decoder.decode_16bit_uint()
        self.register_count = decoder.decode_16bit_uint()
        if not self.error:
            self.register_values = [decoder.decode_16bit_uint() for _ in range(self.register_count)]
        self.check = decoder.decode_16bit_uint()

    def _ensure_valid_state(self) -> None:
        self._ensure_registers_spec_correct()

        if not self.error and self.register_count != 1 and self.base_register % 60 != 0:
            _logger.warning(f'Base register {self.base_register} not aligned on 60-byte boundary')

        if self.error:
            expected_padding = 0x12
        else:
            expected_padding = 0x8A
        if self.padding != expected_padding:
            _logger.debug(f'Expected padding {hex(expected_padding)}, found {hex(self.padding)} instead: {self}')

        # FIXME how to test crc
        # crc_builder = BinaryPayloadBuilder(byteorder=Endian.Big)
        # crc_builder.add_8bit_uint(self.function_code)
        # crc_builder.add_16bit_uint(self.base_register)
        # crc_builder.add_16bit_uint(self.register_count)
        # # [crc_builder.add_16bit_uint(r) for r in self.register_values]
        # crc = CrcModbus().process(crc_builder.to_string()).final()
        # _logger.warning(f'supplied crc = {self.check}, calculated crc = {crc}')

    def to_dict(self) -> dict[int, int]:
        """Return the registers as a dict of register_index:value. Accounts for base_register offsets."""
        return {k: v for k, v in enumerate(self.register_values, start=self.base_register)}


class ReadHoldingRegisters(ReadRegisters, ABC):
    """Request & Response PDUs for function #3/Read Holding Registers."""

    inner_function_code = 3


class ReadHoldingRegistersRequest(ReadHoldingRegisters, ReadRegistersRequest):
    """Concrete PDU implementation for handling function #3/Read Holding Registers request messages."""

    def expected_response_pdu(self):  # noqa D102 - see superclass
        return ReadHoldingRegistersResponse(
            base_register=self.base_register, register_count=self.register_count, slave_address=self.slave_address
        )


class ReadHoldingRegistersResponse(ReadHoldingRegisters, ReadRegistersResponse):
    """Concrete PDU implementation for handling function #3/Read Holding Registers response messages."""


class ReadInputRegisters(ReadRegisters, ABC):
    """Request & Response PDUs for function #4/Read Input Registers."""

    inner_function_code = 4


class ReadInputRegistersRequest(ReadInputRegisters, ReadRegistersRequest):
    """Concrete PDU implementation for handling function #4/Read Input Registers request messages."""

    def expected_response_pdu(self):  # noqa D102 - see superclass
        return ReadInputRegistersResponse(
            base_register=self.base_register, register_count=self.register_count, slave_address=self.slave_address
        )


class ReadInputRegistersResponse(ReadInputRegisters, ReadRegistersResponse):
    """Concrete PDU implementation for handling function #4/Read Input Registers response messages."""

    # def _ensure_valid_state(self):
    #     super()._ensure_valid_state()
    #     if (
    #         self.base_register == 60
    #         and self.register_count == 60
    #         and 0x30 <= self.slave_address <= 0x37
    #         and sum(self.register_values[50:55]) == 0x0  # all-null serial number
    #     ):
    #         # GivEnergy quirk: Unsolicited BMS responses get received, even for non-existent devices – likely
    #         # part of a discovery mechanism?
    #         raise InvalidPduState(self, 'BMS data with empty serial number, battery is likely not installed', True)
