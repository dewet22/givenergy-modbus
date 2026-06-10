import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest

from givenergy_modbus.exceptions import ExceptionBase
from givenergy_modbus.model import TimeSlot
from givenergy_modbus.model.battery import Battery
from givenergy_modbus.model.inverter import (
    BatteryCalibrationStage,
    BatteryPowerMode,
    BatteryType,
    MeterType,
    Model,
    PowerFactorFunctionModel,
    SinglePhaseInverter,
    Status,
)
from givenergy_modbus.model.inverter import UsbDevice as SinglePhaseInverterUsbDevice
from givenergy_modbus.model.plant import (
    Plant,
    PlantCapabilities,
    _coerce_model,
    _derive_inverter_address,
)
from givenergy_modbus.model.register import HR, IR, Register
from givenergy_modbus.model.register_cache import RegisterCache
from givenergy_modbus.pdu import (
    ClientIncomingMessage,
    HeartbeatRequest,
    NullResponse,
    ReadHoldingRegistersResponse,
    ReadInputRegistersResponse,
    ReadRegistersResponse,
    WriteHoldingRegisterResponse,
)
from tests.conftest import CLIENT_MESSAGES, PduTestCaseSig


@pytest.fixture
def plant():
    """Yield a Plant."""
    yield Plant()


def test_instantiation():
    assert (plant := Plant()).model_dump() == {
        "capabilities": None,
        "data_adapter_serial_number": "",
        "inverter_serial_number": "",
        "register_caches": {0x32: {}},
    }
    assert json.loads(plant.model_dump_json()) == {
        "capabilities": None,
        "register_caches": {"50": {}},
        "inverter_serial_number": "",
        "data_adapter_serial_number": "",
    }

    rc = RegisterCache(registers={HR(1): 2})
    assert Plant(inverter_serial_number="AB1234", register_caches={0x30: rc}).model_dump() == {
        "capabilities": None,
        "data_adapter_serial_number": "",
        "inverter_serial_number": "AB1234",
        "register_caches": {0x30: rc},
    }


def test_plant(
    plant: Plant,
    register_cache_inverter_daytime_discharging_with_solar_generation,
    register_cache_battery_daytime_discharging,
):
    """Ensure we can instantiate a Plant from existing DTOs."""
    assert plant.model_dump() == {
        "capabilities": None,
        "data_adapter_serial_number": "",
        "inverter_serial_number": "",
        "register_caches": {0x32: {}},
    }

    # inject register values
    plant.register_caches[0x32].update(register_cache_inverter_daytime_discharging_with_solar_generation)
    plant.register_caches[0x32].update(register_cache_battery_daytime_discharging)

    assert plant.model_dump() == {
        "capabilities": None,
        "data_adapter_serial_number": "",
        "inverter_serial_number": "",
        "register_caches": plant.register_caches,
    }

    i = SinglePhaseInverter.from_register_cache(register_cache_inverter_daytime_discharging_with_solar_generation)
    assert i.serial_number == "SA1234G567"  # type: ignore[attr-defined]
    b = Battery.from_register_cache(register_cache_battery_daytime_discharging)
    assert b.serial_number == "BG1234G567"  # type: ignore[attr-defined]

    assert isinstance(plant.inverter, SinglePhaseInverter)
    assert plant.inverter == i
    assert plant.number_batteries == 1
    assert isinstance(plant.batteries[0], Battery)
    assert plant.batteries[0] == b

    # assert Plant(**plant.dict()) == plant
    # assert Plant.from_registers(plant) == plant


def test_number_batteries_handles_decode_value_error(
    plant: Plant,
    register_cache_battery_daytime_discharging,
    monkeypatch,
):
    """Regression test for #49: ValueError from a device's register decode is swallowed.

    A ValueError raised while probing a device (e.g. an out-of-range enum value)
    must not propagate out of number_batteries — it should be treated the same
    as a missing or invalid battery and stop the probe loop.
    """
    plant.register_caches[0x32].update(register_cache_battery_daytime_discharging)
    plant.register_caches[0x33] = RegisterCache()  # simulate a second device responding

    original_from_register_cache = Battery.from_register_cache

    def raise_for_0x33(cache):
        if cache is plant.register_caches[0x33]:
            raise ValueError("11 is not a valid SomeEnum")
        return original_from_register_cache(cache)

    monkeypatch.setattr(Battery, "from_register_cache", raise_for_0x33)

    assert plant.number_batteries == 1


def test_number_batteries_counts_all_six_when_all_valid(plant: Plant, monkeypatch):
    """A plant with 6 valid batteries must return 6, not 5 (no off-by-one when loop completes)."""
    for device_addr in range(0x32, 0x38):
        plant.register_caches[device_addr] = RegisterCache()

    always_valid_battery = MagicMock(spec=Battery)
    always_valid_battery.is_valid.return_value = True
    monkeypatch.setattr(Battery, "from_register_cache", lambda _cache: always_valid_battery)

    assert plant.number_batteries == 6


def test_number_batteries_honours_is_valid_check(plant: Plant, monkeypatch):
    """is_valid() must be honoured to stop the probe loop (was an assert, now an explicit if)."""
    plant.register_caches[0x32] = RegisterCache()
    plant.register_caches[0x33] = RegisterCache()  # extra cache so missing-key isn't the early-exit

    invalid_battery = MagicMock(spec=Battery)
    invalid_battery.is_valid.return_value = False
    monkeypatch.setattr(Battery, "from_register_cache", lambda _cache: invalid_battery)

    assert plant.number_batteries == 0


@pytest.mark.parametrize(PduTestCaseSig, CLIENT_MESSAGES)
async def test_update(
    plant: Plant,
    str_repr: str,
    pdu_class: type[ClientIncomingMessage],
    constructor_kwargs: dict[str, Any],
    mbap_header: bytes,
    inner_frame: bytes,
    ex: ExceptionBase | None,
):
    """Ensure we can update a Plant from PDU Response messages."""
    pdu: ClientIncomingMessage = pdu_class(**constructor_kwargs)
    assert plant.register_caches == {0x32: {}}
    orig_plant_dict = plant.model_dump()
    assert orig_plant_dict == {
        "capabilities": None,
        "register_caches": {0x32: {}},
        "inverter_serial_number": "",
        "data_adapter_serial_number": "",
    }

    plant.update(pdu)

    d = plant.model_dump()
    # with pytest.raises(TypeError, match='keys must be str, int, float, bool or None, not HR'):
    #     plant.json()
    assert d.keys() == {"capabilities", "register_caches", "inverter_serial_number", "data_adapter_serial_number"}

    expected_caches_keys = {0x32}
    if isinstance(pdu, (ReadRegistersResponse, WriteHoldingRegisterResponse)):
        expected_caches_keys.add(pdu.device_address)
    assert set(d["register_caches"].keys()) == expected_caches_keys

    if isinstance(pdu, ReadRegistersResponse):
        assert d != orig_plant_dict
        register_type: type[Register]
        if isinstance(pdu, ReadInputRegistersResponse):
            register_type = IR
        else:
            register_type = HR
        assert len(plant.register_caches[pdu.device_address]) > 30
        assert plant.register_caches[pdu.device_address] == {
            register_type(k): v for k, v in enumerate(pdu.register_values, start=pdu.base_register)
        }
        assert d["register_caches"][pdu.device_address] == {
            register_type(k): v for k, v in enumerate(pdu.register_values, start=pdu.base_register)
        }
        # assert len(j) > 1400
    elif isinstance(pdu, WriteHoldingRegisterResponse):
        assert d != orig_plant_dict
        assert d["register_caches"][pdu.device_address] == {HR(pdu.register): pdu.value}
        # assert j == ''.join(
        #     [
        #         '{"register_caches": {"',
        #         str(pdu.device_address),
        #         '": {"HR(',
        #         str(pdu.register),
        #         ')": ',
        #         str(pdu.value),
        #         '}}, ' '"inverter_serial_number": "SA1234G567", ' '"data_adapter_serial_number": "WF1234G567"}',
        #     ]
        # )
    elif isinstance(pdu, (NullResponse, HeartbeatRequest)):
        assert d["register_caches"] == {k: {} for k in expected_caches_keys}
        # assert j == json.dumps(
        #     {
        #         'register_caches': {k: {} for k in expected_caches_keys},
        #         'inverter_serial_number': '',
        #         'data_adapter_serial_number': '',
        #     }
        # )
    else:  # unknown message
        assert False


def test_from_actual():
    """Ensure we can instantiate a plant from actual register values."""
    register_caches = {
        50: RegisterCache(
            registers={
                HR(0): 8193,
                HR(1): 3,
                HR(2): 2098,
                HR(3): 513,
                HR(4): 0,
                HR(5): 50000,
                HR(6): 3600,
                HR(7): 1,
                HR(8): 16967,
                HR(9): 12594,
                HR(10): 13108,
                HR(11): 18229,
                HR(12): 13879,
                HR(13): 21313,
                HR(14): 12594,
                HR(15): 13108,
                HR(16): 18229,
                HR(17): 13879,
                HR(18): 3005,
                HR(19): 449,
                HR(20): 0,
                HR(21): 449,
                HR(22): 2,
                HR(23): 0,
                HR(24): 32768,
                HR(25): 30235,
                HR(26): 6000,
                HR(27): 1,
                HR(28): 0,
                HR(29): 0,
                HR(30): 17,
                HR(31): 0,
                HR(32): 4,
                HR(33): 7,
                HR(34): 140,
                HR(35): 22,
                HR(36): 4,
                HR(37): 27,
                HR(38): 23,
                HR(39): 29,
                HR(40): 18,
                HR(41): 1,
                HR(42): 2,
                HR(43): 0,
                HR(44): 0,
                HR(45): 0,
                HR(46): 101,
                HR(47): 1,
                HR(48): 0,
                HR(49): 0,
                HR(50): 100,
                HR(51): 0,
                HR(52): 0,
                HR(53): 1,
                HR(54): 1,
                HR(55): 160,
                HR(56): 0,
                HR(57): 0,
                HR(58): 1,
                HR(59): 0,
                HR(60): 1500,
                HR(61): 30,
                HR(62): 30,
                HR(63): 1840,
                HR(64): 2740,
                HR(65): 4700,
                HR(66): 5198,
                HR(67): 126,
                HR(68): 27,
                HR(69): 24,
                HR(70): 28,
                HR(71): 1840,
                HR(72): 2620,
                HR(73): 4745,
                HR(74): 5200,
                HR(75): 126,
                HR(76): 52,
                HR(77): 1,
                HR(78): 28,
                HR(79): 1755,
                HR(80): 2837,
                HR(81): 4700,
                HR(82): 5200,
                HR(83): 2740,
                HR(84): 0,
                HR(85): 0,
                HR(86): 0,
                HR(87): 0,
                HR(88): 0,
                HR(89): 0,
                HR(90): 0,
                HR(91): 0,
                HR(92): 0,
                HR(93): 0,
                HR(94): 30,
                HR(95): 430,
                HR(96): 1,
                HR(97): 4320,
                HR(98): 5850,
                HR(99): 0,
                HR(100): 0,
                HR(101): 0,
                HR(102): 0,
                HR(103): 0,
                HR(104): 0,
                HR(105): 0,
                HR(106): 0,
                HR(107): 0,
                HR(108): 6,
                HR(109): 1,
                HR(110): 4,
                HR(111): 50,
                HR(112): 50,
                HR(113): 0,
                HR(114): 4,
                HR(115): 0,
                HR(116): 100,
                HR(117): 0,
                HR(118): 0,
                HR(119): 0,
                HR(120): 0,
                HR(121): 0,
                HR(122): 0,
                HR(123): 24,
                HR(124): 0,
                HR(125): 1,
                HR(126): 0,
                HR(127): 0,
                HR(128): 1,
                HR(129): 1,
                HR(130): 255,
                HR(131): 20000,
                HR(132): 255,
                HR(133): 20000,
                HR(134): 255,
                HR(135): 20000,
                HR(136): 255,
                HR(137): 20000,
                HR(138): 2484,
                HR(139): 2530,
                HR(140): 2116,
                HR(141): 2070,
                HR(142): 20,
                HR(143): 5,
                HR(144): 2415,
                HR(145): 2300,
                HR(146): 0,
                HR(147): 0,
                HR(148): 0,
                HR(149): 0,
                HR(150): 0,
                HR(151): 0,
                HR(152): 0,
                HR(153): 0,
                HR(154): 0,
                HR(155): 0,
                HR(156): 0,
                HR(157): 0,
                HR(158): 0,
                HR(159): 0,
                HR(160): 0,
                HR(161): 0,
                HR(162): 0,
                HR(163): 0,
                HR(164): 0,
                HR(165): 0,
                HR(166): 0,
                HR(167): 0,
                HR(168): 0,
                HR(169): 0,
                HR(170): 0,
                HR(171): 0,
                HR(172): 0,
                HR(173): 0,
                HR(174): 0,
                HR(175): 0,
                HR(176): 0,
                HR(177): 0,
                HR(178): 0,
                HR(179): 0,
                IR(120): 0,
                IR(121): 0,
                IR(122): 0,
                IR(123): 0,
                IR(124): 0,
                IR(125): 0,
                IR(126): 0,
                IR(127): 0,
                IR(128): 0,
                IR(129): 0,
                IR(130): 0,
                IR(131): 0,
                IR(132): 0,
                IR(133): 0,
                IR(134): 0,
                IR(135): 0,
                IR(136): 0,
                IR(137): 0,
                IR(138): 0,
                IR(139): 0,
                IR(140): 0,
                IR(141): 0,
                IR(142): 0,
                IR(143): 0,
                IR(144): 0,
                IR(145): 0,
                IR(146): 0,
                IR(147): 0,
                IR(148): 0,
                IR(149): 0,
                IR(150): 0,
                IR(151): 0,
                IR(152): 0,
                IR(153): 0,
                IR(154): 0,
                IR(155): 0,
                IR(156): 0,
                IR(157): 0,
                IR(158): 0,
                IR(159): 0,
                IR(160): 0,
                IR(161): 0,
                IR(162): 0,
                IR(163): 0,
                IR(164): 0,
                IR(165): 0,
                IR(166): 0,
                IR(167): 0,
                IR(168): 0,
                IR(169): 0,
                IR(170): 0,
                IR(171): 0,
                IR(172): 0,
                IR(173): 0,
                IR(174): 0,
                IR(175): 0,
                IR(176): 0,
                IR(177): 0,
                IR(178): 0,
                IR(179): 0,
                IR(0): 1,
                IR(1): 180,
                IR(2): 178,
                IR(3): 3885,
                IR(4): 0,
                IR(5): 2404,
                IR(6): 0,
                IR(7): 18527,
                IR(8): 0,
                IR(9): 0,
                IR(10): 41,
                IR(11): 0,
                IR(12): 11929,
                IR(13): 5006,
                IR(14): 5,
                IR(15): 2760,
                IR(16): 8160,
                IR(17): 195,
                IR(18): 0,
                IR(19): 159,
                IR(20): 0,
                IR(21): 0,
                IR(22): 1639,
                IR(23): 0,
                IR(24): 921,
                IR(25): 24,
                IR(26): 123,
                IR(27): 0,
                IR(28): 7211,
                IR(29): 0,
                IR(30): 65497,
                IR(31): 0,
                IR(32): 0,
                IR(33): 19783,
                IR(34): 0,
                IR(35): 43,
                IR(36): 57,
                IR(37): 59,
                IR(38): 0,
                IR(39): 0,
                IR(40): 0,
                IR(41): 322,
                IR(42): 745,
                IR(43): 654,
                IR(44): 380,
                IR(45): 0,
                IR(46): 16987,
                IR(47): 0,
                IR(48): 2754,
                IR(49): 1,
                IR(50): 5128,
                IR(51): 2165,
                IR(52): 1075,
                IR(53): 2390,
                IR(54): 5004,
                IR(55): 318,
                IR(56): 190,
                IR(57): 0,
                IR(58): 266,
                IR(59): 57,
                IR(180): 9061,
                IR(181): 9466,
                IR(182): 59,
                IR(183): 57,
                IR(184): 0,
                IR(185): 0,
                IR(186): 0,
                IR(187): 0,
                IR(188): 0,
                IR(189): 0,
                IR(190): 0,
                IR(191): 0,
                IR(192): 0,
                IR(193): 0,
                IR(194): 0,
                IR(195): 0,
                IR(196): 0,
                IR(197): 0,
                IR(198): 0,
                IR(199): 0,
                IR(200): 0,
                IR(201): 0,
                IR(202): 0,
                IR(203): 0,
                IR(204): 0,
                IR(205): 0,
                IR(206): 0,
                IR(207): 0,
                IR(208): 0,
                IR(209): 0,
                IR(210): 0,
                IR(211): 0,
                IR(212): 0,
                IR(213): 0,
                IR(214): 0,
                IR(215): 0,
                IR(216): 0,
                IR(217): 0,
                IR(218): 0,
                IR(219): 0,
                IR(220): 0,
                IR(221): 0,
                IR(222): 0,
                IR(223): 0,
                IR(224): 0,
                IR(225): 0,
                IR(226): 0,
                IR(227): 300,
                IR(228): 0,
                IR(229): 0,
                IR(230): 0,
                IR(231): 0,
                IR(232): 0,
                IR(233): 0,
                IR(234): 0,
                IR(235): 0,
                IR(236): 0,
                IR(237): 0,
                IR(238): 0,
                IR(239): 0,
                IR(60): 3221,
                IR(61): 3224,
                IR(62): 3219,
                IR(63): 3217,
                IR(64): 3217,
                IR(65): 3216,
                IR(66): 3221,
                IR(67): 3217,
                IR(68): 3225,
                IR(69): 3222,
                IR(70): 3221,
                IR(71): 3221,
                IR(72): 3222,
                IR(73): 3229,
                IR(74): 3227,
                IR(75): 3225,
                IR(76): 199,
                IR(77): 186,
                IR(78): 191,
                IR(79): 182,
                IR(80): 51555,
                IR(81): 255,
                IR(82): 0,
                IR(83): 51548,
                IR(84): 0,
                IR(85): 19202,
                IR(86): 0,
                IR(87): 16000,
                IR(88): 0,
                IR(89): 11071,
                IR(90): 0,
                IR(91): 3600,
                IR(92): 256,
                IR(93): 0,
                IR(94): 0,
                IR(95): 0,
                IR(96): 116,
                IR(97): 16,
                IR(98): 3005,
                IR(99): 0,
                IR(100): 58,
                IR(101): 0,
                IR(102): 16000,
                IR(103): 199,
                IR(104): 186,
                IR(105): 0,
                IR(106): 0,
                IR(107): 0,
                IR(108): 0,
                IR(109): 0,
                IR(110): 16967,
                IR(111): 12594,
                IR(112): 13108,
                IR(113): 18229,
                IR(114): 13879,
                IR(115): 8,
                IR(116): 0,
                IR(117): 0,
                IR(118): 0,
                IR(119): 0,
            }
        ),
        51: RegisterCache(
            registers={
                IR(60): 0,
                IR(61): 0,
                IR(62): 0,
                IR(63): 0,
                IR(64): 0,
                IR(65): 0,
                IR(66): 0,
                IR(67): 0,
                IR(68): 0,
                IR(69): 0,
                IR(70): 0,
                IR(71): 0,
                IR(72): 0,
                IR(73): 0,
                IR(74): 0,
                IR(75): 0,
                IR(76): 45,
                IR(77): 0,
                IR(78): 0,
                IR(79): 0,
                IR(80): 0,
                IR(81): 256,
                IR(82): 0,
                IR(83): 0,
                IR(84): 0,
                IR(85): 0,
                IR(86): 0,
                IR(87): 0,
                IR(88): 0,
                IR(89): 0,
                IR(90): 0,
                IR(91): 0,
                IR(92): 0,
                IR(93): 0,
                IR(94): 0,
                IR(95): 0,
                IR(96): 0,
                IR(97): 0,
                IR(98): 0,
                IR(99): 0,
                IR(100): 0,
                IR(101): 0,
                IR(102): 0,
                IR(103): 0,
                IR(104): 0,
                IR(105): 0,
                IR(106): 0,
                IR(107): 0,
                IR(108): 0,
                IR(109): 0,
                IR(110): 0,
                IR(111): 0,
                IR(112): 0,
                IR(113): 0,
                IR(114): 0,
                IR(115): 0,
                IR(116): 0,
                IR(117): 0,
                IR(118): 0,
                IR(119): 0,
            }
        ),
        52: RegisterCache(
            registers={
                IR(60): 0,
                IR(61): 0,
                IR(62): 0,
                IR(63): 0,
                IR(64): 0,
                IR(65): 0,
                IR(66): 0,
                IR(67): 0,
                IR(68): 0,
                IR(69): 0,
                IR(70): 0,
                IR(71): 0,
                IR(72): 0,
                IR(73): 0,
                IR(74): 0,
                IR(75): 0,
                IR(76): 0,
                IR(77): 0,
                IR(78): 0,
                IR(79): 0,
                IR(80): 0,
                IR(81): 0,
                IR(82): 0,
                IR(83): 0,
                IR(84): 0,
                IR(85): 0,
                IR(86): 0,
                IR(87): 0,
                IR(88): 0,
                IR(89): 0,
                IR(90): 0,
                IR(91): 0,
                IR(92): 0,
                IR(93): 0,
                IR(94): 0,
                IR(95): 0,
                IR(96): 0,
                IR(97): 0,
                IR(98): 0,
                IR(99): 0,
                IR(100): 0,
                IR(101): 0,
                IR(102): 0,
                IR(103): 0,
                IR(104): 0,
                IR(105): 0,
                IR(106): 0,
                IR(107): 0,
                IR(108): 0,
                IR(109): 0,
                IR(110): 0,
                IR(111): 0,
                IR(112): 0,
                IR(113): 0,
                IR(114): 0,
                IR(115): 0,
                IR(116): 0,
                IR(117): 0,
                IR(118): 0,
                IR(119): 0,
            }
        ),
        53: RegisterCache(
            registers={
                IR(60): 0,
                IR(61): 0,
                IR(62): 0,
                IR(63): 0,
                IR(64): 0,
                IR(65): 0,
                IR(66): 0,
                IR(67): 0,
                IR(68): 0,
                IR(69): 0,
                IR(70): 0,
                IR(71): 0,
                IR(72): 0,
                IR(73): 0,
                IR(74): 0,
                IR(75): 0,
                IR(76): 0,
                IR(77): 0,
                IR(78): 0,
                IR(79): 0,
                IR(80): 0,
                IR(81): 0,
                IR(82): 0,
                IR(83): 0,
                IR(84): 0,
                IR(85): 0,
                IR(86): 0,
                IR(87): 0,
                IR(88): 0,
                IR(89): 0,
                IR(90): 0,
                IR(91): 0,
                IR(92): 0,
                IR(93): 0,
                IR(94): 0,
                IR(95): 0,
                IR(96): 0,
                IR(97): 0,
                IR(98): 0,
                IR(99): 0,
                IR(100): 0,
                IR(101): 0,
                IR(102): 0,
                IR(103): 0,
                IR(104): 0,
                IR(105): 0,
                IR(106): 0,
                IR(107): 0,
                IR(108): 0,
                IR(109): 0,
                IR(110): 0,
                IR(111): 0,
                IR(112): 0,
                IR(113): 0,
                IR(114): 0,
                IR(115): 0,
                IR(116): 0,
                IR(117): 0,
                IR(118): 0,
                IR(119): 0,
            }
        ),
        54: RegisterCache(
            registers={
                IR(60): 0,
                IR(61): 0,
                IR(62): 0,
                IR(63): 0,
                IR(64): 0,
                IR(65): 0,
                IR(66): 0,
                IR(67): 0,
                IR(68): 0,
                IR(69): 0,
                IR(70): 0,
                IR(71): 0,
                IR(72): 0,
                IR(73): 0,
                IR(74): 0,
                IR(75): 0,
                IR(76): 0,
                IR(77): 0,
                IR(78): 0,
                IR(79): 0,
                IR(80): 0,
                IR(81): 0,
                IR(82): 0,
                IR(83): 0,
                IR(84): 0,
                IR(85): 0,
                IR(86): 0,
                IR(87): 0,
                IR(88): 0,
                IR(89): 0,
                IR(90): 0,
                IR(91): 0,
                IR(92): 0,
                IR(93): 0,
                IR(94): 0,
                IR(95): 0,
                IR(96): 0,
                IR(97): 0,
                IR(98): 0,
                IR(99): 0,
                IR(100): 0,
                IR(101): 0,
                IR(102): 0,
                IR(103): 0,
                IR(104): 0,
                IR(105): 0,
                IR(106): 0,
                IR(107): 0,
                IR(108): 0,
                IR(109): 0,
                IR(110): 0,
                IR(111): 0,
                IR(112): 0,
                IR(113): 0,
                IR(114): 0,
                IR(115): 0,
                IR(116): 0,
                IR(117): 0,
                IR(118): 0,
                IR(119): 0,
            }
        ),
        55: RegisterCache(
            registers={
                IR(60): 0,
                IR(61): 0,
                IR(62): 0,
                IR(63): 0,
                IR(64): 0,
                IR(65): 0,
                IR(66): 0,
                IR(67): 0,
                IR(68): 0,
                IR(69): 0,
                IR(70): 0,
                IR(71): 0,
                IR(72): 0,
                IR(73): 0,
                IR(74): 0,
                IR(75): 0,
                IR(76): 0,
                IR(77): 0,
                IR(78): 0,
                IR(79): 0,
                IR(80): 0,
                IR(81): 0,
                IR(82): 0,
                IR(83): 0,
                IR(84): 0,
                IR(85): 0,
                IR(86): 0,
                IR(87): 0,
                IR(88): 0,
                IR(89): 0,
                IR(90): 0,
                IR(91): 0,
                IR(92): 0,
                IR(93): 0,
                IR(94): 0,
                IR(95): 0,
                IR(96): 0,
                IR(97): 0,
                IR(98): 0,
                IR(99): 0,
                IR(100): 0,
                IR(101): 0,
                IR(102): 0,
                IR(103): 0,
                IR(104): 0,
                IR(105): 0,
                IR(106): 0,
                IR(107): 0,
                IR(108): 0,
                IR(109): 0,
                IR(110): 0,
                IR(111): 0,
                IR(112): 0,
                IR(113): 0,
                IR(114): 0,
                IR(115): 0,
                IR(116): 0,
                IR(117): 0,
                IR(118): 0,
                IR(119): 0,
            }
        ),
    }

    p = Plant(register_caches=register_caches)
    i = p.inverter
    assert i.model_dump() == {
        "battery_charge_limit": 50,
        "battery_discharge_limit": 50,
        "battery_discharge_min_power_reserve": 4,
        "battery_high_voltage_protection_limit": 58.5,
        "battery_low_force_charge_time": 6,
        "battery_low_voltage_protection_limit": 43.2,
        # 'battery_percent': 57,
        "battery_soc_reserve": 4,
        # 'battery_voltage_adjust': 0,
        "charge_slot_1": TimeSlot.from_repr(30, 430),
        "charge_soc_stop_1": 0,
        "charge_soc_stop_2": 0,
        # 'charge_status': 5,
        "charge_target_soc": 100,
        # 'charger_warning_code': 0,
        "cmd_bms_flash_update": None,
        # 'dci_1_i': 0.0,
        # 'dci_1_time': 0,
        # 'dci_2_i': 0.0,
        # 'dci_2_time': 0,
        # 'dci_fault_value': 0.0,
        "debug_inverter": 0,
        "discharge_soc_stop_1": 0,
        "discharge_soc_stop_2": 0,
        # HYBRID_GEN1 (dtc 0x2001, arm 449): facade routes today→alt2, total→alt1 (#76).
        # Raw IR alt1/alt2 sources are asserted in the IR-block sections below.
        "e_battery_charge_today_alt3": None,  # HR(4114), dead/never polled
        "e_battery_charge_today": 5.7,  # canonical: GEN1 today→alt2 (IR183)
        "e_battery_charge_total_alt2": None,  # HR(4111-4112), dead/never polled
        "e_battery_charge_total": 946.6,  # canonical: GEN1 total→alt1 (IR181)
        "e_battery_discharge_today_alt3": None,  # HR(4113), dead/never polled
        "e_battery_discharge_today": 5.9,  # canonical: GEN1 today→alt2 (IR182)
        "e_battery_discharge_total_alt2": None,  # HR(4109-4110), dead/never polled
        "e_battery_discharge_total": 906.1,  # canonical: GEN1 total→alt1 (IR180)
        # 'e_battery_throughput_total': 1852.7,
        # 'e_discharge_year': 0.0,
        # 'e_grid_in_day': 12.3,
        # 'e_grid_in_total': 1978.3,
        # 'e_grid_out_day': 2.4,
        # 'e_grid_out_total': 163.9,
        "e_inverter_export_total": None,
        # 'e_inverter_in_day': 4.3,
        # 'e_inverter_in_total': 721.1,
        # 'e_inverter_out_day': 38.0,
        # 'e_inverter_out_total': 1698.7,
        # 'e_pv1_day': 19.5,
        # 'e_pv2_day': 15.9,
        # 'e_pv_day': 35.4,
        # 'e_pv_total': 1192.9,
        # 'e_solar_diverter': 0.0,
        "enable_above_6kw_system": False,
        "enable_battery_cable_impedance_alarm": False,
        "enable_battery_on_pv_or_grid": False,
        "enable_bms_read": True,
        "enable_buzzer": False,
        "enable_charge": True,
        "enable_frequency_derating": True,
        "enable_g100_limit_switch": False,
        "enable_inverter_parallel_mode": None,
        "enable_low_voltage_fault_ride_through": False,
        "enable_spi": True,
        "enable_ups_mode": False,
        "smart_load_slot_1": None,
        "smart_load_slot_2": None,
        "smart_load_slot_3": None,
        "smart_load_slot_4": None,
        "smart_load_slot_5": None,
        "smart_load_slot_6": None,
        "smart_load_slot_7": None,
        "smart_load_slot_8": None,
        "smart_load_slot_9": None,
        "smart_load_slot_10": None,
        # 'f_ac1': 50.06,
        # 'f_ac_fault_value': 0.0,
        # 'f_ac_high_c': 52.0,
        # 'f_ac_high_in': 52.0,
        # 'f_ac_high_in_time': 28,
        # 'f_ac_high_out': 51.98,
        # 'f_ac_high_out_time': 28,
        # 'f_ac_low_c': 47.0,
        # 'f_ac_low_in': 47.45,
        # 'f_ac_low_in_time': 1,
        # 'f_ac_low_out': 47.0,
        # 'f_ac_low_out_time': 24,
        # 'f_eps_backup': 50.04,
        # 'fault_code': 0,
        "frequency_load_limit_rate": 24,
        # 'gfci_1_i': 0.0,
        # 'gfci_1_time': 0,
        # 'gfci_2_i': 0.0,
        # 'gfci_2_time': 0,
        # 'gfci_fault_value': 0.0,
        # 'grid_power_adjust': 0,
        # 'grid_r_voltage_adjust': 0,
        # 'grid_s_voltage_adjust': 0,
        # 'grid_t_voltage_adjust': 0,
        # 'i_ac1': 0.41,
        # 'i_battery': 21.65,
        # 'i_grid_port': 2.66,
        # 'i_pv1': 0.0,
        # 'i_pv2': 0.0,
        # 'inverter_countdown': 0,
        # 'inverter_reboot': 0,
        # 'inverter_status': 1,
        # 'island_check_continue': 0,
        # 'iso1': 0,
        # 'iso2': 0,
        # 'iso_fault_value': 0.0,
        "enable_local_command_test": False,
        # 'p_battery': 1075,
        # 'p_eps_backup': 0,
        # 'p_grid_apparent': 654,
        # 'p_grid_out': -39,
        # 'p_inverter_out': 921,
        # 'p_load_demand': 745,
        # 'p_pv': 0,
        # 'p_pv1': 0,
        # 'p_pv2': 0,
        # 'pf_cmd_memory_state': True,
        # 'pf_inverter_out': -0.184,
        # 'pf_limit_lp1_lp': 255,
        # 'pf_limit_lp1_pf': 1.0,
        # 'pf_limit_lp2_lp': 255,
        # 'pf_limit_lp2_pf': 1.0,
        # 'pf_limit_lp3_lp': 255,
        # 'pf_limit_lp3_pf': 1.0,
        # 'pf_limit_lp4_lp': 255,
        # 'pf_limit_lp4_pf': 1.0,
        "power_factor_function_model": PowerFactorFunctionModel.PF_1,
        # 'pv1_power_adjust': 0,
        # 'pv1_voltage_adjust': 0,
        # 'pv2_power_adjust': 0,
        # 'pv2_voltage_adjust': 0,
        "pv_power_setting": None,
        "v_pv_start": 150.0,
        # 'real_v_f_value': 0.0,
        # 'remote_bms_restart': False,
        "restart_delay_time": 30,
        # 'safety_time_limit': 0.0,
        # 'safety_v_f_limit': 0.0,
        "start_countdown_timer": 30,
        "start_system_auto_test": False,
        # 'system_mode': 1,
        # 'temp_battery': 19.0,
        # 'temp_charger': 31.8,
        # 'temp_fault_value': 0.0,
        # 'temp_inverter_heatsink': 32.2,
        # 'test_treat_time': 0,
        # 'test_treat_value': 0.0,
        # 'test_value': 0.0,
        "threephase_abc": 0,
        "threephase_balance_1": 0,
        "threephase_balance_2": 0,
        "threephase_balance_3": 0,
        "threephase_balance_mode": 0,
        # 'user_code': 7,
        # 'v_10_min_protection': 274.0,
        # 'v_ac1': 240.4,
        # 'v_ac_fault_value': 0.0,
        # 'v_ac_high_c': 283.7,
        # 'v_ac_high_in': 262.0,
        # 'v_ac_high_in_time': 52,
        # 'v_ac_high_out': 274.0,
        # 'v_ac_high_out_time': 27,
        # 'v_ac_low_c': 175.5,
        # 'v_ac_low_in': 184.0,
        # 'v_ac_low_in_time': 126,
        # 'v_ac_low_out': 184.0,
        # 'v_ac_low_out_time': 126,
        # 'v_battery': 51.28,
        # 'v_eps_backup': 239.0,
        # 'v_highbrigh_bus': 2760,
        # 'v_n_bus': 0.0,
        # 'v_p_bus': 388.5,
        # 'v_pv1': 18.0,
        # 'v_pv2': 17.8,
        # 'v_pv_fault_value': 0.0,
        # 'work_time_total_hours': 2754,
        "active_power_rate": 100,
        "arm_firmware_version": 449,
        "battery_max_power": 2600,
        "battery_calibration_stage": BatteryCalibrationStage.OFF,
        "battery_capacity_ah": 160,
        "battery_capacity_kwh": 8.192,
        "battery_power_mode": BatteryPowerMode.SELF_CONSUMPTION,
        "battery_type": BatteryType.LITHIUM,
        "bms_firmware_version": 101,
        "charge_slot_2": TimeSlot.from_repr(0, 4),
        "charge_soc": 0,
        "device_type_code": "2001",
        "discharge_slot_1": TimeSlot.from_repr(0, 0),
        "discharge_slot_2": TimeSlot.from_repr(0, 0),
        "discharge_soc": 0,
        "dsp_firmware_version": 449,
        "enable_60hz_freq_mode": False,
        "enable_ammeter": True,
        "enable_auto_judge_battery_type": True,
        "enable_charge_target": False,
        "enable_discharge": False,
        "enable_drm_rj45_port": True,
        "enable_inverter": True,
        "enable_inverter_auto_restart": False,
        "enable_reversed_115_meter": False,
        "enable_reversed_418_meter": False,
        "enable_reversed_ct_clamp": True,
        "firmware_version": "D0.449-A0.449",
        "first_battery_bms_firmware_version": 3005,
        "grid_port_max_power_output": 6000,
        "meter_type": MeterType.EM115,
        "modbus_address": 0x11,
        "modbus_version": "1.40",
        "model": Model.HYBRID,
        "inverter_max_power": 5000,
        "is_ac_coupled": False,
        "module": "00030832",
        "num_mppt": 2,
        "num_phases": 1,
        "power_factor": 0,
        "reactive_power_rate": 0,
        "select_arm_chip": False,
        "serial_number": "SA1234G567",
        "status": Status.NORMAL,
        "v_pv1": 18.0,
        "v_pv2": 17.8,
        "v_p_bus": 388.5,
        "v_n_bus": 0.0,
        "v_ac1": 240.4,
        "e_battery_throughput": 1852.7,
        "i_pv1": 0.0,
        "i_pv2": 0.0,
        "i_ac1": 4.1,
        "e_pv_total": 1192.9,
        "f_ac1": 50.06,
        "charge_status": 5,
        "v_highbrigh_bus": 276.0,
        "pf_inverter_output_now": 8160,
        "e_pv1_day": 19.5,
        "p_pv1": 0,
        "e_pv2_day": 15.9,
        "p_pv2": 0,
        "e_grid_out_total": 163.9,
        "e_solar_diverter": 0.0,
        "p_grid_out_ph1": 921,
        "e_grid_out_day": 2.4,
        "e_grid_in_day": 12.3,
        "e_inverter_in_total": 721.1,
        "e_discharge_year": 0.0,
        "p_grid_out": -39,
        "p_backup": 0,
        "e_grid_in_total": 1978.3,
        "e_ac_charge_today": 4.3,  # IR(35) — was mislabelled e_load_day (#174)
        # computed: e_pv_generation_today + e_grid_in_day − e_grid_out_day − e_ac_charge_today
        #         = 38.0 + 12.3 − 2.4 − 4.3
        "e_consumption_today": 43.6,
        "e_battery_charge_today_alt1": 5.7,  # IR(36)
        "e_battery_discharge_today_alt1": 5.9,  # IR(37)
        "countdown": 0,
        "fault_code": "00000000",
        "t_inverter_heatsink": 32.2,
        "p_load_demand": 745,
        "p_grid_apparent": 654,
        "e_pv_generation_today": 38.0,  # IR(44) — was mislabelled e_inverter_out_day (#174)
        "e_pv_generation_total": 1698.7,  # IR(45/46) — was mislabelled e_inverter_out_total (#174)
        "work_time_total_hours": 2754,
        "system_mode": 1,
        "v_battery": 51.28,
        "i_battery": 21.65,
        "p_battery": 1075,
        "v_ac1_output": 239.0,
        "f_ac1_output": 50.04,
        "t_charger": 31.8,
        "t_battery": 19.0,
        "charger_warning_code": 0,
        "i_grid_port": 2.66,
        "battery_soc": 57,
        "system_time": datetime(2022, 4, 27, 23, 29, 18),
        "usb_device_inserted": SinglePhaseInverterUsbDevice.DISK,
        "user_code": 7,
        "variable_address": 32768,
        "variable_value": 30235,
        "battery_voltage_adjust": 0.0,
        "inverter_reboot": 0,
        "enable_rtc": False,
        "inverter_errors": None,
        "inverter_fault_messages": None,
        "charge_target_soc_1": None,
        "charge_slot_2_x": None,
        "charge_target_soc_2": None,
        "charge_slot_3": None,
        "charge_target_soc_3": None,
        "charge_slot_4": None,
        "charge_target_soc_4": None,
        "charge_slot_5": None,
        "charge_target_soc_5": None,
        "charge_slot_6": None,
        "charge_target_soc_6": None,
        "charge_slot_7": None,
        "charge_target_soc_7": None,
        "charge_slot_8": None,
        "charge_target_soc_8": None,
        "charge_slot_9": None,
        "charge_target_soc_9": None,
        "charge_slot_10": None,
        "charge_target_soc_10": None,
        "discharge_target_soc_1": None,
        "discharge_target_soc_2": None,
        "discharge_slot_3": None,
        "discharge_target_soc_3": None,
        "discharge_slot_4": None,
        "discharge_target_soc_4": None,
        "discharge_slot_5": None,
        "discharge_target_soc_5": None,
        "discharge_slot_6": None,
        "discharge_target_soc_6": None,
        "discharge_slot_7": None,
        "discharge_target_soc_7": None,
        "discharge_slot_8": None,
        "discharge_target_soc_8": None,
        "discharge_slot_9": None,
        "discharge_target_soc_9": None,
        "discharge_slot_10": None,
        "discharge_target_soc_10": None,
        "export_priority": None,
        "battery_charge_limit_ac": None,
        "battery_discharge_limit_ac": None,
        "enable_eps": None,
        "battery_pause_mode": None,
        "battery_pause_slot_1": None,
        "e_battery_discharge_total_alt1": 906.1,  # IR(180)
        "e_battery_charge_total_alt1": 946.6,  # IR(181)
        "e_battery_discharge_today_alt2": 5.9,  # IR(182)
        "e_battery_charge_today_alt2": 5.7,  # IR(183)
        "p_combined_generation": None,
    }

    assert p.number_batteries == 1
    b = p.batteries[0]
    assert b.model_dump() == {
        "bms_firmware_version": 3005,
        "cap_design": 160.0,
        "cap_design2": 160.0,
        "cap_calibrated": 192.02,
        "num_cells": 16,
        "num_cycles": 116,
        "cap_remaining": 110.71,
        "serial_number": "BG1234G567",
        "soc": 58,
        "status_1": 0,
        "status_2": 0,
        "status_3": 14,
        "status_4": 16,
        "status_5": 1,
        "status_6": 0,
        "status_7": 0,
        "t_bms_mosfet": 25.5,
        "t_cells_01_04": 19.9,
        "t_cells_05_08": 18.6,
        "t_cells_09_12": 19.1,
        "t_cells_13_16": 18.2,
        "t_max": 19.9,
        "t_min": 18.6,
        "usb_device_inserted": 8,
        "v_cell_01": 3.221,
        "v_cell_02": 3.224,
        "v_cell_03": 3.219,
        "v_cell_04": 3.217,
        "v_cell_05": 3.217,
        "v_cell_06": 3.216,
        "v_cell_07": 3.221,
        "v_cell_08": 3.217,
        "v_cell_09": 3.225,
        "v_cell_10": 3.222,
        "v_cell_11": 3.221,
        "v_cell_12": 3.221,
        "v_cell_13": 3.222,
        "v_cell_14": 3.229,
        "v_cell_15": 3.227,
        "v_cell_16": 3.225,
        "v_cells_sum": 51.555,
        "v_out": 51.548,
        "warning_1": 0,
        "warning_2": 0,
    }


# ---------------------------------------------------------------------------
# Double-buffer / bank validation tests
# ---------------------------------------------------------------------------


def _make_ir_pdu(
    registers: dict[int, int],
    device_address: int = 0x32,
    base_register: int = 0,
    register_count: int = 60,
) -> ReadInputRegistersResponse:
    """Build a minimal ReadInputRegistersResponse mock for update() tests."""
    pdu = MagicMock(spec=ReadInputRegistersResponse)
    pdu.device_address = device_address
    pdu.base_register = base_register
    pdu.register_count = register_count
    pdu.error = False
    pdu.inverter_serial_number = ""
    pdu.data_adapter_serial_number = ""
    pdu.to_dict.return_value = registers
    pdu.is_suspicious.return_value = False
    return pdu


def _make_hr_pdu(
    registers: dict[int, int],
    device_address: int = 0x32,
    base_register: int = 0,
    register_count: int = 60,
) -> ReadHoldingRegistersResponse:
    """Build a minimal ReadHoldingRegistersResponse mock for update() tests."""
    pdu = MagicMock(spec=ReadHoldingRegistersResponse)
    pdu.device_address = device_address
    pdu.base_register = base_register
    pdu.register_count = register_count
    pdu.error = False
    pdu.inverter_serial_number = ""
    pdu.data_adapter_serial_number = ""
    pdu.to_dict.return_value = registers
    return pdu


def test_commit_bank_valid_registers_are_committed(plant: Plant):
    """A bank with all values within bounds must be written to the cache."""
    # IR(5) = v_ac1, deci, bounds 0–300. Raw 2367 → 236.7 V — valid.
    pdu = _make_ir_pdu({5: 2367})
    plant.update(pdu)
    assert plant.register_caches[0x32].get(IR(5)) == 2367


def test_commit_bank_bounds_violation_logs_and_commits(plant: Plant, caplog):
    """A bank with out-of-bounds values must still be committed; violations are logged at DEBUG."""
    import logging

    # IR(5) = v_ac1; raw 65535 → 6553.5 V, exceeds max=500.0.
    pdu = _make_ir_pdu({5: 65535, 59: 50})
    with caplog.at_level(logging.DEBUG, logger="givenergy_modbus.model.plant"):
        plant.update(pdu)
    assert IR(5) in plant.register_caches[0x32]
    assert IR(59) in plant.register_caches[0x32]
    assert any("bounds" in r.message.lower() for r in caplog.records)


def test_commit_bank_out_of_bounds_overwrites_prior_data(plant: Plant):
    """An out-of-bounds bank is committed and does overwrite previously committed values."""
    plant.register_caches[0x32].update({IR(5): 2367})  # prime with known-good value

    pdu = _make_ir_pdu({5: 65535})
    plant.update(pdu)

    assert plant.register_caches[0x32].get(IR(5)) == 65535  # overwritten by incoming bank


def test_commit_bank_unknown_device_skips_validation(plant: Plant):
    """Banks for unknown device addresses (no getter) are committed without validation."""
    # 0x99 has no getter — unknown hardware passes through unchecked.
    pdu = _make_ir_pdu({5: 65535}, device_address=0x99)
    plant.update(pdu)
    assert plant.register_caches[0x99].get(IR(5)) == 65535


def _make_write_pdu(register: int, value: int, device_address: int = 0x11) -> WriteHoldingRegisterResponse:
    """Build a WriteHoldingRegisterResponse with the envelope serials update() expects."""
    pdu = WriteHoldingRegisterResponse(register=register, value=value, device_address=device_address)
    pdu.inverter_serial_number = ""
    pdu.data_adapter_serial_number = ""
    return pdu


@pytest.mark.parametrize(
    ("model", "read_addr"),
    [(Model.HYBRID_GEN1, 0x31), (Model.HYBRID, 0x11)],
)
def test_write_echo_routed_to_inverter_address(model: Model, read_addr: int):
    """A write echo lands in the cache the model reads (caps.inverter_address).

    Writes go out to 0x11 and the response echoes 0x11, but for AC/HYBRID_GEN1 the model
    reads caps.inverter_address = 0x31. The echo must be routed there so plant.inverter
    reflects the write immediately — without a load_config(), and even though refresh() is
    IR-only. For 0x11 models this is a no-op (echo and reads already share a cache).
    """
    plant = Plant()
    plant.capabilities = PlantCapabilities(device_type=model)
    assert plant.capabilities.inverter_address == read_addr  # guard the premise

    # CHARGE_TARGET_SOC = HR(116); the response echoes the 0x11 write address.
    plant.update(_make_write_pdu(116, 85))

    assert plant.register_caches[read_addr].get(HR(116)) == 85
    # Visible on the model with no load_config/refresh (model_dump is the mypy-clean read).
    assert plant.inverter.model_dump()["charge_target_soc"] == 85


def test_write_echo_not_left_at_wire_address_for_0x31_models():
    """Regression: for HYBRID_GEN1 the echo must NOT remain at the 0x11 wire address.

    Pre-fix the value landed in register_caches[0x11], which plant.inverter (reading 0x31)
    never sees — the reported bug where a write only showed up after load_config().
    """
    plant = Plant()
    plant.capabilities = PlantCapabilities(device_type=Model.HYBRID_GEN1)

    plant.update(_make_write_pdu(116, 85))

    assert HR(116) not in plant.register_caches.get(0x11, RegisterCache())
    assert plant.register_caches[0x31].get(HR(116)) == 85


def test_write_echo_without_capabilities_falls_back_to_wire_address():
    """With no capabilities (write before detect()) the echo stays at the wire address."""
    plant = Plant()
    assert plant.capabilities is None

    plant.update(_make_write_pdu(116, 85))

    assert plant.register_caches[0x11].get(HR(116)) == 85


def test_update_stores_0x11_under_its_true_address(plant: Plant):
    """A response at 0x11 must land in register_caches[0x11], not be rewritten to 0x32.

    Regression for issue #119: the old rewrite folded 0x11/0x00 into 0x32, masking
    that 0x11 is the inverter's canonical address and 0x32 is LV battery pack #1.
    """
    pdu = _make_ir_pdu({5: 2367}, device_address=0x11)
    plant.update(pdu)
    assert plant.register_caches[0x11].get(IR(5)) == 2367
    assert IR(5) not in plant.register_caches.get(0x32, {})


def test_coerce_model_accepts_instance_name_value_and_rejects_garbage():
    """_coerce_model handles a Model instance, an enum name, an enum value, and rejects garbage."""
    assert _coerce_model(Model.EMS) is Model.EMS
    assert _coerce_model("HYBRID") is Model.HYBRID  # enum name
    assert _coerce_model("2") is Model.HYBRID  # enum value (name lookup misses, value lookup hits)
    assert _coerce_model("nonsense") is None
    assert _coerce_model(None) is None


def test_derive_inverter_address_fills_only_when_unpinned_and_coercible():
    """_derive_inverter_address sets the model-derived address, never overrides an explicit one."""
    derived = {"device_type": Model.AC}
    _derive_inverter_address(derived)
    assert derived["inverter_address"] == 0x31

    explicit = {"device_type": Model.EMS, "inverter_address": 0x99}
    _derive_inverter_address(explicit)
    assert explicit["inverter_address"] == 0x99  # explicit wins

    uncoercible = {"device_type": "nonsense"}
    _derive_inverter_address(uncoercible)
    assert "inverter_address" not in uncoercible  # left for Pydantic to reject


def test_getter_for_device_address_with_capabilities():
    """With capabilities, the inverter getter keys at the model's address; 0x32-0x37 are batteries (#119)."""
    plant = Plant(capabilities=PlantCapabilities(device_type=Model.HYBRID))  # inverter at 0x11
    assert plant._getter_for_device_address(0x11).__name__ == "SinglePhaseInverterRegisterGetter"
    assert plant._getter_for_device_address(0x32).__name__ == "BatteryRegisterGetter"
    assert plant._getter_for_device_address(0x05).__name__ == "MeterRegisterGetter"
    assert plant._getter_for_device_address(0x99) is None


def test_commit_bank_incoherent_serial_discards_bank(plant: Plant, caplog):
    """A battery bank whose serial number registers decode to garbage must be discarded.

    The discard is logged at DEBUG, not WARNING — this fires routinely on a shared bus
    when other clients poll empty battery slots and we observe the responses, which
    isn't actionable for the end user.
    """
    import logging

    # Battery serial is at IR(110-114). All zeros → empty string → incoherent.
    pdu = _make_ir_pdu({110: 0, 111: 0, 112: 0, 113: 0, 114: 0, 60: 3221}, device_address=0x33)
    with caplog.at_level(logging.DEBUG, logger="givenergy_modbus.model.plant"):
        plant.update(pdu)
    assert IR(60) not in plant.register_caches.get(0x33, {})
    discard_records = [r for r in caplog.records if "Discarding register bank" in r.message]
    assert len(discard_records) == 1
    assert discard_records[0].levelno == logging.DEBUG, (
        f"discard log must be DEBUG (not actionable for end users), got {discard_records[0].levelname}"
    )


def test_commit_bank_valid_serial_allows_bank(plant: Plant):
    """A battery bank with a valid serial number must be committed."""
    # "BG1234G567" encoded across IR(110-114): each register holds two ASCII chars
    # 'B'=0x42, 'G'=0x47 → 0x4247; '1'=0x31, '2'=0x32 → 0x3132; etc.
    pdu = _make_ir_pdu(
        {110: 0x4247, 111: 0x3132, 112: 0x3334, 113: 0x3536, 114: 0x3738, 60: 3221},
        device_address=0x33,
    )
    plant.update(pdu)
    assert plant.register_caches[0x33].get(IR(60)) == 3221


def test_commit_bank_write_holding_register_bypasses_validation(plant: Plant):
    """WriteHoldingRegisterResponse is always applied — user-initiated writes are trusted."""
    pdu = MagicMock(spec=WriteHoldingRegisterResponse)
    pdu.device_address = 0x32
    pdu.error = False
    pdu.inverter_serial_number = ""
    pdu.data_adapter_serial_number = ""
    pdu.register = 20
    pdu.value = 99999  # deliberately extreme
    plant.update(pdu)
    assert plant.register_caches[0x32].get(HR(20)) == 99999


def test_update_error_pdu_is_ignored(plant: Plant):
    """PDUs with error=True must be silently discarded."""
    pdu = _make_ir_pdu({5: 1234})
    pdu.error = True
    plant.update(pdu)
    assert IR(5) not in plant.register_caches[0x32]


def test_update_discards_suspicious_ir_pdu(plant: Plant):
    """Pattern A (issue #78) substituted IR banks must be rejected before they corrupt the cache.

    `ReadInputRegistersResponse.is_suspicious()` carries the 16-field fingerprint of the
    historic dongle-side response substitution. When it fires, the bank is discarded —
    `_commit_bank` is never called, no register from the suspicious frame reaches the cache.
    """
    pdu = _make_ir_pdu({5: 1234, 59: 0x661E})
    pdu.is_suspicious.return_value = True  # type: ignore[attr-defined]
    plant.update(pdu)
    assert IR(5) not in plant.register_caches[0x32]
    assert IR(59) not in plant.register_caches[0x32]


def test_update_pattern_a_signature_is_recognised_and_discarded(plant: Plant):
    """End-to-end: a real Pattern A fingerprint (per #78) must be rejected via is_suspicious().

    Exercises the actual `is_suspicious()` logic rather than a mocked return value — the
    integration between Plant.update() and the PDU-level fingerprint check.
    """
    # The 17 hardcoded indices/values from is_suspicious(). >5 matches => suspicious.
    pattern_a = {
        28: 0x4C32,
        30: 0xA119,
        31: 0x34EA,
        32: 0xE77F,
        33: 0xD475,
        35: 0x4500,
        40: 0xE4F9,
        41: 0xC0A8,
        43: 0xC0A8,
        46: 0xC5E9,
        50: 0x60EF,
        51: 0x8018,
        52: 0x43E0,
        53: 0xF6CE,
        56: 0x080A,
        58: 0xFCC1,
        59: 0x661E,
    }
    # Build a real ReadInputRegistersResponse rather than a mock so is_suspicious() runs for real.
    real_pdu = ReadInputRegistersResponse(
        base_register=0,
        register_count=60,
        register_values=[pattern_a.get(i, 0) for i in range(60)],
        device_address=0x32,
        inverter_serial_number="",
        data_adapter_serial_number="",
        error=False,
        padding=0x8A,
    )
    plant.update(real_pdu)
    # None of the Pattern A register positions should have been committed.
    for reg in pattern_a:
        assert IR(reg) not in plant.register_caches[0x32], (
            f"IR({reg}) leaked into the cache despite Pattern A fingerprint"
        )


# ---------------------------------------------------------------------------
# Ingestion timestamps (#65) — block_age() / register_block_updated_at
# ---------------------------------------------------------------------------


def test_update_stamps_ingestion_timestamp_on_commit(plant: Plant):
    """A committed IR bank records its ingestion time keyed by (device, type, base)."""
    t = datetime(2026, 6, 6, 12, 0, 0, tzinfo=UTC)
    plant.update(_make_ir_pdu({5: 2367}, base_register=0), received_at=t)
    assert plant.register_block_updated_at[(0x32, "IR", 0, 60)] == t
    # block_age measured from a later 'now' is the elapsed seconds.
    assert plant.block_age(0x32, "IR", 0, 60, now=t + timedelta(seconds=9)) == 9.0


def test_update_stamps_hr_block_distinctly(plant: Plant):
    """HR and IR blocks at the same base are tracked under separate keys."""
    t = datetime(2026, 6, 6, 12, 0, 0, tzinfo=UTC)
    plant.update(_make_hr_pdu({20: 1}, base_register=0), received_at=t)
    assert plant.register_block_updated_at[(0x32, "HR", 0, 60)] == t
    assert (0x32, "IR", 0, 60) not in plant.register_block_updated_at


def test_update_stamps_block_at_its_base_register(plant: Plant):
    """The timestamp key uses the response's base_register, not a fixed 0."""
    t = datetime(2026, 6, 6, 12, 0, 0, tzinfo=UTC)
    plant.update(_make_ir_pdu({180: 1}, base_register=180), received_at=t)
    assert plant.block_age(0x32, "IR", 180, 60, now=t) == 0.0
    assert plant.block_age(0x32, "IR", 0, 60) is None  # a different block was never seen


def test_discarded_bank_is_not_stamped(plant: Plant):
    """An incoherent (discarded) bank must NOT record an ingestion time — it never landed."""
    # All-zero battery serial at IR(110-114) → incoherent → discarded by _commit_bank.
    t = datetime(2026, 6, 6, 12, 0, 0, tzinfo=UTC)
    pdu = _make_ir_pdu({110: 0, 111: 0, 112: 0, 113: 0, 114: 0, 60: 3221}, device_address=0x33, base_register=60)
    plant.update(pdu, received_at=t)
    assert plant.block_age(0x33, "IR", 60, 60) is None


def test_block_age_none_for_never_seen_block(plant: Plant):
    """block_age returns None when the block has never been committed."""
    assert plant.block_age(0x99, "IR", 0, 60) is None


def test_stamp_block_normalises_naive_received_at(plant: Plant):
    """A timezone-naive received_at is treated as UTC rather than raising TypeError (#208 Gemini)."""
    naive = datetime(2026, 6, 6, 12, 0, 0)  # no tzinfo
    plant.update(_make_ir_pdu({5: 2367}, base_register=0), received_at=naive)
    # Should have been stamped at UTC; block_age at the same naive-but-equivalent UTC moment is ~0.
    age = plant.block_age(0x32, "IR", 0, 60, now=datetime(2026, 6, 6, 12, 0, 5, tzinfo=UTC))
    assert age == 5.0


def test_block_age_normalises_naive_now(plant: Plant):
    """A timezone-naive now is treated as UTC rather than raising TypeError (#208 Gemini)."""
    t = datetime(2026, 6, 6, 12, 0, 0, tzinfo=UTC)
    plant.update(_make_ir_pdu({5: 2367}, base_register=0), received_at=t)
    # Pass a naive now that is 7 seconds later; should compute without TypeError.
    age = plant.block_age(0x32, "IR", 0, 60, now=datetime(2026, 6, 6, 12, 0, 7))
    assert age == 7.0


def test_hr_bank_rejected_by_commit_is_not_stamped(plant: Plant):
    """An incoherent HR bank must not record an ingestion timestamp."""
    # Seed non-zero HR data, then push all-zero (Pattern B) to trigger rejection.
    plant.update(_make_hr_pdu({0: 1, 20: 100}, base_register=0))
    plant.update(_make_hr_pdu({0: 0, 20: 0}, base_register=0))
    # Cache should still hold the good values; the all-zero bank was rejected.
    from givenergy_modbus.model.register import HR

    assert plant.register_caches[0x32][HR(0)] == 1
    assert plant.register_caches[0x32][HR(20)] == 100


# ---------------------------------------------------------------------------
# All-zero bank rejection — Pattern B (#206)
# ---------------------------------------------------------------------------


def test_commit_rejects_allzero_over_nonzero_inverter_bank(plant: Plant, caplog):
    """#199: an all-zero IR(0,60) over good inverter data is rejected and logged at WARNING.

    The inverter bank has no serial, so is_coherent can't catch this — the Pattern B rule must.
    This is the genuinely-new protection (and the evidence-collection WARNING).
    """
    import logging

    plant.update(_make_ir_pdu({0: 1, 5: 2367}, device_address=0x32))
    with caplog.at_level(logging.WARNING, logger="givenergy_modbus.model.plant"):
        plant.update(_make_ir_pdu({0: 0, 5: 0}, device_address=0x32))
    assert plant.register_caches[0x32][IR(5)] == 2367  # last-good retained, not zeroed
    assert plant.register_caches[0x32][IR(0)] == 1
    warns = [r for r in caplog.records if r.levelno == logging.WARNING and "Pattern B" in r.message]
    assert len(warns) == 1, "an all-zero bank rejected over good data must log once at WARNING"


def test_commit_rejects_allzero_over_nonzero_battery_bank(plant: Plant):
    """#147: an all-zero battery page over previously-good data is rejected (kept last-good)."""
    # Valid serial ("BG1234G567" across IR110-114) + data, so the seed is coherent and commits.
    seed = {110: 0x4247, 111: 0x3132, 112: 0x3334, 113: 0x3536, 114: 0x3738, 60: 3221}
    plant.update(_make_ir_pdu(seed, device_address=0x33, base_register=60))
    assert plant.register_caches[0x33][IR(60)] == 3221
    plant.update(_make_ir_pdu(dict.fromkeys(seed, 0), device_address=0x33, base_register=60))
    assert plant.register_caches[0x33][IR(60)] == 3221  # retained


def test_commit_allows_allzero_on_first_read(plant: Plant):
    """An all-zero bank with no prior data (absent / first read) is NOT rejected by Pattern B.

    Uses an unknown device (no getter) so the Pattern B check is the only gate in play.
    """
    plant.update(_make_ir_pdu({60: 0, 61: 0}, device_address=0x99, base_register=60))
    assert IR(60) in plant.register_caches[0x99]  # committed, not rejected


def test_commit_allows_mixed_bank_with_some_nonzero(plant: Plant):
    """A bank with any non-zero value commits normally — the all-zero gate must not catch it."""
    plant.update(_make_ir_pdu({0: 0, 1: 5, 2: 0}, device_address=0x32))
    assert plant.register_caches[0x32][IR(1)] == 5


def test_allzero_rejection_preserves_staleness(plant: Plant):
    """A rejected all-zero bank records no ingestion timestamp, so block_age keeps growing (#65/#206)."""
    t0 = datetime(2026, 6, 6, 12, 0, 0, tzinfo=UTC)
    plant.update(_make_ir_pdu({0: 1, 5: 2367}, device_address=0x32), received_at=t0)
    t1 = t0 + timedelta(seconds=30)
    plant.update(_make_ir_pdu({0: 0, 5: 0}, device_address=0x32), received_at=t1)  # rejected
    # age reflects t0 (last good commit), not t1 — the rejected bank left no fresh stamp.
    assert plant.block_age(0x32, "IR", 0, 60, now=t0 + timedelta(seconds=45)) == 45.0


def test_commit_allows_short_read_zero_transition(plant: Plant):
    """Pattern B must not block a short read (register_count < 60) going legitimately to zero.

    A single-register fan-out of e.g. a power reading can validly go non-zero → zero (power
    off at night) and must commit normally. Regression for Codex review on PR #208.
    """
    # Seed a non-zero value for a single register at device 0x32.
    plant.update(_make_ir_pdu({5: 100}, device_address=0x32, register_count=1))
    # A subsequent single-register read returning zero should commit, not be rejected.
    plant.update(_make_ir_pdu({5: 0}, device_address=0x32, register_count=1))
    assert plant.register_caches[0x32][IR(5)] == 0  # zero committed normally


def test_getter_for_device_meter_address(plant: Plant):
    """A bank arriving on a meter device address (0x01–0x08) must be accepted."""
    pdu = _make_ir_pdu({0: 1}, device_address=0x01)
    plant.update(pdu)
    assert 0x01 in plant.register_caches


def test_getter_for_device_bcu_address(plant: Plant):
    """A bank arriving on a BCU device address (0x70–0x8F) must be accepted."""
    pdu = _make_ir_pdu({0: 42}, device_address=0x70)
    plant.update(pdu)
    assert 0x70 in plant.register_caches


class TestPlantCapabilitiesProperties:
    """PlantCapabilities predicate properties return correct values per device type."""

    from givenergy_modbus.model.plant import PlantCapabilities

    def _caps(self, model: Model) -> "PlantCapabilities":
        """Build a minimal PlantCapabilities for the given model."""
        from givenergy_modbus.model.plant import PlantCapabilities

        return PlantCapabilities(device_type=model)

    def test_is_hv_true_for_hv_models(self):
        """HV models report is_hv True."""
        for m in (Model.HYBRID_3PH, Model.AC_3PH, Model.ALL_IN_ONE, Model.HYBRID_HV_GEN3, Model.ALL_IN_ONE_HYBRID):
            assert self._caps(m).is_hv, f"{m} should be HV"

    def test_is_hv_false_for_single_phase(self):
        """Single-phase hybrid reports is_hv False."""
        assert not self._caps(Model.HYBRID).is_hv

    def test_is_three_phase_true(self):
        """Three-phase models report is_three_phase True."""
        three_phase = (
            Model.HYBRID_3PH,
            Model.AC_3PH,
            Model.AIO_COMMERCIAL,
            Model.ALL_IN_ONE_HYBRID,
            Model.HYBRID_HV_GEN3,
        )
        for m in three_phase:
            assert self._caps(m).is_three_phase, f"{m} should be three-phase"

    def test_is_three_phase_false(self):
        """Single-phase and non-inverter models report is_three_phase False.

        The residential ALL_IN_ONE (DTC family "8", e.g. 0x8001) is HV but single-phase: it
        has no 1000-range per-phase bank (it error-responds to those reads) and so must NOT
        be polled there. Confirmed against real AIO hardware + owner confirmation (#105).
        """
        for m in (Model.HYBRID, Model.AC, Model.EMS, Model.GATEWAY, Model.ALL_IN_ONE):
            assert not self._caps(m).is_three_phase, f"{m} should not be three-phase"

    def test_all_in_one_is_hv_and_extended_but_not_three_phase(self):
        """The AIO keeps its HV + extended-slot capabilities while not being three-phase.

        Guards the split: removing ALL_IN_ONE from the per-phase poll set must not regress
        the capabilities that are correctly model-keyed (HV battery, 10-slot map).
        """
        caps = self._caps(Model.ALL_IN_ONE)
        assert caps.is_hv is True
        assert caps.has_extended_slots is True
        assert caps.is_three_phase is False

    def test_has_extended_slots_true(self):
        """Models with 10-slot support report has_extended_slots True."""
        extended = (
            Model.HYBRID_GEN3,
            Model.HYBRID_GEN4,
            Model.ALL_IN_ONE,
            Model.ALL_IN_ONE_HYBRID,
            Model.HYBRID_HV_GEN3,
        )
        for m in extended:
            assert self._caps(m).has_extended_slots, f"{m} should have extended slots"

    def test_has_extended_slots_false(self):
        """Non-extended models report has_extended_slots False."""
        for m in (Model.HYBRID, Model.HYBRID_GEN2, Model.AC, Model.EMS):
            assert not self._caps(m).has_extended_slots, f"{m} should not have extended slots"

    def test_has_ac_config_block_true(self):
        """AC-coupled inverters and the All-in-One carry the HR(300-359) AC-output config block."""
        for m in (Model.AC, Model.AC_3PH, Model.ALL_IN_ONE):
            assert self._caps(m).has_ac_config_block, f"{m} should have the AC config block"

    def test_has_ac_config_block_false(self):
        """DC-coupled/hybrid models lack HR(300-359) and time out if polled for it (#162)."""
        for m in (Model.HYBRID, Model.HYBRID_GEN1, Model.HYBRID_GEN3, Model.HYBRID_3PH, Model.EMS, Model.GATEWAY):
            assert not self._caps(m).has_ac_config_block, f"{m} should not have the AC config block"

    def test_has_smart_load_block_empty_for_all_models(self):
        """No model carries a confirmed readable HR(540-599) Smart Load block yet (#179).

        The gate set is deliberately empty pending live-hardware confirmation; HYBRID_GEN1
        is confirmed to time out on the read. When a model is confirmed, add it to
        _SMART_LOAD_CAPABLE_MODELS and assert it here.
        """
        for m in (
            Model.HYBRID,
            Model.HYBRID_GEN1,
            Model.HYBRID_GEN3,
            Model.HYBRID_GEN4,
            Model.AC,
            Model.AC_3PH,
            Model.ALL_IN_ONE,
            Model.HYBRID_3PH,
            Model.EMS,
            Model.GATEWAY,
        ):
            assert not self._caps(m).has_smart_load_block, f"{m} should not have the Smart Load block"

    def test_is_ems_true(self):
        """EMS and EMS_COMMERCIAL report is_ems True."""
        assert self._caps(Model.EMS).is_ems
        assert self._caps(Model.EMS_COMMERCIAL).is_ems

    def test_is_ems_false(self):
        """Non-EMS models report is_ems False."""
        assert not self._caps(Model.HYBRID).is_ems

    def test_is_gateway(self):
        """GATEWAY reports is_gateway True; other models False."""
        assert self._caps(Model.GATEWAY).is_gateway
        assert not self._caps(Model.HYBRID).is_gateway


def test_plant_capabilities_is_ac_coupled():
    """PlantCapabilities.is_ac_coupled gates AC-only controls without a hardcoded model set.

    This is the surface the givenergy-hass consumer relies on (composed with
    `not is_three_phase` to scope single-phase AC). True for both AC families,
    False for DC-coupled systems.
    """
    assert PlantCapabilities(device_type=Model.AC).is_ac_coupled is True
    assert PlantCapabilities(device_type=Model.AC_3PH).is_ac_coupled is True
    for model in (Model.HYBRID, Model.HYBRID_3PH, Model.ALL_IN_ONE, Model.EMS, Model.GATEWAY):
        assert PlantCapabilities(device_type=model).is_ac_coupled is False, f"{model} not AC-coupled"

    # The consumer's composition: single-phase AC is AC-coupled and not three-phase.
    ac = PlantCapabilities(device_type=Model.AC)
    assert (ac.is_ac_coupled and not ac.is_three_phase) is True
    ac3 = PlantCapabilities(device_type=Model.AC_3PH)
    assert (ac3.is_ac_coupled and not ac3.is_three_phase) is False


# ---------------------------------------------------------------------------
# Inverter-serial identity: only the inverter's own PDU sets it (givenergy-hass#95)
# ---------------------------------------------------------------------------


def test_inverter_serial_not_clobbered_by_module_pdu():
    """A module PDU's envelope serial must not overwrite the real inverter serial (hass#95).

    On an AIO the 0x50-0x53 battery-module responses carry their own HX… serial in the PDU
    envelope. Adopting it would merge the inverter device into a battery module downstream. The
    dongle (data_adapter) serial is identical on every response, so it rides along unchanged.
    """
    plant = Plant(capabilities=PlantCapabilities(device_type=Model.ALL_IN_ONE, inverter_address=0x11))

    inv = _make_ir_pdu({5: 2367}, device_address=0x11)
    inv.inverter_serial_number = "CH2414G047"
    inv.data_adapter_serial_number = "WJ2414G000"
    plant.update(inv)
    assert plant.inverter_serial_number == "CH2414G047"
    assert plant.data_adapter_serial_number == "WJ2414G000"

    module = _make_ir_pdu({60: 3280}, device_address=0x50)
    module.inverter_serial_number = "HX2414G047"
    module.data_adapter_serial_number = "WJ2414G000"  # same dongle on every response
    plant.update(module)
    assert plant.inverter_serial_number == "CH2414G047", "module envelope must not clobber inverter serial"
    assert plant.data_adapter_serial_number == "WJ2414G000"


def test_data_adapter_serial_adopted_from_any_device_but_inverter_serial_is_not():
    """The dongle serial is adopted from a peripheral-only stream; the inverter serial is not.

    data_adapter_serial_number identifies the TCP dongle, identical across every response
    regardless of addressed device, so a battery/meter/BCU response must still populate it.
    inverter_serial_number stays gated to the inverter address.
    """
    plant = Plant()

    batt = _make_ir_pdu({60: 3221}, device_address=0x32)
    batt.inverter_serial_number = "ZZ9999Z999"  # the battery's own envelope serial
    batt.data_adapter_serial_number = "WJ2414G000"
    plant.update(batt)

    assert plant.data_adapter_serial_number == "WJ2414G000", "dongle serial must be adopted from any PDU"
    assert plant.inverter_serial_number == "", "a battery PDU must not set the inverter serial"


def test_inverter_serial_set_from_canonical_addresses():
    """Both canonical inverter addresses (0x11 and the AC/HYBRID_GEN1 0x31 facade) set the serial."""
    plant = Plant()

    inv = _make_ir_pdu({5: 2367}, device_address=0x11)
    inv.inverter_serial_number = "CH2414G047"
    plant.update(inv)
    assert plant.inverter_serial_number == "CH2414G047"

    facade = _make_ir_pdu({5: 2367}, device_address=0x31)
    facade.inverter_serial_number = "SA2114G047"
    plant.update(facade)
    assert plant.inverter_serial_number == "SA2114G047"


def test_inverter_serial_ignores_stale_0x32_capability():
    """Even a stale pre-#119 capability with inverter_address=0x32 can't let a battery PDU set it.

    0x32 is battery pack #1; a persisted pre-#119 capability may still carry it as the inverter
    address until detect() self-heals. The gate is the canonical {0x11, 0x31} set, so 0x32 never
    qualifies regardless of capabilities.
    """
    plant = Plant(capabilities=PlantCapabilities(device_type=Model.HYBRID_GEN1, inverter_address=0x32))

    batt = _make_ir_pdu({60: 3221}, device_address=0x32)
    batt.inverter_serial_number = "ZZ9999Z999"
    plant.update(batt)
    assert plant.inverter_serial_number == "", "a stale 0x32 inverter_address must not let a battery clobber it"


def test_plant_redact_clears_header_serials_and_redacts_caches():
    """Plant.redact() redacts every cache AND the out-of-cache header serials (audit H2).

    inverter_serial_number / data_adapter_serial_number live on the Plant, not in any cache, so
    redacting caches alone still leaks them in a shared dump. redact() returns a copy with both
    the caches and the header serials redacted, leaving the original untouched.
    """

    def _enc(serial, base):
        padded = serial.encode("latin1").ljust(10, b"\x00")[:10]
        return {HR(base + i): int.from_bytes(padded[i * 2 : i * 2 + 2], "big") for i in range(5)}

    plant = Plant()
    plant.inverter_serial_number = "CH2414G047"
    plant.data_adapter_serial_number = "WF2414G047"
    plant.register_caches[0x11] = RegisterCache(_enc("SA2114G123", 13))  # inverter serial HR(13-17)

    redacted = plant.redact()

    assert redacted.inverter_serial_number == "CH2414G000"
    assert redacted.data_adapter_serial_number == "WF2414G000"
    raw = b"".join((redacted.register_caches[0x11][HR(13 + i)] & 0xFFFF).to_bytes(2, "big") for i in range(5))
    assert raw.decode("latin1").replace("\x00", "").upper() == "SA2114G000"
    # original untouched
    assert plant.inverter_serial_number == "CH2414G047"
    orig = b"".join((plant.register_caches[0x11][HR(13 + i)] & 0xFFFF).to_bytes(2, "big") for i in range(5))
    assert orig.decode("latin1").replace("\x00", "").upper() == "SA2114G123"


def test_plant_redact_handles_empty_serials():
    """redact() with empty header serials returns empty, not an error (audit H2 — the `or ''` path)."""
    plant = Plant()
    plant.inverter_serial_number = ""
    plant.data_adapter_serial_number = ""
    redacted = plant.redact()
    assert redacted.inverter_serial_number == ""
    assert redacted.data_adapter_serial_number == ""


def test_plant_redact_fails_closed_on_unrecognised_header_serial():
    """redact() blanks an unrecognised header serial rather than leaking it (audit H2, fail-closed).

    Converter.redact_serial is fail-open (returns unrecognised shapes unchanged); the share-safe
    redact() must not pass a vendor/non-standard identifier through verbatim.
    """
    plant = Plant()
    plant.inverter_serial_number = "UNKNOWN123"  # valid charset, matches no GE pattern
    plant.data_adapter_serial_number = "ODD-SERIAL"

    redacted = plant.redact()

    assert redacted.inverter_serial_number == ""
    assert redacted.data_adapter_serial_number == ""
