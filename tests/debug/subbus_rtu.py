"""Decoder for the GivEnergy battery **sub-bus** (RS485) Modbus-RTU variant.

This is a DIFFERENT protocol from the TCP transparent framing the library speaks: it is the
raw conversation on the RS485 daisy-chain between a pack (acting as local master) and the
pack(s) behind it, captured off a serial-to-TCP bridge. Reverse-engineered 2026-07-12 from a
live tap on a two-pack loft install; see project_subbus_splice_corruption memory.

Framing (all CRC-16/MODBUS, poly 0xA001, init 0xFFFF), quirks and all:

- **Request** (master->pack, read holding): ``[addr:1][0x03][start:2 BE][count:2 BE][crc:2 BE]``
- **Write**   (master->pack, single):       ``[addr:1][0x06][reg:2 BE][value:2 BE][crc:2 BE]``
- **Response** (pack->master):              ``[addr:1][0x03][bytelen:2 BE][data:bytelen][crc:2 LE]``

Note the CRC byte order differs by direction: requests/writes append the CRC **big-endian**,
responses **little-endian** (standard RTU order). Every real frame validates under that rule,
so we CRC-drive the parse: a byte run that matches no valid frame is emitted as ``Garbage`` —
which is how a spliced/corrupt sub-bus frame surfaces (the whole point of the exercise).
"""

from __future__ import annotations

from dataclasses import dataclass, field

_SERIAL_LEN = 20  # response payload bytes 0..19 = ASCII pack serial (reg 0-9), space-padded


def crc16(data: bytes) -> int:
    """CRC-16/MODBUS (poly 0xA001, init 0xFFFF). Returns the 16-bit value; caller picks byte order."""
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def _crc_ok(body: bytes, trailer: bytes, *, big_endian: bool) -> bool:
    c = crc16(body)
    hi, lo = c >> 8, c & 0xFF
    return (trailer[0], trailer[1]) == ((hi, lo) if big_endian else (lo, hi))


@dataclass(frozen=True)
class Request:
    addr: int
    start: int
    count: int


@dataclass(frozen=True)
class Write:
    addr: int
    reg: int
    value: int


@dataclass(frozen=True)
class Response:
    addr: int
    payload: bytes  # the ``bytelen`` register bytes (no header/CRC)

    @property
    def serial(self) -> str:
        """ASCII pack serial from payload reg 0-9 (space-padded on the wire)."""
        return self.payload[:_SERIAL_LEN].decode("ascii", "replace").rstrip()

    @property
    def cell_mv(self) -> list[int]:
        """The per-cell millivolt values: the longest run of adjacent, *tightly-clustered* uint16-BE.

        Two wrinkles the naive band-filter trips on: (1) the cell block sits at an ODD byte offset
        in the payload (a 1-byte field precedes it — the alignment quirk), while temps are
        even-aligned, so we scan both parities; (2) config regs (3600) and temps (~2970) fall in
        the LiFePO4 band too, so we cut the run on a voltage step — balanced cells sit within a few
        mV of each other, a jump of >150 mV ends the block. Returns [] if no run of >= 8 is found.
        """
        best: list[int] = []
        for parity in (0, 1):
            run: list[int] = []
            off = _SERIAL_LEN + parity
            while off <= len(self.payload) - 2:
                v = (self.payload[off] << 8) | self.payload[off + 1]
                in_band = 2500 <= v <= 3650
                if in_band and (not run or abs(v - run[-1]) <= 150):
                    run.append(v)
                else:
                    if len(run) > len(best):
                        best = run
                    run = [v] if in_band else []
                off += 2
            if len(run) > len(best):
                best = run
        return best if len(best) >= 8 else []


@dataclass(frozen=True)
class Garbage:
    """A byte run that matched no valid-CRC frame — an inter-frame gap or a corrupt/spliced frame."""

    raw: bytes


Frame = Request | Write | Response | Garbage


def _try_frame(s: bytes, pos: int) -> tuple[Request | Write | Response | None, int]:
    """Try to read one valid-CRC frame at ``pos``. Returns (frame, bytes_consumed) or (None, 0)."""
    n = len(s)
    if pos + 4 > n:
        return None, 0
    addr, func = s[pos], s[pos + 1]
    # read request (8 bytes, BE CRC)
    if func == 0x03 and pos + 8 <= n and _crc_ok(s[pos : pos + 6], s[pos + 6 : pos + 8], big_endian=True):
        return Request(addr, (s[pos + 2] << 8) | s[pos + 3], (s[pos + 4] << 8) | s[pos + 5]), 8
    # write (8 bytes, BE CRC)
    if func == 0x06 and pos + 8 <= n and _crc_ok(s[pos : pos + 6], s[pos + 6 : pos + 8], big_endian=True):
        return Write(addr, (s[pos + 2] << 8) | s[pos + 3], (s[pos + 4] << 8) | s[pos + 5]), 8
    # response (addr, func, 2-byte length, data, LE CRC)
    if func == 0x03:
        ln = (s[pos + 2] << 8) | s[pos + 3]
        end = pos + 4 + ln
        if 0 < ln <= 512 and end + 2 <= n and _crc_ok(s[pos:end], s[end : end + 2], big_endian=False):
            return Response(addr, bytes(s[pos + 4 : end])), 4 + ln + 2
    return None, 0


def parse(stream: bytes) -> list[Frame]:
    """CRC-drive the byte stream into frames, coalescing unmatched bytes into ``Garbage`` runs."""
    frames: list[Frame] = []
    pos = 0
    garbage = bytearray()
    while pos < len(stream):
        frame, consumed = _try_frame(stream, pos)
        if frame is not None:
            if garbage:
                frames.append(Garbage(bytes(garbage)))
                garbage = bytearray()
            frames.append(frame)
            pos += consumed
        else:
            garbage.append(stream[pos])
            pos += 1
    if garbage:
        frames.append(Garbage(bytes(garbage)))
    return frames


def redact(stream: bytes, placeholder: str = "XX0000A000") -> bytes:
    """Return a copy with every response's ASCII pack serial replaced and its (LE) CRC recomputed.

    For producing committable fixtures — the raw capture carries the real pack serial in every
    response frame. Requests/writes carry no serial and pass through untouched.
    """
    out = bytearray(stream)
    pos = 0
    filler = placeholder.encode("ascii")[:_SERIAL_LEN].ljust(_SERIAL_LEN, b" ")
    while pos < len(out):
        frame, consumed = _try_frame(bytes(out), pos)
        if isinstance(frame, Response):
            body_start = pos + 4
            out[body_start : body_start + _SERIAL_LEN] = filler
            end = body_start + len(frame.payload)
            c = crc16(bytes(out[pos:end]))
            out[end], out[end + 1] = c & 0xFF, c >> 8  # LE
            pos += consumed
        elif frame is not None:
            pos += consumed
        else:
            pos += 1
    return bytes(out)


@dataclass
class Cycle:
    """One poll round: who was polled, who replied, what was written."""

    polled: list[int] = field(default_factory=list)
    replied: dict[int, Response] = field(default_factory=dict)
    writes: list[Write] = field(default_factory=list)
    garbage: int = 0


def cycles(frames: list[Frame]) -> list[Cycle]:
    """Group frames into poll rounds (a new cycle starts when a previously-polled addr is polled again)."""
    rounds: list[Cycle] = []
    cur = Cycle()
    for f in frames:
        if isinstance(f, Request):
            if f.addr in cur.polled:
                rounds.append(cur)
                cur = Cycle()
            cur.polled.append(f.addr)
        elif isinstance(f, Response):
            cur.replied[f.addr] = f
        elif isinstance(f, Write):
            cur.writes.append(f)
        else:
            cur.garbage += 1
    rounds.append(cur)
    return rounds


# Fixed tails that uniquely identify a master frame regardless of its (possibly mangled) address:
# a read-60 request ends ``03 00 00 00 3c``; the keepalive write ends ``06 00 06 05 05``.
_MASTER_TAILS = (bytes.fromhex("030000003c"), bytes.fromhex("0600060505"))


def write_stats(frames: list[Frame]) -> dict[tuple[int, int], int]:
    """Tally writes by ``(reg, value)``.

    A single key ``(6, 0x0505)`` = a fixed keepalive token; any drift in the value means the
    write carries command/state, not just a heartbeat.
    """
    counts: dict[tuple[int, int], int] = {}
    for f in frames:
        if isinstance(f, Write):
            counts[(f.reg, f.value)] = counts.get((f.reg, f.value), 0) + 1
    return counts


@dataclass(frozen=True)
class GarbageDiag:
    """Diagnosis of a CRC-fail (``Garbage``) run.

    Is it a mangled response, and does it carry a master-frame pattern embedded mid-run — the
    half-duplex collision signature (a request/write transmitted on top of an in-flight response)?
    """

    length: int
    looks_like_response: bool  # starts [addr][0x03][0x00][len>=8] — a response header shape
    embedded_master_at: int | None  # byte offset of a master-frame tail found *inside* the run


def diagnose_garbage(g: Garbage) -> GarbageDiag:
    raw = g.raw
    looks_resp = len(raw) >= 4 and raw[1] == 0x03 and raw[2] == 0x00 and raw[3] >= 8
    embedded: int | None = None
    for tail in _MASTER_TAILS:
        idx = raw.find(tail)
        if idx > 0:  # >0, not at offset 0: a master frame sitting *inside* the run, not leading it
            embedded = idx
            break
    return GarbageDiag(len(raw), looks_resp, embedded)


def _summary(frames: list[Frame]) -> str:
    lines: list[str] = []

    ws = write_stats(frames)
    if ws:
        pretty = ", ".join(f"r{r}=0x{v:04x} x{n}" for (r, v), n in sorted(ws.items()))
        drift = " *** VALUE DRIFT ***" if len({v for (_r, v) in ws}) > 1 else " (fixed token)"
        lines.append(f"writes: {pretty}{drift}")

    garbage = [f for f in frames if isinstance(f, Garbage)]
    if garbage:
        lines.append(f"CRC-fail runs: {len(garbage)}")
        for g in garbage:
            d = diagnose_garbage(g)
            tag = "  <-- COLLISION (master frame embedded in a response)" if d.embedded_master_at is not None else ""
            shape = "mangled-response" if d.looks_like_response else "fragment"
            lines.append(f"  {d.length}B {shape}{tag}")

    for i, c in enumerate(cycles(frames)):
        parts = [f"cycle {i:>4}", f"polled={sorted(set(c.polled))}"]
        for addr, r in sorted(c.replied.items()):
            cv = r.cell_mv
            span = f"{min(cv)}-{max(cv)}mV Δ{max(cv) - min(cv)}" if cv else "no-cells"
            parts.append(f"reply[{addr}]={r.serial}:{len(cv)}c {span}")
        if c.writes:
            parts.append("writes=" + ",".join(f"{w.addr}:r{w.reg}=0x{w.value:04x}" for w in c.writes))
        if c.garbage:
            parts.append(f"*** CRC-FAIL x{c.garbage} ***")  # candidate splice/corruption
        lines.append("  ".join(parts))
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    raw = open(sys.argv[1], "rb").read() if len(sys.argv) > 1 else sys.stdin.buffer.read()
    print(_summary(parse(raw)))
