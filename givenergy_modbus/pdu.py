"""`pymodbus.pdu.ModbusPDU` implementations for GivEnergy-specific PDU messages."""

from __future__ import annotations

import logging
from abc import ABC
from typing import Any

from crccheck.crc import CrcModbus
from pymodbus import pdu as pymodbus_pdu
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
    def remaining_payload(self) -> bytes:
        """Return the unprocessed / remaining tail of the payload."""
        return self._payload[self._pointer :]


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
        def format_kv(key, val):
            if val is None:
                val = '?'
            elif key in ('slave_address',):
                val = f'0x{val:02x}'
            return f'{key}={val}'

        filtered_keys = (
            'transaction_id',
            'protocol_id',
            'unit_id',
            'check',
            'skip_encode',  # from pymodbus
            'register_values',
            'builder',
            'inverter_serial_number',
            'data_adapter_serial_number',
            'padding',
        )
        filtered_args = [format_kv(k, v) for k, v in vars(self).items() if k not in filtered_keys]
        return f"{getattr(self, 'function_code', '_')}/{self.__class__.__name__}({' '.join(filtered_args)})"

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
        decoder = PayloadDecoder(data)
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
        if not decoder.decoding_complete:
            _logger.error(
                f'Decoder did not fully decode {function_code} packet: decoded {decoder.decoded_bytes}b but '
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

    def has_same_shape(self, o: object):
        """Calculates whether a given message has the "same shape".

        Messages are similarly shaped when they match message type (response, error state), location (slave device,
        register type, register indexes) etc. but not data / register values.

        This is not an identity check but could be used both for creating template expected responses from
        outgoing requests (to facilitate tracking future responses), but also allows incoming messages to be
        hashed consistently to avoid (e.g.) multiple messages of the same shape getting enqueued unnecessarily –
        the theory being that newer messages being enqueued might as well replace older ones of the same shape.
        """
        if isinstance(o, ModbusResponse):
            return self._shape_hash() == o._shape_hash()
        return NotImplemented

    def _shape_hash(self) -> int:
        """Calculates the "shape hash" for a given message."""
        return hash(self._shape_hash_keys())

    def _shape_hash_keys(self) -> tuple:
        """Defines which keys to compare to see if two messages have the same shape."""
        return (type(self), self.function_code, self.slave_address, self.error) + self._extra_shape_hash_keys()

    def _extra_shape_hash_keys(self) -> tuple:
        """Allows extra message-specific keys to be mixed in."""
        raise NotImplementedError()


#################################################################################
class ModbusRequest(ModbusPDU, pymodbus_pdu.ModbusRequest, ABC):
    """Root of the hierarchy for Request PDUs."""

    def expected_response_pdu(self) -> ModbusResponse:
        """Create a template of the expected response to this Request."""
        raise NotImplementedError()


class ModbusResponse(ModbusPDU, pymodbus_pdu.ModbusResponse, ABC):
    """Root of the hierarchy for Response PDUs."""

    error: bool = False

    def _update_check_code(self):
        if hasattr(self, 'check'):
            # Until we know how Responses' CRCs are calculated there's nothing we can do here; self.check stays 0x0000
            _logger.warning('Unable to recalculate checksum, using whatever value was set')
            self.builder.add_16bit_uint(self.check)


#################################################################################
class NullResponse(ModbusResponse):
    """Concrete PDU implementation for handling function #0/Null Response messages."""

    function_code = 0

    def _encode_function_data(self) -> None:
        pass

    def _decode_function_data(self, decoder: PayloadDecoder) -> None:
        decoder.skip_bytes(decoder.payload_size - 20)

    def _calculate_function_data_size(self) -> int:
        pass

    def _ensure_valid_state(self) -> None:
        pass

    def _extra_shape_hash_keys(self) -> tuple:
        return ()


#################################################################################
class RegistersRangeMessage(ModbusPDU, ABC):
    """Mixin for commands that specify base register and register count semantics."""

    base_register: int
    register_count: int

    def _extra_shape_hash_keys(self) -> tuple:
        return self.base_register, self.register_count

    def _ensure_registers_spec_correct(self):
        if self.base_register is None:
            raise ValueError('Base register must be set', self)
        if 0xFFFF < self.base_register < 0:
            raise ValueError('Base register must be an unsigned 16-bit int', self)
        if not self.error and self.register_count != 1 and self.base_register % 60 != 0:
            _logger.warning(f'Base register {self.base_register} not aligned on 60-byte boundary')

        if self.register_count is None:
            raise ValueError('Register count must be set', self)
        if 60 < self.register_count < 0:
            raise ValueError('Register count must be in [0,60]', self)


#################################################################################
class ReadRegistersRequest(ModbusRequest, RegistersRangeMessage, ABC):
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


class ReadRegistersResponse(ModbusResponse, RegistersRangeMessage, ABC):
    """Handles all messages that respond with a range of registers."""

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


#################################################################################
class ReadHoldingRegistersMeta:
    """Request & Response PDUs for function #3/Read Holding Registers."""

    function_code = 3


class ReadHoldingRegistersRequest(ReadHoldingRegistersMeta, ReadRegistersRequest):
    """Concrete PDU implementation for handling function #3/Read Holding Registers request messages."""

    def expected_response_pdu(self) -> ModbusResponse:  # noqa D102 - see superclass
        return ReadHoldingRegistersResponse(
            base_register=self.base_register, register_count=self.register_count, slave_address=self.slave_address
        )


class ReadHoldingRegistersResponse(ReadHoldingRegistersMeta, ReadRegistersResponse):
    """Concrete PDU implementation for handling function #3/Read Holding Registers response messages."""

    def _calculate_function_data_size(self) -> int:
        raise NotImplementedError()


#################################################################################
class ReadInputRegistersMeta:
    """Request & Response PDUs for function #4/Read Input Registers."""

    function_code = 4


class ReadInputRegistersRequest(ReadInputRegistersMeta, ReadRegistersRequest):
    """Concrete PDU implementation for handling function #4/Read Input Registers request messages."""

    def expected_response_pdu(self) -> ModbusResponse:  # noqa D102 - see superclass
        return ReadInputRegistersResponse(
            base_register=self.base_register, register_count=self.register_count, slave_address=self.slave_address
        )


class ReadInputRegistersResponse(ReadInputRegistersMeta, ReadRegistersResponse):
    """Concrete PDU implementation for handling function #4/Read Input Registers response messages."""

    def _calculate_function_data_size(self) -> int:
        raise NotImplementedError()


#################################################################################
class WriteHoldingRegisterMeta(ModbusPDU, ABC):
    """Request & Response PDUs for function #6/Write Holding Register."""

    function_code = 6

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

    def _extra_shape_hash_keys(self) -> tuple:
        return (self.register,)

    def _ensure_valid_state(self):
        if self.register is None:
            raise ValueError('Register must be set explicitly', self)
        elif self.register not in self.writable_registers:
            raise ValueError(f'Register {self.register} is not safe to write to', self)
        if self.value is None:
            raise ValueError('Register value must be set explicitly', self)
        elif 0 > self.value > 0xFFFF:
            raise ValueError(f'Register value {hex(self.value)} must be an unsigned 16-bit int', self)


class WriteHoldingRegisterRequest(WriteHoldingRegisterMeta, ModbusRequest, ABC):
    """Concrete PDU implementation for handling function #6/Write Holding Register request messages."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.register: int = kwargs.get('register', None)
        self.value: int = kwargs.get('value', None)

    def _encode_function_data(self):
        self.builder.add_16bit_uint(self.register)
        self.builder.add_16bit_uint(self.value)
        # self.check added via self._update_check_code()

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

    def expected_response_pdu(self) -> WriteHoldingRegisterResponse:  # noqa D102 - see superclass
        return WriteHoldingRegisterResponse(register=self.register, value=self.value, slave_address=self.slave_address)


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
        self.builder.add_16bit_uint(self.value)

    def _decode_function_data(self, decoder):
        """Decode response PDU message and populate instance attributes."""
        self.inverter_serial_number = decoder.decode_string(10).decode("ascii")
        self.register = decoder.decode_16bit_uint()
        self.value = decoder.decode_16bit_uint()
        self.check = decoder.decode_16bit_uint()


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
        decoder = PayloadDecoder(data)
        self.data_adapter_serial_number = decoder.decode_string(10).decode("ascii")
        self.data_adapter_type = decoder.decode_8bit_uint()
        _logger.debug(f"Successfully decoded {len(data)} bytes")

    def expected_response_pdu(self) -> HeartbeatResponse:
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
        decoder = PayloadDecoder(data)
        self.data_adapter_serial_number = decoder.decode_string(10).decode("ascii")
        self.data_adapter_type = decoder.decode_8bit_uint()
        _logger.debug(f"Successfully decoded {len(data)} bytes")

    @staticmethod
    def get_response_pdu_size(**kwargs) -> int:
        """Predict the size of the response PDU."""
        return 11
