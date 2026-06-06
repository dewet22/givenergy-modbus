#!/usr/bin/env python3
r"""Find unsolicited (fan-out / broadcast) responses in a wire capture — #196.

A GivEnergy dongle fans out the responses to *whoever* is polling it — the GE
cloud, the vendor app, another TCP client — to every connected client. So a
library client sees a continuous stream of register responses it never
requested. This harness quantifies that stream: it pairs each received
``TransparentResponse`` to a preceding ``TransparentRequest`` using the
library's own ``shape_hash`` matching (the same logic
``Client._task_network_consumer`` uses to resolve futures), and reports the
responses that match no request — i.e. the dongle volunteered them.

Why it matters for #196: if the live blocks (``IR(0,60)`` etc.) arrive reliably
unsolicited, then a slow *solicited* read is not necessarily a failure — the
cache may already have been refreshed by a fan-out frame. The cadence/jitter
figures show how reliable that stream is, and whether it differs by dongle
generation (the open Gen3 question).

Note on interpretation: a *passive* capture (no ``tx`` lines) trivially reports
every response as unsolicited — there were no requests to match. Only a capture
that contains the client's own ``tx`` requests proves fan-out coexists with
solicited traffic. The cadence figures are meaningful either way.

Usage::

    uv run python tests/debug/unsolicited_responses.py CAPTURE.log [CAPTURE2.log ...]

Capture files are ``givenergy-cli capture`` ``.log`` output (``<ts> rx|tx <hex>``).
"""

from __future__ import annotations

import sys
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path

from givenergy_modbus.pdu import (
    ClientIncomingMessage,
    ServerIncomingMessage,  # = ClientOutgoingMessage; decodes tx frames as requests
    TransparentRequest,
    TransparentResponse,
)
from givenergy_modbus.pdu.heartbeat import HeartbeatRequest, HeartbeatResponse

_MARKER = bytes.fromhex("59590001")


def _decode(raw: bytes, direction: str) -> object:
    """Decode a frame with the direction-appropriate base class (tx=request, rx=response)."""
    cls = ServerIncomingMessage if direction == "tx" else ClientIncomingMessage
    try:
        return cls.decode_bytes(raw)
    except Exception as e:  # noqa: BLE001 — untrusted capture bytes; report, don't crash
        return e


def _frames(path: str | Path):
    """Yield (ts, direction, raw_frame) from a capture, splitting chunks on the MBAP marker."""
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[1] not in ("tx", "rx"):
            continue
        try:
            ts = datetime.fromisoformat(parts[0])
            buf = bytes.fromhex(parts[-1])
        except ValueError:
            continue
        i, n = 0, len(buf)
        while i + 6 <= n:
            if buf[i : i + 4] != _MARKER:
                i += 1
                continue
            flen = 6 + int.from_bytes(buf[i + 4 : i + 6], "big")
            if flen < 18 or i + flen > n:
                break
            yield ts, parts[1], buf[i : i + flen]
            i += flen


def _shape_key(pdu: object) -> str:
    fc = getattr(pdu, "transparent_function_code", None)
    dev = getattr(pdu, "device_address", None)
    base = getattr(pdu, "base_register", None)
    cnt = getattr(pdu, "register_count", None)
    dev_s = f"0x{dev:02x}" if isinstance(dev, int) else dev
    fc_s = f"0x{fc:02x}" if isinstance(fc, int) else fc
    return f"{type(pdu).__name__} dev={dev_s} fc={fc_s} base={base} count={cnt}"


def analyse(paths: list[str]) -> None:
    events = sorted((e for p in paths for e in _frames(p)), key=lambda e: e[0])

    pending: dict[int, deque[datetime]] = defaultdict(deque)  # shape_hash -> unanswered request times
    unsolicited: dict[str, list[datetime]] = defaultdict(list)
    solicited = requests = hb_in = hb_out = decode_errors = 0

    for ts, direction, raw in events:
        pdu = _decode(raw, direction)
        if isinstance(pdu, HeartbeatRequest):
            hb_in += 1
        elif isinstance(pdu, HeartbeatResponse):
            hb_out += 1
        elif isinstance(pdu, TransparentRequest):
            requests += 1
            try:
                pending[pdu.expected_response().shape_hash()].append(ts)
            except Exception:  # noqa: BLE001  # nosec B110 — malformed request; skip silently
                pass
        elif isinstance(pdu, TransparentResponse):
            h = pdu.shape_hash()
            if pending[h]:
                pending[h].popleft()
                solicited += 1
            else:
                unsolicited[_shape_key(pdu)].append(ts)
        elif isinstance(pdu, Exception):
            decode_errors += 1

    unanswered = sum(len(q) for q in pending.values())
    total_unsol = sum(len(v) for v in unsolicited.values())

    print(f"events={len(events)}  requests(tx)={requests}  responses(rx)={solicited + total_unsol}")
    print(f"heartbeats: in={hb_in} out={hb_out}  decode_errors={decode_errors}")
    print(f"solicited (matched a prior request) = {solicited}")
    print(f"unanswered requests                 = {unanswered}")
    print(f"UNSOLICITED (no prior request)      = {total_unsol}")
    print()
    for key, tss in sorted(unsolicited.items(), key=lambda kv: -len(kv[1])):
        tss.sort()
        cadence = ""
        if len(tss) >= 2:
            deltas = [(b - a).total_seconds() for a, b in zip(tss, tss[1:])]
            cadence = f"  cadence: min={min(deltas):.2f}s avg={sum(deltas) / len(deltas):.2f}s max={max(deltas):.2f}s"
        print(f"  [{len(tss):5d}x] {key}{cadence}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    analyse(sys.argv[1:])
