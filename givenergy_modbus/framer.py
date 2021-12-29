"""ModbusFramer implementation for GivEnergy protocol.

A framer abstracts away all the detail about how marshall the wire
protocol, e.g. to detect if a current message frame exists, decoding
it, sending it, etc.  This implementation understands the
idiosyncracies that GivEnergy implemented for their Modbus
interface.

Raises:
    InvalidMessageReceivedException: When unable to decode an incoming message.
    ModbusIOException: When the identified function decoder fails to decode a message.
"""

from __future__ import annotations

import logging
import struct
from typing import Callable, Container, Optional

from pymodbus.client.sync import BaseModbusClient
from pymodbus.exceptions import InvalidMessageReceivedException, ModbusIOException
from pymodbus.framer import ModbusFramer
from pymodbus.interfaces import IModbusDecoder
from pymodbus.pdu import ModbusPDU
from pymodbus.utilities import hexlify_packets

_logger = logging.getLogger(__package__)


class GivModbusFramer(ModbusFramer):
    """GivEnergy Modbus Frame controller.

    This is a variation on the official ModbusSocketFramer but adapted for
    GivEnergy's idiosyncratic implementation of the Modbus spec. On the wire
    each Modbus TCP message starts with a 7-byte MBAP header, consisting of:
      * `transaction id` (always 0x5959/'YY')
      * `protocol id` (always 0x1, official Modbus uses 0x0)
      * `byte count/length` of the data block (**including** the 1-byte unit
        id, which is why there is always an off-by-one difference from normal
        Modbus length calculations)
      * `unit id` (always 0x1)

    This is followed by a `function id` which is always 2:

        [         MBAP Header         ] [ Function id ] [ Data ]
        [ tid ][ pid ][ length ][ uid ]
          2b     2b     2b        1b           1b           Nb

        while len(message) > 8:
          tid, pid, length, uid, fid = struct.unpack(">HHHBB", message)
          data = message[8:6+length]
          process(tid, pid, length, uid, fid, data)
          message = message[6+length:]

    Because of this it is simpler to consider the static function code as part
    of the header. The data block has a consistent format specific to
    GivEnergy's protocol:

        [ serial ] [ pad ] [ addr ] [ func ] [ Data ] [ crc ]
            10b       8b      1b       1b       Nb       2b

     * `serial` is that of the data adapter (wifi/GPRS/ethernet?) plugged
       into the inverter
     * `pad` is unknown - generally seems to be a single byte that changes
       (some kind of check/crc?) and zero-padded on the left
     * `addr` is the slave address, always 0x32
     * `func` is the actual function to be executed:
        * 3 - read holding registers
        * 4 - read input registers
        * 6 - write single register
     * `data` is a format specific to the function
     * `crc` - not clear how those for responses are calculated
    """

    FRAME_HEAD = ">HHHBB"
    FRAME_TAIL = ">H"

    def __init__(self, decoder: IModbusDecoder, client: Optional[BaseModbusClient] = None):
        """Constructor.

        Args:
            decoder: Frame decoder implementation.
            client (optional): Synchronous Modbus Client. Defaults to None.
        """
        _logger.debug(f"decoder:{decoder}, client:{client}")
        self._buffer = b""
        self._header = {"tid": 0, "pid": 0, "len": 0, "uid": 0, "fid": 0}
        self._hsize = 0x08
        self._check = 0x0
        self.decoder = decoder
        self.client = client

    def decode_data(self, data: bytes) -> dict:
        """Decodes the MBAP frame header and performs a few sanity checks.

        Args:
            data: Raw data from the frame buffer.

        Returns:
            dict: Extracted values of:
              * `tid`: Transaction ID (should always be `0x5959` for GivEnergy systems)
              * `pid`: Protocol ID (should always be `0x0001` for GivEnergy systems)
              * `uid`: Unit ID (should always be `0x0001` for GivEnergy systems)
              * `fid`: Function ID (should always be `0x0002` for GivEnergy systems)
        """
        if self.isFrameReady():
            _logger.debug(
                f"extracting header using {self.FRAME_HEAD} from {self._buffer[:self._hsize].decode('ascii')}"
            )
            tid, pid, len_, uid, fid = struct.unpack(self.FRAME_HEAD, self._buffer[: self._hsize])
            header = dict(tid=tid, pid=pid, len=len_, uid=uid, fid=fid)
            _logger.debug(f"extracted MBAP header: { dict((k, hex(v)) for k,v in header.items()) }")
            if tid != 0x5959:
                _logger.warning(f"Unexpected Transaction ID {tid} - GivEnergy systems should be using 0x5959")
            if pid != 0x1:
                _logger.warning(f"Unexpected Protocol ID {pid} - GivEnergy systems should be using 0x0001")
            if uid != 0x1:
                _logger.warning(f"Unexpected Unit ID {uid} - GivEnergy systems should be using 0x01")
            if fid != 0x2:
                _logger.warning(f"Unexpected Function ID {fid} - GivEnergy systems should be using 0x02")
            return header
        return dict()

    def checkFrame(self) -> bool:
        """Check and decode the next frame. Returns operation success."""
        if self.isFrameReady():
            hdr = self.decode_data(self._buffer)
            self._header.update(hdr)

            # this short a message should not be possible?
            if self._header["len"] < 2:
                _logger.warning(f"unexpected short message length {self._header['len']}, advancing frame")
                self.advanceFrame()
            # we have at least a complete message, continue
            else:
                if len(self._buffer) >= self._hsize + self._header["len"] - 2:
                    _logger.debug("complete message in buffer")
                    return True
                _logger.debug("no complete message in buffer yet")
        # we don't have enough of a message yet, wait
        return False

    def advanceFrame(self):
        """Pop the frontmost frame from the buffer."""
        length = self._hsize + self._header["len"] - 2
        _logger.debug(f'length {length} = {self._hsize} + {self._header["len"]} - 2, len(buffer) = {len(self._buffer)}')
        self._buffer = self._buffer[length:]
        _logger.debug(f"buffer is now {len(self._buffer)} bytes: {self._buffer}")
        self._header = {"tid": 0, "pid": 0, "len": 0, "uid": 0, "fid": 0}

    def addToFrame(self, message: bytes) -> None:
        """Add incoming data to the processing buffer."""
        self._buffer += message

    def isFrameReady(self):
        """Check if we have enough data in the buffer to read at least a frame header."""
        return len(self._buffer) >= self._hsize

    def getFrame(self):
        """Extract the frontmost PDU frame from the buffer, separating the encapsulating head and tail."""
        extracted_length = self._hsize + self._header["len"] - 4
        return (
            self._buffer[: self._hsize],  # head
            self._buffer[self._hsize : extracted_length],  # PDU frame
            self._buffer[extracted_length : extracted_length + 2],  # tail
        )

    def populateResult(self, result: ModbusPDU):
        """Populates the Modbus PDU object's metadata attributes from the decoded MBAP headers."""
        result.transaction_id = self._header["tid"]
        result.protocol_id = self._header["pid"]
        result.unit_id = self._header["uid"]
        result.check = self._check

    def processIncomingPacket(
        self, data: bytes, callback: Callable, unit: Container[int] | int, single: Optional[bool] = False, **kwargs
    ) -> None:
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
            unit: Filter to allow processing only frames intended for the
              specified unit id(s). Servers can listen for multiple, whereas
              clients semantically have a single id.
            single: If True, ignore unit address validation (intended for
              client implementations).
        """
        if isinstance(unit, int):
            _logger.warning("Unit supplied as bare int, wrapping in list.")
            unit = [unit]
        single = kwargs.get("single", False)
        _logger.debug("Processing: " + hexlify_packets(data))
        self.addToFrame(data)
        while True:
            if self.isFrameReady():
                if self.checkFrame():
                    _logger.debug(f"validating unit {unit} and single {single}")
                    if self._validate_unit_id(unit, single):
                        self._process(callback)
                    else:
                        _logger.warning("Not a valid unit id - {}, " "ignoring!!".format(self._header["uid"]))
                        self.resetFrame()
                else:
                    _logger.debug("Frame check failed, ignoring!!")
                    self.resetFrame()
            else:
                if len(self._buffer):
                    # Possible error ???
                    if self._header["len"] < 2:
                        self._process(callback, error=True)
                break

    def _process(self, callback, error=False):
        """Process incoming packets irrespective error condition."""
        if error:
            data = self.getRawFrame()
            result = self.decoder.decode(data)
            if result.function_code < 0x80:
                raise InvalidMessageReceivedException(result)
        else:
            _, data, self._check = self.getFrame()
            result = self.decoder.decode(data)
            if result is None:
                raise ModbusIOException("Unable to decode request")

        self.populateResult(result)
        self.advanceFrame()
        callback(result)  # defer or push to a thread?

    def resetFrame(self):
        """Reset the entire message buffer."""
        self._buffer = b""
        self._header = {"tid": 0, "pid": 0, "len": 0, "uid": 0, "fid": 0}

    def getRawFrame(self):
        """Returns the complete buffer."""
        return self._buffer

    def buildPacket(self, message: ModbusPDU) -> bytes:
        """Creates a finalised GivEnergy Modbus packet ready to go on the wire.

        :param message: The populated Modbus PDU to send
        """
        data = message.encode()
        return (
            struct.pack(
                self.FRAME_HEAD,
                0x5959,  # hardcode instead of message.transaction_id because the transaction manager is dumb
                # message.transaction_id,
                message.protocol_id,
                len(data) + 4,  # 2 bytes each for frame head (uid+fid) + tail (crc)
                message.unit_id,
                0x02,
            )
            + data
            + struct.pack(self.FRAME_TAIL, message.check)  # append CRC
        )
