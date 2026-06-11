"""Golden-master regression tests over the committed wire-capture fixtures.

These replay each real-hardware capture in ``tests/fixtures/captures/`` through
the *actual* decode machinery — framer → ``Plant.update()`` (true device
addressing, no rewrite) → ``resolve_model()`` → ``PlantCapabilities`` derivation
→ typed accessors (``ems``, ``inverters``, ``hv_stacks``) — and pin the full
decoded topology each plant should produce.

This is the regression trap #127 was opened to close. The pre-#121 ``0x11→0x32``
rewrite made an earlier EMS check (#95) pass for the wrong reason: it relabelled
the ``0x11`` capture data as ``0x32``, so a replay looked green without ever
exercising the real ``[0x11]`` path. Asserting the *classification and topology*
(not just which register address data lands at — that's
``test_addressing_from_captures.py``) means any future drift in the model/decode
machinery trips here, against real hardware data rather than synthetic primes.

Classification mirrors what ``Client.detect()`` does — read HR(0)/HR(21) from the
inverter address, ``resolve_model()`` — but runs offline against the passively
captured caches, since the fixtures are recordings of cloud/app polling rather
than responses to detect()'s own request sequence.
"""

from pathlib import Path

import pytest

from givenergy_modbus.framer import ClientFramer
from givenergy_modbus.model.inverter import Model, inverter_address_for, resolve_model
from givenergy_modbus.model.plant import Plant, PlantCapabilities
from givenergy_modbus.model.register import HR
from givenergy_modbus.model.register_cache import RegisterCache
from givenergy_modbus.pdu import TransparentResponse

_CAPTURES = Path(__file__).parents[1] / "fixtures" / "captures"


def _rx_frames(*relpaths: str) -> list[bytes]:
    """Read rx frames from one or more ``<ts> rx <hex>`` capture logs, ts-sorted."""
    entries: list[tuple[str, bytes]] = []
    for relpath in relpaths:
        for line in (_CAPTURES / relpath).read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[1] == "rx":
                try:
                    entries.append((parts[0], bytes.fromhex(parts[-1])))
                except ValueError:
                    continue
    entries.sort(key=lambda e: e[0])
    return [raw for _, raw in entries]


async def _replay(*relpaths: str) -> Plant:
    """Decode a plant's rx frames into a bare Plant via the real framer + update()."""
    framer = ClientFramer()
    plant = Plant()
    for raw in _rx_frames(*relpaths):
        async for pdu in framer.decode(raw):
            if isinstance(pdu, TransparentResponse) and not pdu.error:
                plant.update(pdu)
    return plant


def _classify(plant: Plant) -> PlantCapabilities:
    """Resolve the model the way detect() does — HR(0)/HR(21) at 0x11 — and attach caps.

    The inverter identity bank is mirrored at 0x11 on every device type (it's the
    bank detect() reads first), so classification keys off 0x11 regardless of where
    the model's *operational* banks live (0x31 for AC/GEN1, etc.).
    """
    cache: RegisterCache = plant.register_caches.get(0x11, RegisterCache())
    raw_dtc = cache.get(HR(0))
    assert raw_dtc is not None, "HR(0) must be populated at 0x11 for classification"
    arm_fw = cache.get(HR(21)) or 0
    plant.capabilities = PlantCapabilities(device_type=resolve_model(raw_dtc, arm_fw))
    return plant.capabilities


@pytest.mark.timeout(20)
async def test_ems_plant_classifies_and_decodes_topology():
    """EMS controller: 0x5001/fw1036 → Model.EMS @ 0x11, rollup decodes 2 managed inverters."""
    plant = await _replay("ems_2_inv_3_bat_a/ems_arm1036_60s.log")
    caps = _classify(plant)

    assert caps.device_type is Model.EMS
    assert caps.inverter_address == 0x11
    assert caps.is_ems

    ems = plant.ems
    assert ems is not None
    assert ems.inverter_count == 2

    # The managed-inverter rollup projects one entry per populated slot, sourced
    # from the EMS rollup (these inverters aren't directly reachable in the capture).
    managed = plant.inverters
    assert len(managed) == 2
    assert all(i.data_source == "ems_rollup" for i in managed)
    assert all(i.serial_number for i in managed)


@pytest.mark.timeout(20)
async def test_aio_classifies_as_hv_all_in_one():
    """All-in-One: 0x8001/fw612 → Model.ALL_IN_ONE @ 0x11, HV BCU stack separately addressed."""
    plant = await _replay("aio_a/aio_arm612_5min.log")
    caps = _classify(plant)

    assert caps.device_type is Model.ALL_IN_ONE
    assert caps.inverter_address == 0x11
    assert caps.is_hv
    assert not caps.is_ems

    # HV battery is a separately-addressed BCU stack, not register-embedded:
    # BCU at 0x70, BMS at 0xA0, BMU modules at 0x50-0x53.
    assert 0x70 in plant.register_caches
    assert 0xA0 in plant.register_caches
    assert all(0x50 + i in plant.register_caches for i in range(4))
    # Inverter answers at 0x11; nothing served at 0x32 (the old wrong poll address).
    assert HR(0) in plant.register_caches[0x11]


@pytest.mark.timeout(20)
async def test_hybrid_gen1_passive_capture_classifies_at_0x11_banks_stay_at_0x31():
    """HYBRID_GEN1 passive dongle capture: 0x2001/fw449 → Model.HYBRID_GEN1 @ 0x11 (#189).

    This capture predates the 0x31 retirement: the dongle polled the operational banks
    at the 0x31 facade, so they live there in the replayed caches — and must STAY there
    (no folding to the classification address; that's the anti-fold property #127
    guards). The 0x11-polled sibling fixture below covers the current polling shape.
    """
    plant = await _replay("hybrid_2_bat_a/hybrid_gen1_arm449_givbat82_givbat95gen3_60min.log")
    caps = _classify(plant)

    assert caps.device_type is Model.HYBRID_GEN1
    assert caps.inverter_address == 0x11
    assert not caps.is_hv
    assert not caps.is_ems

    # Operational banks where the dongle polled them (0x31); identity-only at 0x11 in
    # this capture. LV battery packs at 0x32/0x33.
    assert HR(60) in plant.register_caches[0x31]
    assert HR(60) not in plant.register_caches[0x11]
    assert 0x32 in plant.register_caches
    assert 0x33 in plant.register_caches


@pytest.mark.timeout(20)
async def test_hybrid_gen1_0x11_poll_capture_serves_full_banks_at_0x11():
    """HYBRID_GEN1 polled by this library at 0x11 (#189): full banks land at 0x11.

    Recorded with the library's own detect → load_config → refresh loop addressing the
    inverter at 0x11 — the live-hardware proof that 0x11 is a full facade, not
    identity-only. Passive HA traffic on the same bus still polls 0x31, which must
    remain separately cached (anti-fold), and the LV packs answer at 0x32/0x33.
    """
    plant = await _replay("hybrid_2_bat_a/hybrid_gen1_arm449_0x11_poll_10min.log")
    caps = _classify(plant)

    assert caps.device_type is Model.HYBRID_GEN1
    assert caps.inverter_address == 0x11
    assert not caps.is_hv
    assert not caps.is_ems

    # Full config banks at 0x11 — what the old "identity-only" claim said couldn't happen.
    assert HR(60) in plant.register_caches[0x11]
    assert HR(120) in plant.register_caches[0x11]
    # Passive 0x31 traffic from another consumer stays at its wire address (anti-fold).
    assert HR(60) in plant.register_caches[0x31]
    # LV battery packs.
    assert 0x32 in plant.register_caches
    assert 0x33 in plant.register_caches


def test_inverter_address_matches_classification_for_all_fixtures():
    """Belt-and-braces: the model→address map agrees with where the library polls.

    Unified on 0x11 for every model since #189 — the passive hybrid capture's 0x31
    banks above are a record of pre-#189 dongle behaviour, not of the polling map.
    """
    assert inverter_address_for(Model.EMS) == 0x11
    assert inverter_address_for(Model.ALL_IN_ONE) == 0x11
    assert inverter_address_for(Model.HYBRID_GEN1) == 0x11


@pytest.mark.parametrize(
    ("relpath", "expected_errors"),
    [
        ("aio_a/aio_arm612_5min.log", 1),
        ("hybrid_2_bat_a/hybrid_gen1_arm449_givbat82_givbat95gen3_60min.log", 4),
        ("ems_2_inv_3_bat_a/ems_arm1036_30min.log", 0),
        ("ems_2_inv_3_bat_a/ac_arm282_1x_givbat512gen3_30min.log", 0),
    ],
)
async def test_fixture_error_response_count(relpath: str, expected_errors: int):
    """Pin each fixture's error-response coverage.

    A decode→re-encode CRC regen once silently stripped the transparent-function-code error
    bit (encode didn't re-add the 0x80 that decode strips into `error`), turning genuine
    error frames into malformed "success" frames that no longer decode. Counting the error
    responses requires them to decode as `error=True`, so this guards both the bit and
    decodability against a recurrence (#158).
    """
    framer = ClientFramer()
    errors = 0
    for raw in _rx_frames(relpath):
        async for pdu in framer.decode(raw):
            if isinstance(pdu, TransparentResponse) and pdu.error:
                errors += 1
    assert errors == expected_errors
