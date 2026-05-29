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
  digits like ``XX22``. The library-wide ``[A-Z]{2}\d{2,}`` pattern
  needed to catch these would over-match decimal-data-with-letters in
  other frames.

Redaction follows the same policy as the library redactor (see #113):
preserve the family prefix, the YYWW manufacture-date digits (the first
four), and any letters; zero only the trailing unit-identifier digits.
This keeps the script idempotent against the library output — a complete
serial the library already redacted (``CE2242G000``) is left untouched
here rather than having its date re-clobbered.

Same-length substitution, frame offsets preserved.

Usage::

    uv run python tests/fixtures/captures/_redact_extra.py <log_file> [...]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Standard GE-style serial OR a truncation thereof: 2 letters + at least one digit,
# optionally followed by a middle letter and trailing digits. Catches the partial
# fragments left at frame boundaries (observed in the EMS IR(2066..2085) rollup).
GE_SERIAL_PARTIAL = re.compile(rb"[A-Z]{2}\d{2,}(?:[A-Z]\d*)?")


def _preserve_date_zero_unit(match: re.Match[bytes]) -> bytes:
    """Keep letters and the first four (YYWW) digits; zero any digits beyond them.

    Mirrors the library redactor's policy so running this after it is a no-op on
    complete serials and only ever touches genuine fragments. A fragment with four
    or fewer digits is a (partial) date with no unit component, so it is preserved
    intact.
    """
    out = bytearray()
    digits_seen = 0
    for byte in match.group(0):
        if 0x30 <= byte <= 0x39:  # ASCII '0'–'9'
            digits_seen += 1
            out.append(byte if digits_seen <= 4 else 0x30)  # 0x30 == b"0"
        else:
            out.append(byte)
    return bytes(out)


def redact(frame: bytes) -> bytes:
    """Apply the residual-leak substitution to a single frame."""
    return GE_SERIAL_PARTIAL.sub(_preserve_date_zero_unit, frame)


def redact_log_file(path: Path) -> int:
    """Rewrite the log file in place. Return the number of frames changed.

    Redaction is **reassembly-aware, per direction**: payloads are grouped by
    direction (``rx`` / ``tx``), each direction's frames concatenated and
    redacted as one stream, then sliced back to their original per-frame
    lengths.

    A per-line pass would miss a serial split across two frames — the leading
    fragment (``…CE22``) lands in one frame and the unit-bearing continuation
    (``42G612…``) in the next, so neither line on its own presents a serial-
    shaped run. The split is real: it occurs inside the EMS rollup at
    ``IR(2066..2085)`` where consecutive inverter serials straddle a frame
    boundary.

    Reassembly is kept *within* a direction rather than across the whole log.
    A split is only ever contiguous in one direction's stream (responses
    arrive on ``rx``); concatenating both directions in log order would both
    fabricate boundary matches between unrelated rx/tx frames and miss a real
    split whenever an opposite-direction frame is logged between the two
    fragments. Redaction is length-preserving, so re-slicing keeps every
    frame's byte offsets and length fields intact.
    """
    records: list[tuple[str, str, bytes] | str] = []  # parsed frame or verbatim line
    for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
        parts = line.rstrip("\n").split(maxsplit=2)
        if len(parts) < 3:
            records.append(line)
            continue
        ts, direction, hex_payload = parts
        records.append((ts, direction, bytes.fromhex(hex_payload)))

    # One redacted stream per direction, reassembled in log order.
    streams: dict[str, bytes] = {}
    for r in records:
        if not isinstance(r, str):
            streams[r[1]] = streams.get(r[1], b"") + r[2]
    redacted = {direction: redact(blob) for direction, blob in streams.items()}

    new_lines: list[str] = []
    changed = 0
    offsets: dict[str, int] = {}
    for r in records:
        if isinstance(r, str):
            new_lines.append(r)
            continue
        ts, direction, original = r
        off = offsets.get(direction, 0)
        piece = redacted[direction][off : off + len(original)]
        offsets[direction] = off + len(original)
        if piece != original:
            changed += 1
        new_lines.append(f"{ts} {direction} {piece.hex()}\n")
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
