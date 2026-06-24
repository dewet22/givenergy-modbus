#!/usr/bin/env python3
"""Live probe (#301): does HYBRID_GEN1 battery output exceed the 50% discharge limit when set higher?

Run this *while an EV charge (or any sustained load the battery supplies) is active*,
so the battery is discharging near its ceiling. The probe sweeps the discharge power
limit (HR112) up through 50 -> 100 % and reports the actual battery power (IR52) at
each step. If output rises past ~2.5 kW (the Gen1 battery subsystem's ~50%-of-rated
ceiling) the subsystem has genuine headroom above 50; if it plateaus, the firmware
clamps it (the widen is still correct, just inert above the real rating).

Safety:
- Touches exactly one register (BATTERY_DISCHARGE_LIMIT, HR112, WRITE_SAFE), and
  ALWAYS restores the original value in a finally block.
- Requires the #301 widen (set_battery_discharge_limit accepting >50); run from the
  feat/widen-battery-power-limits branch or a release that includes it.
- Read-only until you confirm at the prompt.

    uv run python tests/debug/probe_discharge_limit_clamp.py <inverter-host>
"""

from __future__ import annotations

import asyncio
import sys

from givenergy_modbus.client import commands
from givenergy_modbus.client.client import Client
from givenergy_modbus.client.commands import RegisterMap
from givenergy_modbus.model.inverter import Model
from givenergy_modbus.model.register import HR, IR
from givenergy_modbus.model.register_cache import RegisterCache

SWEEP = (50, 60, 70, 85, 100)  # discharge-limit % steps to walk through
SETTLE_SECONDS = 8.0  # let the inverter apply each write and the battery ramp


def _signed16(raw: int | None) -> int | None:
    """Interpret a raw uint16 cache value as int16 (p_battery is signed: + = discharging)."""
    if raw is None:
        return None
    return raw - 65536 if raw >= 32768 else raw


async def _refresh(client: Client) -> RegisterCache:
    # Patient timeouts: the inverter is contended by other TCP clients (dongle fan-out).
    await client.refresh_plant(full_refresh=True, timeout=3.0, retries=2)
    caps = client.plant.capabilities
    assert caps is not None, "detect() must run before reading"
    return client.plant.register_caches.get(caps.inverter_address, RegisterCache())


async def _read(client: Client) -> tuple[int | None, int | None]:
    """Return (discharge_limit HR112, p_battery W IR52)."""
    cache = await _refresh(client)
    return cache.get(HR(RegisterMap.BATTERY_DISCHARGE_LIMIT)), _signed16(cache.get(IR(52)))


async def _set_limit(client: Client, val: int) -> None:
    await client.one_shot_command(commands.set_battery_discharge_limit(val), timeout=3.0, retries=2)


async def main(host: str) -> None:
    client = Client(host, 8899)
    await client.connect()
    try:
        caps = await client.detect()
        print(f"detected: {caps.device_type.name}, inverter_address=0x{caps.inverter_address:02x}")
        if caps.device_type != Model.HYBRID_GEN1:
            print(f"WARNING: expected HYBRID_GEN1, got {caps.device_type.name} — aborting to be safe.")
            return

        original, p0 = await _read(client)
        print(f"baseline: discharge_limit={original}%  p_battery={p0} W (+ = discharging)")
        if not isinstance(original, int):
            print("could not read a sane baseline discharge limit — aborting before any write.")
            return

        print(
            "\nStart/confirm an EV charge (or another sustained load the battery supplies) so the\n"
            "battery is discharging near its limit, THEN proceed. The probe sweeps the discharge\n"
            "limit and logs battery power at each step, restoring the original limit afterwards."
        )
        answer = await asyncio.to_thread(input, f"Proceed sweeping discharge limit {SWEEP} %? [y/N] ")
        if answer.strip().lower() != "y":
            print("aborted — no writes were sent.")
            return

        results: list[tuple[int, int | None]] = []
        try:
            for limit in SWEEP:
                print(f"  set discharge_limit={limit}% ...")
                await _set_limit(client, limit)
                await asyncio.sleep(SETTLE_SECONDS)
                _lim, p = await _read(client)
                print(f"    -> p_battery={p} W")
                results.append((limit, p))
        finally:
            print(f"restoring discharge_limit={original}% ...")
            try:
                await _set_limit(client, original)
            except Exception as e:  # noqa: BLE001 — best-effort cleanup, report and continue
                print(f"  failed to restore: {e} — please set it back to {original}% manually")

        print("\nlimit% -> battery power (W):")
        for limit, p in results:
            print(f"  {limit:3d}%  {p} W")
        print(
            "\nReading: if power rises past ~2500 W as the limit goes above 50, the battery subsystem\n"
            "has headroom above 50%; if it plateaus, the firmware clamps at the rated max."
        )
    finally:
        await client.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: probe_discharge_limit_clamp.py <inverter-host>", file=sys.stderr)
        raise SystemExit(2)
    asyncio.run(main(sys.argv[1]))
