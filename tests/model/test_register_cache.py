import datetime

import pytest

from givenergy_modbus.model.register import HoldingRegister, InputRegister  # type: ignore  # shut up mypy
from givenergy_modbus.model.register_cache import RegisterCache
from tests.model.test_register import HOLDING_REGISTERS, INPUT_REGISTERS  # type: ignore  # shut up mypy

JSON_INVERTER_DAYTIME_DISCHARGING_WITH_SOLAR_GENERATION = (
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
    '"IR:59": 68, "IR:105": 34, "IR:106": 91, "IR:120": 0, "IR:121": 0, "IR:122": 0, "IR:123": 0, "IR:124": 0, '
    '"IR:125": 0, "IR:126": 0, '
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
    '"IR:238": 0, "IR:239": 0, "IR:240": 2331, "IR:241": 0, "IR:242": 0, "IR:243": 0, "IR:244": 0, "IR:245": 0, '
    '"IR:246": 90, "IR:247": 0, "IR:248": 0, "IR:249": 0, "IR:250": 0, "IR:251": 0, "IR:252": 0, "IR:253": 0, '
    '"IR:254": 0, "IR:255": 0, "IR:256": 0, "IR:257": 0, "IR:258": 0, "IR:259": 0, "IR:260": 0, "IR:261": 0, '
    '"IR:262": 0, "IR:263": 0, "IR:264": 0, "IR:265": 0, "IR:266": 0, "IR:267": 0, "IR:268": 0, "IR:269": 0, '
    '"IR:270": 0, "IR:271": 0, "IR:272": 0, "IR:273": 0, "IR:274": 0, "IR:275": 0, "IR:276": 0, "IR:277": 0, '
    '"IR:278": 0, "IR:279": 0, "IR:280": 0, "IR:281": 0, "IR:282": 0, "IR:283": 0, "IR:284": 0, "IR:285": 0, '
    '"IR:286": 0, "IR:287": 0, "IR:288": 0, "IR:289": 0, "IR:290": 0, "IR:291": 0, "IR:292": 0, "IR:293": 0, '
    '"IR:294": 0, "IR:295": 0, "IR:296": 0, "IR:297": 0, "IR:298": 0, "IR:299": 0}'
)
JSON_BATTERY_DAYTIME_DISCHARGING = (
    '{"IR:60": 3232, "IR:61": 3237, "IR:62": 3235, "IR:63": 3232, "IR:64": 3235, "IR:65": 3229, "IR:66": 3237, '
    '"IR:67": 3233, "IR:68": 3238, "IR:69": 3237, "IR:70": 3235, "IR:71": 3235, "IR:72": 3235, "IR:73": 3235, '
    '"IR:74": 3240, "IR:75": 3238, "IR:76": 168, "IR:77": 157, "IR:78": 165, "IR:79": 146, "IR:80": 51832, '
    '"IR:81": 172, "IR:82": 0, "IR:83": 51816, "IR:84": 0, "IR:85": 19513, "IR:86": 0, "IR:87": 16000, "IR:88": 0, '
    '"IR:89": 13142, "IR:90": 0, "IR:91": 3600, "IR:92": 256, "IR:93": 0, "IR:94": 0, "IR:95": 0, "IR:96": 23, '
    '"IR:97": 16, "IR:98": 3005, "IR:99": 0, "IR:100": 67, "IR:101": 0, "IR:102": 16000, "IR:103": 168, "IR:104": 157, '
    '"IR:105": 1696, "IR:106": 1744, "IR:107": 0, "IR:108": 0, "IR:109": 0, "IR:110": 16967, "IR:111": 12594, '
    '"IR:112": 13108, "IR:113": 18229, "IR:114": 13879, "IR:115": 8, "IR:116": 0, "IR:117": 0, "IR:118": 0, '
    '"IR:119": 0}'
)
JSON_BATTERY_UNSURE = (
    '{"IR:60": 0, "IR:61": 0, "IR:62": 0, "IR:63": 0, "IR:64": 0, "IR:65": 0, "IR:66": 0, "IR:67": 0, "IR:68": 0, '
    '"IR:69": 0, "IR:70": 0, "IR:71": 0, "IR:72": 0, "IR:73": 0, "IR:74": 0, "IR:75": 0, "IR:76": 52, "IR:77": 0, '
    '"IR:78": 0, "IR:79": 0, "IR:80": 0, "IR:81": 256, "IR:82": 0, "IR:83": 0, "IR:84": 0, "IR:85": 0, "IR:86": 0, '
    '"IR:87": 0, "IR:88": 0, "IR:89": 0, "IR:90": 0, "IR:91": 0, "IR:92": 0, "IR:93": 0, "IR:94": 0, "IR:95": 0, '
    '"IR:96": 0, "IR:97": 0, "IR:98": 0, "IR:99": 0, "IR:100": 0, "IR:101": 0, "IR:102": 0, "IR:103": 0, "IR:104": 0, '
    '"IR:105": 0, "IR:106": 0, "IR:107": 0, "IR:108": 0, "IR:109": 0, "IR:110": 0, "IR:111": 0, "IR:112": 0, '
    '"IR:113": 0, "IR:114": 0, "IR:115": 0, "IR:116": 0, "IR:117": 0, "IR:118": 0, "IR:119": 0}'
)
JSON_BATTERY_MISSING = (
    '{"IR:60": 0, "IR:61": 0, "IR:62": 0, "IR:63": 0, "IR:64": 0, "IR:65": 0, "IR:66": 0, "IR:67": 0, "IR:68": 0, '
    '"IR:69": 0, "IR:70": 0, "IR:71": 0, "IR:72": 0, "IR:73": 0, "IR:74": 0, "IR:75": 0, "IR:76": 0, "IR:77": 0, '
    '"IR:78": 0, "IR:79": 0, "IR:80": 0, "IR:81": 0, "IR:82": 0, "IR:83": 0, "IR:84": 0, "IR:85": 0, "IR:86": 0, '
    '"IR:87": 0, "IR:88": 0, "IR:89": 0, "IR:90": 0, "IR:91": 0, "IR:92": 0, "IR:93": 0, "IR:94": 0, "IR:95": 0, '
    '"IR:96": 0, "IR:97": 0, "IR:98": 0, "IR:99": 0, "IR:100": 0, "IR:101": 0, "IR:102": 0, "IR:103": 0, "IR:104": 0, '
    '"IR:105": 0, "IR:106": 0, "IR:107": 0, "IR:108": 0, "IR:109": 0, "IR:110": 0, "IR:111": 0, "IR:112": 0, '
    '"IR:113": 0, "IR:114": 0, "IR:115": 0, "IR:116": 0, "IR:117": 0, "IR:118": 0, "IR:119": 0}'
)


@pytest.fixture
def register_cache() -> RegisterCache:
    """Ensure we can instantiate a RegisterCache and set registers in it."""
    i = RegisterCache()
    i.set_registers(HoldingRegister, HOLDING_REGISTERS)
    i.set_registers(InputRegister, INPUT_REGISTERS)
    return i


@pytest.fixture
def register_cache_inverter_daytime_discharging_with_solar_generation() -> RegisterCache:
    """Ensure we can instantiate a RegisterCache and set registers in it."""
    return RegisterCache.from_json(JSON_INVERTER_DAYTIME_DISCHARGING_WITH_SOLAR_GENERATION)


@pytest.fixture
def register_cache_battery_daytime_discharging() -> RegisterCache:
    """Ensure we can instantiate a RegisterCache and set registers in it."""
    return RegisterCache.from_json(JSON_BATTERY_DAYTIME_DISCHARGING)


@pytest.fixture
def register_cache_battery_unsure() -> RegisterCache:
    """Ensure we can instantiate a RegisterCache and set registers in it."""
    return RegisterCache.from_json(JSON_BATTERY_UNSURE)


@pytest.fixture
def register_cache_battery_missing() -> RegisterCache:
    """Ensure we can instantiate a RegisterCache and set registers in it."""
    return RegisterCache.from_json(JSON_BATTERY_MISSING)


def test_register_cache(register_cache):
    """Ensure we can instantiate a RegisterCache and set registers in it."""
    expected = {HoldingRegister(k): v for k, v in HOLDING_REGISTERS.items()}
    expected.update({InputRegister(k): v for k, v in INPUT_REGISTERS.items()})
    assert register_cache == expected


def test_attributes(register_cache):
    """Ensure we can instantiate a RegisterCache and derive correct attributes from it."""
    for k in (
        'inverter_serial_number',
        'model',
        'battery_serial_number',
        'system_time',
        'charge_slot_1',
        'charge_slot_2',
        'discharge_slot_1',
        'discharge_slot_2',
    ):
        with pytest.raises(KeyError) as e:
            assert getattr(register_cache, k)
        assert e.value.args[0] == k

    assert register_cache.device_type_code == '2001'
    assert register_cache.inverter_module == 198706
    assert register_cache.bms_firmware_version == 3005
    assert register_cache.dsp_firmware_version == 449
    assert register_cache.arm_firmware_version == 449
    assert register_cache.enable_charge_target
    # assert register_cache.system_time == datetime.datetime(2022, 1, 1, 23, 57, 19)

    # time slots are BCD-encoded: 30 == 00:30, 430 == 04:30
    assert register_cache.charge_slot_1_start == datetime.time(0, 30)
    assert register_cache.charge_slot_1_end == datetime.time(4, 30)
    # assert register_cache.charge_slot_1 == (datetime.time(0, 30), datetime.time(4, 30))
    assert register_cache.charge_slot_2_start == datetime.time(0, 0)
    assert register_cache.charge_slot_2_end == datetime.time(0, 4)
    # assert register_cache.charge_slot_2 == (datetime.time(0, 0), datetime.time(0, 4))
    assert register_cache.discharge_slot_1_start == datetime.time(0, 0)
    assert register_cache.discharge_slot_1_end == datetime.time(0, 0)
    # assert register_cache.discharge_slot_1 == (datetime.time(0, 0), datetime.time(0, 0))
    assert register_cache.discharge_slot_2_start == datetime.time(0, 0)
    assert register_cache.discharge_slot_2_end == datetime.time(0, 0)
    # assert register_cache.discharge_slot_2 == (datetime.time(0, 0), datetime.time(0, 0))

    assert register_cache.v_pv1 == 1.4
    assert register_cache.v_pv2 == 1.0
    assert register_cache.v_p_bus == 7.0
    assert register_cache.v_n_bus == 0.0
    assert register_cache.v_ac1 == 236.7

    assert register_cache.e_pv1_day == 0.4
    assert register_cache.e_pv2_day == 0.5
    assert register_cache.e_grid_out_total_l == 0.6

    assert register_cache.battery_percent == 4
    assert register_cache.e_battery_discharge_total == 169.6
    assert register_cache.e_battery_charge_total == 174.4

    assert register_cache.e_battery_throughput_total_h == 0
    assert register_cache.e_battery_throughput_total_l == 183.2
    assert register_cache.e_battery_throughput_total == 183.2

    assert register_cache.v_battery_cell_01 == 3.117
    assert register_cache.v_battery_cell_16 == 3.119


def test_to_from_json_quick():
    """Ensure we can serialize and unserialize a RegisterCache to and from JSON."""
    registers = {HoldingRegister(1): 2, InputRegister(3): 4}
    json = RegisterCache(registers=registers).to_json()
    assert json == '{"HR:1": 2, "IR:3": 4}'
    rc = RegisterCache.from_json(json)
    assert rc == registers
    assert len(rc._register_lookup_table) > 100  # ensure we have all registers ready to look up


def test_to_from_json_actual_data():
    """Ensure we can serialize and unserialize a RegisterCache to and from JSON."""
    rc = RegisterCache.from_json(JSON_INVERTER_DAYTIME_DISCHARGING_WITH_SOLAR_GENERATION)
    assert len(rc) == 422
    assert len(rc._register_lookup_table) > 100  # ensure we have all registers ready to look up
