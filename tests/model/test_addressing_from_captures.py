"""Regression tests for #119 device addressing, replayed from real wire captures.

Rather than synthetic register primes, these feed the committed captures in
``tests/fixtures/captures/`` through the framer into a bare ``Plant`` and assert
the address each topology actually serves its inverter banks at — the concrete
``0x11`` / ``0x31`` / ``0x32`` evidence the addressing redesign turns on:

- **AIO** answers at ``0x11`` and exposes nothing at ``0x32`` (root cause of #105).
- **HYBRID_GEN1** answers identity-only at ``0x11`` and serves full banks at
  ``0x31`` — which is why GEN1/AC map to ``0x31`` rather than the ``0x11`` default.
- **EMS** serves its IR(2040) rollup at ``0x11``.
"""

from pathlib import Path

import pytest

from givenergy_modbus.framer import ClientFramer
from givenergy_modbus.model.plant import Plant
from givenergy_modbus.model.register import HR, IR
from givenergy_modbus.pdu import TransparentResponse

_CAPTURES = Path(__file__).parents[1] / "fixtures" / "captures"


def _rx_frames(relpath: str) -> list[bytes]:
    """Read the ``rx`` frames from a ``<ts> rx <hex>`` capture log."""
    frames: list[bytes] = []
    for line in (_CAPTURES / relpath).read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1] == "rx":
            try:
                frames.append(bytes.fromhex(parts[-1]))
            except ValueError:
                continue
    return frames


async def _replay(relpath: str) -> Plant:
    """Decode a capture's rx frames into a bare (no-capabilities) Plant.

    Mirrors the offline replay harness: no detect(), so Plant.update() stores
    each response under its true wire address with no model-aware rewriting.
    """
    framer = ClientFramer()
    plant = Plant()
    for raw in _rx_frames(relpath):
        async for pdu in framer.decode(raw):
            if isinstance(pdu, TransparentResponse) and not pdu.error:
                plant.update(pdu)
    return plant


@pytest.mark.timeout(15)
async def test_aio_answers_at_0x11_and_nothing_at_0x32():
    """ALL_IN_ONE serves its inverter banks at 0x11, not 0x32.

    The #105 root cause is that the old code polled 0x32, where the AIO
    answers nothing.
    """
    plant = await _replay("aio_a/aio_arm612_5min.log")

    assert HR(0) in plant.register_caches[0x11]
    assert IR(0) in plant.register_caches[0x11]
    # Nothing committed at 0x32 (only the empty default pre-alloc may exist).
    cache_32 = plant.register_caches.get(0x32, {})
    assert HR(0) not in cache_32
    assert IR(0) not in cache_32
    # The integral battery is an HV BCU stack, separately addressed.
    assert 0x70 in plant.register_caches  # BCU


@pytest.mark.timeout(15)
async def test_hybrid_gen1_full_banks_at_0x31_identity_only_at_0x11():
    """HYBRID_GEN1 serves full banks at 0x31, identity-only at 0x11.

    So it must map to 0x31, not the 0x11 default (#119).
    """
    plant = await _replay("hybrid_2_bat_a/hybrid_gen1_arm449_givbat82_givbat95gen3_60min.log")

    cache_11 = plant.register_caches.get(0x11, {})
    cache_31 = plant.register_caches.get(0x31, {})
    # Identity is visible at 0x11, but the full banks are not.
    assert HR(0) in cache_11
    assert HR(60) not in cache_11
    # 0x31 carries the full inverter map (config HR + operational IR banks).
    assert HR(60) in cache_31
    assert IR(0) in cache_31
    assert len(cache_31) > len(cache_11)
    # LV battery packs sit at 0x32 / 0x33, distinct from the inverter.
    assert 0x32 in plant.register_caches
    assert 0x33 in plant.register_caches


@pytest.mark.timeout(15)
async def test_ems_serves_rollup_at_0x11():
    """The EMS controller serves identity and the IR(2040) plant rollup at 0x11."""
    plant = await _replay("ems_2_inv_3_bat_a/ems_arm1036_60s.log")

    assert HR(0) in plant.register_caches[0x11]
    assert IR(2040) in plant.register_caches[0x11]
