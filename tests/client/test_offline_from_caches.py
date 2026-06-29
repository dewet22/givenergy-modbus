"""Offline `Plant.from_caches()` — derive a fully-typed plant from a register-cache dump (#268).

The contract: `_derive_capabilities` over a complete cache must reproduce exactly what a live
`detect()` derives from the same hardware. We drive the real Client through MockPlant (which
synthesises responses from the captures), then assert `Plant.from_caches(client.plant.register_caches)`
yields the identical capabilities — proving the offline enumeration matches the wire path with no
duplicate source of truth to drift.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from givenergy_modbus.client.client import Client
from givenergy_modbus.exceptions import CommunicationError
from givenergy_modbus.model.inverter import Model
from givenergy_modbus.model.plant import Plant
from givenergy_modbus.model.register import HR, IR
from givenergy_modbus.model.register_cache import RegisterCache
from givenergy_modbus.testing import MockPlant
from givenergy_modbus.testing.mock_plant import plant_from_capture

_CAPTURES = Path(__file__).parents[1] / "fixtures" / "captures"

# (relative capture path, expected device_type) — the identity-complete fixtures detect() runs over.
# (The three_phase_hv_a capture is a passive refresh dump with no HR(0,60) identity block at 0x11, so
# it is neither detect-capable nor typeable offline — from_caches correctly raises on it; see
# test_from_caches_raises_without_identity.)
_FIXTURES = [
    ("aio_a/aio_arm612_5min.log", Model.ALL_IN_ONE),
    ("ems_2_inv_3_bat_a/ems_arm1036_60s.log", Model.EMS),
    ("hybrid_2_bat_a/hybrid_gen1_arm449_0x11_poll_10min.log", Model.HYBRID_GEN1),
]

# Fast probe params: absent peripheral addresses time out, so keep them short.
_DETECT = dict(timeout=1.0, retries=0, probe_timeout=0.1, probe_retries=0)


async def _client_for(relpath: str) -> AsyncIterator[Client]:
    mock = MockPlant.from_capture(_CAPTURES / relpath)
    host, port = await mock.start("127.0.0.1", 0)
    client = Client(host, port, tx_message_wait=0, tx_jitter=0)
    await client.connect()
    try:
        yield client
    finally:
        await client.close()
        await mock.aclose()


@pytest.mark.parametrize("relpath,expected_model", _FIXTURES)
@pytest.mark.timeout(30)
async def test_from_caches_capabilities_match_live_detect(relpath, expected_model):
    """from_caches over detect's resulting caches reproduces detect's capabilities exactly."""
    async for client in _client_for(relpath):
        live_caps = await client.detect(**_DETECT)
        assert live_caps.device_type is expected_model

        offline = Plant.from_caches(client.plant.register_caches)
        assert offline.capabilities == live_caps


@pytest.mark.parametrize("relpath,expected_model", _FIXTURES)
def test_from_caches_recipe_lights_up_facades(relpath, expected_model):
    """The documented offline recipe yields a typed plant; facades match the live-detected shape."""
    caches = plant_from_capture(_CAPTURES / relpath).register_caches
    plant = Plant.from_caches(caches)

    assert plant.capabilities is not None
    assert plant.capabilities.device_type is expected_model
    # The inverter view is always typed; .inverters is non-empty for every plant family.
    assert plant.inverter is not None
    assert len(plant.inverters) >= 1


@pytest.mark.parametrize("relpath,expected_model", _FIXTURES)
@pytest.mark.timeout(30)
async def test_from_caches_hinted_matches_cold(relpath, expected_model):
    """Passing the derived caps back as a `prior` (hinted candidate restriction) reproduces them."""
    async for client in _client_for(relpath):
        live = await client.detect(**_DETECT)
        hinted = Plant.from_caches(client.plant.register_caches, prior=live)
        assert hinted.capabilities == live


def test_derive_capabilities_aio_hv_lv_bcu_branches():
    """Exercise the AIO / HV-BMU / LV-BCU enumeration branches (no identity-complete fixture has them).

    Each synthetic stack deliberately claims more BCUs/modules than are present, so the absent-skip
    paths are taken alongside the append paths.
    """
    # A real, valid per-module cache — AIO modules share the HV BMU IR(60-119) block (#265).
    aio = plant_from_capture(_CAPTURES / "aio_a/aio_arm612_5min.log")
    module_cache = next(aio.register_caches[a] for a in (0x50, 0x51, 0x52, 0x53) if a in aio.register_caches)

    # ALL_IN_ONE (0x8001): the BCU claims 4 modules but only two are present → absent-module skip.
    aio_caps = Plant.from_caches(
        {
            0x11: RegisterCache({HR(0): 0x8001, HR(21): 612}),
            0xA0: RegisterCache({IR(61): 1}),
            0x70: RegisterCache({IR(64): 4}),
            0x50: module_cache,
            0x51: module_cache,
        }
    ).capabilities
    assert aio_caps.device_type is Model.ALL_IN_ONE
    assert aio_caps.aio_battery_module_addresses == [0x50, 0x51]

    # NON-AIO HV (0x8101): BMS claims 2 BCUs (only 0x70 present), which claims 3 modules (only
    # 0x50/0x51 present) — exercises the absent-BCU skip, the BMU band derivation, and the
    # absent-module skip.
    hv_src = {
        0x11: RegisterCache({HR(0): 0x8101, HR(21): 300}),
        0xA0: RegisterCache({IR(61): 2}),
        0x70: RegisterCache({IR(64): 3}),
        0x50: module_cache,
        0x51: module_cache,
    }
    hv_caps = Plant.from_caches(hv_src).capabilities
    assert hv_caps.device_type is Model.HYBRID_HV_GEN3
    assert hv_caps.bcu_stacks == [(0, 3)]
    assert hv_caps.hv_bmu_addresses == [0x50, 0x51]

    # Hinted re-derive restricts BCU/BMU candidates to the prior's known set and reproduces the caps.
    assert Plant.from_caches(hv_src, prior=hv_caps).capabilities == hv_caps

    # An HV inverter dump with no BCU/battery data present → empty topology (early return).
    bare_hv = Plant.from_caches({0x11: RegisterCache({HR(0): 0x8101, HR(21): 300})}).capabilities
    assert bare_hv.device_type is Model.HYBRID_HV_GEN3
    assert bare_hv.bcu_stacks == [] and bare_hv.hv_bmu_addresses == []

    # LV system with an LV BCU present at 0x31 (bms_status_1 = IR(60) non-zero → is_valid).
    lv_caps = Plant.from_caches(
        {
            0x11: RegisterCache({HR(0): 0x2001, HR(21): 100}),  # HYBRID_GEN1
            0x31: RegisterCache({IR(60): 5}),
        }
    ).capabilities
    assert lv_caps.lv_bcu_address == 0x31


def test_from_caches_raises_without_identity():
    """No HR(0) at 0x11 → CommunicationError, mirroring detect's identity-read failure."""
    with pytest.raises(CommunicationError, match="HR.0."):
        Plant.from_caches({0x32: RegisterCache({HR(0): 0x2001})})  # data present, but not at 0x11
