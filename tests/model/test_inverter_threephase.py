import pytest

from givenergy_modbus.model.inverter import Model, SinglePhaseInverter, Status
from givenergy_modbus.model.inverter_threephase import (
    THREE_PHASE_SLOTS,
    ThreePhaseInverter,
    ThreePhaseInverterRegisterGetter,
    select_inverter,
)
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


def test_hr101_104_phase_split():
    """HR(101-104) carry the three-phase R/S/T grid adjustment meaning.

    Not the single-phase grid_import_limit / enable_lora / self-heating names.
    """
    cache = _cache({HR(101): 11, HR(102): 22, HR(103): 33, HR(104): 44})
    tph = ThreePhaseInverter.from_register_cache(cache)
    dump = tph.model_dump()

    # Three-phase names present and reading the right addresses.
    assert dump["grid_r_voltage_adjustment"] == 11
    assert dump["grid_s_voltage_adjustment"] == 22
    assert dump["grid_t_voltage_adjustment"] == 33
    assert dump["grid_power_adjustment"] == 44

    # Single-phase-only names must NOT leak onto the three-phase model.
    for name in (
        "grid_import_limit",
        "grid_import_limit_enabled",
        "enable_lora",
        "enable_battery_self_heating",
    ):
        assert name not in dump

    # The single-phase model reads the same addresses under the 1ph names instead.
    sph = SinglePhaseInverter.from_register_cache(cache).model_dump()
    assert sph["grid_import_limit"] == 11
    assert sph["grid_import_limit_enabled"] is True  # HR(102) = 22 → truthy bool
    assert "grid_r_voltage_adjustment" not in sph


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
        (IR(1140), 65536 - 50, "i_battery", -0.5),  # int16 at centi scale
        (HR(1002), 95, "active_rate", 95),
    ],
)
def test_individual_fields(reg, value, field, expected):
    cache = _cache({reg: value})
    tph = ThreePhaseInverter.from_register_cache(cache)
    assert getattr(tph, field) == expected


def test_i_battery_centi_scale():
    """i_battery on three-phase is centi (÷100), matching single-phase IR(51).

    Field-confirmed against a real GIV-3HY-11 HV capture: the V×I identity at the
    battery terminals only balances against p_battery_charge under the centi scale.
    """
    neg = ThreePhaseInverter.from_register_cache(_cache({IR(1140): 65536 - 50}))
    assert neg.i_battery == pytest.approx(-0.50)
    pos = ThreePhaseInverter.from_register_cache(_cache({IR(1140): 250}))
    assert pos.i_battery == pytest.approx(2.50)


def test_p_battery_derived_from_charge_discharge():
    """Three-phase p_battery is derived: discharge − charge (+ve = discharging).

    Sign matches single-phase, where battery_discharge_power = max(0, p_battery).
    The inherited single-phase IR(52) reads frozen on three-phase firmware, so the
    register-backed field is dropped in favour of this computed one.
    """
    # discharge 0, charge 200.0 → -200.0 (charging)
    charging = ThreePhaseInverter.from_register_cache(_cache({IR(1136): 0, IR(1137): 0, IR(1138): 0, IR(1139): 2000}))
    assert charging.p_battery == pytest.approx(-200.0)  # type: ignore[attr-defined]
    assert charging.battery_charge_power == pytest.approx(200.0)  # type: ignore[attr-defined]
    assert charging.battery_discharge_power == pytest.approx(0.0)  # type: ignore[attr-defined]

    # discharge 350.0, charge 0 → +350.0 (discharging)
    discharging = ThreePhaseInverter.from_register_cache(
        _cache({IR(1136): 0, IR(1137): 3500, IR(1138): 0, IR(1139): 0})
    )
    assert discharging.p_battery == pytest.approx(350.0)  # type: ignore[attr-defined]

    # Either input missing → None (matches single-phase computed-field posture)
    assert ThreePhaseInverter.from_register_cache(_cache({IR(1136): 0, IR(1137): 100})).p_battery is None  # type: ignore[attr-defined]
    assert ThreePhaseInverter.from_register_cache(RegisterCache()).p_battery is None  # type: ignore[attr-defined]

    assert "p_battery" in discharging.model_dump()


def test_e_battery_throughput_derived_from_totals():
    """Three-phase e_battery_throughput = charge_total + discharge_total (kWh)."""
    inv = ThreePhaseInverter.from_register_cache(_cache({IR(1390): 0, IR(1391): 100, IR(1394): 0, IR(1395): 50}))
    # discharge_total 10.0 + charge_total 5.0 = 15.0
    assert inv.e_battery_throughput == pytest.approx(15.0)  # type: ignore[attr-defined]

    # Either input missing → None
    missing = ThreePhaseInverter.from_register_cache(_cache({IR(1394): 0, IR(1395): 50}))
    assert missing.e_battery_throughput is None  # type: ignore[attr-defined]
    assert ThreePhaseInverter.from_register_cache(RegisterCache()).e_battery_throughput is None  # type: ignore[attr-defined]

    assert "e_battery_throughput" in inv.model_dump()


def test_derived_battery_fields_are_not_register_backed():
    """p_battery / e_battery_throughput are computed fields, not LUT entries."""
    assert ThreePhaseInverter.precision_of("p_battery") is None
    assert ThreePhaseInverter.precision_of("e_battery_throughput") is None
    assert ThreePhaseInverterRegisterGetter.registers_of("p_battery") == ()
    assert ThreePhaseInverterRegisterGetter.registers_of("e_battery_throughput") == ()


def test_three_phase_inverter_slot_map():
    tph = ThreePhaseInverter.from_register_cache(RegisterCache())
    assert tph.slot_map is THREE_PHASE_SLOTS


def test_select_inverter_three_phase():
    result = select_inverter(Model.HYBRID_3PH, RegisterCache())
    assert isinstance(result, ThreePhaseInverter)


def test_select_inverter_single_phase():
    result = select_inverter(Model.HYBRID, RegisterCache())
    assert isinstance(result, SinglePhaseInverter)


def test_select_inverter_residential_aio_is_single_phase():
    """Residential ALL_IN_ONE (0x8001) decodes single-phase, not three-phase.

    Decoding it as ThreePhaseInverter shadows ~30 live fields (battery_soc, v_ac1, f_ac1,
    firmware, charge slots, status…) to the IR/HR(1000+) addresses the AIO doesn't expose,
    zeroing them; its data actually lives in the single-phase IR(0)/IR(180) banks. Verified
    against a real AIO register dump (#105).
    """
    assert isinstance(select_inverter(Model.ALL_IN_ONE, RegisterCache()), SinglePhaseInverter)


def test_work_time_total_hours_rename_and_deprecated_alias():
    """ThreePhaseInverter inherits the rename via the merged LUT and exposes the same alias shim."""
    import warnings

    cache = _cache({IR(47): 0, IR(48): 385})
    tph = ThreePhaseInverter.from_register_cache(cache)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        assert tph.work_time_total_hours == 385  # type: ignore[attr-defined]
    assert [x for x in w if issubclass(x.category, DeprecationWarning)] == []

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        assert tph.work_time_total == 385  # type: ignore[attr-defined]
    deprecations = [x for x in w if issubclass(x.category, DeprecationWarning)]
    assert len(deprecations) == 1
    assert "work_time_total_hours" in str(deprecations[0].message)

    dumped = tph.model_dump()
    assert "work_time_total_hours" in dumped
    assert "work_time_total" not in dumped


def test_battery_reserve_soc_rename_and_deprecated_alias():
    """battery_power_cutoff (HR1078) is renamed to battery_reserve_soc; old name warns for a release."""
    import warnings

    cache = _cache({HR(1078): 10})
    tph = ThreePhaseInverter.from_register_cache(cache)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        assert tph.battery_reserve_soc == 10  # type: ignore[attr-defined]
    assert [x for x in w if issubclass(x.category, DeprecationWarning)] == []

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        assert tph.battery_power_cutoff == 10  # type: ignore[attr-defined]
    deprecations = [x for x in w if issubclass(x.category, DeprecationWarning)]
    assert len(deprecations) == 1
    assert "battery_reserve_soc" in str(deprecations[0].message)

    dumped = tph.model_dump()
    assert "battery_reserve_soc" in dumped
    assert "battery_power_cutoff" not in dumped


def test_p_pv_sum():
    tph = ThreePhaseInverter.from_register_cache(_cache({IR(1017): 0, IR(1018): 3000, IR(1019): 0, IR(1020): 2000}))
    assert tph.p_pv() == pytest.approx(300.0 + 200.0)  # type: ignore[attr-defined]

    tph_partial = ThreePhaseInverter.from_register_cache(_cache({IR(1017): 0, IR(1018): 3000}))
    assert tph_partial.p_pv() is None  # type: ignore[attr-defined]


def test_e_pv_day_uses_combined_register():
    tph = ThreePhaseInverter.from_register_cache(_cache({IR(1412): 0, IR(1413): 450}))
    assert tph.e_pv_day() == pytest.approx(450 * 0.1)  # type: ignore[attr-defined]

    tph_empty = ThreePhaseInverter.from_register_cache(RegisterCache())
    assert tph_empty.e_pv_day() is None  # type: ignore[attr-defined]


def test_battery_capacity_kwh():
    # HYBRID_3PH: system_battery_voltage = 76.8 V; 100 Ah → 7.68 kWh
    tph = ThreePhaseInverter.from_register_cache(_cache({HR(0): 0x4001, HR(55): 100}))
    assert tph.battery_capacity_kwh == pytest.approx(7.68)  # type: ignore[attr-defined]
    assert "battery_capacity_kwh" in tph.model_dump()

    tph_no_ah = ThreePhaseInverter.from_register_cache(_cache({HR(0): 0x4001}))
    assert tph_no_ah.battery_capacity_kwh is None  # type: ignore[attr-defined]


def test_three_phase_inverter_is_ac_coupled():
    """is_ac_coupled is True for the AC three-phase model, False for DC-coupled 3ph.

    This is the case PlantCapabilities.is_three_phase deliberately excludes downstream,
    but the inverter field must still report topology correctly (the field is duplicated
    onto ThreePhaseInverter, not inherited from SinglePhaseInverter).
    """
    ac3 = ThreePhaseInverter.from_register_cache(_cache({HR(0): 0x6001}))
    assert ac3.model is Model.AC_3PH
    assert ac3.is_ac_coupled is True
    assert ac3.model_dump()["is_ac_coupled"] is True

    for dtc in (0x4001, 0x8001):  # HYBRID_3PH, ALL_IN_ONE
        inv = ThreePhaseInverter.from_register_cache(_cache({HR(0): dtc}))
        assert inv.is_ac_coupled is False, f"{inv.model} should not be AC-coupled"


def test_directional_power_aliases():
    """Canonical directional-power names alias the 3-phase native registers (#205)."""
    tph = ThreePhaseInverter.from_register_cache(
        _cache(
            {
                IR(1079): 0,
                IR(1080): 3500,  # p_meter_import = 350.0
                IR(1081): 0,
                IR(1082): 0,  # p_meter_export = 0.0
                IR(1136): 0,
                IR(1137): 0,  # p_battery_discharge = 0.0
                IR(1138): 0,
                IR(1139): 2000,  # p_battery_charge = 200.0
            }
        )
    )
    assert tph.grid_import_power == pytest.approx(350.0)  # type: ignore[attr-defined]
    assert tph.grid_export_power == pytest.approx(0.0)  # type: ignore[attr-defined]
    assert tph.battery_charge_power == pytest.approx(200.0)  # type: ignore[attr-defined]
    assert tph.battery_discharge_power == pytest.approx(0.0)  # type: ignore[attr-defined]

    # Missing registers → None
    empty = ThreePhaseInverter.from_register_cache(_cache({}))
    assert empty.grid_import_power is None  # type: ignore[attr-defined]
    assert empty.grid_export_power is None  # type: ignore[attr-defined]
    assert empty.battery_charge_power is None  # type: ignore[attr-defined]
    assert empty.battery_discharge_power is None  # type: ignore[attr-defined]
