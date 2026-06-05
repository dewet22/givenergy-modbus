"""Record a wire capture of the HYBRID_GEN1 inverter where all reads go to 0x11.

The existing hybrid_2_bat_a fixture was recorded passively from the dongle's bus
traffic, which polled inverter banks at 0x31. This script uses the library's own
polling path (detect → load_config → refresh loop) — which already reads at
caps.inverter_address — and tees all redacted frames to a .log file in the same
format as the existing fixtures.

With caps.inverter_address == 0x31 for HYBRID_GEN1, load_config and refresh still
read 0x31. To get an 0x11-polled fixture we temporarily monkey-patch
inverter_address_for to return 0x11 for HYBRID_GEN1 so detect() derives
inverter_address=0x11, after which all subsequent reads go there.

Usage:
    uv run python capture_0x11.py <host> [duration_seconds]

Output:
    tests/fixtures/captures/hybrid_2_bat_a/hybrid_gen1_arm449_0x11_poll_<n>min.log
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

FIXTURE_DIR = Path("tests/fixtures/captures/hybrid_2_bat_a")


async def main(host: str, duration: float) -> None:
    # Monkey-patch before importing Client so PlantCapabilities derives 0x11.
    from givenergy_modbus.model import inverter as _inv_mod

    _orig = _inv_mod.inverter_address_for

    def _patched(model):
        from givenergy_modbus.model.inverter import Model

        if model in (Model.AC, Model.HYBRID_GEN1):
            return 0x11
        return _orig(model)

    _inv_mod.inverter_address_for = _patched

    from givenergy_modbus.client.client import Client

    minutes = int(duration // 60) or 1
    outpath = FIXTURE_DIR / f"hybrid_gen1_arm449_0x11_poll_{minutes}min.log"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    frames: list[str] = []

    def sink(direction: str, data: bytes) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        frames.append(f"{ts} {direction} {data.hex()}")

    client = Client(host=host, port=8899)
    await client.connect()
    try:
        print(f"starting {minutes}-minute capture to {outpath.name} ...")

        async def poll_loop() -> None:
            caps = await client.detect()
            print(f"detected: {caps.device_type.name}, inverter_address=0x{caps.inverter_address:02x}")
            if caps.inverter_address != 0x11:
                print("ERROR: inverter_address is not 0x11 — patch may have failed.")
                return
            # load_config is part of the capture window so its HR(0x11) reads are recorded.
            for attempt in range(3):
                try:
                    await client.load_config(timeout=5.0, retries=3)
                    print(f"load_config OK (attempt {attempt + 1})")
                    break
                except Exception as e:
                    print(f"load_config partial ({type(e).__name__}), attempt {attempt + 1}/3")
            while True:
                try:
                    await client.refresh(timeout=3.0, retries=1)
                except Exception:
                    pass
                # Periodically re-run load_config so HR banks appear throughout the capture.
                if len(frames) % 60 == 0 and len(frames) > 0:
                    try:
                        await client.load_config(timeout=5.0, retries=2)
                    except Exception:
                        pass
                await asyncio.sleep(10)

        poll_task = asyncio.create_task(poll_loop())
        try:
            await client.capture_frames(sink, duration=duration)
        finally:
            poll_task.cancel()
            try:
                await poll_task
            except asyncio.CancelledError, Exception:
                pass
    finally:
        await client.close()

    outpath.write_text("\n".join(frames) + "\n", encoding="utf-8")
    print(f"wrote {len(frames)} frames to {outpath}")
    print(
        'verify: uv run python -c "'
        "from givenergy_modbus.testing.mock_plant import _iter_capture_frames; "
        f"print(len(_iter_capture_frames('{outpath}')), 'frames')\""
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: uv run python capture_0x11.py <host> [duration_seconds]")
    asyncio.run(main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 600))
