import logging
from abc import ABC
from collections.abc import AsyncIterator, Callable

from givenergy_modbus.exceptions import ExceptionBase, InvalidFrame, InvalidPduState
from givenergy_modbus.pdu import BasePDU, ClientIncomingMessage, ServerIncomingMessage

_logger = logging.getLogger(__name__)

PduProcessedCallback = Callable[[BasePDU | None, bytes], None]
DataProcessedCallback = Callable[[BasePDU | None, bytes], None]

HEADER_START_MARKER: bytes = bytes.fromhex("59590001")


class Framer(ABC):
    """Modbus Framer for parsing the GivEnergy data format.

    A framer knows how to unmarshal a wire protocol, in particular detecting if a message frame is likely present in
    a buffer, whether it is complete, extracting the frame, and handing off to a decoder. This implementation
    understands the idiosyncrasies of GivEnergy's implementation of the Modbus spec.

    The wire protocol looks very similar to normal Modbus TCP, with each message still having a regular 7-byte MBAP
    header consisting of:

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
        * ``0x01/Heartbeat``: The data adapter will send this request every 3 minutes and the client needs to respond
          within 5 seconds. After three missed heartbeats the TCP socket will be closed and the client will need to
          re-establish a connection.
        * ``0x02/Transparent``: The primary way to interact with the inverter. The data payload is a GivEnergy
          specific sub-frame which encodes the actual command and data for the inverter. It is functionally similar to
          Modbus sub-functions, using `0x02` as main function.

    Because the first two header fields are static we scan for ``0x59590001`` to find the start of candidate frames
    in a byte stream.

    GivEnergy Transparent sub-frames have a consistent format:

    * ``serial`` (10 bytes) of the responding data adapter (wifi/GPRS/ethernet) plugged into the inverter. For
      client-originating messages this is seemingly not important and can be an arbitrary alphanumeric string.
    * ``pad`` (8 bytes) is not well understood but appears to be a single zero-padded byte that is fairly predictable
      based on the command. Setting this to zero makes the inverter stop responding to requests.
    * ``addr`` (1 byte) unit identifier, of which a few are known:
        * ``0x00``: Android (+iOS?) app
        * ``0x11``: inverter, but responses get forwarded to the GivEnergy cloud - high frequency queries (anything
          less than 5-minute intervals) should avoid this unit id and use ``0x32`` instead
        * ``0x32`` to ``0x36``: BMS for battery packs 1-5 connected to the inverter, but only for Input Registers
          60-119. This is also the strategy to detect which batteries are present: query these unit ids for those
          Input Register pages and use all-zero responses to indicate missing units
    * ``func`` (1 byte) is the command to be executed:
        * `0x03` - read holding registers
        * `0x04` - read input registers
        * `0x06` - write single holding register
        * `0x10` - write multiple holding registers (not implemented by this library)
    * ``data`` (*n* bytes) depends on the function invoked
    * ``crc`` (2 bytes) CRC for a request is calculated using the function id, base register and
      step count, but it is unclear how a response CRC is calculated or should be verified.

    **Layering note — what the TCP surface actually exposes.** The Modbus dialect this framer
    parses is the dongle's *TCP server*, not a direct view of the inverter or any BMS. The
    physical chain is roughly::

        library client ↔ TCP ↔ wifi/GPRS dongle ↔ internal serial ↔ inverter ↔ RS485 ↔ BMS(s)

    The inverter polls its connected BMSes over RS485 and caches the results; the dongle
    polls the inverter over an internal serial link and re-exposes that cache via TCP. So a
    read of ``addr=0x32`` IR(60..119) does not round-trip to the battery — it returns the
    inverter's most recent cached page for BMS pack 1. Two consequences worth knowing:

    * **Cache freeze** — if a BMS stops responding on RS485 (e.g. while in bootloader mode
      during a firmware update), the inverter's cache keeps serving the last-known-good
      values rather than blanking. From the TCP side this looks like a battery emitting
      byte-for-byte identical responses indefinitely while neighbouring batteries update
      normally. Distinguishing "frozen cache" from "live but unchanged" requires comparing
      multiple consecutive reads.
    * **Exception responses are inverter-originated**, not BMS-originated. The BMS firmware
      itself silently drops malformed frames (CRC failures, illegal function codes return
      exception code ``1``); anything richer comes from the inverter rejecting a TCP-side
      request against its own cached register banks.

    The authoritative reference for the *BMS-side* RS485 dialect (what the inverter sees,
    one layer below this framer) is the open-giv/bms-analysis repository — see
    ``docs/architecture.md`` § References.
    """

    _buffer: bytes = b""
    pdu_class: type[BasePDU]

    async def decode(self, data: bytes) -> AsyncIterator[BasePDU | ExceptionBase]:
        """Receive incoming network data and attempt to decode frames into messages.

        This method receives raw bytes as passed from the underlying transport and appends it onto an internal
        buffer. This means we might have any number of complete frames, potentially followed by a partial frame in
        the buffer ready for unframing and processing. There is also plenty of evidence that garbage and corruption
        is present from time to time which we attempt to skip over. This framer repeatedly attempts sliding window
        framing on the buffer by scanning for a constant start-of-frame marker, extracting the expected frame size,
        and if the buffer is long enough extracts that frame and trims the buffer. This will extract, decode and
        yield all complete messages that are able to be unframed this way, and returns when the first partial frame
        is encountered (i.e., the buffer is too short to contain any viable message due to fragmentation or
        buffering), with the expectation that this partial frame will be completed as more data arrives and gets
        passed here.

        Every complete frame gets passed through the decoder – the result (either a valid message or a caught
        exception) is yielded to the caller for onward processing, dispatching, error handling and debugging,
        and the frame buffer is always advanced over that frame.
        """
        self._buffer += data
        while len(self._buffer) >= 18:  # shortest known message is 18b (heartbeat request)
            # ensure the head of the buffer starts with a valid MBAP header
            frame_start_offset = self._buffer.find(HEADER_START_MARKER)
            if frame_start_offset < 0:
                # No marker found anywhere in the accumulated buffer. Trim to
                # the tail bytes that could still be the start of a marker
                # split across reads (the first len(marker)-1 bytes), so a
                # faulty/malicious peer streaming non-marker data can't grow
                # this buffer without bound. See #88.
                #
                # The while-loop's `>= 18` guard means the buffer is always
                # larger than `keep` (= 3) at this point, so there's always
                # something to discard. The log level is tiered so a peer
                # drip-feeding a few bytes at a time doesn't flood operator
                # logs with warnings — a sustained substantial discard still
                # surfaces as a warning so operators have visibility.
                keep = len(HEADER_START_MARKER) - 1
                discarded = len(self._buffer) - keep
                if discarded > 100:
                    _logger.warning(
                        "No frame header in %db accumulated buffer, "
                        "discarding %db of leading garbage and retaining trailing %db",
                        len(self._buffer),
                        discarded,
                        keep,
                    )
                else:
                    _logger.debug(
                        "No frame header in %db buffer, discarding %db, retaining trailing %db",
                        len(self._buffer),
                        discarded,
                        keep,
                    )
                self._buffer = self._buffer[-keep:]
                break
            elif frame_start_offset > 0:
                # The next candidate frame header is not at the start of the buffer: skip forward to that position
                _logger.warning(
                    f"Candidate frame found {frame_start_offset} bytes into buffer, "
                    f"discarding leading garbage: 0x{self._buffer[:frame_start_offset].hex()}"
                )
                self._buffer = self._buffer[frame_start_offset:]
                continue

            _logger.debug(f"Found next frame: 0x{self._buffer[:8].hex()}..., buffer_len={len(self._buffer)}")

            # check that the current frame isn't invalid / weirdly truncated
            next_frame_start_offset = self._buffer.find(HEADER_START_MARKER, 1)
            if 0 < next_frame_start_offset < 18:
                _logger.error(
                    "Next frame start found implausibly near, current frame likely corrupt/invalid. "
                    f"Skipping forward {next_frame_start_offset}b. "
                    f"Buffer={len(self._buffer)}b: 0x{self._buffer.hex()}"
                )
                self._buffer = self._buffer[next_frame_start_offset:]
                continue

            # sanity check the rest of the MBAP header
            hdr_len, u_id, f_id = int.from_bytes(self._buffer[4:6], byteorder="big"), self._buffer[6], self._buffer[7]
            if hdr_len > 300 or u_id not in (0, 1) or f_id not in (1, 2):
                _logger.warning(
                    f"Unexpected header values found (len={hdr_len:04x}, u_id={u_id:02x}, f_id={f_id:02x}), "
                    f"discarding candidate frame and resuming search"
                )
                self._buffer = self._buffer[4:]
                continue

            # Calculate how many bytes is needed to read the current frame completely and await more data if necessary
            frame_len = 6 + hdr_len
            if len(self._buffer) < frame_len:
                _logger.debug(
                    f"Buffer ({len(self._buffer)}b) insufficient for frame of length {frame_len}b, await more data"
                )
                break

            # Extract the frame and try to decode it
            frame = self._buffer[:frame_len]
            self._buffer = self._buffer[frame_len:]
            try:
                yield self.pdu_class.decode_bytes(frame)
            except (InvalidPduState, InvalidFrame) as e:
                yield e
            except Exception as e:
                # Defence-in-depth against malformed-frame DoS: any unexpected
                # exception from low-level decoding (e.g. `struct.error` from a
                # too-short payload, `ValueError` / `IndexError` from misaligned
                # offsets) is wrapped as `InvalidFrame` so the consumer task
                # keeps running rather than terminating on a single bad frame
                # from the network. Broad catch is deliberate here — this is
                # the trust boundary for untrusted network input. See #88.
                yield InvalidFrame(f"frame failed low-level decode: {type(e).__name__}: {e}", frame)


class ClientFramer(Framer):
    """Framer implementation for client-side use."""

    def __init__(self):
        self.pdu_class = ClientIncomingMessage


class ServerFramer(Framer):
    """Framer implementation for server-side use."""

    def __init__(self):
        self.pdu_class = ServerIncomingMessage
