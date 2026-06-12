#!/usr/bin/env python3
r"""Classify battery-bank frame transitions by physics-impossible deltas — #256.

Companion to ``byte_slip_scan.py`` (which fingerprints the known splice
shapes); this tool is the generic classifier that produced the corpus
numbers grounding #256's detection design: across 1,103 consecutive-frame
transitions, 1,086 were clean and 17 corruption-related, with zero false
trips — every corruption event trips >=2 physically independent registers or
changes a normally-constant one, and the only physics-singleton in the
corpus (a MOSFET temperature stepping 6.3 degC in one poll) is genuine.

For every consecutive pair of polls of an LV battery bank (devices
0x32-0x37, IR(60,120)) it counts registers whose per-poll movement exceeds
a per-register-class physics threshold — set at roughly 10x what the
quantity can really do in a ~30 s poll interval:

- cell voltages barely move between polls (thermal/electrochemical inertia);
- cell-mass temperatures drift, the junction-adjacent MOSFET sensor steps
  (hence its much wider threshold);
- capacities move with charge current (~0.5 Ah/poll at LV power levels);
- status/bitfield words carry no physics and are exempt (IR(91) legitimately
  toggles 0x0E10 <-> 0x0610 every few minutes);
- ``num_cells``, ``bms_firmware_version`` and the serial block are constant —
  ANY transient change is corruption on its own.

Transitions are reported with their trip count and the offending registers;
a transient splice shows up twice (onset + recovery).

Usage::

    uv run python tests/debug/physics_delta_classify.py tests/fixtures/captures/*/*.log

Capture files are ``givenergy-cli capture`` ``.log`` output
(``<ts> rx|tx <hex>``).
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from collections import Counter
from pathlib import Path

from givenergy_modbus.framer import ClientFramer
from givenergy_modbus.pdu import ReadInputRegistersResponse

CAPTURE_LINE = re.compile(r"^(\S+) (rx|tx) ([0-9a-f]+)")
BATTERY_DEVICES = range(0x32, 0x38)
BANK_BASE = 60

# (class name, indices within the bank, threshold on |delta| in raw units).
# Indices are register - 60. Thresholds ~10x the real per-poll maximum.
SCALAR_RULES = [
    ("cell_mV", list(range(0, 16)), 100),  # cells: ~10 mV/poll real max
    ("cell_temp_deci", [16, 17, 18, 19, 43, 44], 50),  # IR(76-79,103,104): thermal mass
    ("mosfet_temp_deci", [21], 200),  # IR(81): junction-adjacent, steps with load
    ("v_cells_sum_mV", [20], 1600),
    ("soc_pct", [40], 10),
    ("e_total_deci", [45, 46], 50),  # IR(105/106) lifetime energy
]
# uint32 pairs: (class name, (high index, low index), threshold on pair value).
PAIR_RULES = [
    ("v_out_mV", (22, 23), 2000),
    ("cap_centiAh", (24, 25), 1000),  # cap_calibrated
    ("cap_centiAh", (26, 27), 1000),  # cap_design
    ("cap_centiAh", (28, 29), 1000),  # cap_remaining
    ("cap_centiAh", (41, 42), 1000),  # cap_design2
]
# num_cells, bms_firmware_version, serial block + trailing constant IR(115).
IMMUTABLE = [37, 38, *range(50, 56)]
# Exempt (no physics): status/warning words IR(90-94), i_battery IR(95),
# num_cycles IR(96), unknown/reserved IR(99,107-109,116-119).


def load_rx_frames(paths: list[Path]) -> list[tuple[str, str, bytes]]:
    """Read all rx frames from the given capture files: (file, ts, raw)."""
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
                entries.append((path.name, m.group(1), raw))
    return entries


def bonkers(
    regs: list[int], prev: list[int]
) -> tuple[list[tuple[int, str, int, int]], list[tuple[int, str, int, int]]]:
    """Return (physics trips, immutable violations) for one transition.

    Each entry is (register number, class name, previous raw, new raw).
    """
    phys, immut = [], []
    for name, idxs, thr in SCALAR_RULES:
        for i in idxs:
            if abs(regs[i] - prev[i]) > thr:
                phys.append((i + BANK_BASE, name, prev[i], regs[i]))
    for name, (h, lo), thr in PAIR_RULES:
        a, b = (regs[h] << 16) | regs[lo], (prev[h] << 16) | prev[lo]
        if abs(a - b) > thr:
            phys.append((h + BANK_BASE, name, b, a))
    for i in IMMUTABLE:
        if regs[i] != prev[i]:
            immut.append((i + BANK_BASE, "IMMUTABLE", prev[i], regs[i]))
    return phys, immut


async def classify(paths: list[Path]) -> int:
    framer = ClientFramer()
    prevs: dict[tuple[str, int], list[int]] = {}
    transitions = 0
    counts: Counter[int] = Counter()
    for fname, ts, raw in load_rx_frames(paths):
        async for pdu in framer.decode(raw):
            if (
                not isinstance(pdu, ReadInputRegistersResponse)
                or pdu.device_address not in BATTERY_DEVICES
                or pdu.base_register != BANK_BASE
            ):
                continue
            regs = list(pdu.register_values)
            if len(regs) < 60 or all(r == 0 for r in regs):
                continue  # absent battery slot
            key = (fname, pdu.device_address)
            prev = prevs.get(key)
            prevs[key] = regs
            if prev is None:
                continue
            transitions += 1
            phys, immut = bonkers(regs, prev)
            n = len(phys) + len(immut)
            counts[n] += 1
            if n:
                print(f"{fname} {ts} device=0x{pdu.device_address:02x}: {len(phys)} physics + {len(immut)} immutable")
                for reg, name, a, b in phys + immut:
                    print(f"    IR({reg}) {name}: 0x{a:04X} -> 0x{b:04X}")
    print(
        f"\n{transitions} transitions; trip-count distribution: {dict(sorted(counts.items()))}",
        file=sys.stderr,
    )
    return sum(v for k, v in counts.items() if k)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("captures", nargs="+", type=Path)
    args = parser.parse_args()
    flagged = asyncio.run(classify(args.captures))
    sys.exit(1 if flagged else 0)


if __name__ == "__main__":
    main()
