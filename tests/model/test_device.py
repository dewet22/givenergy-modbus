from enum import Enum
from typing import Callable

from pydantic import BaseConfig, create_model

from givenergy_modbus.model.register import HR, IR
from givenergy_modbus.model.register import DataType as DT
from givenergy_modbus.model.register import RegisterDefinition as Def
from givenergy_modbus.model.register import RegisterGetter

# fmt: off
HOLDING_REGISTERS: dict[HR, int] = {HR(i): v for i, v in enumerate([
    8193, 3, 2098, 513, 0, 50000, 3600, 1, 16967, 12594,  # 00x
    13108, 18229, 13879, 21313, 12594, 13108, 18229, 13879, 3005, 449,  # 01x
    1, 449, 2, 0, 32768, 30235, 6000, 1, 0, 0,  # 02x
    17, 0, 4, 7, 140, 22, 1, 1, 23, 57,  # 03x
    19, 1, 2, 0, 0, 0, 101, 1, 0, 0,  # 04x
    100, 0, 0, 1, 1, 160, 0, 0, 1, 0,  # 05x
    1500, 30, 30, 1840, 2740, 4700, 5198, 126, 27, 24,  # 06x
    28, 1840, 2620, 4745, 5200, 126, 52, 1, 28, 1755,  # 07x
    2837, 4700, 5200, 2740, 0, 0, 0, 0, 0, 0,  # 08x
    0, 0, 0, 0, 30, 430, 1, 4320, 5850, 0,  # 09x
    0, 0, 0, 0, 0, 0, 0, 0, 6, 1,  # 10x
    4, 50, 50, 0, 4, 0, 100, 0, 0, 0,  # 11x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 12x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 13x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 14x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 15x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 16x
])}
INPUT_REGISTERS: dict[IR, int] = {IR(i): v for i, v in enumerate([
    0, 14, 10, 70, 0, 2367, 0, 1832, 0, 0,  # 00x
    0, 0, 159, 4990, 0, 12, 4790, 4, 4, 5,  # 01x
    9, 0, 6, 0, 0, 0, 209, 0, 946, 0,  # 02x
    65194, 0, 0, 3653, 0, 93, 90, 89, 30, 0,  # 03x
    0, 222, 342, 680, 81, 0, 930, 0, 213, 1,  # 04x
    4991, 0, 0, 2356, 4986, 223, 170, 0, 292, 4,  # 05x

    3117, 3124, 3129, 3129, 3125, 3130, 3122, 3116, 3111, 3105,  # 06x
    3119, 3134, 3146, 3116, 3135, 3119, 175, 167, 171, 161,  # 07x
    49970, 172, 0, 50029, 0, 19097, 0, 16000, 0, 1804,  # 08x
    0, 1552, 256, 0, 0, 0, 12, 16, 3005, 0,  # 09x
    9, 0, 16000, 174, 167, 1696, 1744, 0, 0, 0,  # 10x
    16967, 12594, 13108, 18229, 13879, 8, 0, 0, 0, 0,  # 11x

    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 12x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 13x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 14x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 15x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 16x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 17x
    1696, 1744, 89, 90, 0, 0, 0, 0, 0, 0,  # 18x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 19x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 20x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 21x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 22x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 23x
])}
# fmt: on
REGISTERS = HOLDING_REGISTERS | INPUT_REGISTERS


class FooStatus(Enum):
    UNKNOWN = None
    WAITING = 0
    NORMAL = 1
    WARNING = 2
    FAULT = 3
    FLASHING = 4


class Model(Enum):
    # FOO = None
    BAT = '2'

    @classmethod
    def _missing_(cls, key):
        return cls(key[0])


class FooRegisterGetter(RegisterGetter):
    REGISTER_LUT = {
        'device_type_code': Def(DT.hex, None, HR(0)),
        'model': Def(DT.hex, Model, HR(0)),
        'module': Def(DT.uint32, (DT.hex, 8), HR(1), HR(2)),
        'num_mppt': Def((DT.duint8, 0), None, HR(3)),
        'num_phases': Def((DT.duint8, 1), None, HR(3)),
        'enable_ammeter': Def(DT.bool, None, HR(7)),
        'serial_number': Def(DT.string, None, HR(13), HR(14), HR(15), HR(16), HR(17)),
        'status': Def(DT.uint16, FooStatus, IR(0)),
    }


class FooConfig(BaseConfig):
    orm_mode = True
    getter_dict = FooRegisterGetter


Foo = create_model(
    'Foo',
    __config__=FooConfig,
    **FooRegisterGetter.to_fields(),
    computed_field=(int, None),
)  # type: ignore[call-overload]


def test_foo():
    def foo(pre_conv: Callable, post_conv: Callable, *r: int):
        return post_conv([pre_conv(i) for i in r])

    assert foo(float, str, 1, 22, 3) == '[1.0, 22.0, 3.0]'


def test_getter():
    assert FooRegisterGetter.to_fields() == {
        'device_type_code': (str, None),
        'model': (Model, None),
        'module': (str, None),
        'num_mppt': (int, None),
        'num_phases': (int, None),
        'enable_ammeter': (bool, None),
        'serial_number': (str, None),
        'status': (FooStatus, None),
    }


def test_device():
    assert Foo.schema()['properties'] == {
        'computed_field': {'title': 'Computed Field', 'type': 'integer'},
        'device_type_code': {'title': 'Device Type Code', 'type': 'string'},
        'model': {'$ref': '#/definitions/Model'},
        'enable_ammeter': {'title': 'Enable Ammeter', 'type': 'boolean'},
        'module': {'title': 'Module', 'type': 'string'},
        'serial_number': {'title': 'Serial Number', 'type': 'string'},
        'status': {'$ref': '#/definitions/FooStatus'},
        'num_mppt': {'title': 'Num Mppt', 'type': 'integer'},
        'num_phases': {'title': 'Num Phases', 'type': 'integer'},
    }

    d = Foo.from_orm(REGISTERS)
    assert d.dict() == {
        'computed_field': None,
        'device_type_code': '2001',
        'model': Model.BAT,
        'module': '00030832',
        'num_mppt': 2,
        'num_phases': 1,
        'enable_ammeter': True,
        'serial_number': 'SA1234G567',
        'status': FooStatus.WAITING,
    }
    assert d.json() == (
        '{"device_type_code": "2001", "model": "2", "module": "00030832", "num_mppt": '
        '2, "num_phases": 1, "enable_ammeter": true, "serial_number": "SA1234G567", '
        '"status": 0, "computed_field": null}'
    )
    assert d.validate(d.dict())

    assert d.schema()['properties'] == {
        'computed_field': {'title': 'Computed Field', 'type': 'integer'},
        'device_type_code': {'title': 'Device Type Code', 'type': 'string'},
        'model': {'$ref': '#/definitions/Model'},
        'enable_ammeter': {'title': 'Enable Ammeter', 'type': 'boolean'},
        'module': {'title': 'Module', 'type': 'string'},
        'num_mppt': {'title': 'Num Mppt', 'type': 'integer'},
        'num_phases': {'title': 'Num Phases', 'type': 'integer'},
        'serial_number': {'title': 'Serial Number', 'type': 'string'},
        'status': {'$ref': '#/definitions/FooStatus'},
    }

    assert str(Foo.from_orm({})) == (
        'device_type_code=None model=None module=None num_mppt=None num_phases=None enable_ammeter=None '
        'serial_number=None status=None computed_field=None'
    )
    assert str(Foo()) == (
        'device_type_code=None model=None module=None num_mppt=None num_phases=None enable_ammeter=None '
        'serial_number=None status=None computed_field=None'
    )

    assert Foo().json() == (
        '{"device_type_code": null, "model": null, "module": null, "num_mppt": null, "num_phases": null, '
        '"enable_ammeter": null, "serial_number": null, "status": null, "computed_field": null}'
    )


def test_validators():
    f = Foo.from_orm({HR(0): 8193})
    assert f.dict() == {
        'computed_field': None,
        'device_type_code': '2001',
        'model': Model.BAT,
        'module': None,
        'num_mppt': None,
        'num_phases': None,
        'enable_ammeter': None,
        'serial_number': None,
        'status': None,
    }
    assert f.json() == (
        '{"device_type_code": "2001", "model": "2", "module": null, "num_mppt": null, '
        '"num_phases": null, "enable_ammeter": null, "serial_number": null, "status": '
        'null, "computed_field": null}'
    )

    f = Foo(device_type_code='2001')
    assert f.dict() == {
        'computed_field': None,
        'device_type_code': '2001',
        'model': None,
        'module': None,
        'num_mppt': None,
        'num_phases': None,
        'enable_ammeter': None,
        'serial_number': None,
        'status': None,
    }
    assert f.json() == (
        '{"device_type_code": "2001", "model": null, "module": null, "num_mppt": '
        'null, "num_phases": null, "enable_ammeter": null, "serial_number": null, '
        '"status": null, "computed_field": null}'
    )
