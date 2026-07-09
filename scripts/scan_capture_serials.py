r"""Scan capture logs for un-redacted GivEnergy serials before committing them (#375/#378).

The FrameRedactor auto-redacts serials at *known* register locations (anything modelled as
C.serial → _get_serial_groups). This is the belt-and-braces net for the case it structurally
can't cover: a serial at an as-yet-undiscovered location, or one stored SPLIT across
non-contiguous registers (module 0x55 on the 3ph HV stack, #378 — 'HY' at IR110, the
'…G705' tail at IR115-118, which the contiguous-group redactor misses).

It's a DETECTOR, not a redactor — run it on a fresh capture before committing. It flags two
shapes carrying non-zero unit digits (redacted serials end in the …000 placeholder, so those
are ignored):
  - full GE serial:      [A-Z]{2}\\d{4}[A-Z]\\d{3}   (e.g. HY2336G705)
  - prefixless tail:     \\d{4}[A-Z]\\d{3}            (the split-serial fragment)

A hit means: redact it (hand-zero the unit digits through the library encoder, and where the
location is contiguous, model the register as C.serial so it auto-redacts thereafter), then
re-scan. Exits non-zero if any real serial is found.

    uv run python scripts/scan_capture_serials.py <capture.log> [more...]
    uv run python scripts/scan_capture_serials.py            # scans the committed corpus
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_CAPTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "captures"

_FULL = re.compile(rb"[A-Z]{2}\d{4}[A-Z]\d{3}")
_TAIL = re.compile(rb"\d{4}[A-Z]\d{3}")


def _frame_bytes(path: Path) -> bytes:
    """Concatenate the hex payloads of a capture's rx/tx lines (both cli and HA formats)."""
    chunks: list[bytes] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.replace(":", " ").split()
        if len(parts) >= 2 and parts[-2] in ("rx", "tx"):
            token = parts[-1]
        elif len(parts) >= 2 and parts[0] in ("rx", "tx"):
            token = parts[-1]
        else:
            continue
        try:
            chunks.append(bytes.fromhex(token))
        except ValueError:
            continue
    return b"".join(chunks)


def scan(path: Path) -> list[str]:
    """Return descriptions of any serial-shaped ASCII with non-zero unit digits."""
    data = _frame_bytes(path)
    full = {m.group() for m in _FULL.finditer(data) if not m.group().endswith(b"000")}
    # Prefixless tails, minus any that are just the tail of a full serial already reported.
    tails = {
        m.group()
        for m in _TAIL.finditer(data)
        if not m.group().endswith(b"000") and not any(m.group() in f for f in full)
    }
    return [f"full serial {s.decode()}" for s in sorted(full)] + [
        f"prefixless tail {s.decode()}" for s in sorted(tails)
    ]


def main() -> int:
    """Scan the given capture files (or the committed corpus) and report leaks."""
    args = sys.argv[1:]
    if args:
        paths = [Path(a) for a in args]
    else:
        paths = sorted(_CAPTURES.rglob("*.log")) + sorted(_CAPTURES.rglob("*.txt"))

    total = 0
    for p in paths:
        hits = scan(p)
        if hits:
            total += len(hits)
            print(f"LEAK  {p}:")
            for h in hits:
                print(f"        {h}")
        else:
            print(f"clean {p}")
    if total:
        print(f"\n{total} un-redacted serial(s) found — redact before committing.")
        return 1
    print("\nno un-redacted serials found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
