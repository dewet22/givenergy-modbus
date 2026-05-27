#!/usr/bin/env python3
r"""Offline wire-capture replay harness for #82 corruption investigation.

Replays an existing wire-capture file (as produced by `givenergy-cli capture`)
through a single live ``Plant``, watching for cache writes that produce
out-of-bounds field values. Each OOB event is emitted as a JSONL line on the
configured output stream with full context: timestamp, affected field,
post-conversion value, originating frame's raw bytes.

Discriminates between "wire-delivered" and "library-internal" corruption
hypotheses for #82. See ``tests/debug/README.md`` for the full rationale.

Usage:
    uv run python tests/debug/replay.py \
        --capture ~/git/givenergy-cli/frames-*.log \
        --output replay-events.jsonl

Stats summary is written to stderr at the end of the run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import IO, Any

from givenergy_modbus.exceptions import ExceptionBase
from givenergy_modbus.framer import ClientFramer
from givenergy_modbus.model.plant import Plant
from givenergy_modbus.model.register import HR, IR, Register, RegisterDefinition, RegisterGetter
from givenergy_modbus.pdu import (
    ReadHoldingRegistersResponse,
    ReadInputRegistersResponse,
    TransparentResponse,
)
from givenergy_modbus.pdu.base import BasePDU

CAPTURE_LINE = re.compile(r"^(\S+) (rx|tx) ([0-9a-f]+)")


def load_rx_frames(paths: list[Path]) -> list[tuple[str, bytes]]:
    """Read all rx frames from the given capture files, sorted by timestamp."""
    entries: list[tuple[str, bytes]] = []
    for path in paths:
        with open(path) as f:
            for line in f:
                m = CAPTURE_LINE.match(line.strip())
                if not m or m.group(2) != "rx":
                    continue
                try:
                    raw = bytes.fromhex(m.group(3))
                except ValueError:
                    continue
                entries.append((m.group(1), raw))
    # ISO 8601 strings sort lexicographically as wall clock.
    entries.sort(key=lambda e: e[0])
    return entries


def compute_post_conv_value(defn: RegisterDefinition, raw_regs: list[int]) -> Any:
    """Apply pre_conv + post_conv to raw registers, bypassing bounds suppression.

    Mirrors ``RegisterGetter.get()`` but never returns ``None`` for OOB — we
    want the actual value the library would have produced before the
    post-#82 suppression in ``faad5c4`` was added.
    """
    if defn.pre_conv:
        if isinstance(defn.pre_conv, tuple):
            args = list(raw_regs) + list(defn.pre_conv[1:])
            val = defn.pre_conv[0](*args)
        else:
            val = defn.pre_conv(*raw_regs)
    else:
        val = raw_regs[0] if len(raw_regs) == 1 else raw_regs

    if defn.post_conv:
        if isinstance(defn.post_conv, tuple):
            val = defn.post_conv[0](val, *defn.post_conv[1:])
        else:
            val = defn.post_conv(val)
    return val


def is_oob(val: Any, defn: RegisterDefinition) -> bool:
    """True iff val is outside the field's declared bounds."""
    if val is None:
        return False
    if defn.min_value is not None and val < defn.min_value:
        return True
    if defn.max_value is not None and val > defn.max_value:
        return True
    return False


def affected_field_names(
    getter_cls: type[RegisterGetter],
    pdu_registers: set[Register],
    field_filter: set[str] | None,
) -> Iterator[tuple[str, RegisterDefinition]]:
    """Yield (field_name, defn) for fields whose registers overlap the PDU.

    Restricts the scan to fields that this PDU could have actually changed;
    avoids re-reporting stale OOB values left in the cache from earlier commits.
    """
    for name, defn in getter_cls.REGISTER_LUT.items():
        if defn.min_value is None and defn.max_value is None:
            continue
        if field_filter and name not in field_filter:
            continue
        if not any(r in pdu_registers for r in defn.registers):
            continue
        yield name, defn


def detect_oob_events(
    pdu: TransparentResponse,
    plant: Plant,
    device_address: int,
    field_filter: set[str] | None,
) -> list[dict[str, Any]]:
    """Scan the cache for OOB field values written by this PDU.

    Returns one event dict per OOB field. Empty list if all post-commit
    values for affected fields are in bounds.
    """
    cache = plant.register_caches.get(device_address)
    if cache is None:
        return []
    getter_cls = plant._getter_for_device_address(device_address)
    if getter_cls is None:
        return []

    pdu_registers: set[Register] = set()
    if isinstance(pdu, ReadInputRegistersResponse):
        pdu_registers = {IR(k) for k in pdu.to_dict().keys()}
    elif isinstance(pdu, ReadHoldingRegistersResponse):
        pdu_registers = {HR(k) for k in pdu.to_dict().keys()}
    if not pdu_registers:
        return []

    events: list[dict[str, Any]] = []
    for field_name, defn in affected_field_names(getter_cls, pdu_registers, field_filter):
        raw_regs_maybe = [cache.get(r) for r in defn.registers]
        if any(r is None for r in raw_regs_maybe):
            continue
        # The None-check above narrows the values, but mypy doesn't track that —
        # rebind to a definitely-typed list so the call site stays clean.
        raw_regs: list[int] = [r for r in raw_regs_maybe if r is not None]
        if all(r == 0 for r in raw_regs):
            # Mirrors the get()/validate_bank carve-out for "hardware sentinel"
            # all-zero banks — don't flag those as OOB.
            continue

        val = compute_post_conv_value(defn, raw_regs)
        if not is_oob(val, defn):
            continue

        events.append(
            {
                "field": field_name,
                "registers": [str(r) for r in defn.registers],
                "raw_register_values": raw_regs,
                "post_conv_value": val,
                "min": defn.min_value,
                "max": defn.max_value,
            }
        )
    return events


async def replay(
    frames: list[tuple[str, bytes]],
    field_filter: set[str] | None,
    output: IO[str],
) -> dict[str, int]:
    """Replay frames through a single Plant, emit OOB events as JSONL."""
    framer = ClientFramer()
    plant = Plant()
    stats = {
        "rx_frames": 0,
        "decoded_pdus": 0,
        "committed_pdus": 0,
        "decode_errors": 0,
        "oob_events": 0,
    }

    for ts, raw in frames:
        stats["rx_frames"] += 1
        try:
            decoded: list[BasePDU | ExceptionBase] = []
            async for pdu in framer.decode(raw):
                decoded.append(pdu)
        except Exception as exc:
            stats["decode_errors"] += 1
            print(f"[{ts}] framer error: {exc}", file=sys.stderr)
            continue

        for pdu in decoded:
            if isinstance(pdu, ExceptionBase):
                stats["decode_errors"] += 1
                continue
            stats["decoded_pdus"] += 1
            if not isinstance(pdu, TransparentResponse) or pdu.error:
                continue

            device_address = pdu.device_address
            if device_address in (0x11, 0x00):
                device_address = 0x32

            plant.update(pdu)
            stats["committed_pdus"] += 1

            events = detect_oob_events(pdu, plant, device_address, field_filter)
            for ev in events:
                ev.update(
                    {
                        "ts": ts,
                        "device_address": f"0x{device_address:02x}",
                        "pdu_type": type(pdu).__name__,
                        "pdu_base_register": getattr(pdu, "base_register", None),
                        "pdu_register_count": getattr(pdu, "register_count", None),
                        "raw_frame": (pdu.raw_frame.hex() if getattr(pdu, "raw_frame", None) else None),
                    }
                )
                output.write(json.dumps(ev) + "\n")
                output.flush()
                stats["oob_events"] += 1

    return stats


def expand_capture_args(args: list[str]) -> list[Path]:
    """Resolve --capture args (which may be globs or directories) into Path list."""
    out: list[Path] = []
    for arg in args:
        p = Path(arg)
        if p.is_dir():
            out.extend(sorted(p.glob("*.log")))
        elif p.exists():
            out.append(p)
        else:
            # Treat as a glob pattern relative to cwd.
            matches = sorted(Path().glob(arg))
            if not matches:
                print(f"warning: no files match {arg!r}", file=sys.stderr)
            out.extend(matches)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay wire captures through a Plant, detect OOB cache writes (#82).")
    parser.add_argument(
        "--capture",
        required=True,
        nargs="+",
        help="Capture file paths or globs (e.g. ~/git/givenergy-cli/frames-*.log).",
    )
    parser.add_argument(
        "--fields",
        default=None,
        help="Comma-separated field names to watch (default: every field with declared bounds).",
    )
    parser.add_argument(
        "--output",
        default="-",
        help="Path for JSONL output, or '-' for stdout (default: -).",
    )
    args = parser.parse_args(argv)

    paths = expand_capture_args(args.capture)
    if not paths:
        print("no capture files to read", file=sys.stderr)
        return 1
    field_filter = set(args.fields.split(",")) if args.fields else None

    output: IO[str]
    output_owned = False
    if args.output == "-":
        output = sys.stdout
    else:
        output = open(args.output, "w")
        output_owned = True

    print(
        f"Loading {len(paths)} capture file(s)...",
        file=sys.stderr,
    )
    frames = load_rx_frames(paths)
    print(f"Loaded {len(frames):,} rx frames. Replaying...", file=sys.stderr)

    try:
        stats = asyncio.run(replay(frames, field_filter, output))
    finally:
        if output_owned:
            output.close()

    print("\nReplay stats:", file=sys.stderr)
    for k, v in stats.items():
        print(f"  {k}: {v:,}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
