import logging
import sys
from abc import ABC
from typing import Set

from givenergy_modbus.codec import PayloadDecoder, PayloadEncoder
from givenergy_modbus.exceptions import InvalidPduState
from givenergy_modbus.model.register import HoldingRegister
from givenergy_modbus.pdu.transparent import TransparentMessage, TransparentRequest, TransparentResponse

_logger = logging.getLogger(__name__)

# Canonical list of registers that are safe to write to.
WRITE_SAFE_REGISTERS: Set[HoldingRegister] = {
    HoldingRegister[x]
    for x in (
        'BATTERY_CHARGE_LIMIT',
        'BATTERY_DISCHARGE_LIMIT',
        'BATTERY_DISCHARGE_MIN_POWER_RESERVE',
        'BATTERY_POWER_MODE',
        'BATTERY_SOC_RESERVE',
        'CHARGE_SLOT_1_END',
        'CHARGE_SLOT_1_START',
        'CHARGE_SLOT_2_END',
        'CHARGE_SLOT_2_START',
        'CHARGE_TARGET_SOC',
        'DISCHARGE_SLOT_1_END',
        'DISCHARGE_SLOT_1_START',
        'DISCHARGE_SLOT_2_END',
        'DISCHARGE_SLOT_2_START',
        'ENABLE_CHARGE',
        'ENABLE_CHARGE_TARGET',
        'ENABLE_DISCHARGE',
        'SYSTEM_TIME_DAY',
        'SYSTEM_TIME_HOUR',
        'SYSTEM_TIME_MINUTE',
        'SYSTEM_TIME_MONTH',
        'SYSTEM_TIME_SECOND',
        'SYSTEM_TIME_YEAR',
    )
}


class WriteHoldingRegister(TransparentMessage, ABC):
    """Request & Response PDUs for function #6/Write Holding Register."""

    transparent_function_code = 6

    register: HoldingRegister
    value: int

    def __init__(self, *args, **kwargs):
        if len(args) == 2:
            kwargs['register'] = args[0]
            kwargs['value'] = args[1]
        kwargs['slave_address'] = kwargs.get('slave_address', 0x11)
        super().__init__(**kwargs)
        register = kwargs.get('register')
        if isinstance(register, HoldingRegister):
            self.register = register
        elif isinstance(register, int):
            self.register = HoldingRegister(register)
        elif isinstance(register, str):
            self.register = HoldingRegister[register]
        elif register is None:
            raise InvalidPduState('Register must be set', self)
        else:
            raise ValueError(f'Register type {type(register)} is unacceptable')
        self.value = kwargs.get('value')

    def __str__(self) -> str:
        if self.register is not None and self.value is not None:
            return (
                f'{self.function_code}:{self.transparent_function_code}/{self.__class__.__name__}'
                f"({'ERROR ' if self.error else ''}{self.register}/{self.register.name} -> "
                f'{self.register.repr(self.value)}/0x{self.value:04x})'
            )
        else:
            return super().__str__()

    def __eq__(self, o: object) -> bool:
        return (
            isinstance(o, type(self))
            and self.has_same_shape(o)
            and o.register == self.register
            and o.value == self.value
        )

    def _encode_function_data(self):
        super()._encode_function_data()
        self._builder.add_16bit_uint(self.register.value)
        self._builder.add_16bit_uint(self.value)
        self._update_check_code()

    @classmethod
    def decode_transparent_function(cls, decoder: PayloadDecoder, **attrs) -> 'WriteHoldingRegister':
        attrs['register'] = HoldingRegister(decoder.decode_16bit_uint())
        attrs['value'] = decoder.decode_16bit_uint()
        attrs['check'] = decoder.decode_16bit_uint()
        return cls(**attrs)

    def _extra_shape_hash_keys(self) -> tuple:
        return super()._extra_shape_hash_keys() + (self.register,)

    def ensure_valid_state(self):
        """Sanity check our internal state."""
        super().ensure_valid_state()
        if self.register is None:
            raise InvalidPduState('Register must be set', self)
        if self.value is None:
            raise InvalidPduState('Register value must be set', self)
        elif 0 > self.value > 0xFFFF:
            raise InvalidPduState(f'Value {self.value}/0x{self.value:04x} must be an unsigned 16-bit int', self)


class WriteHoldingRegisterRequest(WriteHoldingRegister, TransparentRequest):
    """Concrete PDU implementation for handling function #6/Write Holding Register request messages."""

    def ensure_valid_state(self):
        """Sanity check our internal state."""
        super().ensure_valid_state()
        if self.register not in WRITE_SAFE_REGISTERS:
            raise InvalidPduState(f'{self.register}/{self.register.name} is not safe to write to', self)

    def _update_check_code(self):
        crc_builder = PayloadEncoder()
        crc_builder.add_8bit_uint(self.transparent_function_code)
        crc_builder.add_16bit_uint(self.register.value)
        crc_builder.add_16bit_uint(self.value)
        self.check = crc_builder.calculate_crc()
        self._builder.add_16bit_uint(self.check)

    def expected_response(self):
        return WriteHoldingRegisterResponse(register=self.register, value=self.value, slave_address=self.slave_address)


class WriteHoldingRegisterResponse(WriteHoldingRegister, TransparentResponse):
    """Concrete PDU implementation for handling function #6/Write Holding Register response messages."""

    def ensure_valid_state(self):
        """Sanity check our internal state."""
        super().ensure_valid_state()
        if self.register not in WRITE_SAFE_REGISTERS and not self.error:
            _logger.warning(f'{self} is not safe for writing')


__all__ = ()
