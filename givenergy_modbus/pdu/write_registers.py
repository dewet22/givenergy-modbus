from __future__ import annotations

import logging
from abc import ABC

from crccheck.crc import CrcModbus
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadBuilder

from givenergy_modbus.exceptions import InvalidPduState
from givenergy_modbus.model.register import HoldingRegister
from givenergy_modbus.pdu.transparent import TransparentMessage, TransparentRequest, TransparentResponse

_logger = logging.getLogger(__name__)

# Canonical list of registers that are safe to write to.
WRITE_SAFE_REGISTERS: set[HoldingRegister] = {
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

    inner_function_code = 6

    register: HoldingRegister
    value: int

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        register = kwargs.get('register')
        if isinstance(register, HoldingRegister):
            self.register = register
        elif isinstance(register, int):
            self.register = HoldingRegister(register)
        elif isinstance(register, str):
            self.register = HoldingRegister[register]
        else:
            self.register = None
        self.value = kwargs.get('value')

    def __str__(self) -> str:
        if self.register is not None and self.value is not None:
            return (
                f"{self.main_function_code}:{getattr(self, 'inner_function_code', '_')}/"
                f"{self.__class__.__name__}({'ERROR ' if self.error else ''}"
                f"{self.register}/{self.register.name} -> "
                f"{self.register.repr(self.value)}/0x{self.value:04x})"
            )
        else:
            return super().__str__()

    def _encode_function_data(self):
        super()._encode_function_data()
        self._builder.add_16bit_uint(self.register.value)
        self._builder.add_16bit_uint(self.value)
        self._update_check_code()

    def _decode_function_data(self, decoder):
        super()._decode_function_data(decoder)
        self.register = HoldingRegister(decoder.decode_16bit_uint())
        self.value = decoder.decode_16bit_uint()
        self.check = decoder.decode_16bit_uint()

    def _extra_shape_hash_keys(self) -> tuple:
        return super()._extra_shape_hash_keys() + (self.register,)

    def ensure_valid_state(self):
        """Sanity check our internal state."""
        super().ensure_valid_state()
        if self.register is None:
            raise InvalidPduState('Register must be set explicitly', self)
        if self.value is None:
            raise InvalidPduState('Register value must be set explicitly', self)
        elif 0 > self.value > 0xFFFF:
            raise InvalidPduState(f'Register value {hex(self.value)} must be an unsigned 16-bit int', self)


class WriteHoldingRegisterRequest(WriteHoldingRegister, TransparentRequest, ABC):
    """Concrete PDU implementation for handling function #6/Write Holding Register request messages."""

    def ensure_valid_state(self):
        """Sanity check our internal state."""
        super().ensure_valid_state()
        if self.register not in WRITE_SAFE_REGISTERS:
            raise InvalidPduState(f'{self.register}/{self.register.name} is not safe to write to', self)

    def _update_check_code(self):
        crc_builder = BinaryPayloadBuilder(byteorder=Endian.Big)
        crc_builder.add_8bit_uint(self.inner_function_code)
        crc_builder.add_16bit_uint(self.register.value)
        crc_builder.add_16bit_uint(self.value)
        self.check = CrcModbus().process(crc_builder.to_string()).final()
        self._builder.add_16bit_uint(self.check)

    def expected_response(self) -> WriteHoldingRegisterResponse:  # noqa D102 - see superclass
        return WriteHoldingRegisterResponse(register=self.register, value=self.value, slave_address=self.slave_address)


class WriteHoldingRegisterResponse(WriteHoldingRegister, TransparentResponse, ABC):
    """Concrete PDU implementation for handling function #6/Write Holding Register response messages."""

    def ensure_valid_state(self):
        """Sanity check our internal state."""
        super().ensure_valid_state()
        if self.register not in WRITE_SAFE_REGISTERS:
            _logger.warning(f'Wrote {self.value} to register {self.register} which is not safe for writing')
