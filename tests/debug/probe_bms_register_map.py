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

    uv run python tests/debug/probe_bms_register_map.py <inverter-host> [addr ...] [--sweep] [--selftest]

``--selftest`` first establishes whether an exception response can reach this
script at all, using a read this project's captures record as error-responding.
Run it before trusting any no-reply result.

With no addresses given it tries a sample of the LV battery range (0x32-0x34, 0x31)
plus the HV BCU/BMU bases; pass addresses explicitly to cover 0x35-0x37 as well.
Addresses are hex, e.g. ``0x32``.

Note that on systems where the inverter presents a facade for the battery controllers,
this characterises the facade rather than the controller behind it - which is itself
worth knowing, and shows up as a narrow served window.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime
from typing import Any

from givenergy_modbus.client.client import Client
from givenergy_modbus.model.plant import Plant
from givenergy_modbus.pdu import (
    ClientIncomingMessage,
    ReadHoldingRegistersRequest,
    ReadInputRegistersRequest,
)

# LV packs 0x32-0x37, LV BCU 0x31, HV BMU 0x50+, HV BCU 0x70+ (see model/plant.py,
# model/hv_bcu.py). Kept short so an unattended run stays quick.
DEFAULT_ADDRS = [0x32, 0x33, 0x34, 0x31, 0x50, 0x70]

ATTEMPTS = 3
TIMEOUT = 3.0

# Candidate addresses above the banks we currently poll.
ANCHOR_MAPPED = 0x0486  # plausibly served, well above the polled range
ANCHOR_UNMAPPED = 0x8000  # far above anything plausible

OK, ERR, DEAD = "data", "exception", "no-reply"


class _ErrorResponseWatcher:
    """Observe exception responses, which never reach the caller of the client API.

    Two layers hide them, and both have to be bypassed:

    1. ``send_request_and_await_response`` never returns a response with ``error``
       set - it logs, consumes a retry, and raises ``TimeoutError``. So inspecting
       the returned PDU can never see an exception.

    2. More importantly, an error response usually does not *match* the request it
       answers. A response is routed to its waiting future by shape hash, which is
       ``(device_address, base_register, register_count)`` - and observed error
       responses carry ``register_count=0`` rather than echoing the count asked for
       (see the ``hybrid_2_bat_a`` and ``aio_a`` captures). The hashes differ, the
       future is never resolved, and even the client's own error log never fires.

    ``Plant.update()`` is called for *every* decoded message before any shape
    matching, so wrapping it sees exception responses whichever way they arrive.

    Responses are recorded by ``(device_address, base_register)`` rather than as a
    bare flag: the dongle fans every response out to all connected clients, so an
    exception provoked by GivTCP or the phone app would otherwise be misread as an
    answer to our own probe.
    """

    def __init__(self, plant: Plant) -> None:
        self.errors: set[tuple[int, int, bool]] = set()
        # Patch the class, not the instance: Plant is a pydantic model, and assigning
        # an attribute on the instance raises "object has no field".
        self._cls: type[Plant] = type(plant)
        self._original = self._cls.update

    def install(self) -> None:
        original, errors = self._original, self.errors

        # Signature must mirror Plant.update exactly, or mypy rejects the assignment.
        def wrapped(plant_self: Plant, pdu: ClientIncomingMessage, *, received_at: datetime | None = None) -> Any:
            if getattr(pdu, "error", False):
                addr = getattr(pdu, "device_address", None)
                base = getattr(pdu, "base_register", None)
                if addr is not None and base is not None:
                    is_input = "Input" in type(pdu).__name__
                    errors.add((addr, base, is_input))
            return original(plant_self, pdu, received_at=received_at)

        self._cls.update = wrapped  # type: ignore[assignment]

    def remove(self) -> None:
        self._cls.update = self._original  # type: ignore[assignment]


async def probe(
    client: Client,
    watcher: _ErrorResponseWatcher,
    addr: int,
    base: int,
    count: int,
    attempts: int = ATTEMPTS,
    timeout: float = TIMEOUT,
    input_regs: bool = False,
) -> str:
    """Classify one read as OK (data), ERR (Modbus exception) or DEAD (no reply).

    Retries only the no-reply case: contention from GivTCP or the phone app shows up
    as a timeout and would otherwise masquerade as a meaningful negative.

    ``retries=0`` matters: with retries left the client would re-send after an error
    response, muddying which attempt produced what.
    """
    request_cls = ReadInputRegistersRequest if input_regs else ReadHoldingRegistersRequest
    for _ in range(attempts):
        watcher.errors.discard((addr, base, input_regs))
        try:
            await client.send_request_and_await_response(
                request_cls(base_register=base, register_count=count, device_address=addr),
                timeout=timeout,
                retries=0,
                warn_timeout=False,
            )
        except TimeoutError:
            if (addr, base, input_regs) in watcher.errors:
                return ERR
            await asyncio.sleep(0.4)
            continue
        return OK
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


async def sweep(
    client: Client,
    watcher: _ErrorResponseWatcher,
    addr: int,
    limit: int = 0x900,
    step: int = 0x20,
    input_regs: bool = False,
) -> None:
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
    kind = "IR" if input_regs else "HR"
    print(
        f"\nsweep 0x{addr:02x}: {kind}(n,1) for n in 0..0x{limit:X} step 0x{step:X} "
        f"({len(bases)} probes, ~{len(bases) * 2}s)"
    )
    results: dict[int, str] = {}
    for base in bases:
        results[base] = await probe(client, watcher, addr, base, 1, attempts=1, timeout=1.5, input_regs=input_regs)
        await asyncio.sleep(0.1)

    edges = [i for i in range(1, len(bases)) if results[bases[i]] != results[bases[i - 1]]]
    if edges:
        print(f"  confirming {len(edges) * 2} addresses either side of {len(edges)} transition(s)...")
    for i in edges:
        for b in (bases[i - 1], bases[i]):
            results[b] = await probe(client, watcher, addr, b, 1, attempts=3, timeout=3.0, input_regs=input_regs)
    # Recompute: a confirmation can dissolve an edge (or expose a new one), and
    # bisecting a boundary that no longer exists would print a meaningless result.
    edges = [i for i in range(1, len(bases)) if results[bases[i]] != results[bases[i - 1]]]

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
            if await probe(client, watcher, addr, mid, 1, attempts=2, timeout=3.0, input_regs=input_regs) == lo_state:
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


async def selftest(client: Client, watcher: _ErrorResponseWatcher, addr: int) -> None:
    """Prove whether an exception response can reach this script at all.

    Every negative result so far has been a no-reply, which is ambiguous: it could
    mean the device stays silent, or that the exception is real but something between
    here and the device swallows it. Two fixes aimed at that ambiguity changed
    nothing, so before trusting any further negative, establish the positive case.

    The control comes from this project's own capture corpus rather than a guess. In
    ``hybrid_2_bat_a`` a Gen1 system with two packs answered ``IR(236, 60)`` at 0x32
    with an error response, while ``IR(60, 60)`` at the same address answered
    normally 346 times. If the control errors here, the instrumentation works and a
    no-reply elsewhere is a real silence. If it does not, the negatives mean nothing.
    """
    print(f"\nself-test on 0x{addr:02x}: can an exception response reach this script?")
    checks = [
        ("IR(60,60)   normally answers", 60, 60, True, OK),
        ("IR(236,60)  recorded as error-responding", 236, 60, True, ERR),
        ("IR(0x8000,1) far out of range", 0x8000, 1, True, None),
        ("HR(0x486,1) the anchor under test", ANCHOR_MAPPED, 1, False, None),
    ]
    got: dict[str, str] = {}
    for label, base, count, ir, expect in checks:
        r = await probe(client, watcher, addr, base, count, input_regs=ir)
        got[label] = r
        flag = "" if expect is None else ("  as expected" if r == expect else f"  EXPECTED {expect}")
        print(f"  {label:<42} {r}{flag}")

    control = got["IR(236,60)  recorded as error-responding"]
    print()
    if control == ERR:
        print(
            "  Instrumentation CONFIRMED: an exception response is visible here.\n"
            "  Every no-reply elsewhere is therefore a genuine silence, not a masked\n"
            "  exception, and reply-vs-silence is the only oracle this stack offers."
        )
    elif control == OK:
        print(
            "  Control answered with DATA rather than erroring. The recorded error was\n"
            "  probably transient, so this control cannot settle the question - it needs\n"
            "  an address that reliably errors on this hardware."
        )
    else:
        print(
            "  Control was ALSO silent. Either exceptions never reach this script, or\n"
            "  that recorded error was a one-off. Until a control does error here, no\n"
            "  no-reply result should be read as evidence of anything."
        )


async def main(
    host: str,
    addrs: list[int],
    do_sweep: bool = False,
    do_selftest: bool = False,
    use_ir: bool = False,
) -> None:
    # Expected error responses would otherwise print over the results table. A
    # NullHandler is needed as well as propagate=False: with neither, logging falls
    # back to lastResort and writes to stderr anyway.
    client_log = logging.getLogger("givenergy_modbus")
    client_log.propagate = False
    client_log.addHandler(logging.NullHandler())

    client = Client(host, 8899)
    await client.connect()
    watcher = _ErrorResponseWatcher(client.plant)
    watcher.install()
    sweepable: list[int] = []
    try:
        print(f"probing {host}:8899 - READ ONLY, {ATTEMPTS} attempts per probe, {TIMEOUT}s timeout\n")
        print(f"{'addr':>5}  {'HR(0,60)':>9}  {'HR(0,1)':>9}  {'HR(0x486,1)':>12}  {'HR(0x8000,1)':>13}  verdict")
        for addr in addrs:
            baseline = await probe(client, watcher, addr, 0, 60)
            if baseline == DEAD:
                print(f"  0x{addr:02x}  {baseline:>9}  {'-':>9}  {'-':>12}  {'-':>13}  {verdict(baseline, '', '', '')}")
                continue
            single = await probe(client, watcher, addr, 0, 1)
            mapped = await probe(client, watcher, addr, ANCHOR_MAPPED, 1)
            unmapped = await probe(client, watcher, addr, ANCHOR_UNMAPPED, 1)
            # Only worth sweeping where single-register reads actually work; a sweep
            # built on HR(n,1) is meaningless if the device rejects that count.
            if single == OK:
                sweepable.append(addr)
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
        if do_selftest:
            await selftest(client, watcher, sweepable[0] if sweepable else addrs[0])
        if do_sweep:
            if sweepable:
                await sweep(client, watcher, sweepable[0], input_regs=use_ir)
            else:
                print("\nnothing to sweep: no address accepted a single-register read.")
    finally:
        watcher.remove()
        await client.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__.rstrip().rsplit("\n\n", 1)[-1], file=sys.stderr)
        raise SystemExit(2)
    flags = {"--sweep", "--selftest", "--ir"}
    args = [a for a in sys.argv[2:] if a not in flags]
    given = [int(a, 16) for a in args] or DEFAULT_ADDRS
    asyncio.run(
        main(
            sys.argv[1],
            given,
            do_sweep="--sweep" in sys.argv,
            do_selftest="--selftest" in sys.argv,
            use_ir="--ir" in sys.argv,
        )
    )
