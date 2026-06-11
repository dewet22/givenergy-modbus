from givenergy_modbus.model.meter import Meter, MeterProduct
from givenergy_modbus.model.register import IR, MR
from givenergy_modbus.model.register_cache import RegisterCache


def _meter_cache(ir_values: dict) -> RegisterCache:
    return RegisterCache({IR(k): v for k, v in ir_values.items()})


def _meter_product_cache(mr_values: dict) -> RegisterCache:
    return RegisterCache({MR(k): v for k, v in mr_values.items()})


# ---------------------------------------------------------------------------
# Meter (FC 0x04)
# ---------------------------------------------------------------------------


def test_meter_empty():
    m1 = Meter()
    m2 = Meter.from_register_cache(RegisterCache())
    assert m1.model_dump() == m2.model_dump()
    assert all(v is None for v in m1.model_dump().values())
    assert m1.is_valid() is False


def test_meter_from_synthetic_registers():
    cache = _meter_cache(
        {
            60: 2300,  # v_phase_1 = 230.0 V  (deci)
            61: 2310,  # v_phase_2 = 231.0 V
            62: 2290,  # v_phase_3 = 229.0 V
            63: 1000,  # i_phase_1 = 10.00 A  (centi)
            64: 950,  # i_phase_2 = 9.50 A
            65: 1050,  # i_phase_3 = 10.50 A
            66: 50,  # i_ln      = 0.50 A
            67: 3000,  # i_total   = 30.00 A
            68: 2300,  # p_active_phase_1 = 2300 W  (int16)
            69: 2200,  # p_active_phase_2
            70: 2400,  # p_active_phase_3
            71: 6900,  # p_active_total
            72: 100,  # p_reactive_phase_1
            73: 100,
            74: 100,
            75: 300,  # p_reactive_total
            76: 23020,  # p_apparent_phase_1 = 2302.0 VA  (deci)
            77: 22020,
            78: 24020,
            79: 30900,  # p_apparent_total = 3090.0 VA
            80: 9990,  # pf_phase_1 = 0.999  (signed 1/10000)
            81: 9980,
            82: 9970,
            83: 9980,  # pf_total
            84: 5000,  # frequency = 50.00 Hz  (centi)
            85: 12345,  # e_import_active = 1234.5 kWh  (deci)
            86: 100,
            87: 500,  # e_export_active = 50.0 kWh
            88: 50,
        }
    )
    m = Meter.from_register_cache(cache)
    assert m.is_valid() is True
    assert m.v_phase_1 == 230.0  # type: ignore[attr-defined]
    assert m.v_phase_2 == 231.0  # type: ignore[attr-defined]
    assert m.v_phase_3 == 229.0  # type: ignore[attr-defined]
    assert m.i_phase_1 == 10.0  # type: ignore[attr-defined]
    assert m.i_phase_2 == 9.5  # type: ignore[attr-defined]
    assert m.i_total == 30.0  # type: ignore[attr-defined]
    assert m.p_active_total == 6900  # type: ignore[attr-defined]
    assert m.p_apparent_total == 3090.0  # type: ignore[attr-defined]
    assert m.pf_total == 0.998  # type: ignore[attr-defined]
    assert m.frequency == 50.0  # type: ignore[attr-defined]
    assert m.e_import_active == 1234.5  # type: ignore[attr-defined]
    assert m.e_export_active == 50.0  # type: ignore[attr-defined]


def test_meter_negative_power():
    """int16 converter handles export (negative active power) correctly."""
    cache = _meter_cache({60: 2300, 71: 65536 - 1000})  # -1000 W export
    m = Meter.from_register_cache(cache)
    assert m.p_active_total == -1000  # type: ignore[attr-defined]


def test_meter_pf_signed_decode():
    """pf_* decode as signed int16 x 1e-4 (EE [-1, +1]) — not unsigned milli (#246).

    Raw values pinned from the committed EMS capture: meter 0x03 read 9998
    (near-unity import) and meter 0x01 read 64670 (-866 as int16; small export).
    The old C.milli decode produced the impossible 9.998 / 64.67.
    """
    m = Meter.from_register_cache(_meter_cache({60: 2300, 80: 9998, 83: 64670}))
    assert m.pf_phase_1 == 0.9998  # type: ignore[attr-defined]
    assert m.pf_total == -0.0866  # type: ignore[attr-defined]


def test_meter_apparent_power_unsigned_above_int16_range():
    """p_apparent_* is an unsigned magnitude — loads above 3.27 kVA must not go negative.

    The capture shows apparent power staying positive during export (p_active < 0),
    so the register is unsigned; a signed decode would overflow for any load above
    32767 raw (3276.7 VA) — e.g. an EV charger or kettle (#246).
    """
    m = Meter.from_register_cache(_meter_cache({60: 2300, 79: 40000}))
    assert m.p_apparent_total == 4000.0  # type: ignore[attr-defined]


def test_meter_pf_precision():
    """precision_of reports 4 decimal places for the pf_signed-converted fields."""
    from givenergy_modbus.model.meter import MeterRegisterGetter

    assert MeterRegisterGetter.precision_of("pf_total") == 4
    assert MeterRegisterGetter.precision_of("p_apparent_total") == 1


def test_meter_is_valid_zero_voltage():
    cache = _meter_cache({60: 0})
    assert Meter.from_register_cache(cache).is_valid() is False


# ---------------------------------------------------------------------------
# MeterProduct (FC 0x16)
# ---------------------------------------------------------------------------


def test_meter_product_empty():
    mp1 = MeterProduct()
    mp2 = MeterProduct.from_register_cache(RegisterCache())
    assert mp1.model_dump() == mp2.model_dump()
    assert all(v is None for v in mp1.model_dump().values())
    assert mp1.is_valid() is False


def test_meter_product_from_synthetic_registers():
    # "GIEV" serial, "ENGY" factory code
    cache = _meter_product_cache(
        {
            60: 0x4749,  # 'G','I'
            61: 0x4556,  # 'E','V'
            62: 0x454E,  # 'E','N'
            63: 0x4759,  # 'G','Y'
            64: 0,  # meter_type
            65: 1,  # hardware_version
            66: 2,  # software_version
            67: 1,  # modbus_id
            68: 9600,  # baud_rate
        }
    )
    mp = MeterProduct.from_register_cache(cache)
    assert mp.is_valid() is True
    assert mp.serial_number == "GIEV"  # type: ignore[attr-defined]
    assert mp.factory_code == "ENGY"  # type: ignore[attr-defined]
    assert mp.meter_type == 0  # type: ignore[attr-defined]
    assert mp.hardware_version == 1  # type: ignore[attr-defined]
    assert mp.software_version == 2  # type: ignore[attr-defined]
    assert mp.modbus_id == 1  # type: ignore[attr-defined]
    assert mp.baud_rate == 9600  # type: ignore[attr-defined]
