"""Property-based fuzzing of the framer's trust boundary.

The framer is the library's network trust boundary: :meth:`Framer.decode`
consumes raw, potentially-hostile bytes and must never raise, never grow its
buffer without bound, and always yield the same messages regardless of how the
byte stream is chunked (#88). Those are *properties* over all inputs, not a
handful of examples, so we assert them with Hypothesis.

Generation is biased towards structurally-valid frames — random bytes almost
never contain the ``0x59590001`` start marker and so get discarded before
reaching the interesting decode paths. We seed from the real capture corpus
(``tests/fixtures/captures``) and mutate around it, which drives coverage into
``decode_bytes`` and the PDU decoders.
"""

import asyncio
import logging
import os
import string
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from givenergy_modbus.exceptions import ExceptionBase
from givenergy_modbus.framer import HEADER_START_MARKER, ClientFramer
from givenergy_modbus.pdu import (
    BasePDU,
    ReadHoldingRegistersResponse,
    ReadInputRegistersResponse,
    WriteHoldingRegisterResponse,
)
from givenergy_modbus.pdu.base import ClientIncomingMessage
from tests.test_framer import EXCEPTION_RESPONSE_FRAME, VALID_REQUEST_FRAME, VALID_RESPONSE_FRAME

# Property tests run many examples and legitimately exceed the suite-wide 1s
# per-test timeout (pyproject ``timeout = 1``); give them their own headroom so
# a deeper GE_FUZZ_EXAMPLES sweep isn't killed mid-run and mistaken for a fault.
pytestmark = pytest.mark.timeout(120)

_CAPTURES = Path(__file__).parent / "fixtures" / "captures"


def _iter_rx_bytes(path: Path):
    """Yield the raw rx byte chunks from a capture log, in file order."""
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split(" ", 2)
        if len(parts) == 3 and parts[1] == "rx":
            try:
                yield bytes.fromhex(parts[2])
            except ValueError:
                continue


def _load_corpus(limit: int = 400) -> list[bytes]:
    """Extract complete, decodable frames from the real capture corpus.

    Concatenating a file's rx chunks reconstructs the wire stream; feeding it
    through a framer yields real complete frames (each PDU carries the exact
    bytes it decoded from as ``raw_frame``). Deduplicated and capped so the
    strategy stays fast and shrinking stays tractable.
    """
    seen: dict[bytes, None] = {}
    for path in sorted(_CAPTURES.rglob("*.log")):
        stream = b"".join(_iter_rx_bytes(path))

        async def _drain(data: bytes):
            framer = ClientFramer()
            return [x async for x in framer.decode(data)]

        for item in asyncio.run(_drain(stream)):
            if isinstance(item, BasePDU):
                seen.setdefault(item.raw_frame, None)
                if len(seen) >= limit:
                    return list(seen)
    return list(seen)


# Recorded constants plus real corpus frames. Falls back gracefully if the
# corpus can't be mined so the garbage-only properties still run.
_CORPUS: list[bytes] = [VALID_REQUEST_FRAME, VALID_RESPONSE_FRAME, EXCEPTION_RESPONSE_FRAME]
_CORPUS += [f for f in _load_corpus() if f not in _CORPUS]


@pytest.fixture(autouse=True)
def _quiet_framer_logs():
    """Silence the library's expected per-garbage discard/CRC/safety warnings.

    Fuzzing emits them by the thousand; muting keeps a real failure visible.
    """
    logger = logging.getLogger("givenergy_modbus")
    prior = logger.level
    logger.setLevel(logging.CRITICAL)
    yield
    logger.setLevel(prior)


def drain(framer: ClientFramer, data: bytes) -> list[object]:
    """Run the async ``decode`` generator to completion (it never truly awaits)."""

    async def _run():
        return [x async for x in framer.decode(data)]

    return asyncio.run(_run())


# --- strategies ---------------------------------------------------------------

valid_frame = st.sampled_from(_CORPUS)

garbage = st.binary(max_size=512)


@st.composite
def mutated_frame(draw) -> bytes:
    """A real frame with one byte flipped, truncated, or extended."""
    frame = bytearray(draw(valid_frame))
    kind = draw(st.sampled_from(("flip", "truncate", "extend")))
    if kind == "flip" and frame:
        i = draw(st.integers(0, len(frame) - 1))
        frame[i] ^= draw(st.integers(1, 255))
    elif kind == "truncate" and frame:
        frame = frame[: draw(st.integers(0, len(frame) - 1))]
    else:
        frame += draw(st.binary(min_size=1, max_size=32))
    return bytes(frame)


chunk = st.one_of(garbage, valid_frame, mutated_frame())

# Default is a fast PR-friendly pass; nightly CI can crank it via the env var
# (e.g. GE_FUZZ_EXAMPLES=5000) for a deeper sweep without touching the code.
_SETTINGS = settings(
    deadline=None,  # asyncio.run-per-example trips the default 200ms deadline
    suppress_health_check=[HealthCheck.too_slow],
    max_examples=int(os.environ.get("GE_FUZZ_EXAMPLES", "300")),
)


def _split_at(data: bytes, cuts: list[int]) -> list[bytes]:
    points = sorted({c % (len(data) + 1) for c in cuts}) if data else []
    pieces, prev = [], 0
    for p in points:
        pieces.append(data[prev:p])
        prev = p
    pieces.append(data[prev:])
    return pieces


# --- properties ---------------------------------------------------------------


@_SETTINGS
@given(chunks=st.lists(chunk, max_size=20))
def test_decode_never_raises_and_only_yields_pdu_or_exception(chunks):
    """No input sequence escapes decode as an unhandled exception (#88).

    Every yielded item is either a decoded PDU or a caught exception.
    """
    framer = ClientFramer()
    for c in chunks:
        for item in drain(framer, c):
            assert isinstance(item, (BasePDU, ExceptionBase))


@_SETTINGS
@given(data=st.binary(min_size=0, max_size=4096))
def test_headerless_garbage_never_grows_buffer(data):
    """Marker-less garbage must be trimmed, not accumulated (anti-DoS, #88).

    Worst case the framer retains a partial frame it still believes viable,
    bounded by the maximum valid frame length (6 + max hdr_len of 300).
    """
    if HEADER_START_MARKER in data:
        return  # only asserting the no-marker path here
    framer = ClientFramer()
    drain(framer, data)
    assert len(framer._buffer) <= 6 + 300


@_SETTINGS
@given(
    frames=st.lists(valid_frame, min_size=1, max_size=8),
    cuts=st.lists(st.integers(min_value=0), max_size=12),
)
def test_chunking_is_invariant(frames, cuts):
    """However the stream is fragmented across reads, the same messages decode.

    This is the streaming property that fixed examples can't cover: it exercises
    marker-straddling and mid-payload splits at arbitrary boundaries.
    """
    stream = b"".join(frames)

    whole = ClientFramer()
    reference = [type(x).__name__ for x in drain(whole, stream)]

    pieces = ClientFramer()
    got: list[str] = []
    for piece in _split_at(stream, cuts):
        got += [type(x).__name__ for x in drain(pieces, piece)]

    assert got == reference


@_SETTINGS
@given(prefix=garbage, frame=valid_frame)
def test_garbage_prefix_is_transparent(prefix, frame):
    """Leading non-marker garbage is transparent to the following frame.

    The frame decodes to exactly what it would on its own, whatever that is.
    """
    if HEADER_START_MARKER in prefix:
        return  # a marker in the "garbage" would start a different frame

    baseline = [type(x).__name__ for x in drain(ClientFramer(), frame)]
    prefixed = [type(x).__name__ for x in drain(ClientFramer(), prefix + frame)]
    assert prefixed == baseline


# --- encode/decode round-trip (fuzzes the codec's register de/serialisation) --

# Serials are 10-char alphanumeric on the wire; fuzzing them exercises the
# string codec (decode_string / add_string) alongside the register path.
serial = st.text(alphabet=string.ascii_uppercase + string.digits, min_size=10, max_size=10)
register16 = st.integers(min_value=0, max_value=0xFFFF)


@st.composite
def read_register_response(draw) -> ReadHoldingRegistersResponse | ReadInputRegistersResponse:
    cls = draw(st.sampled_from((ReadHoldingRegistersResponse, ReadInputRegistersResponse)))
    values = draw(st.lists(register16, min_size=1, max_size=60))  # protocol caps at 60
    return cls(
        inverter_serial_number=draw(serial),
        data_adapter_serial_number=draw(serial),
        device_address=draw(st.integers(0x00, 0xFF)),
        base_register=draw(register16),
        register_count=len(values),
        register_values=values,
    )


@st.composite
def write_register_response(draw) -> WriteHoldingRegisterResponse:
    return WriteHoldingRegisterResponse(
        inverter_serial_number=draw(serial),
        data_adapter_serial_number=draw(serial),
        device_address=draw(st.integers(0x00, 0xFF)),
        register=draw(register16),
        value=draw(register16),
    )


@_SETTINGS
@given(pdu=read_register_response())
def test_read_response_encode_decode_round_trips(pdu):
    """Any register response survives encode → decode intact (codec fidelity).

    This drives ``decode_16bit_uint`` over arbitrary payloads — the layer where a
    signedness or offset slip in the register decoders would surface.
    """
    decoded = ClientIncomingMessage.decode_bytes(pdu.encode())
    assert type(decoded) is type(pdu)
    assert decoded.register_values == pdu.register_values
    assert decoded.base_register == pdu.base_register
    assert decoded.register_count == pdu.register_count
    assert not decoded.crc_failed  # the CRC we wrote must validate on the way back
    assert decoded.encode() == pdu.encode()  # byte-level idempotence


@_SETTINGS
@given(pdu=write_register_response())
def test_write_response_encode_decode_round_trips(pdu):
    """A single-register write echo survives encode → decode intact."""
    decoded = ClientIncomingMessage.decode_bytes(pdu.encode())
    assert type(decoded) is type(pdu)
    assert decoded.register == pdu.register
    assert decoded.value == pdu.value
    assert decoded.encode() == pdu.encode()
