from typing import Any, Dict, Tuple

import pytest

from givenergy_modbus.model.battery import Battery
from givenergy_modbus.model.inverter import Inverter  # type: ignore  # shut up mypy
from givenergy_modbus.model.plant import Plant
from givenergy_modbus.model.register import HoldingRegister  # type: ignore  # shut up mypy
from givenergy_modbus.pdu import HeartbeatResponse, ReadRegistersResponse
from tests import RESPONSE_PDU_MESSAGES, _lookup_pdu_class
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
    p = Plant()
    assert p.dict() == {'number_batteries': 0, 'register_caches': {50: {'slave_address': 50}}}
    assert p.json() == '{"register_caches": {"50": {"slave_address": 50}}, "number_batteries": 0}'

    p = Plant(number_batteries=2)
    assert p.dict() == {
        'number_batteries': 2,
        'register_caches': {50: {'slave_address': 50}, 51: {'slave_address': 51}},
    }
    assert p.json() == (
        '{"register_caches": {"50": {"slave_address": 50}, "51": {"slave_address": 51}}, ' '"number_batteries": 2}'
    )

    p = Plant(number_batteries=1)
    assert p.dict() == {'number_batteries': 1, 'register_caches': {50: {'slave_address': 50}}}
    assert p.json() == '{"register_caches": {"50": {"slave_address": 50}}, "number_batteries": 1}'
    p.register_caches[0x32] = register_cache_inverter_daytime_discharging_with_solar_generation
    p.register_caches[0x32].update(register_cache_battery_daytime_discharging.items())

    i = Inverter.from_orm(register_cache_inverter_daytime_discharging_with_solar_generation)
    assert i.inverter_serial_number == 'SA1234G567'
    b = Battery.from_orm(register_cache_battery_daytime_discharging)
    assert b.battery_serial_number == 'BG1234G567'

    assert isinstance(p.inverter, Inverter)
    assert p.inverter == i
    assert isinstance(p.batteries[0], Battery)
    assert p.batteries[0] == b

    d = p.dict()
    assert d.keys() == {'register_caches', 'number_batteries'}
    assert d['register_caches'] == p.register_caches
    j = p.json()
    assert len(j) > 5000

    assert Plant(**p.dict()) == p
    assert Plant.from_orm(p) == p


@pytest.mark.parametrize("data", RESPONSE_PDU_MESSAGES)
def test_update(data: Tuple[str, Dict[str, Any], bytes, bytes]):
    """Ensure we can update a Plant from PDU Response messages."""
    p = Plant()
    assert p.dict() == {'number_batteries': 0, 'register_caches': {50: {'slave_address': 50}}}
    assert p.json() == '{"register_caches": {"50": {"slave_address": 50}}, "number_batteries": 0}'

    pdu_fn, pdu_fn_kwargs, _, encoded_pdu = data

    pdu: ReadRegistersResponse = _lookup_pdu_class(pdu_fn)(**pdu_fn_kwargs)

    p.update(pdu)
    if isinstance(pdu, HeartbeatResponse):
        # plant state unchanged
        assert p.dict() == {'number_batteries': 0, 'register_caches': {50: {'slave_address': 50}}}
        assert p.json() == '{"register_caches": {"50": {"slave_address": 50}}, "number_batteries": 0}'
    else:
        if isinstance(pdu, ReadRegistersResponse):
            d = p.dict()
            assert d.keys() == {'number_batteries', 'register_caches'}
            assert d['register_caches'].keys() == {50}
            assert len(d['register_caches'][50].keys()) == 61
            assert len(p.json()) > 800
        else:  # WriteHoldingRegisterResponse
            assert p.dict() == {
                'number_batteries': 0,
                'register_caches': {50: {HoldingRegister(35): 8764, 'slave_address': 50}},
            }
            assert (
                p.json() == '{"register_caches": {"50": {"slave_address": 50, "HR:35": 8764}}, "number_batteries": 0}'
            )
