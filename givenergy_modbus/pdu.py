"""`pymodbus.pdu.ModbusPDU` implementations for GivEnergy-specific PDU messages."""

from __future__ import annotations

import logging
from abc import ABC
from typing import Any

from crccheck.crc import CrcModbus
from pymodbus import pdu as pymodbus_pdu
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadBuilder, BinaryPayloadDecoder

from givenergy_modbus.util import friendly_class_name, hexxed

_logger = logging.getLogger(__package__)


class RegisterRangeCommand:
    """Mixin for commands that specify base register and register count semantics."""

    base_register: int
    register_count: int
    error: bool

    def _ensure_registers_spec_correct(self):
        if self.base_register is None:
            raise ValueError('Base register must be set', self)
        if 0xFFFF < self.base_register < 0:
            raise ValueError('Base register must be an unsigned 16-bit int', self)
        if not self.error and self.base_register % 60 != 0:
            _logger.warning(f'Base register {self.base_register} is not aligned on 60-byte boundary according to spec')

        if self.register_count is None:
            raise ValueError('Register count must be set', self)
        if 60 < self.register_count < 0:
            raise ValueError('Register count must be in [0,60]', self)


class ModbusPDU(ABC):
    """Base of the PDU handler tree. Defines the most common shared attributes and code."""

    builder: BinaryPayloadBuilder
    function_code: int
    error: bool = False
    data_adapter_serial_number: str = 'AB1234G567'  # for client requests this seems ignored
    padding: int = 0x8
    slave_address: int = 0x32  # 0x11 is the inverter but the cloud systems interfere, 0x32+ are the batteries

    def __init__(self, **kwargs):
        if "function_id" in kwargs:  # TODO can be removed?
            raise ValueError("function_id= is not valid, use function_code= instead.", self)

        if "function_code" in kwargs:
            if not hasattr(self, 'function_code'):
                raise ValueError(
                    f"Class {self.__class__.__name__} does not have a function code, "
                    f"trying to override it is not supported",
                    self,
                )
            function_code = kwargs["function_code"]
            if function_code >= 0x80:
                self.error = True
                function_code &= 0x7F
            if function_code != self.function_code:
                raise ValueError(
                    f"Specified function code {kwargs['function_code']} is different "
                    f"from what {self} is expecting.",
                    self,
                )
            del kwargs['function_code']
        kwargs.update(  # ensure these can never get overwritten  TODO can be removed?
            {
                "transaction": 0x5959,
                "protocol": 0x0001,
                "unit": 0x01,
            }
        )
        self._set_attribute_if_present('data_adapter_serial_number', kwargs)
        self._set_attribute_if_present('padding', kwargs)
        self._set_attribute_if_present('slave_address', kwargs)
        self._set_attribute_if_present('check', kwargs)

    def __str__(self) -> str:
        filtered_keys = [
            'transaction_id',
            'protocol_id',
            'unit_id',
            'check',
            'skip_encode',  # from pymodbus
            'register_values',
            'builder',
        ]
        filtered_vars = ', '.join([f'{k}: {hexxed(v)}' for k, v in vars(self).items() if k not in filtered_keys])
        if len(filtered_vars) > 0:
            filtered_vars = '{' + filtered_vars + '}'
        return f"{getattr(self, 'function_code', '_')}/{friendly_class_name(self.__class__)}({filtered_vars})"

    def _set_attribute_if_present(self, attr: str, kwargs: dict[str, Any]):
        if attr in kwargs:
            setattr(self, attr, kwargs[attr])

    def encode(self) -> bytes:
        """Encode PDU message from instance attributes."""
        self._ensure_valid_state()
        self.builder = BinaryPayloadBuilder(byteorder=Endian.Big)
        self.builder.add_string(f"{self.data_adapter_serial_number[-10:]:*>10}")  # ensure exactly 10 bytes
        self.builder.add_64bit_uint(self.padding)
        self.builder.add_8bit_uint(self.slave_address)
        self.builder.add_8bit_uint(self.function_code)
        self._encode_function_data()
        self._update_check_code()
        return self.builder.to_string()

    def decode(self, data: bytes) -> None:
        """Decode PDU message and populate instance attributes."""
        decoder = BinaryPayloadDecoder(data, byteorder=Endian.Big)
        self.data_adapter_serial_number = decoder.decode_string(10).decode("ascii")
        self.padding = decoder.decode_64bit_uint()
        self.slave_address = decoder.decode_8bit_uint()
        function_code = decoder.decode_8bit_uint()
        if function_code >= 0x80:
            self.error = True
            function_code = function_code & 0x7F
        if self.function_code != function_code:
            raise ValueError(
                f"Expected function code 0x{self.function_code:02x}, found 0x{function_code:02x} instead.", self
            )

        self._decode_function_data(decoder)
        if decoder._pointer != len(decoder._payload):
            _logger.error(f'Decoder did not fully decode {function_code} packet: decoded {decoder._pointer} bytes but '
                          f'packet header specified length={len(decoder._payload)}. '
                          f'Remaining bytes: [{decoder._payload[decoder._pointer:]}]')
        self._ensure_valid_state()
        _logger.debug(f"Successfully decoded {len(data)} bytes: {self}")

    def _encode_function_data(self) -> None:
        """Complete function-specific encoding of the remainder of the PDU message."""
        raise NotImplementedError()

    def _decode_function_data(self, decoder: BinaryPayloadDecoder) -> None:
        """Complete function-specific decoding of the remainder of the PDU message."""
        raise NotImplementedError()

    def _update_check_code(self) -> None:
        """Recalculate CRC of the PDU message."""
        raise NotImplementedError()

    def _ensure_valid_state(self) -> None:
        """Sanity check our internal state."""
        raise NotImplementedError()

    def get_response_pdu_size(self) -> int:
        """Allows the framer to decapsulate the PDU properly from the MBAP frame header."""
        # 20 = 10 (data adapter serial) + 8 (padding) + 1 (slave addr) + 1 (function code)
        size = 20 + self._calculate_function_data_size()
        _logger.debug(f"Calculated {size} bytes total response PDU size for {self}")
        if size >= 247:
            _logger.error('Expected response size {size}b exceeds Modbus protocol spec')
        return size

    def _calculate_function_data_size(self) -> int:
        raise NotImplementedError()

    def execute(self) -> ModbusPDU | None:
        """Called to create the Response PDU after an incoming message has been completely processed."""
        raise NotImplementedError()


#################################################################################
class ModbusRequest(ModbusPDU, pymodbus_pdu.ModbusRequest, ABC):
    """Root of the hierarchy for Request PDUs."""

    def execute(self):
        """Hook that allows a Response PDU to be created from the same context where the Request was handled."""
        raise NotImplementedError()


class ModbusResponse(ModbusPDU, pymodbus_pdu.ModbusResponse, ABC):
    """Root of the hierarchy for Response PDUs."""

    error: bool = False

    def _update_check_code(self):
        if hasattr(self, 'check'):
            # Until we know how Responses are checksummed there's nothing we can do here; self.check stays 0x0000
            _logger.warning('Unable to recalculate checksum, using whatever value was set')
            self.builder.add_16bit_uint(self.check)

    def execute(self):
        """There is no automatic Reply following the processing of a Response."""

    # fmt: off
    def _ensure_valid_state(self):
        if self.slave_address not in (
            0x0,                     # mobile app
            0x11,                    # inverter
            # 0x30, 0x31,            # ??
            0x32,                    # inverter / first battery?
            0x33, 0x34, 0x35, 0x36,  # 4x additional batteries
        ):
            _logger.warning(f'Unexpected slave {hex(self.slave_address)}: {self}')
    # fmt: on


#################################################################################
class NullResponse(ModbusResponse):
    """Concrete PDU implementation for handling function #0/Null Response messages."""

    function_code = 0

    def _encode_function_data(self) -> None:
        pass

    def _decode_function_data(self, decoder: BinaryPayloadDecoder) -> None:
        decoder.skip_bytes(len(decoder._payload) - 20)

    def _calculate_function_data_size(self) -> int:
        pass

    # def _calculate_function_data_size(self) -> int:
    #     raise NotImplementedError()


#################################################################################
class ReadRegistersRequest(ModbusRequest, RegisterRangeCommand, ABC):
    """Handles all messages that request a range of registers."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.base_register = kwargs.get('base_register', 0)
        self.register_count = kwargs.get('register_count', 60)

    def _encode_function_data(self):
        self.builder.add_16bit_uint(self.base_register)
        self.builder.add_16bit_uint(self.register_count)

    def _decode_function_data(self, decoder):
        self.base_register = decoder.decode_16bit_uint()
        self.register_count = decoder.decode_16bit_uint()
        self.check = decoder.decode_16bit_uint()

    def _update_check_code(self):
        crc_builder = BinaryPayloadBuilder(byteorder=Endian.Big)
        crc_builder.add_8bit_uint(self.function_code)
        crc_builder.add_16bit_uint(self.base_register)
        crc_builder.add_16bit_uint(self.register_count)
        self.check = CrcModbus().process(crc_builder.to_string()).final()
        self.builder.add_16bit_uint(self.check)

    def _calculate_function_data_size(self):
        size = 16 + (self.register_count * 2)
        _logger.debug(f"Calculated {size} bytes partial response size for {self}")
        return size

    def _ensure_valid_state(self):
        self._ensure_registers_spec_correct()


class ReadRegistersResponse(ModbusResponse, RegisterRangeCommand, ABC):
    """Handles all messages that respond with a range of registers."""

    request_class: type[ReadRegistersRequest]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.inverter_serial_number: str = kwargs.get('inverter_serial_number', 'SA1234G567')
        self.base_register: int = kwargs.get('base_register', -1)
        self.register_count: int = kwargs.get('register_count', 0)
        self.register_values: list[int] = kwargs.get('register_values', [])
        if self.register_count != len(self.register_values):
            raise ValueError(
                f'Expected to receive {self.register_count} register values, '
                f'instead received {len(self.register_values)}.',
                self,
            )

    def _encode_function_data(self):
        self.builder.add_string(f"{self.inverter_serial_number[-10:]:*>10}")  # ensure exactly 10 bytes
        self.builder.add_16bit_uint(self.base_register)
        self.builder.add_16bit_uint(self.register_count)
        [self.builder.add_16bit_uint(v) for v in self.register_values]

    def _decode_function_data(self, decoder):
        """Decode response PDU message and populate instance attributes."""
        self.inverter_serial_number = decoder.decode_string(10).decode("ascii")
        self.base_register = decoder.decode_16bit_uint()
        self.register_count = decoder.decode_16bit_uint()
        if not self.error:
            self.register_values = [decoder.decode_16bit_uint() for _ in range(self.register_count)]
        self.check = decoder.decode_16bit_uint()

    def _ensure_valid_state(self) -> None:
        self._ensure_registers_spec_correct()

        if self.error:
            expected_padding = 0x12
        else:
            expected_padding = 0x8A
        if self.padding != expected_padding:
            _logger.debug(f'Expected padding {hex(expected_padding)}, found {hex(self.padding)} instead: {self}')

    def to_dict(self):
        """Return the registers as a dict of register_index:value. Accounts for base_register offsets."""
        return {k: v for k, v in enumerate(self.register_values, start=self.base_register)}


#################################################################################
class ReadHoldingRegistersMeta:
    """Request & Response PDUs for function #3/Read Holding Registers."""

    function_code = 3


class ReadHoldingRegistersRequest(ReadHoldingRegistersMeta, ReadRegistersRequest):
    """Concrete PDU implementation for handling function #3/Read Holding Registers request messages."""

    def execute(self):
        """FIXME if we ever implement a server."""
        raise NotImplementedError()


class ReadHoldingRegistersResponse(ReadHoldingRegistersMeta, ReadRegistersResponse):
    """Concrete PDU implementation for handling function #3/Read Holding Registers response messages."""

    request_class = ReadHoldingRegistersRequest

    def _calculate_function_data_size(self) -> int:
        raise NotImplementedError()


#################################################################################
class ReadInputRegistersMeta:
    """Request & Response PDUs for function #4/Read Input Registers."""

    function_code = 4


class ReadInputRegistersRequest(ReadInputRegistersMeta, ReadRegistersRequest):
    """Concrete PDU implementation for handling function #4/Read Input Registers request messages."""

    def execute(self) -> None:
        """FIXME if we ever implement a server."""
        raise NotImplementedError()


class ReadInputRegistersResponse(ReadInputRegistersMeta, ReadRegistersResponse):
    """Concrete PDU implementation for handling function #4/Read Input Registers response messages."""

    request_class = ReadInputRegistersRequest

    def _calculate_function_data_size(self) -> int:
        raise NotImplementedError()


#################################################################################
class WriteHoldingRegisterMeta:
    """Request & Response PDUs for function #6/Write Holding Register."""

    function_code = 6


class WriteHoldingRegisterRequest(WriteHoldingRegisterMeta, ModbusRequest, ABC):
    """Concrete PDU implementation for handling function #6/Write Holding Register request messages."""

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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.register: int = kwargs.get('register', None)
        self.value: int = kwargs.get('value', None)

    def _encode_function_data(self):
        self.builder.add_16bit_uint(self.register)
        self.builder.add_16bit_uint(self.value)

    def _decode_function_data(self, decoder):
        self.register = decoder.decode_16bit_uint()
        self.value = decoder.decode_16bit_uint()
        self.check = decoder.decode_16bit_uint()

    def _update_check_code(self):
        crc_builder = BinaryPayloadBuilder(byteorder=Endian.Big)
        crc_builder.add_8bit_uint(self.function_code)
        crc_builder.add_16bit_uint(self.register)
        crc_builder.add_16bit_uint(self.value)
        self.check = CrcModbus().process(crc_builder.to_string()).final()
        self.builder.add_16bit_uint(self.check)

    def _calculate_function_data_size(self):
        size = 16
        _logger.debug(f"Calculated {size} bytes partial response size for {self}")
        return size

    def _ensure_valid_state(self):
        if self.register not in self.writable_registers:
            raise ValueError(f'Register {self.register} is not safe to write to', self)
        if self.value is None:
            raise ValueError('Register value must be set explicitly', self)
        elif 0 > self.value > 0xFFFF:
            raise ValueError(f'Register value {hex(self.value)} must be an unsigned 16-bit int', self)


class WriteHoldingRegisterResponse(WriteHoldingRegisterMeta, ModbusResponse, ABC):
    """Concrete PDU implementation for handling function #6/Write Holding Register response messages."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.inverter_serial_number: str = kwargs.get('inverter_serial_number', 'SA1234G567')
        self.register: int = kwargs.get('register', None)
        self.value: int = kwargs.get('value', None)

    def _encode_function_data(self):
        self.builder.add_string(f"{self.inverter_serial_number[-10:]:*>10}")  # ensure exactly 10 bytes
        self.builder.add_16bit_uint(self.register)
        self.builder.add_16bit_uint(0x0001)
        self.builder.add_16bit_uint(self.value)

    def _decode_function_data(self, decoder):
        """Decode response PDU message and populate instance attributes."""
        self.inverter_serial_number = decoder.decode_string(10).decode(
            "ascii",
        )
        self.register = decoder.decode_16bit_uint()
        num_values = decoder.decode_16bit_uint()
        if num_values != 1:
            raise ValueError(f'{num_values} values returned, should be 1', self)
        self.value = decoder.decode_16bit_uint()
        self.check = decoder.decode_16bit_uint()

    def _ensure_valid_state(self):
        if self.register is None:
            raise ValueError('Register must be set explicitly', self)
        if self.value is None:
            raise ValueError('Value must be set explicitly', self)


#################################################################################
class HeartbeatRequest(ModbusRequest, ABC):
    """PDU sent by remote server to check liveness of client."""

    data_adapter_type: int

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.data_adapter_type: int = kwargs.get('data_adapter_type', 0x00)

    def encode(self) -> bytes:
        """Encode request PDU message and populate instance attributes."""
        self.builder = BinaryPayloadBuilder(byteorder=Endian.Big)
        self.builder.add_string(f"{self.data_adapter_serial_number[-10:]:*>10}")  # ensure exactly 10 bytes
        self.builder.add_8bit_uint(self.data_adapter_type)
        return self.builder.to_string()

    def decode(self, data: bytes):
        """Decode response PDU message and populate instance attributes."""
        decoder = BinaryPayloadDecoder(data, byteorder=Endian.Big)
        self.data_adapter_serial_number = decoder.decode_string(10).decode("ascii")
        self.data_adapter_type = decoder.decode_8bit_uint()
        _logger.debug(f"Successfully decoded {len(data)} bytes")

    def execute(self) -> HeartbeatResponse:
        """Create an appropriate response for an incoming HeartbeatRequest."""
        return HeartbeatResponse(data_adapter_type=self.data_adapter_type)

    def _ensure_valid_state(self) -> None:
        if self.padding != 0x8A:
            _logger.warning(f'Expected padding 0x8a, found {hex(self.padding)} instead')

    @staticmethod
    def get_response_pdu_size(**kwargs) -> int:
        """Predict the size of the response PDU."""
        return 11


class HeartbeatResponse(ModbusResponse, ABC):
    """PDU returned by client (within 5s) to confirm liveness."""

    data_adapter_type: int

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.data_adapter_type: int = kwargs.get('data_adapter_type', 0x00)

    def encode(self) -> bytes:
        """Encode request PDU message and populate instance attributes."""
        self.builder = BinaryPayloadBuilder(byteorder=Endian.Big)
        self.builder.add_string(f"{self.data_adapter_serial_number[-10:]:*>10}")  # ensure exactly 10 bytes
        self.builder.add_8bit_uint(self.data_adapter_type)
        return self.builder.to_string()

    def decode(self, data: bytes):
        """Decode response PDU message and populate instance attributes."""
        decoder = BinaryPayloadDecoder(data, byteorder=Endian.Big)
        self.data_adapter_serial_number = decoder.decode_string(10).decode("ascii")
        self.data_adapter_type = decoder.decode_8bit_uint()
        _logger.debug(f"Successfully decoded {len(data)} bytes")

    @staticmethod
    def get_response_pdu_size(**kwargs) -> int:
        """Predict the size of the response PDU."""
        return 11
