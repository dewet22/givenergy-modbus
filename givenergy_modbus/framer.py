from __future__ import annotations

import logging
import struct
from typing import Callable, Container

from pymodbus.client.sync import BaseModbusClient
from pymodbus.exceptions import InvalidMessageReceivedException, ModbusIOException
from pymodbus.framer import ModbusFramer
from pymodbus.interfaces import IModbusDecoder
from pymodbus.pdu import ModbusPDU
from pymodbus.utilities import hexlify_packets

_logger = logging.getLogger(__package__)


class GivModbusFramer(ModbusFramer):
    """GivEnergy Modbus Frame controller.

    A framer abstracts away all the detail about how marshall the wire
    protocol, e.g. to detect if a current message frame exists, decoding
    it, sending it, etc.  This implementation understands the
    idiosyncrasies of GivEnergy's implementation of the Modbus spec.

    It looks very similar to normal Modbus TCP on the wire, with each message still
    starting with a regular 7-byte MBAP header consisting of:
      * `tid`, the transaction id
      * `pid`, the protocol id
      * `len`, the byte count / length of the remaining data following the header
      * `uid`, the unit id for addressing devices on the Modbus network
    This is followed by `fid` / a function code to specify how the message should be
    decoded into a PDU:

    ```
        [_________MBAP Header______] [_fid_] [_______________data________________]
        [_tid_][_pid_][_len_][_uid_]
          2b     2b     2b     1b      1b                  (len-1)b
    ```

    GivEnergy's implementation quicks can be summarised as:
      * `tid` is always `0x5959/'YY'`, so the assumption/interpretation is that clients
         have to poll continually instead of maintaining long-lived connections and
         using varying `tid`s to pair requests with responses
      * `pid` is always `0x0001`, whereas normal Modbus uses `0x0000`
      * `len` **adds** 1 extra byte (anecdotally for the unit id?) which normal
         Modbus does not. This leads to continual off-by-one differences appearing
         whenever header/frame length calculations are done. This is probably the
         biggest reason Modbus libraries struggle working out of the box.
      * `unit_id` is always `0x01`
      * `fid` is always `0x02/Read Discrete Inputs` even for requests that modify
         registers. The actual intended function is encoded 19 bytes into the data
         block. You can interpret this as functionally somewhat akin to Modbus
         sub-functions where we always use the `0x02` main function.

    Because these fields are static and we have to reinterpret what `len` means it is
    simpler to just reconsider the entire header:

    ```
        [___"MBAP+" Header____] [_______________GivEnergy Frame_______________]
        [___h1___][_len_][_h2_]
            4b      2b     2b                      (len+2)b
    ```

      * `h1` is always `0x59590001`, so can be used as a sanity check during decoding
      * `len` needs 2 added during calculations because of the previous extra byte
         off-by-one inconsistency, plus expanding the header by including 1-byte `fid`
      * `h2` is always `0x0102`, so can be used as a sanity check during decoding

    TODO These constant headers being present would allow for us to scan through the
    bytestream to try and recover from stream errors and help reset the framing.

    The GivEnergy frame itself has a consistent format:

    ```
        [____serial____] [___pad___] [_addr_] [_func_] [______data______] [_crc_]
              10b            8b         1b       1b            Nb           2b
    ```

     * `serial` of the responding data adapter (wifi/GPRS?/ethernet?) plugged into
        the inverter. For requests this is simply hardcoded as a dummy `AB1234G567`
     * `pad`'s function is unknown - it appears to be a single zero-padded byte that
        varies across responses, so might be some kind of check/crc?
     * `addr` is the "slave" address, conventionally `0x32`
     * `func` is the actual function to be executed:
        * `0x3` - read holding registers
        * `0x4` - read input registers
        * `0x6` - write single register
     * `data` is specific to the invoked function
     * `crc` - for requests it is calculated using the function id, base register and
        step count, but it is not clear how those for responses are calculated (or
        should be checked)

    In pseudocode, the message unframing algorithm looks like:
        while len(buffer) > 8:
          tid, pid, len, uid, fid = struct.unpack(">HHHBB", buffer)
          data = buffer[8:6+len]
          process_message(tid, pid, len, uid, fid, data)
          buffer = buffer[6+len:]  # skip buffer over frame

    Raises:
        InvalidMessageReceivedException: When unable to decode an incoming message.
        ModbusIOException: When the identified function decoder fails to decode a message.
    """

    FRAME_HEAD = ">HHHBB"  # tid(w), pid(w), length(w), uid(b), fid(b)
    FRAME_TAIL = ">H"  # crc(w)

    def __init__(self, decoder: IModbusDecoder, client: BaseModbusClient | None = None):
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
        self, data: bytes, callback: Callable, unit: Container[int] | int, single: bool | None = False, **kwargs
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
