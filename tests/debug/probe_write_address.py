#!/usr/bin/env python3
"""Live probe for #124: does a HYBRID_GEN1 accept register writes at 0x11 or only at 0x31?

Strategy: reads are always taken at the model's inverter_address (0x31 for GEN1).
We write CHARGE_TARGET_SOC (HR 116, in WRITE_SAFE_REGISTERS) ±1 at 0x11 and check
whether a subsequent read reflects it; if not, we try 0x31. Whichever address
actually changes the value is where GEN1 accepts writes.

Safety:
- Touches exactly one register (CHARGE_TARGET_SOC), by ±1, and ALWAYS restores
  the original value in a finally block (writing it back at both addresses).
- Does NOT touch ENABLE_CHARGE_TARGET, so charge-to-target behaviour is never
  enabled/disabled — only the target *value* moves by 1.
- Read-only until you confirm at the prompt. Best run with no scheduled AC
  charge active, so even the transient ±1 is inert.

    uv run python tests/debug/probe_write_address.py <inverter-host>
"""

from __future__ import annotations

import asyncio
import sys

from givenergy_modbus.client.client import Client
from givenergy_modbus.client.commands import RegisterMap
from givenergy_modbus.model.inverter import Model
from givenergy_modbus.model.register import HR
from givenergy_modbus.model.register_cache import RegisterCache
from givenergy_modbus.pdu import WriteHoldingRegisterRequest

REG = RegisterMap.CHARGE_TARGET_SOC  # HR 116


async def read_target(client: Client) -> int | None:
    """Full refresh (reads HR banks at the model's inverter_address) and return HR(116).

    Patient timeouts: the inverter is contended by other clients, so the stock
    refresh_plant defaults (1.0s / 0 retries) race and time out — see #124 probe notes.
    Reads the raw register rather than the decoded model field, which is built
    dynamically and so isn't statically typed.
    """
    await client.refresh_plant(full_refresh=True, timeout=3.0, retries=2)
    caps = client.plant.capabilities
    assert caps is not None, "detect() must run before read_target()"
    cache: RegisterCache = client.plant.register_caches.get(caps.inverter_address, RegisterCache())
    return cache.get(HR(REG))


async def write_target(client: Client, value: int, device_address: int) -> None:
    await client.one_shot_command(
        [WriteHoldingRegisterRequest(REG, value, device_address=device_address)],
        timeout=3.0,
        retries=2,
    )


async def probe_at(client: Client, device_address: int, original: int) -> bool:
    """Write original±1 at device_address; return True iff a read-back shows the change."""
    target = original - 1 if original > 4 else original + 1
    print(f"  writing CHARGE_TARGET_SOC={target} at 0x{device_address:02x} ...")
    await write_target(client, target, device_address)
    await asyncio.sleep(1.5)  # let the inverter apply
    readback = await read_target(client)
    took = readback == target
    print(f"  read back {readback} (wanted {target}) -> {'TOOK' if took else 'no change'}")
    return took


async def main(host: str) -> None:
    client = Client(host, 8899)
    await client.connect()
    try:
        caps = await client.detect()
        print(f"detected: {caps.device_type.name}, inverter_address=0x{caps.inverter_address:02x}")
        if caps.device_type != Model.HYBRID_GEN1:
            print(f"WARNING: expected HYBRID_GEN1, got {caps.device_type.name} — aborting to be safe.")
            return

        original = await read_target(client)
        print(f"baseline CHARGE_TARGET_SOC = {original}")
        if not isinstance(original, int):
            print("could not read a sane baseline value — aborting before any write.")
            return

        prompt = "\nProceed with the reversible write test (nudge ±1, then restore)? [y/N] "
        # Run blocking input() off the event loop so the client's background reader/writer
        # tasks keep servicing the connection (heartbeats etc.) while we wait at the prompt.
        answer = await asyncio.to_thread(input, prompt)
        if answer.strip().lower() != "y":
            print("aborted — no writes were sent.")
            return

        verdict = "neither 0x11 nor 0x31 took — unexpected, investigate further"
        try:
            if await probe_at(client, 0x11, original):
                verdict = "0x11 — the library default already works; #124 needs no code change"
            elif await probe_at(client, 0x31, original):
                verdict = "0x31 — writes must use the model address; #124 needs the write builders to honour it"
        finally:
            print(f"restoring CHARGE_TARGET_SOC = {original} ...")
            # Best-effort restore: try every address independently so a failure on one
            # (e.g. a contention timeout) doesn't skip the others.
            for addr in (0x11, 0x31):
                try:
                    await write_target(client, original, addr)
                except Exception as e:  # noqa: BLE001 — best-effort cleanup, keep going
                    print(f"  failed to restore at 0x{addr:02x}: {e}")
            await asyncio.sleep(1.0)
            try:
                restored = await read_target(client)
                ok = restored == original
                print(f"  now reads {restored} ({'restored OK' if ok else 'MISMATCH — CHECK MANUALLY'})")
            except Exception as e:  # noqa: BLE001
                print(f"  could not read back restored value: {e} — please verify manually")

        print(f"\nVERDICT (#124): {verdict}")
    finally:
        await client.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: probe_write_address.py <inverter-host>", file=sys.stderr)
        raise SystemExit(2)
    asyncio.run(main(sys.argv[1]))
