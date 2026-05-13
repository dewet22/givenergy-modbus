import pytest

from givenergy_modbus.model.inverter import Model, SinglePhaseInverter, Status
from givenergy_modbus.model.inverter_threephase import THREE_PHASE_SLOTS, ThreePhaseInverter, select_inverter
from givenergy_modbus.model.register import HR, IR
from givenergy_modbus.model.register_cache import RegisterCache


def _cache(values: dict) -> RegisterCache:
    return RegisterCache(values)


def test_empty_cache_gives_all_none():
    tph = ThreePhaseInverter.from_register_cache(RegisterCache())
    dump = tph.model_dump()
    # Computed fields aside, all raw values should be None
    assert dump["battery_soc"] is None
    assert dump["v_ac1"] is None
    assert dump["p_inverter_out"] is None
    assert dump["firmware_version"] is None


def test_three_phase_overrides_shadow_single_phase_registers():
    """Fields present in both LUTs must resolve to the three-phase register address."""
    # battery_soc: single-phase is IR(59), three-phase is IR(1132)
    cache = _cache({IR(59): 50, IR(1132): 80})
    tph = ThreePhaseInverter.from_register_cache(cache)
    assert tph.battery_soc == 80  # type: ignore[attr-defined]

    # v_ac1: single-phase is IR(5), three-phase is IR(1061)
    cache2 = _cache({IR(5): 2200, IR(1061): 2310})
    tph2 = ThreePhaseInverter.from_register_cache(cache2)
    assert tph2.v_ac1 == 231.0  # type: ignore[attr-defined]

    # status: single-phase is IR(0), three-phase is IR(1076)
    cache3 = _cache({IR(0): 3, IR(1076): 1})  # FAULT vs NORMAL
    tph3 = ThreePhaseInverter.from_register_cache(cache3)
    assert tph3.status == Status.NORMAL  # type: ignore[attr-defined]


def test_three_phase_grid_voltages():
    cache = _cache({IR(1061): 2310, IR(1062): 2290, IR(1063): 2300})
    tph = ThreePhaseInverter.from_register_cache(cache)
    assert tph.v_ac1 == 231.0  # type: ignore[attr-defined]
    assert tph.v_ac2 == 229.0  # type: ignore[attr-defined]
    assert tph.v_ac3 == 230.0  # type: ignore[attr-defined]


def test_three_phase_grid_currents():
    cache = _cache({IR(1064): 150, IR(1065): 145, IR(1066): 155})
    tph = ThreePhaseInverter.from_register_cache(cache)
    assert tph.i_ac1 == 15.0  # type: ignore[attr-defined]
    assert tph.i_ac2 == 14.5  # type: ignore[attr-defined]
    assert tph.i_ac3 == 15.5  # type: ignore[attr-defined]


def test_p_inverter_out_positive():
    # 3000 W: high=0, low=30000 → 30000 raw → 3000.0 W after /10
    cache = _cache({IR(1069): 0, IR(1070): 30000})
    tph = ThreePhaseInverter.from_register_cache(cache)
    assert tph.p_inverter_out == 3000.0  # type: ignore[attr-defined]


def test_p_inverter_out_negative():
    # -500 W: raw signed int32 0xFFFFF830 = -2000 → -200.0 W
    raw = (0x100000000 - 2000) & 0xFFFFFFFF
    high = raw >> 16
    low = raw & 0xFFFF
    cache = _cache({IR(1069): high, IR(1070): low})
    tph = ThreePhaseInverter.from_register_cache(cache)
    assert tph.p_inverter_out == -200.0  # type: ignore[attr-defined]


def test_pv_power_uint32():
    # p_pv1 at IR(1017/1018): 5000 W = 50000 deci units, high=0, low=50000
    cache = _cache({IR(1017): 0, IR(1018): 50000})
    tph = ThreePhaseInverter.from_register_cache(cache)
    assert tph.p_pv1 == 5000.0  # type: ignore[attr-defined]


def test_firmware_version_from_three_phase_registers():
    # firmware_version at IR(1325)+IR(1327) — shadows HR(19)+HR(21)
    cache = _cache({HR(19): 100, HR(21): 200, IR(1325): 305, IR(1327): 410})
    tph = ThreePhaseInverter.from_register_cache(cache)
    assert tph.firmware_version == "D0.305-A0.410"  # type: ignore[attr-defined]


def test_charge_slot_1_from_three_phase_registers():
    # charge_slot_1 at HR(1113/1114) shadows single-phase HR(94/95)
    cache = _cache({HR(94): 100, HR(95): 200, HR(1113): 630, HR(1114): 730})
    tph = ThreePhaseInverter.from_register_cache(cache)
    slot = tph.charge_slot_1  # type: ignore[attr-defined]
    assert slot is not None
    assert slot.start.hour == 6
    assert slot.start.minute == 30
    assert slot.end.hour == 7
    assert slot.end.minute == 30


def test_battery_soc_reserve_from_three_phase_registers():
    cache = _cache({HR(110): 10, HR(1109): 20})
    tph = ThreePhaseInverter.from_register_cache(cache)
    assert tph.battery_soc_reserve == 20  # type: ignore[attr-defined]


def test_eps_registers():
    cache = _cache(
        {
            IR(1181): 2310,
            IR(1182): 2290,
            IR(1183): 2300,
            IR(1187): 0,
            IR(1188): 10000,
            IR(1189): 0,
            IR(1190): 9500,
            IR(1191): 0,
            IR(1192): 10500,
        }
    )
    tph = ThreePhaseInverter.from_register_cache(cache)
    assert tph.v_eps_ac1 == 231.0  # type: ignore[attr-defined]
    assert tph.p_eps_ac1 == 1000.0  # type: ignore[attr-defined]
    assert tph.p_eps_ac2 == 950.0  # type: ignore[attr-defined]


def test_energy_totals():
    cache = _cache({IR(1374): 0, IR(1375): 123456})
    tph = ThreePhaseInverter.from_register_cache(cache)
    assert tph.e_pv_total == 12345.6  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "reg,value,field,expected",
    [
        (IR(1067), 5000, "f_ac1", 50.0),
        (IR(1068), 65535 - 100 + 1, "power_factor", -100),  # int16 negative
        (IR(1132), 75, "battery_soc", 75),
        (IR(1140), 65536 - 50, "i_battery", -5.0),  # int16 at deci scale
        (HR(1002), 95, "active_rate", 95),
    ],
)
def test_individual_fields(reg, value, field, expected):
    cache = _cache({reg: value})
    tph = ThreePhaseInverter.from_register_cache(cache)
    assert getattr(tph, field) == expected


def test_three_phase_inverter_slot_map():
    tph = ThreePhaseInverter.from_register_cache(RegisterCache())
    assert tph.slot_map is THREE_PHASE_SLOTS


def test_select_inverter_three_phase():
    result = select_inverter(Model.HYBRID_3PH, RegisterCache())
    assert isinstance(result, ThreePhaseInverter)


def test_select_inverter_single_phase():
    result = select_inverter(Model.HYBRID, RegisterCache())
    assert isinstance(result, SinglePhaseInverter)
