from givenergy_modbus.model.battery import Battery
from givenergy_modbus.model.inverter import Inverter  # type: ignore  # shut up mypy
from givenergy_modbus.model.plant import Plant
from tests.model.test_register_cache import (  # noqa: F401
    register_cache,
    register_cache_battery_daytime_discharging,
    register_cache_inverter_daytime_discharging_with_solar_generation,
)


def test_plant(  # noqa: F811
    register_cache_inverter_daytime_discharging_with_solar_generation,  # noqa: F811
    register_cache_battery_daytime_discharging,  # noqa: F811
):
    """Ensure we can instantiate a Plant from existing DTOs."""
    p = Plant(
        inverter_rc=register_cache_inverter_daytime_discharging_with_solar_generation,
        batteries_rcs=[register_cache_battery_daytime_discharging],
    )

    i = Inverter.from_orm(register_cache_inverter_daytime_discharging_with_solar_generation)
    assert i.inverter_serial_number == 'SA1234G567'
    b = Battery.from_orm(register_cache_battery_daytime_discharging)
    assert b.battery_serial_number == 'BG1234G567'

    assert isinstance(p.inverter, Inverter)
    assert p.inverter == i
    assert isinstance(p.batteries[0], Battery)
    assert p.batteries[0] == b

    d = p.dict()
    assert d.keys() == {'inverter_rc', 'batteries_rcs'}
    j = p.json()
    assert len(j) > 5000

    assert Plant(**p.dict()) == p
    assert Plant.from_orm(p) == p
