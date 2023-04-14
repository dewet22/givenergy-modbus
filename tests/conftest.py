import inspect
from typing import Optional, Union

import pytest

from givenergy_modbus.exceptions import ExceptionBase, InvalidPduState
from givenergy_modbus.model.register import HoldingRegister, InputRegister
from givenergy_modbus.model.register_cache import RegisterCache
from givenergy_modbus.pdu import (
    BasePDU,
    HeartbeatRequest,
    HeartbeatResponse,
    NullResponse,
    ReadHoldingRegistersRequest,
    ReadHoldingRegistersResponse,
    ReadInputRegistersRequest,
    ReadInputRegistersResponse,
    WriteHoldingRegisterRequest,
    WriteHoldingRegisterResponse,
)
from tests.model.test_register import HOLDING_REGISTERS, INPUT_REGISTERS


@pytest.fixture
def json_inverter_daytime_discharging_with_solar_generation() -> str:
    return (
        '{"HR:0": 8193, "HR:1": 3, "HR:2": 2098, "HR:3": 513, "HR:4": 0, "HR:5": 50000, "HR:6": 3600, "HR:7": 1, '
        '"HR:8": 16967, "HR:9": 12594, "HR:10": 13108, "HR:11": 18229, "HR:12": 13879, "HR:13": 21313, "HR:14": 12594, '
        '"HR:15": 13108, "HR:16": 18229, "HR:17": 13879, "HR:18": 3005, "HR:19": 449, "HR:20": 0, "HR:21": 449, '
        '"HR:22": 2, "HR:23": 0, "HR:24": 32768, "HR:25": 30235, "HR:26": 6000, "HR:27": 1, "HR:28": 0, "HR:29": 0, '
        '"HR:30": 17, "HR:31": 0, "HR:32": 4, "HR:33": 7, "HR:34": 140, "HR:35": 22, "HR:36": 1, "HR:37": 11, '
        '"HR:38": 11, "HR:39": 51, "HR:40": 46, "HR:41": 1, "HR:42": 2, "HR:43": 0, "HR:44": 0, "HR:45": 0, '
        '"HR:46": 101, "HR:47": 1, "HR:48": 0, "HR:49": 0, "HR:50": 100, "HR:51": 0, "HR:52": 0, "HR:53": 1, '
        '"HR:54": 1, "HR:55": 160, "HR:56": 0, "HR:57": 0, "HR:58": 1, "HR:59": 0, "HR:60": 1500, "HR:61": 30, '
        '"HR:62": 30, "HR:63": 1840, "HR:64": 2740, "HR:65": 4700, "HR:66": 5198, "HR:67": 126, "HR:68": 27, '
        '"HR:69": 24, "HR:70": 28, "HR:71": 1840, "HR:72": 2620, "HR:73": 4745, "HR:74": 5200, "HR:75": 126, '
        '"HR:76": 52, "HR:77": 1, "HR:78": 28, "HR:79": 1755, "HR:80": 2837, "HR:81": 4700, "HR:82": 5200, '
        '"HR:83": 2740, "HR:84": 0, "HR:85": 0, "HR:86": 0, "HR:87": 0, "HR:88": 0, "HR:89": 0, "HR:90": 0, '
        '"HR:91": 0, "HR:92": 0, "HR:93": 0, "HR:94": 30, "HR:95": 430, "HR:96": 1, "HR:97": 4320, "HR:98": 5850, '
        '"HR:99": 0, "HR:100": 0, "HR:101": 0, "HR:102": 0, "HR:103": 0, "HR:104": 0, "HR:105": 0, "HR:106": 0, '
        '"HR:107": 0, "HR:108": 6, "HR:109": 1, "HR:110": 4, "HR:111": 50, "HR:112": 50, "HR:113": 0, "HR:114": 4, '
        '"HR:115": 0, "HR:116": 100, "HR:117": 0, "HR:118": 0, "HR:119": 0, "HR:120": 0, "HR:121": 0, "HR:122": 0, '
        '"HR:123": 24, "HR:124": 0, "HR:125": 1, "HR:126": 0, "HR:127": 0, "HR:128": 1, "HR:129": 1, "HR:130": 255, '
        '"HR:131": 20000, "HR:132": 255, "HR:133": 20000, "HR:134": 255, "HR:135": 20000, "HR:136": 255, '
        '"HR:137": 20000, "HR:138": 2484, "HR:139": 2530, "HR:140": 2116, "HR:141": 2070, "HR:142": 20, "HR:143": 5, '
        '"HR:144": 2415, "HR:145": 2300, "HR:146": 0, "HR:147": 0, "HR:148": 0, "HR:149": 0, "HR:150": 0, "HR:151": 0, '
        '"HR:152": 0, "HR:153": 0, "HR:154": 0, "HR:155": 0, "HR:156": 0, "HR:157": 0, "HR:158": 0, "HR:159": 0, '
        '"HR:160": 0, "HR:161": 0, "HR:162": 0, "HR:163": 0, "HR:164": 0, "HR:165": 0, "HR:166": 0, "HR:167": 0, '
        '"HR:168": 0, "HR:169": 0, "HR:170": 0, "HR:171": 0, "HR:172": 0, "HR:173": 0, "HR:174": 0, "HR:175": 0, '
        '"HR:176": 0, "HR:177": 0, "HR:178": 0, "HR:179": 0, "IR:0": 1, "IR:1": 3570, "IR:2": 3697, "IR:3": 3830, '
        '"IR:4": 0, "IR:5": 2363, "IR:6": 0, "IR:7": 3565, "IR:8": 3, "IR:9": 3, "IR:10": 27, "IR:11": 0, '
        '"IR:12": 263, "IR:13": 4996, "IR:14": 5, "IR:15": 2829, "IR:16": 9531, "IR:17": 4, "IR:18": 117, "IR:19": 6, '
        '"IR:20": 128, "IR:21": 0, "IR:22": 9, "IR:23": 0, "IR:24": 536, "IR:25": 0, "IR:26": 198, "IR:27": 0, '
        '"IR:28": 1881, "IR:29": 0, "IR:30": 21, "IR:31": 0, "IR:32": 0, "IR:33": 6242, "IR:34": 0, "IR:35": 93, '
        '"IR:36": 91, "IR:37": 34, "IR:38": 0, "IR:39": 0, "IR:40": 0, "IR:41": 244, "IR:42": 515, "IR:43": 554, '
        '"IR:44": 38, "IR:45": 0, "IR:46": 1725, "IR:47": 0, "IR:48": 385, "IR:49": 1, "IR:50": 5173, "IR:51": 647, '
        '"IR:52": 360, "IR:53": 2351, "IR:54": 4992, "IR:55": 241, "IR:56": 160, "IR:57": 0, "IR:58": 257, '
        '"IR:59": 68, '
        '"IR:120": 0, "IR:121": 0, "IR:122": 0, "IR:123": 0, "IR:124": 0, "IR:125": 0, "IR:126": 0, '
        '"IR:127": 0, "IR:128": 0, "IR:129": 0, "IR:130": 0, "IR:131": 0, "IR:132": 0, "IR:133": 0, "IR:134": 0, '
        '"IR:135": 0, "IR:136": 0, "IR:137": 0, "IR:138": 0, "IR:139": 0, "IR:140": 0, "IR:141": 0, "IR:142": 0, '
        '"IR:143": 0, "IR:144": 0, "IR:145": 0, "IR:146": 0, "IR:147": 0, "IR:148": 0, "IR:149": 0, "IR:150": 0, '
        '"IR:151": 0, "IR:152": 0, "IR:153": 0, "IR:154": 0, "IR:155": 0, "IR:156": 0, "IR:157": 0, "IR:158": 0, '
        '"IR:159": 0, "IR:160": 0, "IR:161": 0, "IR:162": 0, "IR:163": 0, "IR:164": 0, "IR:165": 0, "IR:166": 0, '
        '"IR:167": 0, "IR:168": 0, "IR:169": 0, "IR:170": 0, "IR:171": 0, "IR:172": 0, "IR:173": 0, "IR:174": 0, '
        '"IR:175": 0, "IR:176": 0, "IR:177": 0, "IR:178": 0, "IR:179": 0, "IR:180": 1730, "IR:181": 1835, '
        '"IR:182": 34, "IR:183": 91, "IR:184": 0, "IR:185": 0, "IR:186": 0, "IR:187": 0, "IR:188": 0, "IR:189": 0, '
        '"IR:190": 0, "IR:191": 0, "IR:192": 0, "IR:193": 0, "IR:194": 0, "IR:195": 0, "IR:196": 0, "IR:197": 0, '
        '"IR:198": 0, "IR:199": 0, "IR:200": 0, "IR:201": 0, "IR:202": 0, "IR:203": 0, "IR:204": 0, "IR:205": 0, '
        '"IR:206": 0, "IR:207": 0, "IR:208": 0, "IR:209": 0, "IR:210": 0, "IR:211": 0, "IR:212": 0, "IR:213": 0, '
        '"IR:214": 0, "IR:215": 0, "IR:216": 0, "IR:217": 0, "IR:218": 0, "IR:219": 0, "IR:220": 0, "IR:221": 0, '
        '"IR:222": 0, "IR:223": 0, "IR:224": 0, "IR:225": 0, "IR:226": 0, "IR:227": 300, "IR:228": 0, "IR:229": 0, '
        '"IR:230": 0, "IR:231": 0, "IR:232": 0, "IR:233": 0, "IR:234": 0, "IR:235": 0, "IR:236": 0, "IR:237": 0, '
        '"IR:238": 0, "IR:239": 0}'
    )


@pytest.fixture
def json_battery_daytime_discharging() -> str:
    return (
        '{"IR:60": 3232, "IR:61": 3237, "IR:62": 3235, "IR:63": 3232, "IR:64": 3235, "IR:65": 3229, "IR:66": 3237, '
        '"IR:67": 3233, "IR:68": 3238, "IR:69": 3237, "IR:70": 3235, "IR:71": 3235, "IR:72": 3235, "IR:73": 3235, '
        '"IR:74": 3240, "IR:75": 3238, "IR:76": 168, "IR:77": 157, "IR:78": 165, "IR:79": 146, "IR:80": 51832, '
        '"IR:81": 172, "IR:82": 0, "IR:83": 51816, "IR:84": 0, "IR:85": 19513, "IR:86": 0, "IR:87": 16000, "IR:88": 0, '
        '"IR:89": 13142, "IR:90": 0, "IR:91": 3600, "IR:92": 256, "IR:93": 0, "IR:94": 0, "IR:95": 0, "IR:96": 23, '
        '"IR:97": 16, "IR:98": 3005, "IR:99": 0, "IR:100": 67, "IR:101": 0, "IR:102": 16000, "IR:103": 168, '
        '"IR:104": 157, "IR:105": 1696, "IR:106": 1744, "IR:107": 0, "IR:108": 0, "IR:109": 0, "IR:110": 16967, '
        '"IR:111": 12594, "IR:112": 13108, "IR:113": 18229, "IR:114": 13879, "IR:115": 8, "IR:116": 0, "IR:117": 0, '
        '"IR:118": 0, "IR:119": 0}'
    )


@pytest.fixture
def json_battery_unsure() -> str:
    return (
        '{"IR:60": 0, "IR:61": 0, "IR:62": 0, "IR:63": 0, "IR:64": 0, "IR:65": 0, "IR:66": 0, "IR:67": 0, "IR:68": 0, '
        '"IR:69": 0, "IR:70": 0, "IR:71": 0, "IR:72": 0, "IR:73": 0, "IR:74": 0, "IR:75": 0, "IR:76": 52, "IR:77": 0, '
        '"IR:78": 0, "IR:79": 0, "IR:80": 0, "IR:81": 256, "IR:82": 0, "IR:83": 0, "IR:84": 0, "IR:85": 0, "IR:86": 0, '
        '"IR:87": 0, "IR:88": 0, "IR:89": 0, "IR:90": 0, "IR:91": 0, "IR:92": 0, "IR:93": 0, "IR:94": 0, "IR:95": 0, '
        '"IR:96": 0, "IR:97": 0, "IR:98": 0, "IR:99": 0, "IR:100": 0, "IR:101": 0, "IR:102": 0, "IR:103": 0, '
        '"IR:104": 0, "IR:105": 0, "IR:106": 0, "IR:107": 0, "IR:108": 0, "IR:109": 0, "IR:110": 0, "IR:111": 0, '
        '"IR:112": 0, "IR:113": 0, "IR:114": 0, "IR:115": 0, "IR:116": 0, "IR:117": 0, "IR:118": 0, "IR:119": 0}'
    )


@pytest.fixture
def json_battery_missing() -> str:
    return (
        '{"IR:60": 0, "IR:61": 0, "IR:62": 0, "IR:63": 0, "IR:64": 0, "IR:65": 0, "IR:66": 0, "IR:67": 0, "IR:68": 0, '
        '"IR:69": 0, "IR:70": 0, "IR:71": 0, "IR:72": 0, "IR:73": 0, "IR:74": 0, "IR:75": 0, "IR:76": 0, "IR:77": 0, '
        '"IR:78": 0, "IR:79": 0, "IR:80": 0, "IR:81": 0, "IR:82": 0, "IR:83": 0, "IR:84": 0, "IR:85": 0, "IR:86": 0, '
        '"IR:87": 0, "IR:88": 0, "IR:89": 0, "IR:90": 0, "IR:91": 0, "IR:92": 0, "IR:93": 0, "IR:94": 0, "IR:95": 0, '
        '"IR:96": 0, "IR:97": 0, "IR:98": 0, "IR:99": 0, "IR:100": 0, "IR:101": 0, "IR:102": 0, "IR:103": 0, '
        '"IR:104": 0, "IR:105": 0, "IR:106": 0, "IR:107": 0, "IR:108": 0, "IR:109": 0, "IR:110": 0, "IR:111": 0, '
        '"IR:112": 0, "IR:113": 0, "IR:114": 0, "IR:115": 0, "IR:116": 0, "IR:117": 0, "IR:118": 0, "IR:119": 0}'
    )


@pytest.fixture
def register_cache() -> RegisterCache:
    """Ensure we can instantiate a RegisterCache and set registers in it."""
    i = RegisterCache()
    i.update({HoldingRegister(k): v for k, v in HOLDING_REGISTERS.items()})
    i.update({InputRegister(k): v for k, v in INPUT_REGISTERS.items()})
    return i


@pytest.fixture
def register_cache_inverter_daytime_discharging_with_solar_generation(
    json_inverter_daytime_discharging_with_solar_generation,
) -> RegisterCache:
    """Ensure we can instantiate a RegisterCache and set registers in it."""
    return RegisterCache.from_json(json_inverter_daytime_discharging_with_solar_generation)


@pytest.fixture
def register_cache_battery_daytime_discharging(json_battery_daytime_discharging) -> RegisterCache:
    """Ensure we can instantiate a RegisterCache and set registers in it."""
    return RegisterCache.from_json(json_battery_daytime_discharging)


@pytest.fixture
def register_cache_battery_unsure(json_battery_unsure) -> RegisterCache:
    """Ensure we can instantiate a RegisterCache and set registers in it."""
    return RegisterCache.from_json(json_battery_unsure)


@pytest.fixture
def register_cache_battery_missing(json_battery_missing) -> RegisterCache:
    """Ensure we can instantiate a RegisterCache and set registers in it."""
    return RegisterCache.from_json(json_battery_missing)


PDUType = type[BasePDU]
CtorKwargs = dict[str, Union[int, str, list[int]]]
MbapHeader = bytes
InnerFrame = bytes
ExceptionThrown = Optional[ExceptionBase]
StrRepr = str
PduTestCase = tuple[StrRepr, PDUType, CtorKwargs, MbapHeader, InnerFrame, ExceptionThrown]
PduTestCaseSig = 'str_repr, pdu_class, constructor_kwargs, mbap_header, inner_frame, ex'
PduTestCases = list[PduTestCase]

_h2b = bytes.fromhex


def _mbap_header(function_code: int, packet_length: int) -> MbapHeader:
    return _h2b(f'59590001{packet_length:04x}01{function_code:02x}')


def find_subclasses(module, clazz):
    return [cls for name, cls in inspect.getmembers(module) if inspect.isclass(cls) and issubclass(cls, clazz)]


def all_subclasses(cls):
    return set(cls.__subclasses__()).union([s for c in cls.__subclasses__() for s in all_subclasses(c)])


def all_leaf_classes(cls):
    return [c for c in all_subclasses(cls) if not c.__subclasses__()]


# Messages a server should be expected to process (or, typical messages a client would send)
_server_messages: PduTestCases = [
    (
        '2:4/ReadInputRegistersRequest(slave_address=0x32 base_register=16 register_count=6)',
        ReadInputRegistersRequest,
        {
            'base_register': 0x10,
            'register_count': 6,
            'check': 0x0754,
            'data_adapter_serial_number': 'AB1234G567',
            'error': False,
            'padding': 8,
            'slave_address': 0x32,
        },
        b'YY\x00\x01\x00\x1c\x01\x02',  # 8 bytes
        b'AB1234G567' b'\x00\x00\x00\x00\x00\x00\x00\x08' b'\x32\x04\x00\x10\x00\x06' b'\x07\x54',  # 26 bytes
        None,
    ),
    (
        '2:3/ReadHoldingRegistersRequest(slave_address=0x32 base_register=20817 register_count=20)',
        ReadHoldingRegistersRequest,
        {
            'base_register': 0x5151,
            'register_count': 20,
            'check': 0x2221,
            'data_adapter_serial_number': 'AB1234G567',
            'error': False,
            'padding': 8,
            'slave_address': 0x32,
        },
        b'YY\x00\x01\x00\x1c\x01\x02',
        b'AB1234G567' b'\x00\x00\x00\x00\x00\x00\x00\x08' b'\x32\x03\x51\x51\x00\x14' b'\x22\x21',
        None,
    ),
    (
        '2:3/ReadHoldingRegistersRequest(slave_address=0x32 base_register=20817 register_count=30)',
        ReadHoldingRegistersRequest,
        {
            'base_register': 0x5151,
            'register_count': 30,
            'check': 0x25A1,
            'data_adapter_serial_number': 'AB1234G567',
            'error': False,
            'padding': 8,
            'slave_address': 0x32,
        },
        b'YY\x00\x01\x00\x1c\x01\x02',
        b'AB1234G567' b'\x00\x00\x00\x00\x00\x00\x00\x08' b'\x32\x03\x51\x51\x00\x1e' b'\x25\xa1',
        None,
    ),
    (
        '2:6/WriteHoldingRegisterRequest(HR(179)/HOLDING_REG179 -> 2000/0x07d0)',
        WriteHoldingRegisterRequest,
        {
            'register': HoldingRegister(179),
            'value': 2000,
            'check': 0x81EE,
            'data_adapter_serial_number': 'AB1234G567',
            'error': False,
            'padding': 8,
            'slave_address': 0x32,
        },
        b'YY\x00\x01\x00\x1c\x01\x02',
        b'AB1234G567' b'\x00\x00\x00\x00\x00\x00\x00\x08' b'\x32\x06\x00\xb3\x07\xd0' b'\x81\xee',
        InvalidPduState(r'HR\(179\)/HOLDING_REG179 is not safe to write to', None),
    ),
    (
        '2:6/WriteHoldingRegisterRequest(HR(20)/ENABLE_CHARGE_TARGET -> True/0x0001)',
        WriteHoldingRegisterRequest,
        {
            'register': HoldingRegister(0x14),
            'value': 1,
            'check': 0xC42D,
            'data_adapter_serial_number': 'AB1234G567',
            'error': False,
            'padding': 8,
            'slave_address': 0x32,
        },
        b'YY\x00\x01\x00\x1c\x01\x02',
        b'AB1234G567' b'\x00\x00\x00\x00\x00\x00\x00\x08' b'\x32\x06\x00\x14\x00\x01' b'\xc4\x2d',
        None,
    ),
    (
        '1/HeartbeatResponse(data_adapter_serial_number=AB1234G567 data_adapter_type=32)',
        HeartbeatResponse,
        {
            'data_adapter_serial_number': 'AB1234G567',
            'data_adapter_type': 32,
        },
        b'YY\x00\x01\x00\x0d\x01\x01',  # 8b MBAP header
        b'AB1234G567' b'\x20',
        None,
    ),
]

# Messages a client should be expected to process (or, typical messages a server would send)
_client_messages: PduTestCases = [
    (
        '2:4/ReadInputRegistersResponse(slave_address=0x32 base_register=0)',
        ReadInputRegistersResponse,
        {
            'check': 0x8E4B,
            'inverter_serial_number': 'SA1234G567',
            'base_register': 0x0000,
            'register_count': 0x003C,
            # fmt: off
            'register_values': [
                0x0001, 0x0CB0, 0x0C78, 0x0F19, 0x0000, 0x095B, 0x0000, 0x05C5, 0x0001, 0x0002,
                0x0021, 0x0000, 0x008C, 0x138A, 0x0005, 0x0AA9, 0x2B34, 0x0008, 0x0041, 0x0008,
                0x003F, 0x0000, 0x0005, 0x0000, 0x0278, 0x0000, 0x0071, 0x0000, 0x02FF, 0x0000,
                0xFF75, 0x0000, 0x0000, 0x0BF5, 0x0000, 0x0057, 0x0054, 0x0049, 0x0000, 0x0000,
                0x0000, 0x0124, 0x0311, 0x0288, 0x004E, 0x0000, 0x02F7, 0x0000, 0x00B6, 0x0001,
                0x139E, 0x0467, 0x023C, 0x094B, 0x1389, 0x0121, 0x00BE, 0x0000, 0x00F8, 0x0011,
            ],
            # fmt: on
            'data_adapter_serial_number': 'WF1234G567',
            'padding': 0x8A,
            'slave_address': 0x32,
            'error': False,
        },
        b'YY\x00\x01\x00\x9e\x01\x02',  # 8b MBAP header
        # 154b total payload, starting with 34b of fields:
        b'WF1234G567' b'\x00\x00\x00\x00\x00\x00\x00\x8a' b'\x32\x04' b'SA1234G567' b'\x00\x00' b'\x00<'
        # 4x60b chunk, containing register values:
        b'\x00\x01\x0c\xb0\x0cx\x0f\x19\x00\x00\t[\x00\x00\x05\xc5\x00\x01\x00\x02\x00!\x00\x00\x00\x8c\x13\x8a\x00\x05'
        b'\n\xa9+4\x00\x08\x00A\x00\x08\x00?\x00\x00\x00\x05\x00\x00\x02x\x00\x00\x00q\x00\x00\x02\xff\x00\x00'
        b'\xffu\x00\x00\x00\x00\x0b\xf5\x00\x00\x00W\x00T\x00I\x00\x00\x00\x00\x00\x00\x01$\x03\x11\x02\x88\x00N'
        b'\x00\x00\x02\xf7\x00\x00\x00\xb6\x00\x01\x13\x9e\x04g\x02<\tK\x13\x89\x01!\x00\xbe\x00\x00\x00\xf8\x00\x11'
        b'\x8e\x4b',  # 2b crc
        None,
    ),
    (
        '2:3/ReadHoldingRegistersResponse(slave_address=0x32 base_register=0)',
        ReadHoldingRegistersResponse,
        {
            'check': 0x153D,
            'inverter_serial_number': 'SA1234G567',
            'base_register': 0x0000,
            'register_count': 0x003C,
            # fmt: off
            'register_values': [
                0x2001, 0x0003, 0x0832, 0x0201, 0x0000, 0xC350, 0x0E10, 0x0001, 0x4247, 0x3132,
                0x3334, 0x4735, 0x3637, 0x5341, 0x3132, 0x3334, 0x4735, 0x3637, 0x0BBD, 0x01C1,
                0x0000, 0x01C1, 0x0002, 0x0000, 0x8000, 0x761B, 0x1770, 0x0001, 0x0000, 0x0000,
                0x0011, 0x0000, 0x0004, 0x0007, 0x008C, 0x0016, 0x0004, 0x0011, 0x0013, 0x0001,
                0x0001, 0x0001, 0x0002, 0x0000, 0x0000, 0x0000, 0x0065, 0x0001, 0x0000, 0x0000,
                0x0064, 0x0000, 0x0000, 0x0001, 0x0001, 0x00A0, 0x0640, 0x02BC, 0x0001, 0x0000,
            ],
            # fmt: on
            'data_adapter_serial_number': 'WF1234G567',
            'padding': 0x8A,
            'slave_address': 0x32,
            'error': False,
        },
        b'YY\x00\x01\x00\x9e\x01\x02',  # 8b MBAP header
        # 154b total payload, starting with 34b of fields:
        b'WF1234G567' b'\x00\x00\x00\x00\x00\x00\x00\x8a' b'\x32\x03' b'SA1234G567' b'\x00\x00' b'\x00<'
        # 4x60b chunk, containing register values:
        b' \x01\x00\x03\x082\x02\x01\x00\x00\xc3P\x0e\x10\x00\x01BG1234G567SA1234G567\x0b\xbd\x01\xc1\x00\x00\x01'
        b'\xc1\x00\x02\x00\x00\x80\x00v\x1b\x17p\x00\x01\x00\x00\x00\x00\x00\x11\x00\x00\x00\x04\x00\x07\x00\x8c'
        b'\x00\x16\x00\x04\x00\x11\x00\x13\x00\x01\x00\x01\x00\x01\x00\x02\x00\x00\x00\x00\x00\x00\x00e\x00\x01\x00'
        b'\x00\x00\x00\x00d\x00\x00\x00\x00\x00\x01\x00\x01\x00\xa0\x06@\x02\xbc\x00\x01\x00\x00'
        b'\x15=',  # 2b crc
        # b'\x00\x01\x0c\xb0\x0cx\x0f\x19\x00\x00\t[\x00\x00\x05\xc5\x00\x01\x00\x02\x00!\x00\x00\x00\x8c\x13\x8a\x00\x05'
        # b'\n\xa9+4\x00\x08\x00A\x00\x08\x00?\x00\x00\x00\x05\x00\x00\x02x\x00\x00\x00q\x00\x00\x02\xff\x00\x00'
        # b'\xffu\x00\x00\x00\x00\x0b\xf5\x00\x00\x00W\x00T\x00I\x00\x00\x00\x00\x00\x00\x01$\x03\x11\x02\x88\x00N'
        # b'\x00\x00\x02\xf7\x00\x00\x00\xb6\x00\x01\x13\x9e\x04g\x02<\tK\x13\x89\x01!\x00\xbe\x00\x00\x00\xf8\x00\x11'
        # b"\x8e\x4b",  # 2b crc
        None,
    ),
    (
        '2:6/WriteHoldingRegisterResponse(HR(35)/SYSTEM_TIME_YEAR -> 8764/0x223c)',
        WriteHoldingRegisterResponse,
        {
            'check': 0x8E4B,
            'inverter_serial_number': 'SA1234G567',
            'register': HoldingRegister(0x0023),
            'value': 0x223C,
            'data_adapter_serial_number': 'WF1234G567',
            'padding': 0x8A,
            'slave_address': 0x32,
            'error': False,
        },
        b'YY\x00\x01\x00\x26\x01\x02',  # 8b MBAP header
        b'WF1234G567'
        b'\x00\x00\x00\x00\x00\x00\x00\x8a'
        b'\x32\x06'
        b'SA1234G567'
        b'\x00\x23'  # register
        b'\x22\x3c'  # value readback
        b'\x8e\x4b',  # 2b crc
        None,
    ),
    (
        '1/HeartbeatRequest(data_adapter_serial_number=WF1234G567 data_adapter_type=1)',
        HeartbeatRequest,
        {'data_adapter_serial_number': 'WF1234G567', 'data_adapter_type': 1},
        _mbap_header(1, 0x0D),
        b'WF1234G567' + _h2b('01'),
        None,
    ),
    (
        '2:0/NullResponse(slave_address=0x22 nulls=[0]*62)',
        NullResponse,
        {
            'check': 0x0,
            'inverter_serial_number': '\x00' * 10,
            'data_adapter_serial_number': 'KK4321H987',
            'padding': 0x8A,
            'slave_address': 0x22,
            'error': False,
            'nulls': [0] * 62,
        },
        _mbap_header(2, 158),
        _h2b('4b4b3433323148393837000000000000008a2200' + '0000' * 68),
        None,
    ),
]

SERVER_MESSAGES = [pytest.param(*p, id=p[0]) for p in _server_messages]
CLIENT_MESSAGES = [pytest.param(*p, id=p[0]) for p in _client_messages]
ALL_MESSAGES = SERVER_MESSAGES + CLIENT_MESSAGES
