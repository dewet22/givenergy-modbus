import logging
import warnings
from abc import ABC

from crccheck.crc import CrcModbus

from givenergy_modbus.codec import PayloadDecoder
from givenergy_modbus.pdu.base import BasePDU, ClientIncomingMessage, ClientOutgoingMessage

_logger = logging.getLogger(__name__)

_SLAVE_ADDRESS_DEPRECATION_MSG = (
    "slave_address is deprecated in line with Modbus.org's 2020 terminology update; use device_address instead"
)


class TransparentMessage(BasePDU, ABC):
    """Root of the hierarchy for 2/Transparent PDUs."""

    function_code = 2
    transparent_function_code: int

    device_address: int
    error: bool
    padding: int
    check: int

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if "slave_address" in kwargs:
            if "device_address" in kwargs:
                raise TypeError("pass either device_address= or slave_address=, not both")
            warnings.warn(_SLAVE_ADDRESS_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
            kwargs["device_address"] = kwargs.pop("slave_address")
        self.device_address = kwargs.get("device_address", 0x32)
        self.error = kwargs.get("error", False)
        self.padding = kwargs.get("padding", 0x08)  # this does seem significant
        self.check = kwargs.get("check", 0x0000)

    @property
    def slave_address(self) -> int:
        """Deprecated alias for `device_address`."""
        warnings.warn(_SLAVE_ADDRESS_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
        return self.device_address

    @slave_address.setter
    def slave_address(self, value: int) -> None:
        warnings.warn(_SLAVE_ADDRESS_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
        self.device_address = value

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        _logger.debug(f"TransparentMessage.__init_subclass__({cls.__name__})")

    def __str__(self) -> str:
        def format_kv(key, val):
            if val is None:
                val = "?"
            elif key == "device_address":
                # if val == 0x32:
                #     return None
                val = f"0x{val:02x}"
            elif key == "register_count" and val == 60:
                return None
            # elif key in ('check', 'padding'):
            #     val = f'0x{val:04x}'
            # elif key == 'raw_frame':
            #     return f'raw_frame={len(val)}b'
            elif key == "nulls":
                return f"nulls=[0]*{len(val)}"
            elif key in (
                "inverter_serial_number",
                "data_adapter_serial_number",
                "error",
                "check",
                "padding",
                "register_values",
                "raw_frame",
                "_builder",
                "crc_failed",
            ):
                return None
            return f"{key}={val}"

        args = []
        if self.error:
            args += ["ERROR"]
        args += [format_kv(k, v) for k, v in vars(self).items()]

        return (
            f"{self.function_code}:{getattr(self, 'transparent_function_code', '_')}/"
            f"{self.__class__.__name__}({' '.join([a for a in args if a is not None])})"
        )

    def _encode_function_data(self):
        self._builder.add_64bit_uint(self.padding)
        self._builder.add_8bit_uint(self.device_address)
        # The high bit of the transparent function code is the error flag (decode strips
        # it into `self.error`). Re-add it on encode so error responses round-trip — without
        # this, a decoded error response re-encodes as a malformed "success" frame (the bug
        # that silently corrupted fixture error frames during the #158 CRC regen).
        self._builder.add_8bit_uint(self.transparent_function_code | (0x80 if self.error else 0))
        # self._update_check_code()

    @classmethod
    def decode_main_function(cls, decoder: PayloadDecoder, **attrs) -> "TransparentMessage | BasePDU":
        from givenergy_modbus.pdu.lan_config import LanConfigBroadcast

        attrs["data_adapter_serial_number"] = decoder.decode_string(10)

        # LAN-config broadcast discriminator: some WO-prefix dongles emit a function-0x02
        # frame whose body is adapter_serial + 7-byte pad + ",ip,netmask,gateway\r\n\r\n" + check.
        # The 7th pad byte is 0x00 (not a valid transparent_function_code) and the next
        # byte is ',' — nothing in the normal transparent protocol can produce that sequence.
        if LanConfigBroadcast.is_lan_config(decoder.remaining_payload):
            return LanConfigBroadcast.decode_main_function(decoder, **attrs)

        attrs["padding"] = decoder.decode_64bit_uint()
        attrs["device_address"] = decoder.decode_8bit_uint()
        transparent_function_code = decoder.decode_8bit_uint()
        if transparent_function_code & 0x80:
            error = True
            transparent_function_code &= 0x7F
        else:
            error = False
        attrs["error"] = error

        if issubclass(cls, TransparentResponse):
            attrs["inverter_serial_number"] = decoder.decode_string(10)

        decoder_class = cls.lookup_transparent_function_decoder(transparent_function_code)
        return decoder_class.decode_transparent_function(decoder, **attrs)

    @classmethod
    def lookup_transparent_function_decoder(cls, transparent_function_code: int) -> type["TransparentMessage"]:
        raise NotImplementedError()

    @classmethod
    def decode_transparent_function(cls, decoder: PayloadDecoder, **attrs) -> "TransparentMessage":
        raise NotImplementedError()

    def ensure_valid_state(self) -> None:  # flake8: D102
        """Sanity check our internal state."""
        # if self.padding != 0x8A:
        #     _logger.debug(f'Expected padding 0x8a, found 0x{self.padding:02x} instead')

    def _update_check_code(self) -> None:
        """Append the trailing CRC over the already-built payload.

        One scheme for the entire Transparent protocol — every request *and* response
        type. CRC16/Modbus over the buffer from the device-address byte onward (skipping
        the 10-byte data-adapter serial + 8-byte padding = `payload[18:]`), byte-swapped
        on the wire. Operating on the built buffer rather than re-listing fields is what
        keeps request and response CRCs from drifting apart (the bug behind #105/#158).

        Confirmed against real GivTCP + GivEnergy-app request frames (#105:
        ReadHolding(0x11,0,60) → 0x474b) and the real All-in-One response corpus (#158:
        102/102 wire frames valid, incl. error responses).
        """
        raw = CrcModbus().process(self._builder.payload[18:]).final()
        self.check = ((raw & 0xFF) << 8) | ((raw >> 8) & 0xFF)
        self._builder.add_16bit_uint(self.check)

    def _extra_shape_hash_keys(self):
        return (self.device_address,)


class TransparentRequest(TransparentMessage, ClientOutgoingMessage, ABC):
    """Root of the hierarchy for Transparent Request PDUs."""

    @classmethod
    def lookup_transparent_function_decoder(cls, transparent_function_code: int) -> type["TransparentRequest"]:
        from givenergy_modbus.pdu import (
            ReadHoldingRegistersRequest,
            ReadInputRegistersRequest,
            ReadMeterProductRegistersRequest,
            WriteHoldingRegisterRequest,
        )

        if transparent_function_code == 3:
            return ReadHoldingRegistersRequest
        elif transparent_function_code == 4:
            return ReadInputRegistersRequest
        elif transparent_function_code == 6:
            return WriteHoldingRegisterRequest
        elif transparent_function_code == 0x16:
            return ReadMeterProductRegistersRequest
        else:
            raise NotImplementedError(f"TransparentRequest function #{transparent_function_code} decoder")

    def expected_response(self) -> "TransparentResponse":
        """Create a template of a correctly shaped Response expected for this Request."""
        raise NotImplementedError()


class TransparentResponse(TransparentMessage, ClientIncomingMessage, ABC):
    """Root of the hierarchy for Transparent Response PDUs."""

    inverter_serial_number: str

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._set_attribute_if_present("inverter_serial_number", **kwargs)

    def _encode_function_data(self):
        super()._encode_function_data()
        self._builder.add_string(self.inverter_serial_number, 10)

    @classmethod
    def lookup_transparent_function_decoder(cls, transparent_function_code: int) -> type["TransparentResponse"]:
        from givenergy_modbus.pdu import (
            NullResponse,
            ReadHoldingRegistersResponse,
            ReadInputRegistersResponse,
            ReadMeterProductRegistersResponse,
            WriteHoldingRegisterResponse,
        )

        if transparent_function_code == 0:
            return NullResponse
        elif transparent_function_code == 3:
            return ReadHoldingRegistersResponse
        elif transparent_function_code == 4:
            return ReadInputRegistersResponse
        elif transparent_function_code == 6:
            return WriteHoldingRegisterResponse
        elif transparent_function_code == 0x16:
            return ReadMeterProductRegistersResponse
        else:
            raise NotImplementedError(f"TransparentResponse function #{transparent_function_code} decoder")


__all__ = ()
