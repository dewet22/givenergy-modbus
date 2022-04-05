from __future__ import annotations

import logging
import struct
from typing import TYPE_CHECKING, Callable

from pymodbus.interfaces import IModbusDecoder
from pymodbus.pdu import ModbusPDU

from givenergy_modbus.pdu import HeartbeatRequest, HeartbeatResponse
from givenergy_modbus.util import hexlify

_logger = logging.getLogger(__package__)


class GivEnergyModbusFramer:
    """GivEnergy Modbus Frame controller.

    A framer abstracts away all the detail about how marshall the wire protocol, in particular detecting if a message
    frame could be present in a buffer, whether it is complete, extracting the frame and handing off to a decoder,
    and encoding a frame for sending onto a transport layer. This implementation understands the idiosyncrasies of
    GivEnergy's implementation of the Modbus spec.

    Packet exchange looks very similar to normal Modbus TCP, with each
    message still having a regular 7-byte MBAP header consisting of:

    * ``tid``, the unique transaction identifier, used to match up requests and responses
    * ``pid``, the protocol identifier, conventionally ``0x0001`` for regular Modbus
    * ``len``, the number of bytes following from this point
    * ``uid``, the unit identifier of the specific device on the Modbus network being addressed, or ``0x00`` to
      broadcast

    This is followed by ``fid``, a function code which specifies the type of data payload::

        [_________MBAP Header______] [_fid_] [_______________data________________]
        [_tid_][_pid_][_len_][_uid_]
          2b     2b     2b     1b      1b                  (len-1)b

    GivEnergy's implementation quirks can be summarised as:

    * ``tid`` is always ``0x5959`` (``YY`` in ASCII)
    * ``pid`` is always ``0x0001``
    * ``len`` **adds** 1 extra byte compared to regular Modbus
    * ``uid`` is always ``0x01``
    * ``fid`` is one of:
        * ``0x01/Heartbeat``: The data adapter will send this request every 3 minutes and the client needs to
          respond within 5 seconds. After three missed heartbeats the TCP socket will be closed and the
          client will need to re-establish a connection.
        * ``0x02/Transparent``: The primary way to interact with the inverter. The data payload is a GivEnergy
          specific frame which contains the actual command and data for the inverter. It is functionally similar to
          Modbus sub-functions, using `0x02` as main function.

    Because the first two header fields are static you can scan for ``0x59590001`` to find the start of candidate
    frames in a byte stream - see :meth:`.resetFrame` [.resetFrame][]

    GivEnergy Transparent frames have a consistent format:

    * ``serial`` (10 bytes) of the responding data adapter (wifi/GPRS/ethernet) plugged into the inverter. For
      requests this is seemingly not important and can be an arbitrary alphanumeric string.
    * ``pad`` (8 bytes) is not well understood but appears to be a single zero-padded byte that is fairly predictable
      based on the command.
    * ``addr`` (1 byte) unit identifier, of which a few are known:
        * ``0x00``: Android app
        * ``0x11``: inverter
        * ``0x32`` to ``0x36``: battery packs connected to the inverter (max 5)
    * ``func`` (1 byte) is the command to be executed:
        * `0x03` - read holding registers
        * `0x04` - read input registers
        * `0x06` - write single holding register
        * `0x10` - write multiple holding registers
    * ``data`` (*n* bytes)is specific to the function being invoked
    * ``crc`` (2 bytes) CRC for a request is calculated using the function id, base register and
      step count, but it is unclear how a response CRC is calculated or should be verified.

    Raises:
        InvalidMessageReceivedException: When unable to decode an incoming message.
        ModbusIOException: When the identified function decoder fails to decode a message.
    """

    if TYPE_CHECKING:
        from typing import Final

        FRAME_HEAD: Final[str] = ">HHHBB"  # tid(w), pid(w), length(w), uid(b), fid(b)
        FRAME_HEAD_SIZE: Final[int] = struct.calcsize(FRAME_HEAD)
    else:  # FIXME remove when py37 is not supported any more
        FRAME_HEAD: str = ">HHHBB"  # tid(w), pid(w), length(w), uid(b), fid(b)
        FRAME_HEAD_SIZE: int = struct.calcsize(FRAME_HEAD)

    _buffer: bytes = b""
    _length: int

    def __init__(self, decoder: IModbusDecoder):
        self.decoder = decoder

    @classmethod
    def parse_header(cls, buffer: bytes) -> dict:
        """Tries to extract the MBAP frame header and performs a few sanity checks."""
        data = buffer[: cls.FRAME_HEAD_SIZE]
        _logger.debug(f"extracting MBAP header from [{hexlify(data)}] using format {cls.FRAME_HEAD}")
        tid, pid, len_, uid, fid = struct.unpack(cls.FRAME_HEAD, data)
        header = dict(transaction=tid, protocol=pid, length=len_, unit=uid, fcode=fid)
        _logger.debug(f"extracted values: {dict((k, f'0x{v:02x}') for k, v in header.items())}")
        if tid == 0x5959 and pid == 0x1 and uid == 0x1 and fid in (0x1, 0x2):
            return header
        raise ValueError(
            f"Invalid MBAP header: 0x{tid:04x} 0x{pid:04x} 0x{uid:02x}{fid:02x} != 0x5959 0x0001 0x010[12]"
        )

    def check_frame(self) -> bool:
        """Check and decode the next frame. Returns operation success."""
        if self.is_frame_ready():
            try:
                header = self.parse_header(self._buffer)
            except ValueError as e:
                _logger.error(f'Resetting buffer: {e}')
                self.reset_frame()
                return False
            # self._fcode = header["fcode"]
            self._length = header["length"]

            # # this short a message should not be possible?
            # if self._length < 2:
            #     _logger.warning(f"unexpected short message length {self._length}, advancing frame")
            #     self.advanceFrame()
            #     return False
            # we have at least a complete message, continue
            if len(self._buffer) >= self.FRAME_HEAD_SIZE + self._length - 2:
                return True
        # we don't have enough of a message yet, try again later
        _logger.debug('Frame is not complete yet, needs more buffer data')
        return False

    def advance_frame(self):
        """Pop the front-most frame from the buffer."""
        self._buffer = self._buffer[self.FRAME_HEAD_SIZE + self._length - 2 :]
        del self._length

    def add_to_frame(self, message: bytes) -> None:
        """Add incoming data to the processing buffer."""
        self._buffer += message

    def is_frame_ready(self):
        """Check if we have enough data in the buffer to read at least a frame header."""
        return len(self._buffer) >= self.FRAME_HEAD_SIZE

    def get_frame(self):
        """Extract the next PDU frame from the buffer, removing the MBAP header except for the function id."""
        return self._buffer[self.FRAME_HEAD_SIZE - 1 : self.FRAME_HEAD_SIZE + self._length]

    def process_incoming_packet(self, data: bytes, callback: Callable) -> None:
        """Process an incoming packet.

        This takes in a bytestream from the underlying transport and adds it to the
        frame buffer. It then repeatedly attempts to perform framing on the buffer
        by checking for a viable message at the head of the buffer, and if found pops
        off the expected length of the raw frame for processing.

        Returns when the buffer is too short to contain any more viable messages. This
        handles cases where multiple and/or partial messages arrive due to fragmentation
        or buffering on the underlying transport - these partial messages will try to
        be completed eventually as more data subsequently arrives and gets handled here.

        If decoding and processing succeeds for a message, the instantiated PDU DTO is
        handed to the supplied callback function for onward processing and dispatching.

        Args:
            data: Data from underlying transport.
            callback: Processor to receive newly-decoded PDUs.
        """
        self.add_to_frame(data)

        # Try to extract a full frame from what's in the buffer
        while self.is_frame_ready() and self.check_frame():
            frame = self.get_frame()
            try:
                result = self.decoder.decode(frame)
                _logger.debug(f'Decoded response {result}')
                callback(result)
            except ValueError as e:
                if len(e.args) > 1:
                    # Frame valid (PDU identifiable) but PDU itself has invalid/inconsistent data
                    _logger.warning(f'Invalid PDU: {e.args[0]} {e.args[1]}')
                else:
                    _logger.warning(f'Unable to decode frame: {e} [{hexlify(frame)}]')
            finally:
                self.advance_frame()

    def reset_frame(self):
        """Reset a corrupted message buffer when the next frame can be identified."""
        next_header_offset = self._buffer.find(b'\x59\x59\x00\x01', 1)
        if next_header_offset > 0:
            _logger.info(f'Found next frame at offset {next_header_offset}, advancing buffer.')
            self._buffer = self._buffer[next_header_offset:]
        else:
            _logger.info('No following frame found yet, doing nothing.')
            # self._buffer = b""

    def build_packet(self, message: ModbusPDU) -> bytes:
        """Creates a finalised GivEnergy Modbus packet from a constant header plus the encoded PDU."""
        # FIXME this is hacky
        if isinstance(message, HeartbeatRequest) or isinstance(message, HeartbeatResponse):
            fn_code = 0x01
        else:
            fn_code = 0x02
        msg = message.encode()
        return struct.pack(self.FRAME_HEAD, 0x5959, 0x0001, len(msg) + 2, 0x01, fn_code) + msg
