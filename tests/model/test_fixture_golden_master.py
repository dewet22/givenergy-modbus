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
async def test_ems_meter_pf_and_apparent_power_decode():
    """Meter pf_*/p_apparent_* decode pinned to real capture values (#246).

    The displacement-PF identity cosφ = P/√(P² + Q²) settles all three scales on
    this capture: PF is signed int16 ×1e-4 (meter 0x03: raw 9998 → +0.9998 with
    Q=11 var giving cosφ = 0.9998 exactly; meter 0x01: raw 64670 → −0.0866),
    apparent power is deci-scaled (S = 575.2 VA ≥ √(P²+Q²) = 567.1; at 1 VA the
    cross-check collapses), and reactive stays at 1 var (at 0.1 var the identity
    breaks on both meters).
    """
    plant = await _replay("ems_2_inv_3_bat_a/ems_arm1036_30min.log")
    caps = _classify(plant)
    caps.meter_addresses = [0x01, 0x03]

    m1, m3 = plant.meters[0x01], plant.meters[0x03]
    assert m3.pf_total == 0.9998
    assert m3.p_active_total == 567
    assert m3.p_apparent_total == 575.2
    assert m3.p_reactive_total == 11
    assert m1.pf_total == -0.0866
    assert m1.p_active_total == -47
    assert m1.p_apparent_total == 713.2
    assert m1.p_reactive_total == -564


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

    # IR(44)/IR(45-46) carry inverter-output on ALL_IN_ONE, not PV generation (#293).
    inv = plant.inverter
    assert inv.e_pv_generation_today is None  # mislabel retired on AIO (#293)
    assert inv.e_inverter_out_today == 1.8  # raw IR(44) == 18; 18 / 10 == 1.8


@pytest.mark.timeout(20)
async def test_ac_coupled_inverter_gets_inverter_out_identity():
    """AC-coupled single-phase inverter: 0x3001/fw282 → Model.AC; IR44 is inverter output, not PV (#293).

    No existing golden test decoded a Model.AC unit directly (only via the EMS rollup
    that shares this fixture directory), so this pins one against the standalone
    inverter-dongle capture that accompanies the EMS controller fixtures.
    """
    plant = await _replay("ems_2_inv_3_bat_a/ac_arm282_1x_givbat512gen3_30min.log")
    caps = _classify(plant)

    assert caps.device_type is Model.AC
    assert caps.inverter_address == 0x11

    inv = plant.inverter
    assert inv.e_pv_generation_today is None  # mislabel retired on AC (#293)
    assert inv.e_inverter_out_today == 6.3  # raw IR(44) == 63; 63 / 10 == 6.3
    assert inv.e_inverter_out_total == 2643.8  # raw IR(45,46) == (0, 26438); 26438 / 10 == 2643.8


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

    # IR(44)/IR(45-46) stay PV generation on HYBRID_GEN1 — the #293 override doesn't fire.
    inv = plant.inverter
    assert inv.e_pv_generation_today == 19.2  # raw IR(44) == 192; 192 / 10 == 19.2
    assert inv.e_inverter_out_today is None


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

    # IR(44)/IR(45-46) stay PV generation on HYBRID_GEN1 — the #293 override doesn't fire.
    inv = plant.inverter
    assert inv.e_pv_generation_today == 15.8  # raw IR(44) == 158; 158 / 10 == 15.8
    assert inv.e_inverter_out_today is None


@pytest.mark.timeout(20)
async def test_hybrid_gen2_classifies_and_routes_daily_energy_to_alt1():
    """First HYBRID_GEN2 fixture (hass#293): 0x2003/fw920 → Model.HYBRID_GEN2 @ 0x11.

    Gen2 3.6 hybrids were undeclared in ``manifest.VALUE_SOURCES``, so the canonical
    daily battery-energy fields returned ``None`` (the missing HA sensors reported on
    hass#293). This pins the 2.12.2 fix: daily charge/discharge route to alt1
    (``IR36``/``IR37``) like AC/AIO, while the lifetime total stays an honest ``None``
    (alt1's total register reads an implausible 0; the alt2/alt3 ``HR(4100+)`` total
    candidates are never polled on any model). Also confirms ``IR44 == PV generation``
    holds on GEN2 (DC-coupled), de-risking the manifest hybrid field-identity beyond GEN1.
    """
    plant = await _replay("hybrid_gen2_1_bat_a/hybrid_gen2_arm920_60s.log")
    caps = _classify(plant)

    assert caps.device_type is Model.HYBRID_GEN2
    assert caps.inverter_address == 0x11
    assert not caps.is_hv
    assert not caps.is_ems

    inv = plant.inverter
    # Identity fingerprint — the Gen2 discriminator is arm_fw // 100 == 9.
    assert inv.device_type_code == "2003"
    assert inv.arm_firmware_version == 920
    assert inv.inverter_max_power == 3600

    # The hass#293 fix: daily battery energy routes to alt1 (IR36/37), not GEN1's alt2.
    assert inv.e_battery_charge_today == 4.7
    assert inv.e_battery_discharge_today == 5.5
    assert inv.e_battery_charge_today_alt1 == 4.7
    assert inv.e_battery_charge_today_alt2 == 0.0  # GEN1's daily source reads 0 here
    # Lifetime total deferred — honest None (see the fixture README).
    assert inv.e_battery_charge_total is None
    assert inv.e_battery_discharge_total is None

    # IR44 == PV generation on GEN2 (DC-coupled), same as GEN1 — the #293 override is
    # daily-energy only and doesn't disturb the PV identity.
    assert inv.is_ac_coupled is False
    assert inv.e_pv_generation_today == 28.6
    assert inv.e_inverter_out_today is None

    # Characterisation (not asserted-correct): a two-string PV Gen2 reports num_mppt == 0
    # and num_phases == 0. Pinned to flag if a later decode fix changes it — a second Gen2
    # is needed to tell "GE reports 0 here" from a Gen2-specific decode gap.
    assert inv.num_mppt == 0
    assert inv.num_phases == 0


def test_inverter_address_matches_classification_for_all_fixtures():
    """Belt-and-braces: the model→address map agrees with where the library polls.

    Unified on 0x11 for every model since #189 — the passive hybrid capture's 0x31
    banks above are a record of pre-#189 dongle behaviour, not of the polling map.
    """
    assert inverter_address_for(Model.EMS) == 0x11
    assert inverter_address_for(Model.ALL_IN_ONE) == 0x11
    assert inverter_address_for(Model.HYBRID_GEN1) == 0x11
    assert inverter_address_for(Model.HYBRID_GEN2) == 0x11


@pytest.mark.parametrize(
    ("relpath", "expected_errors"),
    [
        ("aio_a/aio_arm612_5min.log", 1),
        ("hybrid_2_bat_a/hybrid_gen1_arm449_givbat82_givbat95gen3_60min.log", 4),
        ("ems_2_inv_3_bat_a/ems_arm1036_30min.log", 0),
        ("ems_2_inv_3_bat_a/ac_arm282_1x_givbat512gen3_30min.log", 0),
        ("hybrid_gen2_1_bat_a/hybrid_gen2_arm920_60s.log", 0),
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


@pytest.mark.timeout(20)
async def test_gateway_classifies_and_decodes_v1_totals():
    """Gen1 Gateway: 0x7001/GAAA0014 → Model.GATEWAY; select_gateway picks the V1 word order (#360).

    The energy-total pins are the #360 regression trap: the old raw-IR(1603) selector chose the
    swapped-word V2 layout on this firmware, inflating every uint32 total by 10^4-10^5. The
    today-counter pin (per-AIO sum == battery total) guards the map's internal consistency.
    """
    from givenergy_modbus.model.gateway import GatewayV1, select_gateway

    plant = await _replay("gateway_2aio_a/gateway_gaaa0014_10min_daylight.log")
    caps = _classify(plant)

    assert caps.device_type is Model.GATEWAY
    assert caps.inverter_address == 0x11
    assert not caps.is_hv and not caps.is_ems

    gw = select_gateway(plant.register_caches[0x11])
    assert isinstance(gw, GatewayV1)
    assert gw.software_version == "GAAA0014"
    assert gw.parallel_aio_num == 2
    # V1 word order: sane lifetime totals (V2 order inflates these to ~4e8 / ~3e8 / ~1.5e8)
    assert gw.e_grid_import_total == 12710.8
    assert gw.e_pv_total == 5087.0
    assert gw.e_battery_charge_total == 8855.9
    # Map-consistency: per-AIO charge todays sum exactly to the battery total
    assert gw.e_aio1_charge_today + gw.e_aio2_charge_today == pytest.approx(gw.e_battery_charge_today)
    # Live AIO-serial layout (#361 review): contiguous 5-register stride from IR(1841).
    # Pinning these keeps FrameRedactor's derived serial groups honest — a wrong layout
    # here silently exempts the slots from redaction.
    assert gw.aio1_serial_number == "CH2414G000"
    assert gw.aio2_serial_number == "CH2542G000"
    assert not gw.aio3_serial_number  # only two AIOs on this plant
    # AIO power sign convention (house: positive = discharge). Daylight, near-full
    # batteries absorbing PV surplus → charging → negative after C.negate.
    assert gw.p_aio_total < 0
    assert gw.p_liberty < 0
    # Per-AIO components share the total's convention and sum to it (both negated).
    assert gw.p_aio1_inverter < 0 and gw.p_aio2_inverter < 0


@pytest.mark.timeout(20)
async def test_gateway_night_capture_classifies_and_selects_v1():
    """The GivTCP-only deep-night capture: same classification and V1 selection, p_pv dark (#360).

    Complements the daylight golden: single-client traffic, zero instantaneous solar —
    guards decode paths where values are legitimately zero rather than absent.
    """
    from givenergy_modbus.model.gateway import GatewayV1, select_gateway

    plant = await _replay("gateway_2aio_a/gateway_gaaa0014_10min_night.log")
    caps = _classify(plant)

    assert caps.device_type is Model.GATEWAY
    gw = select_gateway(plant.register_caches[0x11])
    assert isinstance(gw, GatewayV1)
    assert gw.software_version == "GAAA0014"
    assert gw.parallel_aio_num == 2
    assert gw.p_pv == 0  # deep night
    # V1 word order holds on this capture too (V2 order would inflate ~1.5e8)
    assert 8000 < gw.e_battery_charge_total < 9000
    # AIO power sign convention (house: positive = discharge). Deep night, PV=0,
    # grid ~0 → the house runs off the batteries → discharging → positive after
    # C.negate. Unambiguous: p_aio_total ~ p_load. Per-AIO parts sum to the total.
    assert gw.p_aio_total > 0
    assert gw.p_liberty > 0
    assert gw.p_aio1_inverter > 0 and gw.p_aio2_inverter > 0
    assert gw.p_aio1_inverter + gw.p_aio2_inverter == pytest.approx(gw.p_aio_total)
