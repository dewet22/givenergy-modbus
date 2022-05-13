from crccheck.crc import CrcModbus  # type: ignore[import]
from pymodbus.constants import Endian  # type: ignore[import]
from pymodbus.payload import BinaryPayloadBuilder, BinaryPayloadDecoder  # type: ignore[import]


class PayloadDecoder(BinaryPayloadDecoder):
    """Provide a few convenience shortcuts to the provided BinaryPayloadDecoder."""

    def __init__(self, payload):
        super().__init__(payload, byteorder=Endian.Big, wordorder=Endian.Big)

    def decode_serial_number(self):
        """Returns a 10-character serial number string."""
        return self.decode_string(10).decode('latin1')

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
    def remaining_bytes(self) -> int:
        """Return the number of bytes of the payload that have been decoded."""
        return self.payload_size - self._pointer

    @property
    def remaining_payload(self) -> bytes:
        """Return the unprocessed / remaining tail of the payload."""
        return self._payload[self._pointer :]


class PayloadEncoder(BinaryPayloadBuilder):
    """Provide a few convenience shortcuts to the provided BinaryPayloadBuilder."""

    def __init__(self):
        super().__init__(byteorder=Endian.Big, wordorder=Endian.Big)

    def add_serial_number(self, serial_number: str):
        """Encodes exactly 10 bytes for a typical serial number."""
        self.add_string(f'{serial_number[-10:]:*>10}')

    def calculate_crc(self) -> int:
        """Calculate a Modbus-compatible CRC based on the buffer contents."""
        return CrcModbus().process(self.to_string()).final()
