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

# The thresholds and the transition classifier are the production constants from the #256
# splice guard — imported here so this corpus tool re-validates separation against the very
# same rules the live guard enforces (no drift). See that module for the threshold rationale.
from givenergy_modbus.model.battery_splice import BANK_BASE, classify_transition
from givenergy_modbus.pdu import ReadInputRegistersResponse

CAPTURE_LINE = re.compile(r"^(\S+) (rx|tx) ([0-9a-f]+)")
BATTERY_DEVICES = range(0x32, 0x38)


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


def bonkers(
    regs: list[int], prev: list[int]
) -> tuple[list[tuple[int, str, int, int]], list[tuple[int, str, int, int]]]:
    """Return (physics trips, immutable violations) for one transition.

    Thin compatibility alias over ``battery_splice.classify_transition`` — note the arg
    order flips (``regs`` is the *current* frame, ``prev`` the previous), so the underlying
    call is ``classify_transition(prev, regs)``. Each entry is
    (register number, class name, previous raw, new raw).
    """
    return classify_transition(prev, regs)


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
                print(
                    f"{Path(fname).name} {ts} device=0x{pdu.device_address:02x}: "
                    f"{len(phys)} physics + {len(immut)} immutable"
                )
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
