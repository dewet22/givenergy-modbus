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
    i = Inverter.from_orm(register_cache_inverter_daytime_discharging_with_solar_generation)
    b = Battery.from_orm(register_cache_battery_daytime_discharging)

    assert isinstance(i, Inverter)
    assert isinstance(b, Battery)

    p = Plant(inverter=i, batteries=[b])

    assert p.inverter == i
    assert isinstance(p.inverter, Inverter)
    assert p.batteries[0] == b
    assert isinstance(p.batteries[0], Battery)

    d = p.dict()
    assert d.keys() == {'inverter', 'batteries'}
    j = p.json()
    assert len(j) > 5000
