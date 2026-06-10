import logging
from abc import ABC

from crccheck.crc import CrcModbus

from givenergy_modbus.codec import PayloadDecoder
from givenergy_modbus.exceptions import InvalidPduState
from givenergy_modbus.pdu.transparent import TransparentMessage, TransparentRequest, TransparentResponse

_logger = logging.getLogger(__name__)


class ReadRegistersMessage(TransparentMessage, ABC):
    """Mixin for commands that specify base register and register count semantics."""

    base_register: int
    register_count: int

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.base_register = kwargs.get("base_register", 0)
        self.register_count = kwargs.get("register_count", 0)

    @classmethod
    def decode_transparent_function(cls, decoder: PayloadDecoder, **attrs) -> "ReadRegistersMessage":
        attrs["base_register"] = decoder.decode_16bit_uint()
        attrs["register_count"] = decoder.decode_16bit_uint()
        if issubclass(cls, ReadRegistersResponse) and not attrs.get("error", False):
            # Cap to 60 to prevent buffer exhaustion from a crafted register_count.
            # ensure_valid_state will reject the count/values length mismatch.
            decode_count = min(attrs["register_count"], 60)
            attrs["register_values"] = [decoder.decode_16bit_uint() for _ in range(decode_count)]
        attrs["check"] = decoder.decode_16bit_uint()
        return cls(**attrs)

    def _extra_shape_hash_keys(self) -> tuple:
        return super()._extra_shape_hash_keys() + (self.base_register, self.register_count)

    def _ensure_registers_spec_correct(self):
        if self.base_register is None:
            raise InvalidPduState("Base register must be set", self)
        if self.base_register < 0 or 0xFFFF < self.base_register:
            raise InvalidPduState("Base register must be an unsigned 16-bit int", self)

        if self.register_count is None:
            raise InvalidPduState("Register count must be set", self)
        if self.register_count == 0 and not self.error:
            _logger.warning(f"Register count of 0 does not make sense: {self}")


class ReadRegistersRequest(ReadRegistersMessage, TransparentRequest, ABC):
    """Handles all messages that request a range of registers."""

    def _encode_function_data(self):
        super()._encode_function_data()
        self._builder.add_16bit_uint(self.base_register)
        self._builder.add_16bit_uint(self.register_count)
        self._update_check_code()  # unified CRC lives on TransparentMessage

    def ensure_valid_state(self):
        """Sanity check our internal state."""
        self._ensure_registers_spec_correct()

        # The 1000+ three-phase and 1600+ gateway banks intentionally use non-60-aligned
        # bases (range(1000, 1414, 60) etc.) — confirmed against the GivEnergy Android app
        # which sends the same pattern. Warning removed as it fired on every legitimate
        # three-phase poll, producing noise rather than signal. (#163)
        if self.register_count <= 0 or 60 < self.register_count:
            raise InvalidPduState("Register count must be in (0,60]", self)


class ReadRegistersResponse(ReadRegistersMessage, TransparentResponse, ABC):
    """Handles all messages that respond with a range of registers."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.register_values: list[int] = kwargs.get("register_values", [])

    def _encode_function_data(self):
        super()._encode_function_data()
        self._builder.add_16bit_uint(self.base_register)
        self._builder.add_16bit_uint(self.register_count)
        [self._builder.add_16bit_uint(v) for v in self.register_values]
        self._update_check_code()

    def ensure_valid_state(self) -> None:
        """Sanity check our internal state."""
        self._ensure_registers_spec_correct()

        if not self.error:
            # if self.register_count != 1 and self.base_register % 60 != 0:
            #     _logger.warning(f'Base register {self.base_register} not aligned on 60-byte boundary')
            if self.register_count != len(self.register_values):
                raise InvalidPduState(
                    f"register_count={self.register_count} but len(register_values)={len(self.register_values)}.",
                    self,
                )

        expected_padding = 0x12 if self.error else 0x8A
        if self.padding != expected_padding:
            _logger.debug(f"Expected padding 0x{expected_padding:02x}, found 0x{self.padding:02x} instead: {self}")

        self._validate_check_code()

    def _validate_check_code(self) -> None:
        """Log-only CRC check of a decoded response against the received bytes.

        Recomputes the unified CRC (CRC16/Modbus over `raw_frame[26:-2]` — the
        device-address byte onward, mirroring `TransparentMessage._update_check_code`'s
        `payload[18:]`, byte-swapped) and compares to the decoded `check`. Confirmed valid
        for every frame in the real All-in-One corpus (#158: 102/102, incl. error
        responses). Deliberately **non-fatal**: incoming inverter frames are the source of
        truth, so a mismatch is logged at WARNING for visibility (a corrupted/malformed frame,
        not authenticated tampering — the CRC is unauthenticated) but never rejects the data.
        Only runs when `raw_frame` is present (i.e. on decoded frames).
        """
        raw_frame = getattr(self, "raw_frame", None)
        if not raw_frame or len(raw_frame) < 28:
            return
        computed = CrcModbus().process(raw_frame[26:-2]).final()
        expected = ((computed & 0xFF) << 8) | ((computed >> 8) & 0xFF)
        if expected != self.check:
            _logger.warning(
                f"Response failed CRC integrity check on {self}: "
                f"wire=0x{self.check:04x} computed=0x{expected:04x} — data accepted (non-fatal), "
                f"but the frame was corrupted or malformed in transit"
            )

    def to_dict(self) -> dict[int, int]:
        """Return the registers as a dict of register_index:value. Accounts for base_register offsets."""
        return {k: v for k, v in enumerate(self.register_values, start=self.base_register)}

    def is_suspicious(self) -> bool:
        """Try to identify known-bad data in register lookup calls and prevent them from entering the dispatching."""
        if self.base_register % 60 == 0 and self.register_count == 60 and len(self.register_values) == 60:
            count_known_bad_register_values = (
                self.register_values[28] == 0x4C32,
                self.register_values[30] == 0xA119,
                self.register_values[31] == 0x34EA,
                self.register_values[32] == 0xE77F,
                self.register_values[33] == 0xD475,
                self.register_values[35] == 0x4500,
                self.register_values[40] in (0xE4F9, 0xB619),
                self.register_values[41] == 0xC0A8,
                self.register_values[43] == 0xC0A8,
                self.register_values[46] == 0xC5E9,
                self.register_values[50] in (0x60EF, 0x503C),
                self.register_values[51] == 0x8018,
                self.register_values[52] == 0x43E0,
                self.register_values[53] == 0xF6CE,
                self.register_values[56] == 0x080A,
                self.register_values[58] == 0xFCC1,
                self.register_values[59] == 0x661E,
            ).count(True)
            if count_known_bad_register_values > 5:
                _logger.debug(
                    f"Ignoring known suspicious update with {count_known_bad_register_values} known bad "
                    f"register values {self}: {self.to_dict()}"
                )
                return True
        return False


class ReadHoldingRegisters(ReadRegistersMessage, ABC):
    """Request & Response PDUs for function #3/Read Holding Registers."""

    transparent_function_code = 3


class ReadHoldingRegistersRequest(ReadHoldingRegisters, ReadRegistersRequest):
    """Concrete PDU implementation for handling function #3/Read Holding Registers request messages."""

    def expected_response(self):
        return ReadHoldingRegistersResponse(
            base_register=self.base_register, register_count=self.register_count, device_address=self.device_address
        )


class ReadHoldingRegistersResponse(ReadHoldingRegisters, ReadRegistersResponse):
    """Concrete PDU implementation for handling function #3/Read Holding Registers response messages."""

    def expected_response(self):
        return


class ReadInputRegisters(ReadRegistersMessage, ABC):
    """Request & Response PDUs for function #4/Read Input Registers."""

    transparent_function_code = 4


class ReadInputRegistersRequest(ReadInputRegisters, ReadRegistersRequest):
    """Concrete PDU implementation for handling function #4/Read Input Registers request messages."""

    def expected_response(self):
        return ReadInputRegistersResponse(
            base_register=self.base_register, register_count=self.register_count, device_address=self.device_address
        )


class ReadInputRegistersResponse(ReadInputRegisters, ReadRegistersResponse):
    """Concrete PDU implementation for handling function #4/Read Input Registers response messages."""

    def expected_response(self):
        return


class ReadMeterProductRegisters(ReadRegistersMessage, ABC):
    """Request & Response PDUs for function #0x16/Read Meter Product Registers."""

    transparent_function_code = 0x16


class ReadMeterProductRegistersRequest(ReadMeterProductRegisters, ReadRegistersRequest):
    """Concrete PDU implementation for handling function #0x16/Read Meter Product Registers request messages."""

    def expected_response(self):
        return ReadMeterProductRegistersResponse(
            base_register=self.base_register, register_count=self.register_count, device_address=self.device_address
        )

    # No _update_check_code override: the base ReadRegistersRequest method now uses the
    # device-address-prefixed, byte-swapped layout this FC 0x16 path originally proved
    # (#58) — they're identical, so the override was removed (#105 / #157).


class ReadMeterProductRegistersResponse(ReadMeterProductRegisters, ReadRegistersResponse):
    """Concrete PDU implementation for handling function #0x16/Read Meter Product Registers response messages."""

    def expected_response(self):
        return


__all__ = ()
