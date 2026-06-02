from pathlib import Path

from givenergy_modbus.model.ems import Ems
from givenergy_modbus.model.inverter import Status
from givenergy_modbus.model.meter import MeterStatus
from givenergy_modbus.model.register import HR, IR
from givenergy_modbus.model.register_cache import RegisterCache
from givenergy_modbus.testing.mock_plant import plant_from_capture


def _cache(values: dict) -> RegisterCache:
    return RegisterCache(values)


def test_ems_empty():
    ems = Ems.from_register_cache(RegisterCache())
    assert ems.is_valid() is False
    assert all(v is None for v in ems.model_dump().values())


def test_ems_is_valid_when_status_present():
    ems = Ems.from_register_cache(_cache({IR(2040): 1}))
    assert ems.is_valid() is True


def test_plant_configuration():
    cache = _cache(
        {
            HR(2040): 1,  # plant_status = NORMAL
            HR(2041): 2,  # expected_inverter_count
            HR(2042): 1,  # expected_meter_count
            HR(2043): 0,  # expected_car_charger_count
            HR(2071): 5000,  # export_power_limit
        }
    )
    ems = Ems.from_register_cache(cache)
    assert ems.plant_status == Status.NORMAL  # type: ignore[attr-defined]
    assert ems.expected_inverter_count == 2  # type: ignore[attr-defined]
    assert ems.expected_meter_count == 1  # type: ignore[attr-defined]
    assert ems.export_power_limit == 5000  # type: ignore[attr-defined]


def test_plant_enabled_readback():
    """plant_enabled is a boolean read-back of HR(2040) — the register set_ems_plant writes."""
    # enabled (HR2040 != 0)
    assert Ems.from_register_cache(_cache({HR(2040): 1})).plant_enabled is True
    # disabled (HR2040 == 0)
    assert Ems.from_register_cache(_cache({HR(2040): 0})).plant_enabled is False
    # unread → None, and must not break the "all None when empty" contract
    empty = Ems.from_register_cache(RegisterCache())
    assert empty.plant_enabled is None
    assert "plant_enabled" in empty.model_dump()


def test_charge_and_discharge_slots():
    cache = _cache(
        {
            HR(2053): 700,
            HR(2054): 800,
            HR(2055): 90,
            HR(2044): 1700,
            HR(2045): 2300,
            HR(2046): 20,
        }
    )
    ems = Ems.from_register_cache(cache)
    charge_1 = ems.charge_slot_1  # type: ignore[attr-defined]
    assert charge_1.start.hour == 7
    assert charge_1.start.minute == 0
    assert charge_1.end.hour == 8
    assert charge_1.end.minute == 0
    assert ems.charge_target_1 == 90  # type: ignore[attr-defined]
    discharge_1 = ems.discharge_slot_1  # type: ignore[attr-defined]
    assert discharge_1.start.hour == 17
    assert discharge_1.start.minute == 0
    assert ems.discharge_target_1 == 20  # type: ignore[attr-defined]


def test_meter_status_bitfield():
    # IR(2043) packs 8 × 2-bit meter statuses, LSB-first: slot N occupies bits [2N-2:2N-1].
    # C.bitfield uses MSB-first indices, so slot N = bitfield(16-2N, 17-2N).
    # meter_1 (bits[1:0] = LSB bits 0-1 → 0b01 = ONLINE=1 → 0x0001)
    # meter_2 (bits[3:2] → 0b10 = OFFLINE=2 → 0x0008)
    # meter_3 (bits[5:4] → 0b00 = DISABLED)
    packed = 0b01 | (0b10 << 2)  # = 0x0009
    cache = _cache({IR(2043): packed})
    ems = Ems.from_register_cache(cache)
    assert ems.meter_1_status == MeterStatus.ONLINE  # type: ignore[attr-defined]
    assert ems.meter_2_status == MeterStatus.OFFLINE  # type: ignore[attr-defined]
    assert ems.meter_3_status == MeterStatus.DISABLED  # type: ignore[attr-defined]


def test_inverter_status_bitfield():
    # IR(2045) packs 4 × 3-bit inverter statuses, LSB-first: slot N occupies bits [3N-3:3N-1].
    # C.bitfield uses MSB-first indices, so slot N = bitfield(16-3N, 18-3N).
    # The 3-bit code is surfaced as a hex string (uninterpreted raw code, #108) — NOT the
    # inverter Status enum, whose values don't match this field's encoding.
    # inverter_1 (bits[2:0] → 0b001 = code 1 → "1")
    # inverter_2 (bits[5:3] → 0b011 = code 3 → "3")
    packed = 0b001 | (0b011 << 3)  # = 0x0019
    cache = _cache({IR(2045): packed})
    ems = Ems.from_register_cache(cache)
    assert ems.inverter_1_status == "1"  # type: ignore[attr-defined]
    assert ems.inverter_2_status == "3"  # type: ignore[attr-defined]


def test_bitfield_decode_matches_fixture():
    """Regression for #108 — per-slot status bitfields use LSB-first layout.

    Pinned to the committed ems_2_inv_3_bat_a fixture where:
    - IR(2043)=17 (0b10001): bits[1:0]=01=ONLINE (meter_1 −94 W), bits[5:4]=01=ONLINE
      (meter_3 583 W), everything else DISABLED — verified against the meter power regs.
    - IR(2045)=18 (0b10010): bits[2:0]=010=code 2 (inv_1 present), bits[5:3]=010=code 2
      (inv_2 present), inv_3/inv_4 = code 0 (empty). Per-slot inverter status is an
      uninterpreted hex code (the GivEnergy app doesn't expose it); only 0=empty and
      2=present/idle are verified. Presence is authoritatively given by `inverter_count`.
    """
    fixture = Path(__file__).parent.parent / "fixtures/captures/ems_2_inv_3_bat_a/ems_arm1036_30min.log"
    plant = plant_from_capture(str(fixture))
    cache = plant.register_caches[0x11]
    ems = Ems.from_register_cache(cache)

    # Meter statuses — only meters with power should be ONLINE (verified vs power regs)
    assert ems.meter_1_status == MeterStatus.ONLINE  # type: ignore[attr-defined]  # -94 W
    assert ems.meter_2_status == MeterStatus.DISABLED  # type: ignore[attr-defined]  # 0 W
    assert ems.meter_3_status == MeterStatus.ONLINE  # type: ignore[attr-defined]  # +583 W
    for n in range(4, 9):
        assert getattr(ems, f"meter_{n}_status") == MeterStatus.DISABLED  # type: ignore[attr-defined]

    # Inverter statuses — raw hex codes: inv_1/inv_2 present (code 2), inv_3/inv_4 empty (0)
    assert ems.inverter_1_status == "2"  # type: ignore[attr-defined]
    assert ems.inverter_2_status == "2"  # type: ignore[attr-defined]
    assert ems.inverter_3_status == "0"  # type: ignore[attr-defined]
    assert ems.inverter_4_status == "0"  # type: ignore[attr-defined]
    # inverter_count is the authoritative presence signal (#108)
    assert ems.inverter_count == 2  # type: ignore[attr-defined]


def test_per_inverter_data():
    cache = _cache(
        {
            IR(2044): 2,
            IR(2054): 3500,
            IR(2055): 65536 - 500,  # -500 W (int16)
            IR(2058): 80,
            IR(2059): 65,
            IR(2062): 350,
            IR(2066): 0x4142,
            IR(2067): 0x4344,
            IR(2068): 0x4546,
            IR(2069): 0x4748,
            IR(2070): 0x4900,
        }
    )
    ems = Ems.from_register_cache(cache)
    assert ems.inverter_count == 2  # type: ignore[attr-defined]
    assert ems.inverter_1_power == 3500  # type: ignore[attr-defined]
    assert ems.inverter_2_power == -500  # type: ignore[attr-defined]
    assert ems.inverter_1_soc == 80  # type: ignore[attr-defined]
    assert ems.inverter_2_soc == 65  # type: ignore[attr-defined]
    assert ems.inverter_1_temp == 35.0  # type: ignore[attr-defined]
    assert ems.inverter_1_serial_number == "ABCDEFGHI"  # type: ignore[attr-defined]


def test_plant_power_summary():
    cache = _cache(
        {
            IR(2086): 5000,
            IR(2087): 4800,
            IR(2089): 65536 - 1000,  # -1000 W import (negative = import)
            IR(2090): 65536 - 2000,  # discharging
            IR(2091): 15000,
        }
    )
    ems = Ems.from_register_cache(cache)
    assert ems.calc_load_power == 5000  # type: ignore[attr-defined]
    assert ems.measured_load_power == 4800  # type: ignore[attr-defined]
    assert ems.grid_meter_power == -1000  # type: ignore[attr-defined]
    assert ems.total_battery_power == -2000  # type: ignore[attr-defined]
    assert ems.remaining_battery_wh == 15000  # type: ignore[attr-defined]
