#!/usr/bin/env python3
"""Read-only diagnostic: what register range does each battery device actually serve?

WHY THIS EXISTS
---------------
We poll batteries over a small, fixed set of banks that were established by
observation. There are indications that battery controllers serve additional
register blocks well above the range we read, but we have no map of them, and
guessing at addresses one bank at a time is slow and inconclusive.

A device tells us more than we currently use. A single-register read comes back
in exactly one of three ways:

  data       the address is served
  exception  the address is not served, and the device says so
  no reply   nothing came back - either not served, or the request never arrived

If a device error-responds for unserved addresses, the served ranges can be mapped
precisely by sweeping and bisecting. If it stays silent instead, the same mapping is
still possible but slower, since every negative costs a full timeout. If it answers
everything with zeros, no probe can discriminate at all - that failure has been seen
before (hass#295, where a range answered with zeros rather than error-responding).

So this script does NOT sweep by default. It runs the smallest test that establishes
which of those three regimes a given system is in, before anyone spends minutes
sweeping.

WHAT IT DOES
------------
Per candidate device address, four probes:

  1. HR(0, 60)      baseline: does this address answer a normal block read at all?
  2. HR(0, 1)       is a single-register count accepted? (the library normally reads 60)
  3. HR(0x486, 1)   a candidate address above the range we currently poll
  4. HR(0x8000, 1)  far above anything plausible - expected to be unserved

Verdict:
  - (3) data and (4) exception  -> mapping by sweep + bisection is viable
  - (4) data                    -> zeros substituted; no probe can discriminate
  - both silent                 -> re-run with --sweep to find the served extent

NO WRITES WHATSOEVER - every request is a read, and reading an unserved address is a
no-op: the device either declines it or ignores it, and nothing changes either way.

    uv run python tests/debug/probe_bms_register_map.py <inverter-host> [addr ...] [--sweep]

With no addresses given it tries the LV battery range plus the HV BCU/BMU bases.
Addresses are hex, e.g. ``0x32``.

Note that on systems where the inverter presents a facade for the battery controllers,
this characterises the facade rather than the controller behind it - which is itself
worth knowing, and shows up as a narrow served window.
"""

from __future__ import annotations

import asyncio
import sys

from givenergy_modbus.client.client import Client
from givenergy_modbus.pdu import ReadHoldingRegistersRequest

# LV packs 0x32-0x37, LV BCU 0x31, HV BMU 0x50+, HV BCU 0x70+ (see model/plant.py,
# model/hv_bcu.py). Kept short so an unattended run stays quick.
DEFAULT_ADDRS = [0x32, 0x33, 0x34, 0x31, 0x50, 0x70]

ATTEMPTS = 3
TIMEOUT = 3.0

# Candidate addresses above the banks we currently poll.
ANCHOR_MAPPED = 0x0486  # plausibly served, well above the polled range
ANCHOR_UNMAPPED = 0x8000  # far above anything plausible

OK, ERR, DEAD = "data", "exception", "no-reply"


async def probe(
    client: Client, addr: int, base: int, count: int, attempts: int = ATTEMPTS, timeout: float = TIMEOUT
) -> str:
    """Classify one read as OK (data), ERR (Modbus exception) or DEAD (no reply).

    Retries only the no-reply case: contention from GivTCP or the phone app shows up
    as a timeout and would otherwise masquerade as a meaningful negative. An exception
    response is a definitive answer and is returned immediately.
    """
    for _ in range(attempts):
        try:
            resp = await client.send_request_and_await_response(
                ReadHoldingRegistersRequest(base_register=base, register_count=count, device_address=addr),
                timeout=timeout,
                retries=1,
                warn_timeout=False,
            )
        except TimeoutError:
            await asyncio.sleep(0.4)
            continue
        return ERR if getattr(resp, "error", False) else OK
    return DEAD


def verdict(baseline: str, single: str, mapped: str, unmapped: str) -> str:
    """Turn the four probe results into a go/no-go call."""
    if baseline == DEAD:
        return "ABSENT      - no reply to a normal block read; nothing here (or busy)"
    if single == DEAD:
        return "NO-GO       - single-register reads unsupported; a sweep would need block reads"
    if unmapped == OK:
        return "NO-GO       - unmapped address returned DATA, so exceptions are not relayed (hass#295 mode)"
    if mapped == OK and unmapped == ERR:
        return "GO          - oracle holds: mapped=data, unmapped=exception. Sweeping is viable."
    if mapped == ERR and unmapped == ERR:
        return "INCONCLUSIVE- both addresses error; 0x486 may not be served by this device"
    if mapped == DEAD and unmapped == DEAD:
        # Observed in the field: low registers answer, high ones are met with silence
        # rather than an exception. Either the device serves a narrower range and stays
        # quiet outside it, or something upstream drops out-of-range requests before the
        # device ever sees them. Distinguish with --sweep, which finds the cutoff.
        return "INAPPLICABLE- both anchors silent; run --sweep to find the served range"
    return "INCONCLUSIVE- mixed result, see columns"


async def sweep(client: Client, addr: int, limit: int = 0x900, step: int = 0x20) -> None:
    """Map which single registers answer at ``addr``, to locate the served extent.

    Run when the anchors both come back silent. A clean cutoff at a round boundary
    points at something upstream filtering out-of-range requests; a ragged edge, or
    islands of replies further out, points at the device genuinely serving several
    disjoint blocks, i.e. a real device-side map rather than a round-number cap.
    """
    # Two passes. The first is deliberately light (1 attempt, 1.5s) because silence
    # dominates a sweep and patient retries everywhere would push this past ten minutes.
    # The second re-probes only the addresses either side of a transition, at full
    # patience, so a stray timeout under contention cannot invent a false edge.
    bases = list(range(0, limit + 1, step))
    print(
        f"\nsweep 0x{addr:02x}: HR(n,1) for n in 0..0x{limit:X} step 0x{step:X} "
        f"({len(bases)} probes, ~{len(bases) * 2}s)"
    )
    results: dict[int, str] = {}
    for base in bases:
        results[base] = await probe(client, addr, base, 1, attempts=1, timeout=1.5)
        await asyncio.sleep(0.1)

    edges = [i for i in range(1, len(bases)) if results[bases[i]] != results[bases[i - 1]]]
    if edges:
        print(f"  confirming {len(edges) * 2} addresses either side of {len(edges)} transition(s)...")
    for i in edges:
        for b in (bases[i - 1], bases[i]):
            results[b] = await probe(client, addr, b, 1, attempts=3, timeout=3.0)

    runs: list[tuple[int, int, str]] = []
    for base in bases:
        r = results[base]
        if runs and runs[-1][2] == r:
            runs[-1] = (runs[-1][0], base, r)
        else:
            runs.append((base, base, r))
    for lo, hi, r in runs:
        mark = "  <-- answers" if r == OK else ("  <-- EXCEPTION (usable oracle!)" if r == ERR else "")
        print(f"  0x{lo:04X}-0x{hi:04X}  {r}{mark}")

    # Bisect each step-granularity transition down to the exact register. ~5 probes per
    # edge, so this is nearly free next to the sweep itself, and it turns "somewhere in
    # a 32-register window" into a number worth quoting.
    for i in edges:
        lo, hi = bases[i - 1], bases[i]
        lo_state, hi_state = results[lo], results[hi]
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if await probe(client, addr, mid, 1, attempts=2, timeout=3.0) == lo_state:
                lo = mid
            else:
                hi = mid
        print(f"  edge: last {lo_state} at {lo} (0x{lo:04X}), first {hi_state} at {hi} (0x{hi:04X})")

    if any(r == ERR for _, _, r in runs):
        print("\n  At least one range error-responds, so exceptions DO survive the round trip.")
    else:
        print(
            "\n  No exception anywhere: this stack answers or stays silent, never errors.\n"
            "  Exception-based probing is therefore out - but a sharp, reproducible\n"
            "  reply/silence edge is itself a usable oracle, just slower (every negative\n"
            "  costs a full timeout rather than an immediate error response)."
        )


async def main(host: str, addrs: list[int], do_sweep: bool = False) -> None:
    client = Client(host, 8899)
    await client.connect()
    try:
        print(f"probing {host}:8899 - READ ONLY, {ATTEMPTS} attempts per probe, {TIMEOUT}s timeout\n")
        print(f"{'addr':>5}  {'HR(0,60)':>9}  {'HR(0,1)':>9}  {'HR(0x486,1)':>12}  {'HR(0x8000,1)':>13}  verdict")
        for addr in addrs:
            baseline = await probe(client, addr, 0, 60)
            if baseline == DEAD:
                print(f"  0x{addr:02x}  {baseline:>9}  {'-':>9}  {'-':>12}  {'-':>13}  {verdict(baseline, '', '', '')}")
                continue
            single = await probe(client, addr, 0, 1)
            mapped = await probe(client, addr, ANCHOR_MAPPED, 1)
            unmapped = await probe(client, addr, ANCHOR_UNMAPPED, 1)
            print(
                f"  0x{addr:02x}  {baseline:>9}  {single:>9}  {mapped:>12}  {unmapped:>13}  "
                f"{verdict(baseline, single, mapped, unmapped)}"
            )
        print(
            "\nReading the result:\n"
            "  GO           -> the block boundaries can be recovered by sweep + bisection.\n"
            "  NO-GO (data) -> the stack swallows exceptions; no readability probe can\n"
            "                  discriminate, so this line of enquiry stops here.\n"
            "  ABSENT       -> try other device addresses, or the battery is not on this bus.\n"
            "  INAPPLICABLE -> anchors silent; re-run with --sweep <addr> to map the served range."
        )
        if do_sweep:
            for addr in addrs:
                if await probe(client, addr, 0, 60) != DEAD:
                    await sweep(client, addr)
                    break
    finally:
        await client.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__.rstrip().rsplit("\n\n", 1)[-1], file=sys.stderr)
        raise SystemExit(2)
    args = [a for a in sys.argv[2:] if a != "--sweep"]
    given = [int(a, 16) for a in args] or DEFAULT_ADDRS
    asyncio.run(main(sys.argv[1], given, do_sweep="--sweep" in sys.argv))
