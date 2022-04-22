from __future__ import annotations

import logging
from abc import ABC

from crccheck.crc import CrcModbus
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadBuilder

from givenergy_modbus.pdu.transparent import TransparentMessage, TransparentRequest, TransparentResponse

_logger = logging.getLogger(__package__)


class WriteHoldingRegister(TransparentMessage, ABC):
    """Request & Response PDUs for function #6/Write Holding Register."""

    inner_function_code = 6

    writable_registers = {
        20,  # ENABLE_CHARGE_TARGET
        27,  # BATTERY_POWER_MODE
        31,  # CHARGE_SLOT_2_START
        32,  # CHARGE_SLOT_2_END
        35,  # SYSTEM_TIME_YEAR
        36,  # SYSTEM_TIME_MONTH
        37,  # SYSTEM_TIME_DAY
        38,  # SYSTEM_TIME_HOUR
        39,  # SYSTEM_TIME_MINUTE
        40,  # SYSTEM_TIME_SECOND
        44,  # DISCHARGE_SLOT_2_START
        45,  # DISCHARGE_SLOT_2_END
        56,  # DISCHARGE_SLOT_1_START
        57,  # DISCHARGE_SLOT_1_END
        59,  # ENABLE_DISCHARGE
        94,  # CHARGE_SLOT_1_START
        95,  # CHARGE_SLOT_1_END
        96,  # ENABLE_CHARGE
        110,  # BATTERY_SOC_RESERVE
        111,  # BATTERY_CHARGE_LIMIT
        112,  # BATTERY_DISCHARGE_LIMIT
        114,  # BATTERY_DISCHARGE_MIN_POWER_RESERVE
        116,  # TARGET_SOC
    }
    register: int
    value: int

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.register = kwargs.get('register')
        self.value = kwargs.get('value')

    def _extra_shape_hash_keys(self) -> tuple:
        return super()._extra_shape_hash_keys() + (self.register,)

    def _ensure_valid_state(self):
        if self.register is None:
            raise ValueError('Register must be set explicitly', self)
        elif self.register not in self.writable_registers:
            raise ValueError(f'Register {self.register} is not safe to write to', self)
        if self.value is None:
            raise ValueError('Register value must be set explicitly', self)
        elif 0 > self.value > 0xFFFF:
            raise ValueError(f'Register value {hex(self.value)} must be an unsigned 16-bit int', self)


class WriteHoldingRegisterRequest(WriteHoldingRegister, TransparentRequest, ABC):
    """Concrete PDU implementation for handling function #6/Write Holding Register request messages."""

    def _encode_function_data(self):
        super()._encode_function_data()
        self._builder.add_16bit_uint(self.register)
        self._builder.add_16bit_uint(self.value)
        self._update_check_code()

    def _decode_function_data(self, decoder):
        super()._decode_function_data(decoder)
        self.register = decoder.decode_16bit_uint()
        self.value = decoder.decode_16bit_uint()
        self.check = decoder.decode_16bit_uint()

    def _update_check_code(self):
        crc_builder = BinaryPayloadBuilder(byteorder=Endian.Big)
        crc_builder.add_8bit_uint(self.inner_function_code)
        crc_builder.add_16bit_uint(self.register)
        crc_builder.add_16bit_uint(self.value)
        self.check = CrcModbus().process(crc_builder.to_string()).final()
        self._builder.add_16bit_uint(self.check)

    def expected_response_pdu(self) -> WriteHoldingRegisterResponse:  # noqa D102 - see superclass
        return WriteHoldingRegisterResponse(register=self.register, value=self.value, slave_address=self.slave_address)


class WriteHoldingRegisterResponse(WriteHoldingRegister, TransparentResponse, ABC):
    """Concrete PDU implementation for handling function #6/Write Holding Register response messages."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.register: int = kwargs.get('register', None)
        self.value: int = kwargs.get('value', None)

    def _encode_function_data(self):
        super()._encode_function_data()
        # self._builder.add_string(f"{self.inverter_serial_number[-10:]:*>10}")  # ensure exactly 10 bytes
        self._builder.add_16bit_uint(self.register)
        self._builder.add_16bit_uint(self.value)
        self._update_check_code()

    def _decode_function_data(self, decoder):
        super()._decode_function_data(decoder)
        # self.inverter_serial_number = decoder.decode_string(10).decode("ascii")
        self.register = decoder.decode_16bit_uint()
        self.value = decoder.decode_16bit_uint()
        self.check = decoder.decode_16bit_uint()
