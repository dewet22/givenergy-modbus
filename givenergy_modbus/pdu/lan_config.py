import re
import struct

from givenergy_modbus.codec import PayloadDecoder
from givenergy_modbus.pdu.base import ClientIncomingMessage

_DIGIT_RE = re.compile(rb"\d")
_IPV4 = rb"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}"
# Everything after the adapter serial: a short pad, then the ASCII config, then the
# 2-byte check. Matched on content rather than at fixed offsets: the known broadcast
# pads with 7 zero bytes and a comma, but one seen in the field (britkat1980/giv_tcp#668,
# a 72-byte frame) didn't, and fell through to the transparent decoder — which read a
# character of the IP text as the function code and left the frame undecodable, so the
# capture redactor passed it through with the dongle serial and IPs intact. A transparent
# response can't fullmatch this: it would need its whole payload to be the ASCII CSV.
_LAN_CONFIG_RE = re.compile(
    rb"(?P<pad>.{0,16}?)(?P<csv>(?P<ip>" + _IPV4 + rb"),(?P<netmask>" + _IPV4 + rb"),(?P<gateway>" + _IPV4 + rb")"
    rb"\r\n\r\n)(?P<check>.{2})",
    re.DOTALL,
)


def _zero_ip(s: str | None) -> str:
    """Zero every digit in a dotted-quad IPv4 string, preserving dots and length."""
    if not s:
        return ""
    return _DIGIT_RE.sub(b"0", s.encode("latin1")).decode("latin1")


class LanConfigBroadcast(ClientIncomingMessage):
    r"""Dongle LAN-configuration broadcast (function 0x02 / CSV body).

    Some WO-prefix inverter dongles periodically broadcast their network
    configuration as a function-code 2 frame whose body is:

        adapter_serial[10]  pad[0-16]  <ip>,<netmask>,<gateway>\r\n\r\n  check[2]

    The known pad is 7 zero bytes and a comma; it is kept verbatim, whatever it holds,
    so a redacted frame has the same length as the original.

    Without this class the transparent decoder would read the pad and the start of the
    IP text as a transparent header and bail to InvalidFrame. It intercepts those frames
    at decode time, before the transparent path is attempted, by matching the content
    after the serial (see ``_LAN_CONFIG_RE``) rather than bytes at fixed offsets.

    Refs: #100 (original discovery), #158 (B-3 redactor), britkat1980/giv_tcp#668.
    """

    function_code = 2

    _DEFAULT_PAD = b"\x00" * 7 + b","  # the pad of the first broadcast seen (#100)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ip: str = kwargs.get("ip", "")
        self.netmask: str = kwargs.get("netmask", "")
        self.gateway: str = kwargs.get("gateway", "")
        self.check: int = kwargs.get("check", 0)
        self._pad_raw: bytes = kwargs.get("_pad_raw", self._DEFAULT_PAD)
        self._csv_raw: bytes = kwargs.get("_csv_raw", b"")

    @classmethod
    def is_lan_config(cls, remaining_after_serial: bytes) -> bool:
        r"""Return True if the bytes after the adapter serial are a LAN-config broadcast body.

        The whole remainder must be pad + ``ip,netmask,gateway\r\n\r\n`` + check, so a
        crafted pad can't false-positive and drop a valid transparent response (L6).
        """
        return _LAN_CONFIG_RE.fullmatch(remaining_after_serial) is not None

    @classmethod
    def decode_main_function(cls, decoder: PayloadDecoder, **attrs) -> "LanConfigBroadcast":
        """Called by TransparentMessage.decode_main_function after reading the serial.

        `attrs` already contains `data_adapter_serial_number`; the caller has checked
        :meth:`is_lan_config` on the remaining payload.
        """
        m = _LAN_CONFIG_RE.fullmatch(decoder.remaining_payload)
        if m is None:  # caller contract broken; let the transparent error path report it
            raise ValueError("not a LAN-config broadcast body")
        # Consume all remaining bytes so decoding_complete is satisfied
        decoder.decode_string(decoder.remaining_bytes)
        return cls(
            data_adapter_serial_number=attrs.get("data_adapter_serial_number", ""),
            ip=m["ip"].decode("latin1"),
            netmask=m["netmask"].decode("latin1"),
            gateway=m["gateway"].decode("latin1"),
            check=int.from_bytes(m["check"], "big"),
            _pad_raw=m["pad"],
            _csv_raw=m["csv"],
        )

    def _encode_function_data(self) -> None:
        # BasePDU.encode() has already written data_adapter_serial_number (10 bytes).
        # Write: pad (verbatim) + csv_raw + check(2)
        self._builder._payload += self._pad_raw + self._csv_raw
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
        """Return a new instance with the adapter serial and all IP fields zeroed.

        The trailing 2-byte ``check`` field is carried through verbatim. Its
        derivation for this non-standard frame type is unknown — verified to not
        follow the ``CRC16/Modbus(payload[18:], byte-swapped)`` scheme used by
        all other GivEnergy frames (no candidate span produces a match). This is
        consistent with the fact that real captures arrive with the IPs already
        zeroed and a ``check`` value computed by the dongle over those zeroed bytes;
        redaction of a live frame would leave the check inconsistent with the new CSV
        bytes, but without understanding the formula it cannot be corrected. A comment
        in the test documents the implication.

        The serial goes through the fail-closed ``redact_serial_strict`` (an unrecognised
        shape is blanked, as for envelope serials), and the pad is carried through
        verbatim so the frame keeps its length.
        """
        from givenergy_modbus.model.register import Converter

        redacted_serial = Converter.redact_serial_strict(self.data_adapter_serial_number)
        redacted_ip = _zero_ip(self.ip)
        redacted_netmask = _zero_ip(self.netmask)
        redacted_gateway = _zero_ip(self.gateway)
        new_csv_raw = f"{redacted_ip},{redacted_netmask},{redacted_gateway}\r\n\r\n".encode("latin1")
        return LanConfigBroadcast(
            data_adapter_serial_number=redacted_serial,
            ip=redacted_ip,
            netmask=redacted_netmask,
            gateway=redacted_gateway,
            check=self.check,  # opaque: derivation unknown for this frame type
            _pad_raw=self._pad_raw,
            _csv_raw=new_csv_raw,
        )
