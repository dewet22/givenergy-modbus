r"""Scan capture logs for un-redacted GivEnergy serials before committing them (#375/#378).

The FrameRedactor auto-redacts serials at *known* register locations (anything modelled as
C.serial → _get_serial_groups). This is the belt-and-braces net for the case it structurally
can't cover: a serial at an as-yet-undiscovered location, or one stored SPLIT across
non-contiguous registers (module 0x55 on the 3ph HV stack, #378 — 'HY' at IR110, the
'…G705' tail at IR115-118, which the contiguous-group redactor misses).

It's a DETECTOR, not a redactor — run it on a fresh capture before committing. It flags three
shapes carrying non-zero unit digits (redacted serials end in the …000 placeholder, so those
are ignored):
  - full GE serial:       [A-Z]{2}\\d{4}[A-Z]\\d{3}         (e.g. HY2336G705)
  - prefixless tail:      \\d{4}[A-Z]\\d{3}                  (the split-serial fragment)
  - NUL-interrupted:      [A-Z]{2}[\\d\\x00]{4}[A-Z]\\d{3}    (Gateway write-response envelopes
    carry a serial variant with NUL bytes replacing part of the date — both patterns above
    structurally miss it; first seen on the 2026-07-09 write-path capture)

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
# NUL-interrupted serial variant: some Gateway write-response envelopes replace part of the
# date digits with NUL bytes (e.g. prefix + \x00\x00 + partial date + unit digits), which
# breaks both patterns above while the live unit digits ride through untouched.
_NUL_INTERRUPTED = re.compile(rb"[A-Z]{2}[\d\x00]{4}[A-Z]\d{3}")


def _frame_bytes(path: Path) -> bytes:
    """Concatenate the hex payloads of a capture's rx/tx lines (both cli and HA formats)."""
    chunks: list[bytes] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.replace(":", " ").split()
        # Direction token sits at parts[0] (HA `rx: <hex>`) or parts[-2] (cli `<ts> rx <hex>`);
        # the hex payload is always the last token.
        if len(parts) >= 2 and (parts[0] in ("rx", "tx") or parts[-2] in ("rx", "tx")):
            try:
                chunks.append(bytes.fromhex(parts[-1]))
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
    # NUL-interrupted variants, minus clean full-serial matches (the pattern is a superset).
    nul_hits = {
        m.group()
        for m in _NUL_INTERRUPTED.finditer(data)
        if not m.group().endswith(b"000") and b"\x00" in m.group()
    }
    return (
        [f"full serial {s.decode()}" for s in sorted(full)]
        + [f"prefixless tail {s.decode()}" for s in sorted(tails)]
        + [f"NUL-interrupted serial {s.decode('latin1')!r}" for s in sorted(nul_hits)]
    )


def main() -> int:
    """Scan the given capture files (or the committed corpus) and report leaks."""
    args = sys.argv[1:]
    if args:
        paths = [Path(a) for a in args]
    else:
        paths = sorted(_CAPTURES.rglob("*.log")) + sorted(_CAPTURES.rglob("*.txt"))

    missing = [p for p in paths if not p.is_file()]
    for p in missing:
        print(f"WARN  {p}: not found")
    paths = [p for p in paths if p.is_file()]
    if not paths:
        print("no capture files to scan — check the path(s).")
        return 2

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
