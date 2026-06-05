#!/usr/bin/env python3
"""Read-only diagnostic: which address serves this inverter's active reads (#119/#124).

Determines which device address answers active reads, and whether it carries the
full register map or only the identity block.

For each candidate address (0x11, 0x31, 0x32) it reads HR(0,60) (identity) and
HR(60,60) (config — includes HR116 charge-target), several times with patient
timeouts so contention from other clients (GivTCP/app) doesn't masquerade as a
dead address. Reports a response rate per bank plus the DTC and charge-target
seen, so we can tell identity-only from full-data — then compares 0x11 against
0x31 value-for-value to tell a full facade (same registers, two addresses) from
genuinely distinct data.

NO writes whatsoever — purely diagnostic.

    uv run python tests/debug/probe_read_address.py <inverter-host>
"""

from __future__ import annotations

import asyncio
import sys

from givenergy_modbus.client.client import Client
from givenergy_modbus.model.register import HR
from givenergy_modbus.model.register_cache import RegisterCache
from givenergy_modbus.pdu import ReadHoldingRegistersRequest

ADDRS = [0x11, 0x31, 0x32]
ATTEMPTS = 4


async def read_bank(client: Client, addr: int, base: int) -> int:
    """Return number of successful reads of HR(base,60) at addr out of ATTEMPTS."""
    ok = 0
    for _ in range(ATTEMPTS):
        try:
            await client.send_request_and_await_response(
                ReadHoldingRegistersRequest(base_register=base, register_count=60, device_address=addr),
                timeout=3.0,
                retries=1,
            )
            ok += 1
        except TimeoutError:
            pass
        await asyncio.sleep(0.4)
    return ok


async def main(host: str) -> None:
    client = Client(host, 8899)
    await client.connect()
    try:
        print(f"probing {host}:8899 — {ATTEMPTS} attempts per bank, 3s timeout + 1 retry each\n")
        print(f"{'addr':>5}  {'HR(0,60)':>9}  {'HR(60,60)':>10}  {'DTC':>7}  {'charge_target':>13}")
        for addr in ADDRS:
            ok0 = await read_bank(client, addr, 0)
            ok60 = await read_bank(client, addr, 60)
            cache: RegisterCache = client.plant.register_caches.get(addr, RegisterCache())
            dtc = cache.get(HR(0))
            ct = cache.get(HR(116))
            dtc_s = f"0x{dtc:04x}" if isinstance(dtc, int) else str(dtc)
            print(f"  0x{addr:02x}  {ok0}/{ATTEMPTS:<7}  {ok60}/{ATTEMPTS:<8}  {dtc_s:>7}  {str(ct):>13}")
        print(
            "\nReading: an address that serves the full inverter is one where BOTH banks respond.\n"
            "Identity-only (e.g. HR(0,60) ok but HR(60,60) dead) means it's not the data address."
        )

        # Facade check: does 0x11 mirror 0x31 value-for-value across the config banks just
        # read (HR 0-119)? HR config registers are static, so direct equality is meaningful
        # — but skip HR(35)-HR(40), the system_time RTC, which ticks between the two
        # sequential reads and would masquerade as a data difference (as IR measurements do).
        clock = set(range(35, 41))  # system_time: year/month/day/hour/minute/second
        c11 = client.plant.register_caches.get(0x11, RegisterCache())
        c31 = client.plant.register_caches.get(0x31, RegisterCache())
        shared = [HR(r) for r in range(120) if r not in clock and HR(r) in c11 and HR(r) in c31]
        if not shared:
            print("\nfacade: cannot compare 0x11 vs 0x31 (one address served no config banks).")
        else:
            diffs = [r for r in shared if c11[r] != c31[r]]
            if diffs:
                print(f"\nfacade: 0x11 and 0x31 differ at {len(diffs)}/{len(shared)} HR registers — not a facade.")
                for r in diffs[:8]:
                    print(f"  {r}: 0x11={c11[r]} 0x31={c31[r]}")
            else:
                print(f"\nfacade: 0x11 mirrors 0x31 across all {len(shared)} shared HR registers — full facade.")
    finally:
        await client.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: probe_read_address.py <inverter-host>", file=sys.stderr)
        raise SystemExit(2)
    asyncio.run(main(sys.argv[1]))
