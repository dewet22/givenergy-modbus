#!/usr/bin/env python3
"""Regenerate CRCs in committed wire-capture fixtures (#158 B-3).

The committed .log fixtures have stale CRC bytes: the serial digits were zeroed
at capture time by the original byte-level redactor, but the trailing check field
was never recomputed. After the item-1 unified CRC fix, `encode()` now produces
correct CRCs — so a decode→re-encode round-trip produces the right bytes.

This script applies that round-trip to every decodable frame in every committed
fixture, rewriting only the last two bytes (the check field) where they differ.
Frames that can't be decoded are left untouched. Serial content is NOT changed —
the policy documented in tests/fixtures/captures/README.md is that fixture bytes
stay exactly as they came off the wire.

Usage:
    uv run python scripts/regen_fixture_crcs.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

CAPTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "captures"
FRAME_MARKER = bytes.fromhex("59590001")


def regen_file(path: Path, *, dry_run: bool) -> tuple[int, int]:
    """Rewrite `path` in place with CRCs recomputed. Return (updated, skipped)."""
    from givenergy_modbus.pdu import ClientIncomingMessage

    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    new_lines: list[str] = []
    updated = skipped = 0
    for line in lines:
        parts = line.rstrip("\n").split(maxsplit=2)
        if len(parts) < 3:
            new_lines.append(line)
            continue
        ts, direction, hex_payload = parts[0], parts[1], parts[2]
        try:
            frame = bytes.fromhex(hex_payload)
        except ValueError:
            new_lines.append(line)
            continue
        if frame[:4] != FRAME_MARKER:
            new_lines.append(line)
            continue
        try:
            pdu = ClientIncomingMessage.decode_bytes(frame)
            re_enc = pdu.encode()
        except Exception:
            skipped += 1
            new_lines.append(line)
            continue
        if re_enc != frame:
            updated += 1
            new_lines.append(f"{ts} {direction} {re_enc.hex()}\n")
        else:
            new_lines.append(line)
    if updated and not dry_run:
        path.write_text("".join(new_lines), encoding="utf-8")
    return updated, skipped


def main() -> int:
    """Recompute and rewrite CRCs across all committed capture fixtures."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="report changes without writing")
    args = ap.parse_args()
    total_updated = total_skipped = 0
    for log in sorted(CAPTURES.rglob("*.log")):
        updated, skipped = regen_file(log, dry_run=args.dry_run)
        rel = log.relative_to(CAPTURES.parent.parent)
        if updated or skipped:
            tag = " [DRY RUN]" if args.dry_run else ""
            print(f"{rel}: {updated} CRCs updated, {skipped} frames skipped{tag}")
        total_updated += updated
        total_skipped += skipped
    print(f"\nTotal: {total_updated} CRCs updated, {total_skipped} frames skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
