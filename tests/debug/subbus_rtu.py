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
_PACK_LEN = 120  # a full pack response payload is 120 bytes (60 registers)


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


def _u16(p: bytes, o: int) -> int:
    return (p[o] << 8) | p[o + 1]


def _u32(p: bytes, o: int) -> int:
    return (p[o] << 24) | (p[o + 1] << 16) | (p[o + 2] << 8) | p[o + 3]


def _deci_kelvin_c(v: int) -> float:
    """Sub-bus temps are deci-Kelvin (the inverter converts to deci-degC before the TCP layer)."""
    return round(v / 10 - 273.15, 1)


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
        """The 16 per-cell millivolt values, at the confirmed offset 79 (16 x uint16-BE)."""
        p = self.payload
        return [_u16(p, 79 + 2 * i) for i in range(16)] if len(p) >= _PACK_LEN else []


@dataclass(frozen=True)
class PackState:
    """Fully-decoded pack telemetry from a response payload — the confirmed sub-bus register map.

    Layout ground-truthed against a live capture (20/20 fields) AND cross-checked against GivTCP's
    independent read of the same pack (stable values — cycles, capacities, firmware — matched to the
    digit). All fields are big-endian at their payload byte offset; the cell block sits at odd offset
    79 because the 1-byte cell_count at offset 42 shifts everything after it. Temps are deci-Kelvin.
    """

    serial: str
    cell_count: int
    cycles: int
    soc_pct: int
    pack_mv: int  # pack terminal voltage, mV
    cell_sum_mv: int  # sum of cell voltages, mV
    calibrated_cah: int  # calibrated capacity, centi-Ah (0.01 Ah)
    design_cah: int  # design capacity, centi-Ah
    remaining_cah: int  # remaining capacity, centi-Ah
    firmware: int
    mosfet_temp_c: float
    group_temps_c: tuple[float, ...]  # 4 cell-group temperatures
    max_group_temp_c: float
    min_group_temp_c: float
    cells_mv: tuple[int, ...]  # 16 per-cell voltages, mV
    max_cell_mv: int
    min_cell_mv: int
    status_flags: int  # offset 32, role TBC (was mislabelled "USB device")
    status: int  # offset 119, trailing status byte


def decode_pack(resp: Response) -> PackState | None:
    """Decode a response payload into full pack telemetry, or None if it's too short (truncated)."""
    p = resp.payload
    if len(p) < _PACK_LEN:
        return None
    return PackState(
        serial=resp.serial,
        group_temps_c=tuple(_deci_kelvin_c(_u16(p, o)) for o in (22, 24, 26, 28)),
        mosfet_temp_c=_deci_kelvin_c(_u16(p, 30)),
        status_flags=_u16(p, 32),
        cell_count=p[42],
        cycles=_u16(p, 43),
        pack_mv=_u16(p, 47),
        cell_sum_mv=_u16(p, 49),
        calibrated_cah=_u32(p, 55),
        design_cah=_u32(p, 59),
        remaining_cah=_u32(p, 63),
        soc_pct=p[67],
        firmware=_u16(p, 77),
        cells_mv=tuple(_u16(p, 79 + 2 * i) for i in range(16)),
        max_group_temp_c=_deci_kelvin_c(_u16(p, 111)),
        min_group_temp_c=_deci_kelvin_c(_u16(p, 113)),
        max_cell_mv=_u16(p, 115),
        min_cell_mv=_u16(p, 117),
        status=p[119],
    )


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
            ps = decode_pack(r)
            if ps is None:
                parts.append(f"reply[{addr}]=TRUNCATED")
            else:
                parts.append(
                    f"reply[{addr}]={ps.serial} soc={ps.soc_pct}% "
                    f"{ps.min_cell_mv}-{ps.max_cell_mv}mV Δ{ps.max_cell_mv - ps.min_cell_mv} "
                    f"mosfet={ps.mosfet_temp_c}C cyc={ps.cycles}"
                )
        if c.writes:
            parts.append("writes=" + ",".join(f"{w.addr}:r{w.reg}=0x{w.value:04x}" for w in c.writes))
        if c.garbage:
            parts.append(f"*** CRC-FAIL x{c.garbage} ***")  # candidate splice/corruption
        lines.append("  ".join(parts))
    return "\n".join(lines)


def _bytes_needed(buf: bytes) -> int:
    """How many bytes a candidate frame at offset 0 needs before we can accept-or-reject it."""
    if len(buf) < 4:
        return 4
    if buf[1] == 0x03:
        ln = (buf[2] << 8) | buf[3]
        if 0 < ln <= 512:
            return 4 + ln + 2  # a response: header + declared data + CRC
    return 8  # request/write, or a non-response fn-3 — an 8-byte frame


def stream_frames(read_chunk):
    """Incrementally parse a live byte stream; ``read_chunk()`` returns bytes (``b''`` on EOF).

    Yields Request/Write/Response/Garbage as soon as each is unambiguous. A response is held until
    its full declared length has arrived, so a frame split across a read boundary is never mistaken
    for corruption — only genuinely unparseable bytes surface as Garbage.
    """
    buf = bytearray()
    while True:
        chunk = read_chunk()
        if not chunk:
            break
        buf += chunk
        while buf:
            frame, consumed = _try_frame(bytes(buf), 0)
            if frame is not None:
                yield frame
                del buf[:consumed]
                continue
            if len(buf) >= _bytes_needed(bytes(buf)):
                yield Garbage(bytes(buf[:1]))
                del buf[:1]
                continue
            break  # incomplete frame still arriving — wait for more
    if buf:
        yield Garbage(bytes(buf))


def _live_line(frame: Frame, seen_writes: set) -> str | None:
    import time

    ts = time.strftime("%H:%M:%S")
    if isinstance(frame, Response):
        ps = decode_pack(frame)
        if ps is None:
            return f"{ts}  pack{frame.addr}  TRUNCATED response"
        return (
            f"{ts}  pack{frame.addr} {ps.serial}  SoC {ps.soc_pct}%  "
            f"cells {ps.min_cell_mv}-{ps.max_cell_mv} (Δ{ps.max_cell_mv - ps.min_cell_mv})  "
            f"mosfet {ps.mosfet_temp_c}C  cyc {ps.cycles}"
        )
    if isinstance(frame, Write):
        key = (frame.reg, frame.value)
        if key not in seen_writes:
            seen_writes.add(key)
            return f"{ts}  write addr{frame.addr} reg{frame.reg}=0x{frame.value:04x}  <-- NEW VALUE"
        return None  # suppress the repeat keepalive
    if isinstance(frame, Garbage):
        d = diagnose_garbage(frame)
        if d.length <= 3 and not d.looks_like_response:
            return None  # inter-frame noise
        tag = "  <-- COLLISION (master frame in a response)" if d.embedded_master_at is not None else ""
        shape = "mangled-response" if d.looks_like_response else "fragment"
        return f"{ts}  !!! CRC-FAIL {d.length}B {shape}{tag}"
    return None  # requests: silent


def monitor(host: str, port: int, raw_path: str | None = None) -> None:
    """Live-monitor the sub-bus socket, decoding frames as they arrive and reconnecting on drop.

    Prints each pack read, a NEW-VALUE line when a write value drifts, and a loud CRC-FAIL/COLLISION
    line on corruption. With ``raw_path`` set, every received byte is also appended there for offline
    analysis (raw contains real serials — keep it private).
    """
    import socket
    import time

    raw = open(raw_path, "ab") if raw_path else None  # noqa: SIM115 — long-lived append handle
    seen_writes: set = set()
    while True:
        sock = None
        try:
            sock = socket.create_connection((host, port), timeout=30)
            print(f"{time.strftime('%H:%M:%S')}  connected {host}:{port}", flush=True)

            def read_chunk() -> bytes:
                b = sock.recv(4096)
                if b and raw:
                    raw.write(b)
                    raw.flush()
                return b

            for frame in stream_frames(read_chunk):
                line = _live_line(frame, seen_writes)
                if line:
                    print(line, flush=True)
            print(f"{time.strftime('%H:%M:%S')}  stream ended; reconnecting", flush=True)
        except OSError as e:
            print(f"{time.strftime('%H:%M:%S')}  disconnected: {e}; retry in 2s", flush=True)
        finally:
            if sock is not None:
                sock.close()
        time.sleep(2)


if __name__ == "__main__":
    import argparse
    import sys

    ap = argparse.ArgumentParser(description="GivEnergy battery sub-bus RTU decoder")
    ap.add_argument("file", nargs="?", help="capture file to summarise (omit to read stdin)")
    ap.add_argument("--monitor", metavar="HOST:PORT", help="live-monitor a socket, e.g. 192.168.46.177:8899")
    ap.add_argument("--raw", metavar="FILE", help="with --monitor, also append raw bytes here for offline analysis")
    args = ap.parse_args()

    if args.monitor:
        host, _, port = args.monitor.partition(":")
        monitor(host, int(port or 8899), args.raw)
    else:
        data = open(args.file, "rb").read() if args.file else sys.stdin.buffer.read()
        print(_summary(parse(data)))
