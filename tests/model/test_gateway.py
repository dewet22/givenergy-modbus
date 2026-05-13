import pytest

from givenergy_modbus.model.gateway import Gateway, Gateway2, select_gateway
from givenergy_modbus.model.inverter import WorkMode
from givenergy_modbus.model.register import IR
from givenergy_modbus.model.register_cache import RegisterCache


def _cache(values: dict) -> RegisterCache:
    return RegisterCache(values)


def _fw_cache(version_suffix: int) -> dict:
    """Build register values for a gateway version string."""
    # IR(1600)='G','A', IR(1601)='0','0', IR(1602)=0x0000, IR(1603)=version_suffix
    return {
        IR(1600): 0x4741,  # 'G','A'
        IR(1601): 0x3030,  # '0','0'
        IR(1602): 0x0000,
        IR(1603): version_suffix,
    }


def test_gateway_empty():
    gw = Gateway.from_register_cache(RegisterCache())
    assert gw.is_valid() is False
    assert gw.software_version is None  # type: ignore[attr-defined]


def test_gateway2_empty():
    gw2 = Gateway2.from_register_cache(RegisterCache())
    assert gw2.is_valid() is False


def test_software_version_decoding():
    cache = _cache(_fw_cache(9))
    gw = Gateway.from_register_cache(cache)
    assert gw.software_version == "GA000009"  # type: ignore[attr-defined]
    assert gw.is_valid() is True


def test_software_version_v2():
    cache = _cache(_fw_cache(10))
    gw2 = Gateway2.from_register_cache(cache)
    assert gw2.software_version == "GA0000010"  # type: ignore[attr-defined]
    assert gw2.is_valid() is True


def test_select_gateway_returns_gateway_for_v9():
    cache = _cache(_fw_cache(9))
    gw = select_gateway(cache)
    assert isinstance(gw, Gateway)


def test_select_gateway_returns_gateway2_for_v10():
    cache = _cache(_fw_cache(10))
    gw = select_gateway(cache)
    assert isinstance(gw, Gateway2)


def test_select_gateway_returns_gateway_for_empty_cache():
    gw = select_gateway(RegisterCache())
    assert isinstance(gw, Gateway)


def test_gateway_power_readings():
    cache = _cache(
        {
            IR(1608): 2310,  # v_grid = 231.0 V
            IR(1609): 100,  # i_grid = 10.0 A
            IR(1617): 3000,  # p_pv = 3000 W
            IR(1618): 2000,  # p_load = 2000 W
            IR(1619): 65536 - 500,  # p_liberty = -500 (int16)
            IR(1604): 2,  # work_mode = ON_GRID
        }
    )
    gw = Gateway.from_register_cache(cache)
    assert gw.v_grid == 231.0  # type: ignore[attr-defined]
    assert gw.i_grid == 10.0  # type: ignore[attr-defined]
    assert gw.p_pv == 3000  # type: ignore[attr-defined]
    assert gw.p_load == 2000  # type: ignore[attr-defined]
    assert gw.p_liberty == -500  # type: ignore[attr-defined]
    assert gw.work_mode == WorkMode.ON_GRID  # type: ignore[attr-defined]


def test_gateway_energy_totals_v1():
    # Gateway v1: high register first, then low
    cache = _cache({IR(1641): 1, IR(1642): 0})  # 1<<16 = 65536 raw → 6553.6 deci
    gw = Gateway.from_register_cache(cache)
    assert gw.e_grid_import_total == pytest.approx(6553.6)  # type: ignore[attr-defined]


def test_gateway2_energy_totals_swapped():
    # Gateway2: LOW register first (IR(1642) is high, IR(1641) is low — register order swapped)
    cache = _cache({IR(1641): 0, IR(1642): 1})  # swap: high=IR(1642)=1, low=IR(1641)=0 → 6553.6
    gw2 = Gateway2.from_register_cache(cache)
    assert gw2.e_grid_import_total == pytest.approx(6553.6)  # type: ignore[attr-defined]


def test_gateway_first_inverter_serial():
    cache = _cache(
        {
            IR(1627): 0x4142,
            IR(1628): 0x4344,
            IR(1629): 0x4546,
            IR(1630): 0x4748,
            IR(1631): 0x4900,
        }
    )
    gw = Gateway.from_register_cache(cache)
    assert gw.first_inverter_serial_number == "ABCDEFGHI"  # type: ignore[attr-defined]


def test_gateway_v1_aio_serial_address():
    cache = _cache(
        {
            IR(1831): 0x5152,
            IR(1832): 0x5354,
            IR(1833): 0x5556,
            IR(1834): 0x5758,
            IR(1835): 0x5900,
        }
    )
    gw = Gateway.from_register_cache(cache)
    assert gw.aio1_serial_number == "QRSTUVWXY"  # type: ignore[attr-defined]


def test_gateway2_aio_serial_address_different():
    # Gateway2 aio1_serial starts at IR(1841), not IR(1831)
    cache = _cache(
        {
            IR(1841): 0x5152,
            IR(1842): 0x5354,
            IR(1843): 0x5556,
            IR(1844): 0x5758,
            IR(1845): 0x5900,
        }
    )
    gw2 = Gateway2.from_register_cache(cache)
    assert gw2.aio1_serial_number == "QRSTUVWXY"  # type: ignore[attr-defined]


def test_gateway_aio_soc():
    cache = _cache({IR(1801): 85, IR(1802): 72, IR(1803): 60})
    gw = Gateway.from_register_cache(cache)
    assert gw.aio1_soc == 85  # type: ignore[attr-defined]
    assert gw.aio2_soc == 72  # type: ignore[attr-defined]
    assert gw.aio3_soc == 60  # type: ignore[attr-defined]
