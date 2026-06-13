#!/usr/bin/env python3
r"""Scan wire captures for battery sub-bus splice/slip corruption — #147.

Field evidence (givenergy-hass, 2026-06-12, modbus 2.3.1) identified the
mechanism behind valid-CRC battery garbage: corruption on the battery
sub-bus side of the dongle, re-framed with a fresh (valid) CRC. The wire
CRC is computed by the dongle over already-corrupt payload, so #255's CRC
guard structurally cannot catch it.

Corpus analysis sharpened the shape: it is a *windowed splice*, not a
tail-to-end byte slip. A short window of the payload is overwritten with a
byte-shifted copy of data from elsewhere in the frame (observed donor: the
temperature block), while bytes before and after the window are intact.
E.g. ``cap_remaining`` raw ``0xED00`` = pack temp 23.7 °C (``0x00ED``)
donating its low byte as the garbage value's high byte — the distinctive
``0xXX00`` quantisation seen in the field.

Distinct from (and also reported here): *sustained temp-group zeros* —
IR(76-79) reading exactly 0 for several consecutive polls while cells stay
live, then recovering. Multi-poll persistence means the BMS itself returned
zeros (device-origin), not per-frame transport corruption; cross-pack
clustering within the same wall-clock window implicates the shared sub-bus
path. A different failure needing different handling (sub-group
hold-last-good rather than frame rejection).

The scanner replays capture files, watching LV battery banks (devices
0x32-0x37, IR(60,120)) for:

1. transient ``cap_remaining`` garbage — low byte 0x00 with a large jump
   vs the previous poll (the splice fingerprint);
2. temp-group all-zero runs (reported with run length: single-poll =
   possibly splice, sustained = device-origin);
3. a cell voltage of exactly 3.600 V (0x0E10) while pack-mates sit
   elsewhere — likely the status word IR(91) (persistently 0x0E10 on
   observed packs) spliced into a cell slot, not a real voltage.

For frames flagged with (1) or (3) it extracts the changed-byte window vs
the previous poll and searches the frame for a byte-shifted donor region
matching the spliced content.

Usage::

    uv run python tests/debug/byte_slip_scan.py tests/fixtures/captures/*/*.log

Capture files are ``givenergy-cli capture`` ``.log`` output
(``<ts> rx|tx <hex>``).
"""

from __future__ import annotations

import argparse
import asyncio
import re
import statistics
import sys
from pathlib import Path

from givenergy_modbus.framer import ClientFramer
from givenergy_modbus.pdu import ReadInputRegistersResponse

CAPTURE_LINE = re.compile(r"^(\S+) (rx|tx) ([0-9a-f]+)")

# LV battery banks live at 0x32-0x37 and serve IR(60,120). Other addresses
# carry other register maps (meters at 0x01/0x03, AIO internals at 0x50+);
# decoding those as Battery yields false positives.
BATTERY_DEVICES = range(0x32, 0x38)
BANK_BASE = 60

# Offsets within the IR(60,120) bank (index = register - 60).
CELLS = range(0, 16)  # IR(60-75)
TEMP_GROUPS = range(16, 20)  # IR(76-79)
CAP_REMAINING = (28, 29)  # IR(88/89) uint32, centi-Ah

# A splice writes garbage quantised to 0xXX00; flag cap_remaining excursions
# beyond this many centi-Ah vs the previous poll (50 Ah — far beyond any real
# inter-poll drift, far below observed garbage jumps of 400+ Ah).
CAP_JUMP_CENTI_AH = 5_000


def load_rx_frames(paths: list[Path]) -> list[tuple[str, str, bytes]]:
    """Read all rx frames from the given capture files: (file key, ts, raw).

    The file key is the full path string — distinct captures sharing a
    basename must not share per-file tracker state.
    """
    entries: list[tuple[str, str, bytes]] = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = CAPTURE_LINE.match(line.strip())
                if not m or m.group(2) != "rx":
                    continue
                try:
                    raw = bytes.fromhex(m.group(3))
                except ValueError:
                    continue
                entries.append((str(path), m.group(1), raw))
    return entries


def find_splice_window(suspect: list[int], prev: list[int]) -> tuple[int, int] | None:
    """Return (first, last) changed-byte offsets vs the previous poll, or None."""
    sus = b"".join(v.to_bytes(2, "big") for v in suspect)
    ref = b"".join(v.to_bytes(2, "big") for v in prev)
    changed = [i for i, (a, b) in enumerate(zip(sus, ref)) if a != b]
    if not changed:
        return None
    return changed[0], changed[-1]


def find_donor(suspect: list[int], window: tuple[int, int]) -> str | None:
    """Search the frame for a byte-shifted region matching the spliced window.

    The observed splice copies a byte-shifted slice of the same frame (e.g.
    the temperature block) over the window. Finding such a donor elsewhere in
    the frame is the smoking gun that the garbage is recycled frame content.
    """
    sus = b"".join(v.to_bytes(2, "big") for v in suspect)
    lo, hi = window
    needle = sus[lo : hi + 1]
    if len(needle) < 3:
        return None
    for start in range(0, len(sus) - len(needle) + 1):
        if start == lo:
            continue
        if sus[start : start + len(needle)] == needle:
            reg_lo, reg_hi = BANK_BASE + start // 2, BANK_BASE + (start + len(needle)) // 2
            return f"window is a copy of bytes at IR({reg_lo})-IR({reg_hi}) (offset {start - lo:+d})"
    # tolerate one mismatched byte (live values drift between donor and splice)
    for start in range(0, len(sus) - len(needle) + 1):
        if start == lo:
            continue
        region = sus[start : start + len(needle)]
        if sum(1 for a, b in zip(region, needle) if a != b) <= 1:
            reg_lo, reg_hi = BANK_BASE + start // 2, BANK_BASE + (start + len(needle)) // 2
            return f"window ~matches bytes at IR({reg_lo})-IR({reg_hi}) (offset {start - lo:+d}, 1 byte drift)"
    return None


class BankTracker:
    """Per-(file, device) state for one battery bank's poll sequence."""

    def __init__(self) -> None:
        self.prev: list[int] | None = None
        self.zero_run_start: str | None = None
        self.zero_run_len = 0

    def temp_zero_step(self, ts: str, zero: bool) -> tuple[str, int] | None:
        """Track temp-zero runs; returns (start_ts, length) when a run ends."""
        if zero:
            if self.zero_run_start is None:
                self.zero_run_start = ts
            self.zero_run_len += 1
            return None
        if self.zero_run_start is not None:
            run = (self.zero_run_start, self.zero_run_len)
            self.zero_run_start = None
            self.zero_run_len = 0
            return run
        return None


def flush_open_zero_runs(trackers: dict[tuple[str, int], BankTracker]) -> None:
    """Report zero-runs still open when their capture ends.

    A sustained failure occupying the tail of a capture must not vanish from
    the analysis just because no recovery poll followed it.
    """
    for (fname, device), tracker in trackers.items():
        if tracker.zero_run_start is not None:
            kind = "single-poll (splice?)" if tracker.zero_run_len == 1 else "sustained (device-origin)"
            print(f"{Path(fname).name} {tracker.zero_run_start} device=0x{device:02x}")
            print(f"  - temp group all-zero x{tracker.zero_run_len} polls — {kind}; still open at end of capture")


async def scan(paths: list[Path]) -> int:
    framer = ClientFramer()
    frames = load_rx_frames(paths)
    trackers: dict[tuple[str, int], BankTracker] = {}
    bank_count = 0
    flagged = 0

    for fname, ts, raw in frames:
        async for pdu in framer.decode(raw):
            if not isinstance(pdu, ReadInputRegistersResponse):
                continue
            if pdu.device_address not in BATTERY_DEVICES or pdu.base_register != BANK_BASE:
                continue
            regs = list(pdu.register_values)
            if len(regs) < 60 or all(r == 0 for r in regs):
                continue  # absent battery slot
            bank_count += 1
            key = (fname, pdu.device_address)
            tracker = trackers.setdefault(key, BankTracker())
            label = Path(fname).name
            dev = f"device=0x{pdu.device_address:02x}"
            hits: list[str] = []

            # 1. transient cap_remaining garbage
            cap = (regs[CAP_REMAINING[0]] << 16) | regs[CAP_REMAINING[1]]
            if tracker.prev is not None:
                prev_cap = (tracker.prev[CAP_REMAINING[0]] << 16) | tracker.prev[CAP_REMAINING[1]]
                if abs(cap - prev_cap) > CAP_JUMP_CENTI_AH and (cap & 0xFF) == 0:
                    hits.append(
                        f"cap_remaining jump {prev_cap / 100:.2f} -> {cap / 100:.2f} Ah "
                        f"(raw 0x{cap:08X}, 0xXX00-quantised)"
                    )

            # 2. temp-group zero runs
            cells = [regs[i] for i in CELLS]
            nonzero_cells = [c for c in cells if c]
            temp_zero = bool(nonzero_cells) and all(regs[i] == 0 for i in TEMP_GROUPS)
            run = tracker.temp_zero_step(ts, temp_zero)
            if run:
                start, length = run
                kind = "single-poll (splice?)" if length == 1 else "sustained (device-origin)"
                print(f"{label} {start} {dev}")
                print(f"  - temp group all-zero x{length} polls — {kind}")

            # 3. cell pinned at exactly 0x0E10
            if len(nonzero_cells) >= 4:
                med = statistics.median(nonzero_cells)
                for i, c in enumerate(cells):
                    if c == 0x0E10 and abs(med - c) > 150:
                        hits.append(f"cell_{i + 1:02d}=3.600V exactly (median {med / 1000:.3f}V) — status-word splice?")

            if hits:
                flagged += 1
                print(f"{label} {ts} {dev}")
                for h in hits:
                    print(f"  - {h}")
                if tracker.prev is not None:
                    window = find_splice_window(regs, tracker.prev)
                    if window:
                        lo, hi = window
                        print(
                            f"  changed window: bytes {lo}-{hi} (IR({BANK_BASE + lo // 2})-IR({BANK_BASE + hi // 2}))"
                        )
                        donor = find_donor(regs, window)
                        if donor:
                            print(f"  donor: {donor}")

            if not hits and not temp_zero:
                tracker.prev = regs

    flush_open_zero_runs(trackers)

    print(
        f"\n{len(frames)} rx frames, {bank_count} battery IR({BANK_BASE},60) banks, {flagged} splice-flagged",
        file=sys.stderr,
    )
    return flagged


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("captures", nargs="+", type=Path)
    args = parser.parse_args()
    flagged = asyncio.run(scan(args.captures))
    sys.exit(1 if flagged else 0)


if __name__ == "__main__":
    main()
