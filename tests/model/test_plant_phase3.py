"""Tests for #106 Phase 3 — serial reconciliation and Plant.serial_index.

Covers:
- Plant.serial_index — new additive property
- Plant.add_direct_source() — inject direct-inverter caches for reconciliation
- Plant.inverters reconciliation — EMS + direct source merged by serial
- Client(host, plant=existing_plant) — shared-plant constructor kwarg
"""

from givenergy_modbus.model.devices import Inverter
from givenergy_modbus.model.inverter import Model
from givenergy_modbus.model.plant import Plant, PlantCapabilities
from givenergy_modbus.model.register import HR, IR
from givenergy_modbus.model.register_cache import RegisterCache
from tests.model.test_devices import _add_rollup_slot, _encode_serial

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _inverter_cache(serial: str) -> RegisterCache:
    """A minimal register cache that looks like a direct HYBRID_GEN1 inverter (serial in HR 13-17)."""
    values: dict = {}
    # 0x2001 with arm_fw century 4 (not in gen table) → resolve_model() returns HYBRID_GEN1
    values[HR(0)] = 0x2001
    values[HR(1)] = 0x0441
    for i, v in _encode_serial(serial).items():
        values[HR(13 + i)] = v
    return RegisterCache(values)


def _ems_plant(slot_serials: list[str]) -> Plant:
    """Build an EMS plant with managed-inverter rollup slots populated."""
    values: dict = {IR(2040): 1, IR(2044): len(slot_serials)}
    for idx, serial in enumerate(slot_serials, start=1):
        _add_rollup_slot(values, idx, serial=serial, power=1000 * idx, soc=50 + idx)
    plant = Plant()
    plant.capabilities = PlantCapabilities(device_type=Model.EMS, inverter_address=0x32)
    plant.register_caches[0x32] = RegisterCache(values)
    return plant


def _direct_plant(serial: str) -> Plant:
    """Build a plain single-inverter plant."""
    plant = Plant()
    plant.capabilities = PlantCapabilities(
        device_type=Model.HYBRID_GEN1,
        inverter_address=0x31,
    )
    plant.register_caches[0x31] = _inverter_cache(serial)
    return plant


# ---------------------------------------------------------------------------
# Plant.serial_index
# ---------------------------------------------------------------------------


def test_plant_serial_index_empty_on_fresh_plant():
    """A brand-new plant with no capabilities yields an empty serial_index."""
    assert Plant().serial_index == {}


def test_plant_serial_index_maps_direct_serial():
    """Non-EMS direct plant: serial_index maps the inverter serial to its Inverter facade."""
    plant = _direct_plant("AA2309B123")
    idx = plant.serial_index
    assert "AA2309B123" in idx
    assert isinstance(idx["AA2309B123"], Inverter)
    assert idx["AA2309B123"].data_source == "direct"


def test_plant_serial_index_maps_ems_rollup_serials():
    """EMS plant: serial_index maps each managed-inverter serial to a blinded Inverter."""
    plant = _ems_plant(["XX1234A567", "ZZ9876B543"])
    idx = plant.serial_index
    assert set(idx.keys()) == {"XX1234A567", "ZZ9876B543"}
    assert all(inv.data_source == "ems_rollup" for inv in idx.values())


# ---------------------------------------------------------------------------
# Plant.add_direct_source
# ---------------------------------------------------------------------------


def test_plant_add_direct_source_stores_caches():
    """add_direct_source() persists the caches in the plant (accessible for reconciliation)."""
    plant = _ems_plant(["XX1234A567"])
    direct_caches = {0x31: _inverter_cache("XX1234A567")}
    plant.add_direct_source(direct_caches)
    # The private store is accessible; check via the public reconciliation effect below
    # (also verify no exception is raised)
    assert plant.serial_index  # non-empty after reconciliation


# ---------------------------------------------------------------------------
# Plant.inverters reconciliation
# ---------------------------------------------------------------------------


def test_plant_inverters_unchanged_without_direct_sources():
    """Regression: EMS plant with no direct sources still returns blinded inverters only."""
    plant = _ems_plant(["XX1234A567", "ZZ9876B543"])
    inverters = plant.inverters
    assert len(inverters) == 2
    assert all(inv.data_source == "ems_rollup" for inv in inverters)


def test_plant_inverters_reconciles_matching_serial():
    """EMS + direct source with matching serial → merged Inverter (data_source='merged')."""
    plant = _ems_plant(["XX1234A567", "ZZ9876B543"])
    plant.add_direct_source({0x31: _inverter_cache("XX1234A567")})

    inverters = plant.inverters
    assert len(inverters) == 2
    by_serial = {inv.serial_number: inv for inv in inverters}

    merged = by_serial["XX1234A567"]
    assert merged.data_source == "merged", "direct+rollup serial should be merged"
    assert not merged.is_blinded

    blinded = by_serial["ZZ9876B543"]
    assert blinded.data_source == "ems_rollup", "unmatched EMS slot stays blinded"
    assert blinded.is_blinded


def test_plant_inverters_blinded_for_unmatched_ems_serial():
    """EMS slot whose serial has no matching direct source remains blinded."""
    plant = _ems_plant(["XX1234A567", "ZZ9876B543"])
    # Only provide a direct source for the first serial
    plant.add_direct_source({0x31: _inverter_cache("XX1234A567")})

    inverters = plant.inverters
    blinded_count = sum(1 for inv in inverters if inv.is_blinded)
    assert blinded_count == 1  # ZZ9876B543 still blinded


def test_plant_inverters_orphan_direct_with_no_ems_match():
    """Direct-source inverter whose serial is NOT in EMS rollup appears as from_direct."""
    plant = _ems_plant(["XX1234A567"])
    # Inject a direct source with a DIFFERENT serial (not managed by the EMS)
    plant.add_direct_source({0x31: _inverter_cache("FF0001C999")})

    inverters = plant.inverters
    serials = {inv.serial_number for inv in inverters}
    assert "XX1234A567" in serials  # blinded EMS slot still present
    assert "FF0001C999" in serials  # orphan direct source present as from_direct

    orphan = next(inv for inv in inverters if inv.serial_number == "FF0001C999")
    assert orphan.data_source == "direct"


def test_plant_serial_index_reflects_merged_source():
    """serial_index entry for a reconciled serial has data_source='merged'."""
    plant = _ems_plant(["XX1234A567"])
    plant.add_direct_source({0x31: _inverter_cache("XX1234A567")})
    assert plant.serial_index["XX1234A567"].data_source == "merged"


def test_plant_inverters_skips_direct_cache_with_no_dtc():
    """A direct-source cache that has no HR(0) (no DTC) is silently skipped."""
    plant = _ems_plant(["XX1234A567"])
    plant.add_direct_source({0x31: RegisterCache({})})
    inverters = plant.inverters
    assert len(inverters) == 1
    assert inverters[0].data_source == "ems_rollup"


def test_plant_inverters_skips_direct_cache_with_no_serial():
    """A direct-source cache that decodes to an empty serial is silently skipped."""
    plant = _ems_plant(["XX1234A567"])
    # DTC present but no HR(13-17) serial registers → serial decodes as empty
    plant.add_direct_source({0x31: RegisterCache({HR(0): 0x2001, HR(1): 0x0441})})
    inverters = plant.inverters
    assert len(inverters) == 1
    assert inverters[0].data_source == "ems_rollup"


# ---------------------------------------------------------------------------
# Client — shared-plant constructor kwarg
# ---------------------------------------------------------------------------


def test_client_accepts_existing_plant():
    """Client(host, plant=p) uses the supplied plant rather than creating a new one."""
    from givenergy_modbus.client.client import Client

    shared = Plant()
    client = Client("10.0.0.1", 8899, plant=shared)
    assert client.plant is shared


def test_client_creates_fresh_plant_when_none_supplied():
    """Regression: Client() with no plant arg still creates its own Plant."""
    from givenergy_modbus.client.client import Client

    client = Client("10.0.0.1", 8899)
    assert isinstance(client.plant, Plant)
