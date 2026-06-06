#!/usr/bin/env python3
r"""Soak-test refresh(ir0_max_age=...) against a live inverter — #196.

Drives the poll loop a consumer (hass) would, but its only job is to validate the
fan-out assumption and the skip-if-fresh behaviour on real hardware before wiring
it into hass or broadening its scope. For each tick it logs:

- ``ir0_sent``: how many IR(0,60) requests actually went on the wire this tick
  (0 = skipped because the fan-out kept it fresh; 1+ = solicited). This is the
  ground truth, measured by wrapping send_request_and_await_response — not the
  library's internal decision inferred from outside.
- ``age_before`` / ``age_after``: Plant.block_age() for IR(0,60) — the observed
  fan-out cadence. If ``age_before`` stays comfortably under ``--ir0-max-age``
  most ticks, the fan-out is keeping pace and the skip is safe.
- ``dt``: refresh wall-time, and whether the tick partially failed.
- a freshness proxy (a raw IR(0,60) register read straight from the cache) so you
  can eyeball that the live data is genuinely still updating while being skipped.

Run it ALONGSIDE your normal setup (hass / GivTCP) — those peers are what poll the
dongle and produce the fan-out this exploits. It's a light extra client (skip-if-
fresh actually reduces its request count), polling at ``--interval`` seconds.

Usage::

    uv run python tests/debug/soak_skip_if_fresh.py --host 192.168.1.50 \
        --interval 20 --ir0-max-age 25 --duration 3600

Ctrl-C (or --duration elapsing) prints a summary: tick count, how often IR(0,60)
was skipped vs solicited, and the worst observed age (did the fan-out ever lapse
past the threshold?).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import time

from givenergy_modbus.client.client import Client
from givenergy_modbus.exceptions import RefreshFailed, RefreshPartiallySucceeded
from givenergy_modbus.model.register import IR
from givenergy_modbus.pdu import ReadInputRegistersRequest

_logger = logging.getLogger("soak")


def _is_ir0(request: object, inverter: int) -> bool:
    return (
        isinstance(request, ReadInputRegistersRequest)
        and request.device_address == inverter
        and request.base_register == 0
        and request.register_count == 60
    )


async def soak(args: argparse.Namespace) -> None:
    client = Client(args.host, args.port)
    await client.connect()
    _logger.info("connected to %s:%d — detecting…", args.host, args.port)
    caps = await client.detect(timeout=args.timeout, retries=1)
    inverter = caps.inverter_address
    _logger.info("detected %s @ 0x%02x", caps.device_type.name, inverter)

    # Wrap the send path to count IR(0,60) requests that actually reach the wire.
    ir0_sent_total = 0
    original_send = client.send_request_and_await_response

    async def counting_send(request, *a, **k):
        nonlocal ir0_sent_total
        if _is_ir0(request, inverter):
            ir0_sent_total += 1
        return await original_send(request, *a, **k)

    client.send_request_and_await_response = counting_send  # type: ignore[method-assign]

    tick = skipped = solicited = partials = failures = 0
    worst_age_before: float | None = None
    deadline = None if args.duration <= 0 else time.monotonic() + args.duration

    _logger.info(
        "soaking: interval=%ss ir0_max_age=%ss%s — Ctrl-C to stop",
        args.interval,
        args.ir0_max_age,
        "" if deadline is None else f" duration={args.duration}s",
    )
    try:
        while deadline is None or time.monotonic() < deadline:
            tick += 1
            age_before = client.plant.block_age(inverter, "IR", 0, 60)
            if age_before is not None and (worst_age_before is None or age_before > worst_age_before):
                worst_age_before = age_before
            before_count = ir0_sent_total

            t0 = time.monotonic()
            status = "ok"
            try:
                await client.refresh(retries=args.retries, ir0_max_age=args.ir0_max_age)
            except RefreshPartiallySucceeded as exc:
                status = f"PARTIAL ({len(exc.failures)} failed)"
                partials += 1
            except RefreshFailed as exc:
                status = f"FAILED ({exc})"
                failures += 1
            dt = time.monotonic() - t0

            sent = ir0_sent_total - before_count
            if sent == 0:
                skipped += 1
            else:
                solicited += 1
            age_after = client.plant.block_age(inverter, "IR", 0, 60)
            # Freshness proxy: a raw register from the IR(0,60) block, straight from cache.
            cache = client.plant.register_caches.get(inverter)
            proxy = cache.get(IR(1)) if cache is not None else None

            _logger.info(
                "tick %4d | ir0_sent=%d (%s) | age_before=%s age_after=%s | dt=%.2fs | IR(1)=%s | %s",
                tick,
                sent,
                "SKIP" if sent == 0 else "SOLICIT",
                "—" if age_before is None else f"{age_before:.1f}s",
                "—" if age_after is None else f"{age_after:.1f}s",
                dt,
                proxy,
                status,
            )

            sleep_for = max(0.0, args.interval - dt)
            await asyncio.sleep(sleep_for)
    except (KeyboardInterrupt, asyncio.CancelledError):
        _logger.info("interrupted")
    finally:
        await client.close()
        total = max(1, tick)
        _logger.info(
            "=== summary: %d ticks | skipped=%d (%.0f%%) solicited=%d | "
            "partials=%d failures=%d | worst age_before=%s ===",
            tick,
            skipped,
            100 * skipped / total,
            solicited,
            partials,
            failures,
            "—" if worst_age_before is None else f"{worst_age_before:.1f}s",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Soak-test refresh(ir0_max_age=...) on a live inverter.")
    parser.add_argument("--host", required=True, help="inverter/dongle IP")
    parser.add_argument("--port", type=int, default=8899, help="Modbus TCP port (default: 8899)")
    parser.add_argument("--interval", type=float, default=20.0, help="poll interval seconds (default: 20)")
    parser.add_argument(
        "--ir0-max-age",
        type=float,
        default=25.0,
        help="skip IR(0,60) if fan-out refreshed it within this many seconds (default: 25)",
    )
    parser.add_argument("--retries", type=int, default=1, help="per-read retries (default: 1)")
    parser.add_argument("--timeout", type=float, default=3.0, help="detect timeout seconds (default: 3)")
    parser.add_argument("--duration", type=float, default=0.0, help="run for N seconds then stop (0 = until Ctrl-C)")
    parser.add_argument("-v", "--verbose", action="store_true", help="DEBUG logging (shows the library's skip line)")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(soak(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
