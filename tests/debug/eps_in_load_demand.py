#!/usr/bin/env python3
r"""Does IR(42) p_load_demand include the EPS branch IR(31) p_backup?

Offline analysis answering a givenergy-cli question: is the EPS/backup branch
(IR31 p_backup) *inside* the busbar house-load reading (IR42 p_load_demand), or
*additional* to it?

Method — the AC-busbar residual already noted on the IR(42) Def docstring
("empirically NOT a derived IR(24)-IR(30) identity; residual non-zero in 68% of
samples"). At the inverter AC terminal:

    IR24 (inverter AC out, +ve = delivering)  -  IR30 (grid CT, +ve = export)
        = total AC load drawn off the busbar

If IR42 already accounts for the EPS-protected load, that total equals IR42 and

    r := (IR24 - IR30) - IR42  ~= 0.

If EPS is a *separate* AC output not folded into IR42, the missing power is the
EPS branch and

    r ~= IR31  (p_backup).

So the discriminator is simply: across samples, is |r| small (EPS included), or
is |r - IR31| << |r| with r tracking IR31 (EPS additional)?  We report both, plus
a whole-busbar source/sink cross-check.

CAVEATS (read before trusting the number):
  * Register identities assumed: IR24=p_grid_out_ph1 (inverter terminal, NOT the
    external CT), IR30=p_grid_out (external CT), IR42=p_load_demand, IR31=p_backup,
    IR18/20=p_pv1/2, IR52=p_battery (+discharge/-charge). All raw watts; IR24/30/52
    are int16 (sign-extended here), the rest uint16.
  * The maintainer's HYBRID_GEN1 shows a near-constant ~286 W p_backup — likely a
    standing EPS-output overhead rather than variable protected load. If r tracks
    that constant, "additional" is the cleaner reading; if r is noisy around 0,
    inclusion is more likely. Conversion losses (a few %) and CT-vs-terminal node
    mismatch put real noise on r regardless.
  * Only inverter banks (device 0x11 / 0x31) are scanned; battery banks reuse the
    same IR numbers with a different layout and must not be decoded here.

Usage:
    uv run python tests/debug/eps_in_load_demand.py \
        --capture tests/fixtures/captures/hybrid_2_bat_a tests/fixtures/captures/aio_a
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
from pathlib import Path

from givenergy_modbus.exceptions import ExceptionBase
from givenergy_modbus.framer import ClientFramer
from givenergy_modbus.model.plant import Plant
from givenergy_modbus.model.register import IR
from givenergy_modbus.pdu import ReadInputRegistersResponse, TransparentResponse
from givenergy_modbus.pdu.base import BasePDU

# Reuse the capture loader from the #82 replay harness.
from tests.debug.replay import expand_capture_args, load_rx_frames

INVERTER_ADDRESSES = {0x11, 0x31}
# Power registers, all within the IR(0,60) bank.
R_PV1, R_PV2, R_GRID_TERM, R_GRID_CT, R_BACKUP, R_LOAD, R_BATTERY = (
    IR(18),
    IR(20),
    IR(24),
    IR(30),
    IR(31),
    IR(42),
    IR(52),
)


def _i16(v: int) -> int:
    """Sign-extend a raw 16-bit register value."""
    return v - 65536 if v > 32767 else v


def _sample(cache) -> dict[str, int] | None:
    """Read the seven power registers from a cache; None if any is missing."""
    raw = {r: cache.get(r) for r in (R_PV1, R_PV2, R_GRID_TERM, R_GRID_CT, R_BACKUP, R_LOAD, R_BATTERY)}
    if any(v is None for v in raw.values()):
        return None
    return {
        "pv": raw[R_PV1] + raw[R_PV2],
        "grid_term": _i16(raw[R_GRID_TERM]),  # IR24 inverter AC terminal
        "grid_ct": _i16(raw[R_GRID_CT]),  # IR30 external CT, +export/-import
        "backup": raw[R_BACKUP],  # IR31 EPS
        "load": raw[R_LOAD],  # IR42 house load
        "battery": _i16(raw[R_BATTERY]),  # IR52 +discharge/-charge
    }


async def collect(frames: list[tuple[str, bytes]]) -> dict[int, list[dict[str, int]]]:
    """Replay frames; snapshot inverter power registers after each IR(0,60) commit."""
    framer = ClientFramer()
    plant = Plant()
    by_addr: dict[int, list[dict[str, int]]] = {}
    last: dict[int, tuple] = {}

    for _ts, raw in frames:
        try:
            decoded: list[BasePDU | ExceptionBase] = [pdu async for pdu in framer.decode(raw)]
        except Exception:  # noqa: BLE001  # nosec B112 — malformed frame, skip (expected: captures carry undecodable frames)
            continue
        for pdu in decoded:
            if isinstance(pdu, ExceptionBase) or not isinstance(pdu, TransparentResponse) or pdu.error:
                continue
            if not isinstance(pdu, ReadInputRegistersResponse):
                continue
            addr = pdu.device_address
            if addr not in INVERTER_ADDRESSES or pdu.base_register != 0:
                continue
            plant.update(pdu)
            cache = plant.register_caches.get(addr)
            if cache is None:
                continue
            s = _sample(cache)
            if s is None:
                continue
            # Dedupe identical consecutive snapshots (fan-out repeats the same bank).
            key = tuple(sorted(s.items()))
            if last.get(addr) == key:
                continue
            last[addr] = key
            by_addr.setdefault(addr, []).append(s)
    return by_addr


def _summary(name: str, vals: list[float]) -> str:
    if not vals:
        return f"  {name}: (no samples)"
    return (
        f"  {name}: n={len(vals)} mean={statistics.mean(vals):+.0f} "
        f"median={statistics.median(vals):+.0f} "
        f"min={min(vals):+.0f} max={max(vals):+.0f}"
    )


def report(by_addr: dict[int, list[dict[str, int]]]) -> None:
    for addr, samples in sorted(by_addr.items()):
        eps_active = [s for s in samples if s["backup"] > 0]
        print(f"\n=== device 0x{addr:02x}: {len(samples)} samples, {len(eps_active)} with EPS active ===")
        if not eps_active:
            print("  EPS never active (p_backup == 0) — not informative for this question.")
            continue
        backup = [s["backup"] for s in eps_active]
        # r = (IR24 - IR30) - IR42 : the existing 68%-residual quantity.
        r = [(s["grid_term"] - s["grid_ct"]) - s["load"] for s in eps_active]
        # If EPS is additional, r ~= backup, so r - backup ~= 0.
        r_minus_backup = [ri - bi for ri, bi in zip(r, backup, strict=True)]
        print(_summary("p_backup (IR31, W)", [float(b) for b in backup]))
        print(_summary("residual r = (IR24-IR30)-IR42", [float(x) for x in r]))
        print(_summary("r - p_backup  (~0 => EPS additional)", [float(x) for x in r_minus_backup]))
        # Verdict heuristic: compare typical |r| against |r - backup|.
        med_abs_r = statistics.median([abs(x) for x in r])
        med_abs_r_mb = statistics.median([abs(x) for x in r_minus_backup])
        print(f"  median|r|={med_abs_r:.0f}  median|r-backup|={med_abs_r_mb:.0f}")
        if med_abs_r_mb < med_abs_r * 0.5:
            print("  -> leans EPS ADDITIONAL (IR42 EXCLUDES p_backup; r tracks IR31).")
        elif med_abs_r < med_abs_r_mb * 0.5:
            print("  -> leans EPS INCLUDED (IR42 already accounts for EPS; r ~ 0).")
        else:
            print("  -> INCONCLUSIVE (residual not cleanly explained by IR31 either way).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Test whether IR42 p_load_demand includes IR31 p_backup (EPS).")
    parser.add_argument("--capture", required=True, nargs="+", help="Capture files, globs, or directories.")
    args = parser.parse_args(argv)

    paths: list[Path] = expand_capture_args(args.capture)
    if not paths:
        print("no capture files to read", file=sys.stderr)
        return 1
    print(f"Loading {len(paths)} capture file(s)...", file=sys.stderr)
    frames = load_rx_frames(paths)
    print(f"Loaded {len(frames):,} rx frames. Analysing...", file=sys.stderr)

    by_addr = asyncio.run(collect(frames))
    report(by_addr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
