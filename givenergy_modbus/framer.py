from __future__ import annotations

import logging
import struct
from abc import ABC
from typing import Callable, Optional

from givenergy_modbus.decoder import ClientDecoder, Decoder, ServerDecoder
from givenergy_modbus.exceptions import InvalidPduState, InvalidFrame
from givenergy_modbus.pdu import BasePDU

_logger = logging.getLogger(__package__)

PduProcessedCallback = Callable[[tuple[Optional[BasePDU], bytes]], None]


class Framer(ABC):
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

    # TODO add Final[..] when py37 is not supported any more
    FRAME_HEAD: str = ">HHHBB"  # tid(w), pid(w), length(w), uid(b), fid(b)
    FRAME_HEAD_SIZE: int = struct.calcsize(FRAME_HEAD)

    _buffer: bytes = b""
    _decoder: Decoder

    def process_incoming_data(self, data: bytes, callback: PduProcessedCallback) -> None:
        """Add incoming data to our frame buffer and attempt to process frames found.

        This receives raw bytes as passed from the underlying transport and appends them to an internal frame buffer.
        This means we might have 0, 1 or even more complete frames ready for processing – this method repeatedly
        attempts sliding window framing on the buffer by scanning for a start-of-frame header and incrementally
        parsing data to determine if we have a complete frame. If we run out of buffer we return, and on the next
        invocation will be re-run as new data is added.

        This handles multiple and/or partial messages in the buffer (due to e.g. fragmentation or buffering),
        with these partial messages being completed eventually as more data arrives and gets passed here.

        Every complete frame gets passed through the decoder – the result (either way) plus the raw frame gets passed
        to the supplied callback for onward processing, dispatching, error handling and debugging. The frame buffer
        is always advanced over that frame.

        Args:
            data: Data from underlying transport.
            callback: Callable invoked for every raw frame encountered, including the decoding result.
        """
        self._buffer += data

        header_start = 0
        while header_start >= 0:
            header_start = self._buffer.find(b'\x59\x59\x00\x01')

            # The next header is not at the start of the buffer: wind the buffer forward to that position
            if header_start > 0:
                _logger.warning(
                    f'Likely candidate frame candidate found {header_start} bytes into buffer, '
                    f'skipping over leading garbage (0x{self._buffer[:header_start].hex()})'
                )
                self._buffer = self._buffer[header_start:]
                header_start = 0

            # We are able to extract at least a frame header
            if header_start == 0 and self.buffer_length >= self.FRAME_HEAD_SIZE:
                next_header_start = self._buffer.find(b'\x59\x59\x00\x01', 1)
                if 0 < next_header_start <= 20:
                    _logger.warning(
                        f'Something dodgy going on, another header found impossibly close at '
                        f'{next_header_start}. {self.buffer_length} bytes, '
                        f'0x{self._buffer.hex(bytes_per_sep=2)}'
                    )
                data = self._buffer[: self.FRAME_HEAD_SIZE]
                _logger.debug(f"Candidate MBAP header 0x{data.hex()}, parsing using format {self.FRAME_HEAD}")
                t_id, p_id, hdr_len, u_id, f_id = struct.unpack(self.FRAME_HEAD, data)
                _logger.debug(f"t_id={t_id:04x}, p_id={p_id:04x}, len={hdr_len:04x}, u_id={u_id:02x}, f_id={f_id:02x}")
                # these two must match since they were the search token that led us here:
                assert t_id == 0x5959
                assert p_id == 0x1
                # check the other attributes are reasonable
                if hdr_len > 300 or u_id != 1 or f_id not in (1, 2):
                    _logger.warning(
                        f'Unexpected header values found (len={hdr_len:04x}, u_id={u_id:02x}, f_id={f_id:02x}), '
                        f'discarding candidate frame and resuming search'
                    )
                    self._buffer = self._buffer[4:]
                    continue

                # Calculate how many bytes a complete frame needs
                frame_len = self.FRAME_HEAD_SIZE + hdr_len - 2
                if self.buffer_length < frame_len:
                    _logger.debug(f"Buffer too short ({self.buffer_length}) to complete frame ({frame_len})")
                    return

                # Extract the inner frame and try to decode it
                raw_frame = self._buffer[:frame_len]
                inner_frame = raw_frame[self.FRAME_HEAD_SIZE :]
                self._buffer = self._buffer[frame_len:]
                try:
                    _logger.debug(f'Decoding inner frame {inner_frame.hex()}')
                    pdu = self._decoder.decode(f_id, inner_frame)
                    _logger.debug(f'Successfully decoded {pdu}')
                except InvalidPduState as e:
                    _logger.warning(f'Invalid PDU: {e.args[0]} {e.args[1]}')
                except InvalidFrame as e:
                    _logger.warning(f'Unable to decode frame: {e} [{inner_frame.hex()}]')
                finally:
                    callback((pdu, raw_frame))

        _logger.debug('Frame is not complete yet, needs more data')

    def build_packet(self, message: BasePDU) -> bytes:
        """Creates a packet from the MBAP header plus the encoded PDU."""
        inner_frame = message.encode()
        mbap_header = struct.pack(self.FRAME_HEAD, 0x5959, 0x1, len(inner_frame) + 2, 0x1, message.main_function_code)
        return mbap_header + inner_frame

    @property
    def buffer_length(self):
        """Returns the current length of the bytestream buffer."""
        return len(self._buffer)


class ClientFramer(Framer):
    """Framer implementation for client-side use."""

    def __init__(self):
        self._decoder = ClientDecoder()


class ServerFramer(Framer):
    """Framer implementation for server-side use."""

    def __init__(self):
        self._decoder = ServerDecoder()
