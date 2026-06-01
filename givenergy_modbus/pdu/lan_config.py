import re
import struct

from givenergy_modbus.codec import PayloadDecoder
from givenergy_modbus.pdu.base import ClientIncomingMessage

_DIGIT_RE = re.compile(rb"\d")


def _zero_ip(s: str | None) -> str:
    """Zero every digit in a dotted-quad IPv4 string, preserving dots and length."""
    if not s:
        return ""
    return _DIGIT_RE.sub(b"0", s.encode("latin1")).decode("latin1")


class LanConfigBroadcast(ClientIncomingMessage):
    r"""Dongle LAN-configuration broadcast (function 0x02 / CSV body).

    Some WO-prefix inverter dongles periodically broadcast their network
    configuration as a function-code 2 frame whose body is:

        adapter_serial[10]  6_zeros[6]  null[1]  ,<ip>,<netmask>,<gateway>\r\n\r\n  check[2]

    The standard transparent decoder reads the null byte as
    transparent_function_code (0x30 / '0') and bails to InvalidFrame. This class
    intercepts those frames at decode time before the transparent path is attempted
    (discriminator: remaining_payload[6]==0 and remaining_payload[7]==',').

    Refs: #100 (original discovery), #158 (B-3 redactor).
    """

    function_code = 2

    # Offsets within remaining_payload *after* data_adapter_serial_number is consumed:
    # remaining[0:6] = 6 zero bytes, remaining[6] = 0x00, remaining[7] = 0x2c (',')
    _DISC_NULL_OFFSET = 6
    _DISC_COMMA = 0x2C  # ord(',')
    _PAD_LEN = 7  # 6 zeros + 1 null

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ip: str = kwargs.get("ip", "")
        self.netmask: str = kwargs.get("netmask", "")
        self.gateway: str = kwargs.get("gateway", "")
        self.check: int = kwargs.get("check", 0)
        self._csv_raw: bytes = kwargs.get("_csv_raw", b"")

    @classmethod
    def is_lan_config(cls, remaining_after_serial: bytes) -> bool:
        """Return True if the remaining decoder bytes look like a LAN config broadcast."""
        return (
            len(remaining_after_serial) >= 8
            and remaining_after_serial[cls._DISC_NULL_OFFSET] == 0x00
            and remaining_after_serial[cls._DISC_NULL_OFFSET + 1] == cls._DISC_COMMA
        )

    @classmethod
    def decode_main_function(cls, decoder: PayloadDecoder, **attrs) -> "LanConfigBroadcast":
        """Called by TransparentMessage.decode_main_function after reading the serial.

        `attrs` already contains `data_adapter_serial_number`. Consume the 7 padding bytes
        then parse the CSV from the remaining payload.
        """
        # Consume the 7 padding bytes (6 zeros + 1 null)
        for _ in range(cls._PAD_LEN):
            decoder.decode_8bit_uint()
        remaining = decoder.remaining_payload
        csv_raw = remaining[:-2]
        check_val = int.from_bytes(remaining[-2:], "big")
        # Consume all remaining bytes so decoding_complete is satisfied
        decoder.decode_string(decoder.remaining_bytes)
        # Parse CSV: strip leading comma, split on comma, strip trailing \r\n
        csv_str = csv_raw.decode("latin1").lstrip(",").rstrip("\r\n")
        parts = csv_str.split(",")
        return cls(
            data_adapter_serial_number=attrs.get("data_adapter_serial_number", ""),
            ip=parts[0] if len(parts) > 0 else "",
            netmask=parts[1] if len(parts) > 1 else "",
            gateway=parts[2] if len(parts) > 2 else "",
            check=check_val,
            _csv_raw=csv_raw,
        )

    def _encode_function_data(self) -> None:
        # BasePDU.encode() has already written data_adapter_serial_number (10 bytes).
        # Write: 7 padding bytes + csv_raw + check(2)
        for _ in range(self._PAD_LEN):
            self._builder.add_8bit_uint(0)
        self._builder._payload += self._csv_raw
        self._builder.add_16bit_uint(self.check)

    def encode(self) -> bytes:
        """Re-encode to wire bytes; length-preserving. CRC is not recomputed."""
        from givenergy_modbus.codec import PayloadEncoder

        self._builder = PayloadEncoder()
        self._builder.add_string(self.data_adapter_serial_number, 10)
        self._encode_function_data()
        inner = self._builder.payload
        mbap = struct.pack(">HHHBB", 0x5959, 0x1, len(inner) + 2, 0x1, self.function_code)
        self.raw_frame = mbap + inner
        return self.raw_frame

    def ensure_valid_state(self) -> None:
        """No state validation required for LAN-config broadcast frames."""

    def expected_response(self):
        """No response expected for LAN-config broadcasts."""
        return None

    def _extra_shape_hash_keys(self) -> tuple:
        return ()

    @classmethod
    def lookup_main_function_decoder(cls, function_code: int) -> "type[ClientIncomingMessage]":
        """Not used — LanConfigBroadcast is decoded directly, not via lookup."""
        raise NotImplementedError()

    def redact(self) -> "LanConfigBroadcast":
        """Return a new instance with the adapter serial and all IP fields zeroed."""
        from givenergy_modbus.model.register import Converter

        redacted_serial = Converter.redact_serial(self.data_adapter_serial_number) or ""
        redacted_ip = _zero_ip(self.ip)
        redacted_netmask = _zero_ip(self.netmask)
        redacted_gateway = _zero_ip(self.gateway)
        new_csv_raw = f",{redacted_ip},{redacted_netmask},{redacted_gateway}\r\n\r\n".encode("latin1")
        return LanConfigBroadcast(
            data_adapter_serial_number=redacted_serial,
            ip=redacted_ip,
            netmask=redacted_netmask,
            gateway=redacted_gateway,
            check=self.check,
            _csv_raw=new_csv_raw,
        )
