r"""Residual-leak redactor for committed wire captures.

The CLI's frame-level redactor (``givenergy_modbus.client.redact``)
handles standard GE 10-char serials (``XX####X###``), EMS-style
serials (``EMS#######``), and IPv4 dotted-quads — see PR #99.

One residual case isn't covered there because the regex needed to
catch it has too much false-positive risk to codify in a library-wide
redactor:

- **Truncated GE serials at frame boundaries** — wire frames sometimes
  end mid-serial (observed at frame boundaries inside the EMS rollup
  block at ``IR(2066..2085)``), leaving a 2-letter prefix plus partial
  digits like ``XX00``. The library-wide ``[A-Z]{2}\d{2,}`` pattern
  needed to catch these would over-match decimal-data-with-letters in
  other frames.

This script applies the per-fixture cleanup belt-and-braces, idempotent
on already-redacted captures. Same-length substitution, frame offsets
preserved.

Usage::

    uv run python tests/fixtures/captures/_redact_extra.py <log_file> [...]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Standard GE-style serial OR a truncation thereof: 2 letters + at least one digit,
# optionally followed by a middle letter and trailing digits. Catches the partial
# fragments left at frame boundaries like ``XX00`` (observed in ems_30min.log where
# a wire frame ended mid-serial inside the EMS IR(2066..2085) rollup). Zero every
# digit, keep the letters.
GE_SERIAL_PARTIAL = re.compile(rb"[A-Z]{2}\d{2,}(?:[A-Z]\d*)?")


def _zero_digits_keep_letters(match: re.Match[bytes]) -> bytes:
    return re.sub(rb"\d", b"0", match.group(0))


def redact(frame: bytes) -> bytes:
    """Apply the residual-leak substitution to a single frame."""
    return GE_SERIAL_PARTIAL.sub(_zero_digits_keep_letters, frame)


def redact_log_file(path: Path) -> int:
    """Rewrite the log file in place. Return the number of frames changed."""
    changed = 0
    new_lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
        parts = line.rstrip("\n").split(maxsplit=2)
        if len(parts) < 3:
            new_lines.append(line)
            continue
        ts, direction, hex_payload = parts
        original = bytes.fromhex(hex_payload)
        redacted = redact(original)
        if redacted != original:
            changed += 1
        new_lines.append(f"{ts} {direction} {redacted.hex()}\n")
    path.write_text("".join(new_lines), encoding="utf-8")
    return changed


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    total = 0
    for arg in argv:
        path = Path(arg)
        if not path.is_file():
            print(f"skip: {path} (not a file)", file=sys.stderr)
            continue
        n = redact_log_file(path)
        print(f"{path}: redacted {n} frame(s)")
        total += n
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
