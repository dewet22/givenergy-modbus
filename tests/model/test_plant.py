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
    ChargeStatus,
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
        "enable_plant_mode": None,
        "plant_role": None,
        "plant_meters": None,
        "overfrequency_load_drop_recovery_delay": None,
        "mppt_operating_mode": None,
        "connection_loading_slope": None,
        "eps_nominal_voltage": None,
        "underfrequency_add_load_delay": None,
        "en50549_zero_current_lower_voltage_limit": None,
        "en50549_zero_current_upper_voltage_limit": None,
        "overfrequency_derating_start_point": None,
        "enable_tariff_pricing_battery_logic": None,
        "import_price_battery_discharge_threshold": None,
        "import_price_battery_charge_threshold": None,
        "export_price_battery_discharge_threshold": None,
        "underfrequency_derating_start_point": None,
        "underfrequency_loading_slope": None,
        "overfrequency_derating_stop_point": None,
        "enable_bms_ocv_calibration": None,
        "gateway_power_off_setting": None,
        "force_off_grid": None,
        "enable_micro_grid": None,
        "enable_ev_charger": None,
        "ev_charger_import_limit": None,
        "ev_charger_reconnection_wait_time": None,
        "ev_charger_soc_limit": None,
        "enable_fan": None,
        "fan_speed": None,
        "enable_gateway": None,
        "bms_communication_mode": None,
        "n_pe_relay_toggle": None,
        "afci_setting": None,
        "enable_generator": None,
        "generator_start_soc": None,
        "generator_stop_soc": None,
        "generator_charge_power": None,
        "disable_leds": None,
        "lcd_screen_idle_timeout": None,
        "lead_acid_battery_calibration_upper_limit": None,
        "lead_acid_battery_calibration_lower_limit": None,
        "inverter_operating_mode": None,
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
        "power_factor": -1.0,
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
        "charge_status_label": ChargeStatus.DISCHARGING,
        "v_highbrigh_bus": 276.0,
        "pf_inverter_output_now": -0.184,
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
        # computed: max(0, e_pv_generation_today − e_grid_out_day) = max(0, 38.0 − 2.4)
        "e_self_consumption_today": 35.6,
        # computed: max(0, e_pv_generation_total − e_grid_out_total) = max(0, 1698.7 − 163.9)
        "e_self_consumption_total": 1534.8,
        # computed: max(0, (pv − grid_out) − max(0, battery_charge − ac_charge))
        #         = max(0, 38.0 − 2.4 − max(0, 5.7 − 4.3)) = max(0, 35.6 − 1.4) = 34.2
        "e_pv_direct_today": 34.2,
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
        "charger_warning_messages": [],
        "i_grid_port": 2.66,
        "battery_soc": 57,
        "system_time": datetime(2022, 4, 27, 23, 29, 18),
        "usb_device_inserted": SinglePhaseInverterUsbDevice.DISK,
        "user_code": 7,
        "variable_address": 32768,
        "variable_value": 30235,
        "iso_protection_1": 0,
        "iso_protection_2": 0,
        "gfci_protection_value_1": 0,
        "gfci_protection_time_1": 0,
        "gfci_protection_value_2": 0,
        "gfci_protection_time_2": 0,
        "dci_protection_value_1": 0,
        "dci_protection_time_1": 0,
        "dci_protection_value_2": 0,
        "dci_protection_time_2": 0,
        "string_1_voltage_adjustment": 0,
        "string_2_voltage_adjustment": 0,
        "grid_r_voltage_adjustment": 0,
        "grid_s_voltage_adjustment": 0,
        "grid_t_voltage_adjustment": 0,
        "grid_power_adjustment": 0,
        "string_1_power_adjustment": 0,
        "string_2_power_adjustment": 0,
        "power_factor_cmd_memory_state": 1,
        "power_factor_point_1_load_percent": 255,
        "power_factor_point_1_power_factor": 20000,
        "power_factor_point_2_load_percent": 255,
        "power_factor_point_2_power_factor": 20000,
        "power_factor_point_3_load_percent": 255,
        "power_factor_point_3_power_factor": 20000,
        "power_factor_point_4_load_percent": 255,
        "power_factor_point_4_power_factor": 20000,
        "cei021_v1s_q": 2484,
        "cei021_v2s_q": 2530,
        "cei021_v1l_q": 2116,
        "cei021_v2l_q": 2070,
        "cei021_lock_in_active_power": 20,
        "cei021_lock_out_active_power": 5,
        "cei021_lock_in_grid_voltage": 2415,
        "cei021_lock_out_grid_voltage": 2300,
        "lvfrt_reactive_rate": 0,
        "lvfrt_low_fault_value_1": 0,
        "lvfrt_low_fault_time_1": 0,
        "lvfrt_low_fault_value_2": 0,
        "lvfrt_low_fault_time_2": 0,
        "lvfrt_low_fault_value_3": 0,
        "lvfrt_low_fault_time_3": 0,
        "lvfrt_low_fault_value_4": 0,
        "lvfrt_low_fault_time_4": 0,
        "lvfrt_high_fault_value_1": 0,
        "lvfrt_high_fault_time_1": 0,
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
        "v_ac_low_limit_trip": 184.0,
        "v_ac_high_limit_trip": 274.0,
        "f_ac_low_limit_trip": 47.0,
        "f_ac_high_limit_trip": 51.98,
        "t_ac_low_voltage_trip": 1.26,
        "t_ac_high_voltage_trip": 0.27,
        "t_ac_low_freq_trip": 0.24,
        "t_ac_high_freq_trip": 0.28,
        "v_ac_low_limit_reconnect": 184.0,
        "v_ac_high_limit_reconnect": 262.0,
        "f_ac_low_limit_reconnect": 47.45,
        "f_ac_high_limit_reconnect": 52.0,
        "t_ac_low_voltage_reconnect": 1.26,
        "t_ac_high_voltage_reconnect": 0.52,
        "t_ac_low_freq_reconnect": 0.01,
        "t_ac_high_freq_reconnect": 0.28,
        "v_ac_low_limit_grid": 175.5,
        "v_ac_high_limit_grid": 283.7,
        "f_ac_low_limit_grid": 47.0,
        "f_ac_high_limit_grid": 52.0,
        "v_ac_10min_protect": 274.0,
        "battery_nominal_power": None,
        "battery_nominal_current": None,
        "battery_max_charge_pct": None,
        "hv_cabinet_count": None,
        "hv_racks_per_cabinet": None,
        "hv_batteries_per_rack": None,
        "hv_cells_per_battery": None,
        "hv_total_cells": None,
        "hv_temp_sensors_per_battery": None,
        "hv_total_temp_sensors": None,
        "hv_max_pcs_power": None,
        "hv_max_charge_voltage": None,
        "hv_min_discharge_voltage": None,
        "hv_max_charge_current": None,
        "hv_parallel_count": None,
        "peak_shaving_export_limit_enabled": None,
        "peak_shaving_export_limit": None,
        "peak_shaving_enabled": None,
        "peak_shaving_threshold": None,
        "peak_shaving_import_limit_enabled": None,
        "peak_shaving_import_limit": None,
        "peak_shaving_power": None,
        "valley_filling_power": None,
        "p_combined_generation": None,
        "grid_import_power": 39,  # p_grid_out=-39 → importing
        "grid_export_power": 0,
        "battery_charge_power": 0,
        "battery_discharge_power": 1075,  # p_battery=1075 → discharging
    }

    assert p.number_batteries == 1
    b = p.batteries[0]
    assert b.model_dump() == {
        "bms_firmware_version": 3005,
        "cap_design": 160.0,
        "cap_design2": 160.0,
        "cap_calibrated": 192.02,
        "e_battery_charge_total": 0.0,
        "e_battery_discharge_total": 0.0,
        "force_discharge_flag": 0,
        "i_battery": 0.0,
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
    ("model", "explicit_addr", "read_addr"),
    [
        # pre-#189 persisted capability still pointing at the 0x31 facade
        (Model.HYBRID_GEN1, 0x31, 0x31),
        # current derivation: every model reads at 0x11 (#189)
        (Model.HYBRID_GEN1, None, 0x11),
        (Model.HYBRID, None, 0x11),
    ],
)
def test_write_echo_routed_to_inverter_address(model: Model, explicit_addr: int | None, read_addr: int):
    """A write echo lands in the cache the model reads (caps.inverter_address).

    Writes go out to 0x11 and the response echoes 0x11. Since #189 the model also reads
    at 0x11, making the routing a no-op — but a pre-#189 persisted capability may still
    say 0x31 (the AC/HYBRID_GEN1 facade), and the echo must follow it there so
    plant.inverter reflects the write immediately — without a load_config(), and even
    though refresh() is IR-only.
    """
    plant = Plant()
    if explicit_addr is not None:
        plant.capabilities = PlantCapabilities(device_type=model, inverter_address=explicit_addr)
    else:
        plant.capabilities = PlantCapabilities(device_type=model)
    assert plant.capabilities.inverter_address == read_addr  # guard the premise

    # CHARGE_TARGET_SOC = HR(116); the response echoes the 0x11 write address.
    plant.update(_make_write_pdu(116, 85))

    assert plant.register_caches[read_addr].get(HR(116)) == 85
    # Visible on the model with no load_config/refresh (model_dump is the mypy-clean read).
    assert plant.inverter.model_dump()["charge_target_soc"] == 85


def test_write_echo_not_left_at_wire_address_for_persisted_0x31_caps():
    """Regression: with a capability still reading at 0x31, the echo must NOT stay at 0x11.

    Pre-#187 the value landed in register_caches[0x11], which plant.inverter (reading 0x31)
    never saw — the reported bug where a write only showed up after load_config(). Since
    #189 a 0x31 read address only arises from a pre-#189 persisted capability, simulated
    here with an explicit inverter_address.
    """
    plant = Plant()
    plant.capabilities = PlantCapabilities(device_type=Model.HYBRID_GEN1, inverter_address=0x31)

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
    assert derived["inverter_address"] == 0x11

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


def test_getter_for_device_address_lv_bcu():
    """When capabilities carry lv_bcu_address, that address routes to LvBcuRegisterGetter (#241)."""
    from givenergy_modbus.model.lv_bcu import LvBcuRegisterGetter

    plant = Plant(capabilities=PlantCapabilities(device_type=Model.HYBRID, lv_bcu_address=0x31))
    assert plant._getter_for_device_address(0x31) is LvBcuRegisterGetter


def test_getter_for_device_address_hv_bmu():
    """Addresses in hv_bmu_addresses route to BmuRegisterGetter for refresh validation (#265)."""
    from givenergy_modbus.model.hv_bcu import BmuRegisterGetter

    plant = Plant(capabilities=PlantCapabilities(device_type=Model.HYBRID_HV_GEN3, hv_bmu_addresses=[0x50, 0x51]))
    assert plant._getter_for_device_address(0x50) is BmuRegisterGetter
    assert plant._getter_for_device_address(0x51) is BmuRegisterGetter
    assert plant._getter_for_device_address(0x52) is None  # not in the list → unrouted


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
    """A battery bank with a valid serial number must be committed (after #289 cold-start corroboration)."""
    # "BG1234G567" encoded across IR(110-114): each register holds two ASCII chars
    # 'B'=0x42, 'G'=0x47 → 0x4247; '1'=0x31, '2'=0x32 → 0x3132; etc.
    bank = {110: 0x4247, 111: 0x3132, 112: 0x3334, 113: 0x3536, 114: 0x3738, 60: 3221}
    plant.update(_make_ir_pdu(bank, device_address=0x33))  # held (cold-start, #289)
    plant.update(_make_ir_pdu(bank, device_address=0x33))  # corroborates → committed
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
    plant.update(_make_ir_pdu(seed, device_address=0x33, base_register=60))  # held (cold-start, #289)
    plant.update(_make_ir_pdu(seed, device_address=0x33, base_register=60))  # corroborates → commits
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

    def test_has_hv_cabinet_block_empty_for_all_models(self):
        """No model carries a confirmed readable HR(499-510) HV cabinet topology block yet.

        The gate set is deliberately empty pending live-hardware confirmation. When a
        model is confirmed, add it to _HV_CABINET_MODELS and assert it here.
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
            assert not self._caps(m).has_hv_cabinet_block, f"{m} should not have the HV cabinet block"

    def test_has_peak_shaving_block_empty_for_all_models(self):
        """No model carries a confirmed readable HR(20000-20051) peak-shaving block yet.

        The gate set is deliberately empty pending live-hardware confirmation. When a
        model is confirmed, add it to _PEAK_SHAVING_MODELS and assert it here.
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
            assert not self._caps(m).has_peak_shaving_block, f"{m} should not have the peak-shaving block"

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
# Content-staleness primitive (#91) — content_unchanged_seconds / _track_content_change
#
# Reports how long a register block's content has been byte-identical, keyed off the
# #65 ingestion timestamps. This is the duration substrate the eventual freeze detector
# needs — NOT a freeze verdict: replaying the real corpus showed healthy LV batteries
# hold byte-identical IR(60,60) content for 23-26 consecutive samples (dongle fan-out +
# genuinely-static telemetry), so a verdict needs a threshold validated against more
# than the single freeze capture we have. content_unchanged_seconds() reports the raw
# fact (a duration), makes no claim, and survives arbitrarily long unchanged runs.
# ---------------------------------------------------------------------------


def _feed_bank(
    plant: "Plant",
    bank: dict[int, int],
    *,
    device_address: int = 0x32,
    reg_type: str = "IR",
    base: int = 60,
    count: int = 60,
    received_at: datetime | None = None,
) -> None:
    """Feed one committed bank directly, bypassing PDU construction overhead."""
    pdu: ReadInputRegistersResponse | ReadHoldingRegistersResponse
    if reg_type == "IR":
        pdu = _make_ir_pdu(bank, device_address=device_address, base_register=base, register_count=count)
    else:
        pdu = _make_hr_pdu(bank, device_address=device_address, base_register=base, register_count=count)
    plant.update(pdu, received_at=received_at)


_T0 = datetime(2026, 6, 9, 12, 0, 0, tzinfo=UTC)


def test_content_unchanged_seconds_none_for_never_seen(plant: Plant):
    """A block that has never committed reports None, not a spurious duration."""
    assert plant.content_unchanged_seconds(0x32, "IR", 60, 60) is None


def test_content_unchanged_seconds_accumulates_while_identical(plant: Plant):
    """Identical consecutive banks hold unchanged_since at the first commit, so the duration grows."""
    bank = {110: 0x4358, 111: 0x3232, 112: 0x3331, 113: 0x4734, 114: 0x3832, 60: 1234}
    _feed_bank(plant, bank, received_at=_T0)
    _feed_bank(plant, bank, received_at=_T0 + timedelta(seconds=30))
    # Measured from a later 'now', the duration is since the FIRST identical commit.
    assert plant.content_unchanged_seconds(0x32, "IR", 60, 60, now=_T0 + timedelta(seconds=90)) == 90.0


def test_content_unchanged_seconds_resets_on_change(plant: Plant):
    """A register change resets unchanged_since to that commit's timestamp."""
    bank_a = {110: 0x4358, 111: 0x3232, 112: 0x3331, 113: 0x4734, 114: 0x3832, 60: 1234}
    bank_b = {**bank_a, 60: 5678}
    _feed_bank(plant, bank_a, received_at=_T0)
    _feed_bank(plant, bank_a, received_at=_T0 + timedelta(seconds=30))
    _feed_bank(plant, bank_b, received_at=_T0 + timedelta(seconds=60))  # content changed → reset
    assert plant.content_unchanged_seconds(0x32, "IR", 60, 60, now=_T0 + timedelta(seconds=75)) == 15.0


def test_content_unchanged_survives_run_longer_than_old_deque(plant: Plant):
    """An unchanged run of 20 commits still reports its true origin — the fix for Codex's objection.

    A bounded 10-entry hash deque would have evicted the start of the run, losing whether it
    began seconds or an hour ago. The unchanged_since timestamp is O(1) and survives any run.
    """
    bank = {110: 0x4358, 111: 0x3232, 112: 0x3331, 113: 0x4734, 114: 0x3832, 60: 1234}
    for i in range(20):  # well beyond the former 10-entry deque cap
        _feed_bank(plant, bank, received_at=_T0 + timedelta(seconds=30 * i))
    # Duration spans from the first commit, not just the last 10.
    assert plant.content_unchanged_seconds(0x32, "IR", 60, 60, now=_T0 + timedelta(seconds=600)) == 600.0


def test_content_unchanged_seconds_keyed_per_block(plant: Plant):
    """Distinct (device, type, base, count) blocks track unchanged_since independently."""
    bank = {110: 0x4358, 111: 0x3232, 112: 0x3331, 113: 0x4734, 114: 0x3832}
    _feed_bank(plant, bank, base=60, count=60, received_at=_T0)
    _feed_bank(plant, {0: 1}, base=0, count=60, received_at=_T0 + timedelta(seconds=10))
    assert plant.content_unchanged_seconds(0x32, "IR", 60, 60, now=_T0 + timedelta(seconds=10)) == 10.0
    assert plant.content_unchanged_seconds(0x32, "IR", 0, 60, now=_T0 + timedelta(seconds=10)) == 0.0


def test_discarded_bank_does_not_update_unchanged_since(plant: Plant):
    """A bank rejected by _commit_bank (Pattern B all-zero) leaves unchanged_since untouched."""
    seed = {60: 3221, 110: 0x4358, 111: 0x3232, 112: 0x3331, 113: 0x4734, 114: 0x3832}
    _feed_bank(plant, seed, received_at=_T0)
    _feed_bank(plant, dict.fromkeys(seed, 0), received_at=_T0 + timedelta(seconds=30))  # rejected
    # unchanged_since still anchored at the committed bank; the rejected bank changed nothing.
    assert plant.content_unchanged_seconds(0x32, "IR", 60, 60, now=_T0 + timedelta(seconds=30)) == 30.0


def test_crc_failed_frame_does_not_overwrite_cache(plant: Plant):
    """A CRC-failed response must not commit its payload over previously-good cache data."""
    good_bank = {60: 3221, 110: 0x4358, 111: 0x3232}
    _feed_bank(plant, good_bank, received_at=_T0)

    pdu = _make_ir_pdu({60: 0, 110: 0, 111: 0}, base_register=60, register_count=60)
    pdu.crc_failed = True
    setattr(pdu, "lenient_crc_commit", False)
    plant.update(pdu, received_at=_T0 + timedelta(seconds=10))

    # Cache must still reflect the good bank, not the zeroed CRC-failed payload.
    cache = plant.register_caches[0x32]
    assert cache[IR(60)] == 3221
    assert cache[IR(110)] == 0x4358


def test_crc_failed_cold_start_leaves_cache_empty(plant: Plant):
    """A CRC-failed response on an empty cache must not touch Plant state at all."""
    pdu = _make_ir_pdu({0: 9999}, base_register=0, register_count=60)
    pdu.crc_failed = True
    setattr(pdu, "lenient_crc_commit", False)
    plant.update(pdu)

    # No register data committed (Plant() pre-creates the 0x32 entry, but it stays empty).
    assert IR(0) not in plant.register_caches[0x32]


def test_crc_failed_frame_does_not_clobber_inverter_serial(plant: Plant):
    """A CRC-failed 0x11 response must not overwrite the known inverter serial.

    The CRC spans the device address and serial fields in the envelope, so those
    values are untrusted on exactly the frames that fail here.
    """
    plant.inverter_serial_number = "GOOD1234567"

    pdu = _make_ir_pdu({0: 0}, device_address=0x11, base_register=0, register_count=60)
    pdu.crc_failed = True
    setattr(pdu, "lenient_crc_commit", False)
    pdu.inverter_serial_number = "CORRUPT_SERX"
    plant.update(pdu)

    assert plant.inverter_serial_number == "GOOD1234567"
    assert IR(0) not in plant.register_caches.get(0x11, {})


def test_crc_failed_lenient_commit_allows_data(plant: Plant):
    """With lenient_crc_commit=True, a CRC-failed response is committed as normal."""
    pdu = _make_ir_pdu({60: 42, 61: 7}, base_register=60, register_count=60)
    pdu.crc_failed = True
    setattr(pdu, "lenient_crc_commit", True)
    plant.update(pdu)

    assert plant.register_caches[0x32][IR(60)] == 42
    assert plant.register_caches[0x32][IR(61)] == 7


# --- comms-quality counters (#284) ------------------------------------------


def test_comms_quality_counters_initialised_empty():
    plant = Plant()
    assert plant.crc_failure_count == {}
    assert plant.splice_reject_count == {}
    assert plant.splice_held_count == {}
    assert plant.retry_count == {}
    assert plant.cold_start_held_count == {}


def test_crc_failure_count_increments_per_device(plant: Plant):
    """Each skipped CRC-failed response bumps crc_failure_count for that device."""
    pdu = _make_ir_pdu({60: 0}, base_register=60, register_count=60)
    pdu.crc_failed = True
    setattr(pdu, "lenient_crc_commit", False)
    plant.update(pdu)
    plant.update(pdu)
    assert plant.crc_failure_count == {0x32: 2}


def test_splice_reject_count_increments_on_hard_reject(plant: Plant):
    """A hard-rejected battery bank bumps splice_reject_count, not splice_held_count."""
    _establish_baseline(plant, device_address=_BATT, received_at=_T0)
    corrupt = _coherent_battery_bank({76 + i: 0 for i in range(4)})  # 4 temp-zeros → >=2 physics
    _feed_bank(plant, corrupt, device_address=_BATT, received_at=_T0 + timedelta(seconds=30))
    assert plant.splice_reject_count == {_BATT: 1}
    assert plant.splice_held_count == {}


def test_splice_held_count_increments_on_escrow(plant: Plant):
    """A single-delta escrow hold bumps splice_held_count, not splice_reject_count."""
    _establish_baseline(plant, device_address=_BATT, received_at=_T0)
    wild = _coherent_battery_bank({60: 3700})  # one out-of-threshold delta (+400 > 300) → hold one poll
    _feed_bank(plant, wild, device_address=_BATT, received_at=_T0 + timedelta(seconds=30))
    assert plant.splice_held_count == {_BATT: 1}
    assert plant.splice_reject_count == {}


def test_splice_held_count_tracks_scalar_immutable_coherent_hold(plant: Plant):
    """The #281 coherent scalar-immutable hold counts as a held event."""
    poisoned = _coherent_battery_bank({98: 9999})
    _establish_baseline(plant, poisoned, device_address=_BATT, received_at=_T0)  # corroborate poison in (#289)
    _feed_bank(plant, _coherent_battery_bank(), device_address=_BATT, received_at=_T0 + timedelta(seconds=10))
    assert plant.splice_held_count == {_BATT: 1}
    assert plant.splice_reject_count == {}


def test_content_unchanged_seconds_normalises_naive_now(plant: Plant):
    """A timezone-naive now is treated as UTC rather than raising TypeError (mirrors block_age)."""
    bank = {110: 0x4358, 111: 0x3232, 112: 0x3331, 113: 0x4734, 114: 0x3832}
    _feed_bank(plant, bank, received_at=_T0)
    age = plant.content_unchanged_seconds(0x32, "IR", 60, 60, now=datetime(2026, 6, 9, 12, 0, 7))
    assert age == 7.0


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


# ---------------------------------------------------------------------------
# Unified inverter-serial accessor: Plant.inverter_serial (#227)
# ---------------------------------------------------------------------------


def _serial_to_hr(serial: str, base: int = 13) -> dict[Register, int]:
    """Encode a serial into HR(base..) registers (two ASCII bytes each), mirroring HR13-17."""
    b = serial.encode("latin1")
    return {HR(base + i): int.from_bytes(b[2 * i : 2 * i + 2], "big") for i in range(len(b) // 2)}


def test_inverter_serial_reads_capability_inverter_address_cache():
    """Plant.inverter_serial decodes HR13-17 from the capability-selected inverter cache (0x31)."""
    plant = Plant(capabilities=PlantCapabilities(device_type=Model.AC, inverter_address=0x31))
    plant.register_caches[0x31] = RegisterCache(_serial_to_hr("SA2114G047"))
    assert plant.inverter_serial == "SA2114G047"


def test_inverter_serial_falls_back_to_0x11_in_detect_window():
    """A 0x31 model with an empty 0x31 cache falls back to the 0x11 cache (#227).

    In the detect→first-refresh window, detect()'s HR(0,60) identity read has landed HR13-17 in
    the 0x11 cache even though 0x31 is not yet populated.
    """
    plant = Plant(capabilities=PlantCapabilities(device_type=Model.AC, inverter_address=0x31))
    # 0x31 absent in this window; 0x11 populated by detect()
    plant.register_caches[0x11] = RegisterCache(_serial_to_hr("SA2114G047"))
    assert plant.inverter_serial == "SA2114G047"


def test_inverter_serial_never_reads_0x32_battery_cache():
    """A bare plant must not surface the 0x32 battery serial as the inverter's (#227)."""
    plant = Plant()  # no capabilities; model_post_init seeds an (empty) 0x32 cache
    plant.register_caches[0x32] = RegisterCache(_serial_to_hr("ZZ9999Z999"))
    assert plant.inverter_serial == "", "0x32 is the battery pack, never the inverter"


def test_inverter_serial_falls_back_to_envelope_field():
    """The envelope serial is the final fallback when no register cache is populated (#227).

    It is earliest-available at detect() and the only home on persisted/bare state.
    """
    plant = Plant()
    plant.inverter_serial_number = "CH2414G047"
    assert plant.inverter_serial == "CH2414G047"


def test_inverter_serial_prefers_registers_when_populated():
    """A populated inverter register cache is authoritative over the envelope field (#227)."""
    plant = Plant(capabilities=PlantCapabilities(device_type=Model.HYBRID, inverter_address=0x11))
    plant.register_caches[0x11] = RegisterCache(_serial_to_hr("RG1234G567"))
    plant.inverter_serial_number = "CH2414G047"
    assert plant.inverter_serial == "RG1234G567"


def test_inverter_serial_skips_partial_serial_block():
    """A cache holding only part of HR13-17 is skipped (fail closed), not decoded partially (#227)."""
    plant = Plant(capabilities=PlantCapabilities(device_type=Model.HYBRID, inverter_address=0x11))
    plant.register_caches[0x11] = RegisterCache({HR(13): 0x4348, HR(14): 0x3234})  # only 2 of 5
    plant.inverter_serial_number = "CH2414G047"
    assert plant.inverter_serial == "CH2414G047", "a partial serial block must fall through, not decode"


def test_inverter_serial_skips_all_zero_serial_registers():
    """HR13-17 present but all-zero decodes to empty → fall through to the envelope, not '' (#227)."""
    plant = Plant(capabilities=PlantCapabilities(device_type=Model.HYBRID, inverter_address=0x11))
    plant.register_caches[0x11] = RegisterCache({HR(n): 0 for n in range(13, 18)})
    plant.inverter_serial_number = "CH2414G047"
    assert plant.inverter_serial == "CH2414G047"


def test_inverter_serial_skips_malformed_complete_block():
    """A complete block decoding to a malformed (non-10-char) serial falls through (#227, Codex).

    An interior zero register (HR15=0x0000 → "SA12G047" after the null strip) — or spaces /
    garbage in a restored or tampered cache — passes the not-empty check but is not a valid
    serial, so it must not outrank a known-good envelope serial. Gated by is_valid_serial().
    """
    plant = Plant(capabilities=PlantCapabilities(device_type=Model.HYBRID, inverter_address=0x11))
    # S A 1 2 \x00 \x00 G 0 4 7 → "SA12G047" (8 chars) after the null strip
    plant.register_caches[0x11] = RegisterCache(
        {HR(13): 0x5341, HR(14): 0x3132, HR(15): 0x0000, HR(16): 0x4730, HR(17): 0x3437}
    )
    plant.inverter_serial_number = "CH2414G047"
    assert plant.inverter_serial == "CH2414G047"


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


def test_register_age_finds_containing_window(plant: Plant):
    """register_age() resolves the freshest stamped window containing the register (#247).

    Consumers shouldn't need to know block boundaries or stamped counts — that's the
    private-reach the hass integration had to do before this existed.
    """
    from givenergy_modbus.model.register import IR

    t = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)
    plant.update(_make_ir_pdu({5: 2367, 42: 3685}, base_register=0), received_at=t)
    now = datetime(2026, 6, 11, 12, 0, 30, tzinfo=UTC)
    # IR(42) sits inside the stamped IR(0,60) window.
    assert plant.register_age(0x32, IR(42), now=now) == 30.0
    # Outside any stamped window → None; wrong device → None.
    assert plant.register_age(0x32, IR(180), now=now) is None
    assert plant.register_age(0x99, IR(42), now=now) is None


def test_register_age_freshest_of_overlapping_windows(plant: Plant):
    """With overlapping stamped windows, the freshest containing one wins (#247)."""
    from givenergy_modbus.model.register import IR

    t0 = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 6, 11, 12, 0, 20, tzinfo=UTC)
    plant.update(_make_ir_pdu({5: 2367}, base_register=0), received_at=t0)  # IR(0,60) @ t0
    plant.update(_make_ir_pdu({5: 2368}, base_register=0, register_count=10), received_at=t1)  # IR(0,10) @ t1
    now = datetime(2026, 6, 11, 12, 0, 30, tzinfo=UTC)
    # IR(5) is covered by both; the fresher IR(0,10) stamp wins.
    assert plant.register_age(0x32, IR(5), now=now) == 10.0
    # IR(42) is only covered by the older full-width window.
    assert plant.register_age(0x32, IR(42), now=now) == 30.0


def test_register_age_pairs_with_registers_of(plant: Plant):
    """The advertised composition: registers_of() → register_age() for attribute freshness (#247)."""
    from givenergy_modbus.model.inverter import SinglePhaseInverterRegisterGetter

    t = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)
    plant.update(_make_ir_pdu({42: 3685}, base_register=0), received_at=t)
    regs = SinglePhaseInverterRegisterGetter.registers_of("p_load_demand")
    assert regs, "p_load_demand must be register-backed"
    now = datetime(2026, 6, 11, 12, 0, 15, tzinfo=UTC)
    ages = [plant.register_age(0x32, r, now=now) for r in regs]
    assert ages == [15.0]


def test_register_age_normalises_naive_now(plant: Plant):
    """A timezone-naive now is treated as UTC, matching block_age()'s posture (#208/#247)."""
    from givenergy_modbus.model.register import IR

    t = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)
    plant.update(_make_ir_pdu({5: 2367}, base_register=0), received_at=t)
    assert plant.register_age(0x32, IR(5), now=datetime(2026, 6, 11, 12, 0, 7)) == 7.0


def test_register_age_keeps_freshest_when_older_window_seen_later(plant: Plant):
    """A staler containing window encountered after a fresher one must not displace it (#247)."""
    from givenergy_modbus.model.register import IR

    t_new = datetime(2026, 6, 11, 12, 0, 20, tzinfo=UTC)
    t_old = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)
    # Stamp the fresher narrow window FIRST so iteration meets the older one second.
    plant.update(_make_ir_pdu({5: 2368}, base_register=0, register_count=10), received_at=t_new)
    plant.update(_make_ir_pdu({5: 2367}, base_register=0), received_at=t_old)  # IR(0,60), older
    now = datetime(2026, 6, 11, 12, 0, 30, tzinfo=UTC)
    assert plant.register_age(0x32, IR(5), now=now) == 10.0


# ---------------------------------------------------------------------------
# Battery sub-bus splice guard (#256) — Plant-level integration tests
#
# Tests that the splice guard correctly rejects or escrows LV battery banks
# carrying physics-impossible register deltas, even when CRC, bounds, and
# serial-coherence checks pass. All tests target device 0x33: on a bare
# Plant, 0x32 → SinglePhaseInverterRegisterGetter and 0x33–0x37 →
# BatteryRegisterGetter, so only 0x33+ is guarded.
# ---------------------------------------------------------------------------


def _coherent_battery_bank(overrides: dict[int, int] | None = None) -> dict[int, int]:
    """A valid, coherent LV battery bank keyed by absolute IR number (60..119)."""
    bank: dict[int, int] = {
        # 16 cells at 3.300 V (bank-relative 0–15 → IR60–75)
        **{60 + i: 3300 for i in range(16)},
        # cell-mass temps at 25.0 °C (bank-relative 16–19 → IR76–79)
        **{76 + i: 250 for i in range(4)},
        80: 52800,  # v_cells_sum IR80
        81: 260,  # mosfet_temp IR81
        82: 0,
        83: 52800,  # v_out pair IR82–83
        84: 0,
        85: 16000,  # cap_calibrated IR84–85
        86: 0,
        87: 16000,  # cap_design IR86–87
        88: 0,
        89: 16000,  # cap_remaining IR88–89
        97: 16,  # num_cells IR97 (IMMUTABLE)
        98: 3005,  # bms_fw IR98 (IMMUTABLE)
        100: 55,  # soc IR100
        101: 0,
        102: 16000,  # cap_design2 IR101–102
        103: 250,  # t_max IR103
        104: 240,  # t_min IR104
        105: 1000,  # e_total hi IR105
        106: 1200,  # e_total lo IR106
        # serial IR110–114 (IMMUTABLE) — "BG12345678", same as the Pattern-B battery test (L1797)
        110: 0x4247,
        111: 0x3132,
        112: 0x3334,
        113: 0x3536,
        114: 0x3738,
        115: 8,  # usb_device_inserted IR115 (mutable, exempt from IMMUTABLE)
    }
    if overrides:
        bank.update(overrides)
    return bank


_BATT = 0x33  # battery pack #1 on bare Plant; 0x32 → inverter getter on bare Plant


def _establish_baseline(
    plant: "Plant",
    bank: dict[int, int] | None = None,
    *,
    device_address: int = _BATT,
    received_at: datetime | None = _T0,
) -> None:
    """Commit a corroborated last-good battery baseline (two agreeing cold-start reads, #289).

    Under #289 the first bank seen against an empty cache is *held* pending a corroborating read, so
    a single feed no longer seeds the cache. Splice scenarios that need an established baseline feed
    the same bank twice: the second read (at ``received_at``) corroborates and commits, leaving the
    cache, ingestion stamp and observation clock exactly where a pre-#289 single feed at
    ``received_at`` would — the held first read lands one nominal poll (30 s) earlier. A persistently
    identical value corroborates, so this also primes a poisoned baseline (pass the poison as ``bank``).
    """
    bank = bank if bank is not None else _coherent_battery_bank()
    first_at = received_at - timedelta(seconds=30) if received_at is not None else None
    _feed_bank(plant, bank, device_address=device_address, received_at=first_at)
    _feed_bank(plant, bank, device_address=device_address, received_at=received_at)


def test_splice_scalar_immut_with_physics_held_not_rejected(plant: Plant, caplog):
    """A cap-pair physics step + scalar-immutable mutation is HELD as last-good, not rejected (#286).

    The whole bank is kept last-good — protecting the co-corrupted physics — and logged at INFO
    (a recoverable hold, never a WARNING). It heals only after a long sustained insistence.
    """
    import logging

    _establish_baseline(plant, device_address=_BATT, received_at=_T0)
    corrupted = _coherent_battery_bank({89: 36000, 98: 3006})  # cap-pair physics + IR98 immutable
    with caplog.at_level(logging.INFO, logger="givenergy_modbus.model.plant"):
        _feed_bank(plant, corrupted, device_address=_BATT, received_at=_T0 + timedelta(seconds=30))
    assert plant.register_caches[_BATT][IR(89)] == 16000  # co-corrupted physics protected
    assert plant.register_caches[_BATT][IR(98)] == 3005  # last-good held
    assert plant.splice_held_count == {_BATT: 1}
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING and "0x33" in r.message]
    assert [r for r in caplog.records if "holding last-good" in r.message and "0x33" in r.message]


def test_splice_poisoned_scalar_immut_heals_after_long_insistence(plant: Plant, caplog):
    """A poisoned cold-start IR98 baseline heals only after a long sustained insistence (#286).

    It heals once the true value persists past splice_heal_seconds (default 900 s) with
    >= SCALAR_IMMUT_HEAL_POLLS frames.
    """
    import logging

    poisoned = _coherent_battery_bank({98: 9999})  # corrupt first frame adopted at cold start
    _establish_baseline(plant, poisoned, device_address=_BATT, received_at=_T0)
    healthy = _coherent_battery_bank()  # true IR98 == 3005, coherent
    with caplog.at_level(logging.INFO, logger="givenergy_modbus.model.plant"):
        for n in range(1, 10):  # polls 1-9 @ 100 s: streak started at poll 1, elapsed <= 800 s < 900
            _feed_bank(plant, healthy, device_address=_BATT, received_at=_T0 + timedelta(seconds=100 * n))
        assert plant.register_caches[_BATT][IR(98)] == 9999  # still held — not yet healed
        # poll 10 @ 1000 s: count 10 >= 10 AND elapsed 900 >= 900 → heal.
        _feed_bank(plant, healthy, device_address=_BATT, received_at=_T0 + timedelta(seconds=1000))
    assert plant.register_caches[_BATT][IR(98)] == 3005  # healed
    adopts = [r for r in caplog.records if "adopting as new baseline" in r.message and "0x33" in r.message]
    assert len(adopts) == 1 and adopts[0].levelno == logging.INFO
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING and "0x33" in r.message]


def test_splice_poisoned_baseline_with_drift_heals_whole_bank(plant: Plant, caplog):
    """A poisoned baseline with co-drifting physics heals after the long insistence — whole bank adopts (#286)."""
    import logging

    poisoned = _coherent_battery_bank({98: 9999})
    _establish_baseline(plant, poisoned, device_address=_BATT, received_at=_T0)
    healthy = _coherent_battery_bank({98: 3005, 60: 3600})  # true fw + a sustained real cell delta
    with caplog.at_level(logging.INFO, logger="givenergy_modbus.model.plant"):
        for n in range(1, 11):  # 10 polls @ 100 s → poll 10: count 10, elapsed 900 → heal
            _feed_bank(plant, healthy, device_address=_BATT, received_at=_T0 + timedelta(seconds=100 * n))
    assert plant.register_caches[_BATT][IR(98)] == 3005  # healed
    assert plant.register_caches[_BATT][IR(60)] == 3600  # whole bank adopted
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING and "0x33" in r.message]


def test_splice_transient_corruption_held_not_adopted_soc_protected(plant: Plant, caplog):
    """The field drift episode (#286): transient drift corruption is held, never adopted; SOC protected.

    A sustained-but-transient drift splice (fw + SOC both corrupt) that reverts within minutes is
    held — never adopted — and the co-corrupted SOC stays at last-good.
    """
    import logging

    _establish_baseline(plant, device_address=_BATT, received_at=_T0)  # baseline: fw 3005, soc 55
    corrupt = _coherent_battery_bank({98: 2241, 100: 13})  # IR98 immutable + IR100 soc 55->13 (>10 thresh)
    with caplog.at_level(logging.INFO, logger="givenergy_modbus.model.plant"):
        for n in range(1, 7):  # 6 polls @ 30 s = 180 s, far inside the 900 s heal window
            _feed_bank(plant, corrupt, device_address=_BATT, received_at=_T0 + timedelta(seconds=30 * n))
        assert plant.register_caches[_BATT][IR(98)] == 3005  # fw never adopted
        assert plant.register_caches[_BATT][IR(100)] == 55  # SOC protected — no dip
        # corruption reverts: a clean good frame is accepted and clears the hold.
        _feed_bank(plant, _coherent_battery_bank(), device_address=_BATT, received_at=_T0 + timedelta(seconds=210))
    assert plant.register_caches[_BATT][IR(98)] == 3005
    assert plant.register_caches[_BATT][IR(100)] == 55
    assert not [r for r in caplog.records if "adopting as new baseline" in r.message]  # never healed
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING and "0x33" in r.message]
    assert plant.splice_held_count[_BATT] == 6  # held each corrupt poll — diagnostic climbs


def test_splice_heal_seconds_knob_tunes_hold_duration(plant: Plant):
    """splice_heal_seconds tunes how long a scalar-immutable disagreement is held before healing (#286)."""
    plant.splice_heal_seconds = 60.0  # much shorter than the 900 s default
    poisoned = _coherent_battery_bank({98: 9999})
    _establish_baseline(plant, poisoned, device_address=_BATT, received_at=_T0)
    healthy = _coherent_battery_bank()
    for n in range(1, 11):  # 10 polls @ 10 s → poll 10: count 10, elapsed 90 >= 60 → heal
        _feed_bank(plant, healthy, device_address=_BATT, received_at=_T0 + timedelta(seconds=10 * n))
    assert plant.register_caches[_BATT][IR(98)] == 3005  # healed within 90 s thanks to the lower knob


def test_splice_block_age_grows_during_scalar_immut_hold(plant: Plant):
    """A held scalar-immutable bank records no ingestion timestamp, so block_age keeps growing (#286).

    A consumer can therefore see the data is cached/stale (#65).
    """
    _establish_baseline(plant, device_address=_BATT, received_at=_T0)  # commits at t0
    corrupt = _coherent_battery_bank({98: 2241, 100: 13})  # held (not re-stamped)
    for n in range(1, 4):
        _feed_bank(plant, corrupt, device_address=_BATT, received_at=_T0 + timedelta(seconds=30 * n))
    # block_age reflects the last *committed* bank (t0), not the held ones.
    assert plant.block_age(_BATT, "IR", 60, 60, now=_T0 + timedelta(seconds=120)) == 120.0


def test_splice_oscillating_scalar_immut_never_adopts(plant: Plant, caplog):
    """Oscillating IR98 garbage never self-adopts — a changing signature resets the streak (#281)."""
    import logging

    _establish_baseline(plant, device_address=_BATT, received_at=_T0)  # clean seed: IR98 3005
    with caplog.at_level(logging.INFO, logger="givenergy_modbus.model.plant"):
        for n in range(1, 13):  # 12 polls @ 15 s = 180 s, still < 300 s (no stale bypass)
            garbage = _coherent_battery_bank({98: 9000 + (n % 2) * 500, 60: 3600})  # IR98 flips each poll
            _feed_bank(plant, garbage, device_address=_BATT, received_at=_T0 + timedelta(seconds=15 * n))
    assert plant.register_caches[_BATT][IR(98)] == 3005  # last-good held; garbage never adopted
    assert not [r for r in caplog.records if "adopting as new baseline" in r.message]  # never healed


def test_splice_serial_block_change_always_rejected(plant: Plant, caplog):
    """A serial-block change is hard-rejected forever — wrong-pack / re-address protection (#281)."""
    import logging

    _establish_baseline(plant, device_address=_BATT, received_at=_T0)
    swapped = _coherent_battery_bank({110: 0x4248})  # serial first word BG.. → a different pack
    with caplog.at_level(logging.INFO, logger="givenergy_modbus.model.plant"):
        for n in range(1, 25):  # 24 polls @ 15 s = 360 s; observation clock refreshes so bypass never fires
            _feed_bank(plant, swapped, device_address=_BATT, received_at=_T0 + timedelta(seconds=15 * n))
    assert plant.register_caches[_BATT][IR(110)] == 0x4247  # last-good serial held forever
    serial_rejects = [r for r in caplog.records if "serial-block change" in r.message and "0x33" in r.message]
    assert len(serial_rejects) == 24
    assert not [r for r in caplog.records if "adopting as new baseline" in r.message]  # never healed


def test_splice_heal_requires_uninterrupted_signature(plant: Plant, caplog):
    """Healing requires an *uninterrupted* signature — an interrupting poll resets the streak (#286).

    splice_heal_seconds is set low so the poll-count floor (10) is the operative gate: 9 drift polls,
    an interrupt, then 9 more — each run stays at 9 < 10, so the poison baseline is never adopted.
    """
    import logging

    plant.splice_heal_seconds = 1.0  # make the 10-poll floor the operative gate
    poisoned = _coherent_battery_bank({98: 9999})
    _establish_baseline(plant, poisoned, device_address=_BATT, received_at=_T0)
    drift = _coherent_battery_bank({98: 3005, 60: 3600})  # scalar trip (IR98) + 1 physics trip (IR60)
    interrupt = _coherent_battery_bank({98: 9999, 60: 3600})  # IR98 == baseline → no scalar trip → resets streak
    with caplog.at_level(logging.INFO, logger="givenergy_modbus.model.plant"):
        for n in range(1, 10):  # 9 drift polls: count reaches 9 (one short of 10)
            _feed_bank(plant, drift, device_address=_BATT, received_at=_T0 + timedelta(seconds=10 * n))
        _feed_bank(plant, interrupt, device_address=_BATT, received_at=_T0 + timedelta(seconds=100))  # reset
        for n in range(11, 20):  # 9 more drift polls: streak restarts, never reaches 10
            _feed_bank(plant, drift, device_address=_BATT, received_at=_T0 + timedelta(seconds=10 * n))
    assert plant.register_caches[_BATT][IR(98)] == 9999  # never adopted — interruption reset the streak
    assert not [r for r in caplog.records if "adopting as new baseline" in r.message]


def test_splice_cell_and_temp_cohort_rejected(plant: Plant, caplog):
    """Two independent physics trips (a cell + a temperature) are rejected outright (≥2-physics rule)."""
    import logging

    _establish_baseline(plant, device_address=_BATT, received_at=_T0)
    corrupted = _coherent_battery_bank(
        {
            74: 3700,  # IR74: cell delta 400 mV > 100 threshold
            103: 0,  # IR103: t_max delta 250 > 50 threshold
        }
    )
    with caplog.at_level(logging.WARNING, logger="givenergy_modbus.model.plant"):
        _feed_bank(plant, corrupted, device_address=_BATT, received_at=_T0 + timedelta(seconds=30))
    assert plant.register_caches[_BATT][IR(74)] == 3300
    assert plant.register_caches[_BATT][IR(103)] == 250
    warns = [r for r in caplog.records if "Rejected battery bank" in r.message and "0x33" in r.message]
    assert len(warns) == 1
    assert "physics-impossible" in warns[0].message


def test_splice_temp_cohort_zeros_rejected(plant: Plant, caplog):
    """All four cell-mass temps dropping to zero (4 physics trips) is rejected outright."""
    import logging

    _establish_baseline(plant, device_address=_BATT, received_at=_T0)
    corrupted = _coherent_battery_bank({76 + i: 0 for i in range(4)})  # IR76–79: 250 → 0
    with caplog.at_level(logging.WARNING, logger="givenergy_modbus.model.plant"):
        _feed_bank(plant, corrupted, device_address=_BATT, received_at=_T0 + timedelta(seconds=30))
    assert plant.register_caches[_BATT][IR(76)] == 250  # last-good retained
    warns = [r for r in caplog.records if "Rejected battery bank" in r.message and "0x33" in r.message]
    assert len(warns) == 1


def test_splice_clean_bank_commits_no_false_trip(plant: Plant, caplog):
    """In-threshold jitter on a clean bank commits normally and emits no splice WARNING."""
    import logging

    _establish_baseline(plant, device_address=_BATT, received_at=_T0)
    # +149 mV cell (≤ 150 threshold), +49 deci temp (≤ 50 threshold) — both within limits.
    jitter = _coherent_battery_bank({60: 3449, 76: 299})
    with caplog.at_level(logging.WARNING, logger="givenergy_modbus.model.plant"):
        _feed_bank(plant, jitter, device_address=_BATT, received_at=_T0 + timedelta(seconds=30))
    warns = [r for r in caplog.records if "splice" in r.message.lower() or "Held battery bank" in r.message]
    assert not warns
    assert plant.register_caches[_BATT][IR(60)] == 3449
    assert plant.register_caches[_BATT][IR(76)] == 299


def test_splice_single_step_escrow_then_confirm(plant: Plant, caplog):
    """A lone impossible delta is escrowed; re-reading the same value confirms and commits."""
    import logging

    _establish_baseline(plant, device_address=_BATT, received_at=_T0)
    t1 = _T0 + timedelta(seconds=30)
    t2 = _T0 + timedelta(seconds=60)
    wild = _coherent_battery_bank({60: 3700})  # IR60: +400 mV > 300 threshold — one trip

    # The singleton self-healing path is INFO, never WARNING (#256/hass#186).
    with caplog.at_level(logging.INFO, logger="givenergy_modbus.model.plant"):
        _feed_bank(plant, wild, device_address=_BATT, received_at=t1)
    holds = [r for r in caplog.records if "held one poll pending confirmation" in r.message and "0x33" in r.message]
    assert len(holds) == 1, "single out-of-threshold delta must emit one 'held' log"
    assert holds[0].levelno == logging.INFO, "self-healing hold must be INFO, not WARNING"
    assert plant.register_caches[_BATT][IR(60)] == 3300, "escrowed bank must not commit"

    caplog.clear()
    # Re-read the same value: |3700 − 3700| = 0 ≤ 300 → value-consistent → confirm.
    with caplog.at_level(logging.INFO, logger="givenergy_modbus.model.plant"):
        _feed_bank(plant, wild, device_address=_BATT, received_at=t2)
    confirms = [r for r in caplog.records if "confirmed on re-read" in r.message and "0x33" in r.message]
    assert len(confirms) == 1, "confirmed step must emit one INFO log"
    assert plant.register_caches[_BATT][IR(60)] == 3700, "confirmed step must commit"


def test_splice_single_step_escrow_then_snapback(plant: Plant, caplog):
    """A transient splice that snaps back clears the escrow, logs the reversion (INFO), commits clean."""
    import logging

    _establish_baseline(plant, device_address=_BATT, received_at=_T0)
    t1 = _T0 + timedelta(seconds=30)
    t2 = _T0 + timedelta(seconds=60)
    wild = _coherent_battery_bank({60: 3700})
    with caplog.at_level(logging.INFO, logger="givenergy_modbus.model.plant"):
        _feed_bank(plant, wild, device_address=_BATT, received_at=t1)
    assert plant.register_caches[_BATT][IR(60)] == 3300

    caplog.clear()
    clean = _coherent_battery_bank()  # IR60 back to seed value
    with caplog.at_level(logging.INFO, logger="givenergy_modbus.model.plant"):
        _feed_bank(plant, clean, device_address=_BATT, received_at=t2)
    plant_warns = [
        r for r in caplog.records if r.levelno >= logging.WARNING and r.name == "givenergy_modbus.model.plant"
    ]
    assert not plant_warns, "snapback must emit no WARNING from the splice guard"
    reverts = [r for r in caplog.records if "reverted on re-read" in r.message and "0x33" in r.message]
    assert len(reverts) == 1, "snapback must emit one INFO reversion log"
    assert plant.register_caches[_BATT][IR(60)] == 3300


def test_splice_two_wild_values_in_a_row_held(plant: Plant, caplog):
    """Two consecutive wild values for the same register are both held (value-consistency guard)."""
    import logging

    _establish_baseline(plant, device_address=_BATT, received_at=_T0)
    t1 = _T0 + timedelta(seconds=30)
    t2 = _T0 + timedelta(seconds=60)
    # v1: IR60 → 3700 (|3700 − 3300| = 400 > 300) → escrow (IR60, 3700).
    # v2: IR60 → 4200 (|4200 − 3700| = 500 > 300) → does NOT confirm → re-escrow (IR60, 4200).
    v1 = _coherent_battery_bank({60: 3700})
    v2 = _coherent_battery_bank({60: 4200})
    with caplog.at_level(logging.INFO, logger="givenergy_modbus.model.plant"):
        _feed_bank(plant, v1, device_address=_BATT, received_at=t1)
        _feed_bank(plant, v2, device_address=_BATT, received_at=t2)
    holds = [r for r in caplog.records if "held one poll pending confirmation" in r.message and "0x33" in r.message]
    assert len(holds) == 2, "each wild read must emit its own 'held' INFO log"
    assert plant.register_caches[_BATT][IR(60)] == 3300, "neither wild value must have committed"


def test_near_full_soc_knee_surge_commits(plant: Plant, caplog):
    """A near-100%-SOC LiFePO4 knee surge commits in one poll, not hard-rejected (#299).

    Field signature (device 0x33 topping out — ~18.5 min of rejections): two cells (IR65/IR68)
    stepped ~198 mV and the pack terminal voltage IR(82–83) ~2.3 V in a single poll as the pack
    entered the LiFePO4 charge knee. Pre-#299 thresholds (cell_mV 150, v_out 2000) counted three
    physics trips (>=2) and hard-rejected the whole bank for the entire surge. Widened to 300 / 4000
    the surge sits within threshold: zero trips → commits directly (no escrow, no rejection).
    """
    import logging

    _establish_baseline(plant, device_address=_BATT, received_at=_T0)
    # IR65/IR68 +198 mV (150 < 198 < 300); v_out IR(82–83) +2263 mV (2000 < 2263 < 4000);
    # v_cells_sum a coherent sub-threshold step. Pre-#299 this was 3 trips → reject.
    knee = _coherent_battery_bank({65: 3498, 68: 3498, 80: 53200, 82: 0, 83: 55063})
    with caplog.at_level(logging.INFO, logger="givenergy_modbus.model.plant"):
        _feed_bank(plant, knee, device_address=_BATT, received_at=_T0 + timedelta(seconds=30))
    assert plant.register_caches[_BATT][IR(65)] == 3498, "knee surge must commit (cell)"
    assert plant.register_caches[_BATT][IR(83)] == 55063, "knee surge must commit (v_out)"
    assert plant.splice_reject_count == {}, "knee surge must not be rejected"
    assert plant.splice_held_count == {}, "zero trips → committed directly, not escrowed"


def test_splice_sustained_step_rejected_when_heal_disabled(plant: Plant):
    """With the heal off (default), a sustained >=2-physics step still hard-rejects forever (#299).

    Two cells surge >300 mV above the frozen baseline (>=2 cell_mV trips each poll), evolving
    smoothly. Without ``splice_reject_heal_seconds`` set the >=2-physics path stays terminal — the
    bank is held at last-good every poll. This pins the opt-in default: zero behaviour change.
    """
    assert plant.splice_reject_heal_seconds is None  # default: heal disabled
    _establish_baseline(plant, device_address=_BATT, received_at=_T0)  # cells @ 3300
    for n in range(1, 11):
        v = 3700 + 20 * (n - 1)  # 3700, 3720, ... 3880 — smooth, in range, >300 above baseline
        surge = _coherent_battery_bank({60: v, 65: v})
        _feed_bank(plant, surge, device_address=_BATT, received_at=_T0 + timedelta(seconds=35 * n))
    assert plant.register_caches[_BATT][IR(60)] == 3300  # baseline held — never healed
    assert plant.splice_reject_count[_BATT] == 10  # hard-rejected each poll


def test_splice_sustained_step_heals_when_enabled(plant: Plant, caplog):
    """An opted-in sustained, smooth, in-range voltage surge heals after N polls / T seconds (#299).

    The near-full-SOC charge knee: two cells climb >300 mV above the frozen baseline (>=2 cell_mV
    trips vs baseline → reject bucket each poll) but only ~20 mV/poll vs the previous incoming
    (smooth). With the heal enabled, the streak advances each smooth poll and adopts the latest frame
    once it has run >= SPLICE_REJECT_HEAL_POLLS (10) AND >= splice_reject_heal_seconds (300). After
    the heal the new baseline makes the settling drift commit clean.
    """
    import logging

    plant.splice_reject_heal_seconds = 300.0  # opt in
    _establish_baseline(plant, device_address=_BATT, received_at=_T0)
    with caplog.at_level(logging.INFO, logger="givenergy_modbus.model.plant"):
        for n in range(1, 11):  # polls 1..10 @ 35 s → poll 10 at 350 s; count 10, elapsed 315 >= 300
            v = 3700 + 20 * (n - 1)
            surge = _coherent_battery_bank({60: v, 65: v})
            _feed_bank(plant, surge, device_address=_BATT, received_at=_T0 + timedelta(seconds=35 * n))
            if n < 10:
                assert plant.register_caches[_BATT][IR(60)] == 3300, f"held at poll {n}, not yet healed"
    assert plant.register_caches[_BATT][IR(60)] == 3880  # healed to the latest surge frame
    assert plant.register_caches[_BATT][IR(65)] == 3880
    assert plant.splice_reject_count == {}, "a held-then-healed surge is never a reject"
    assert plant.splice_held_count[_BATT] == 9  # polls 1-9 held; poll 10 healed (no bump)
    adopts = [r for r in caplog.records if "adopting as new baseline" in r.message and "0x33" in r.message]
    assert len(adopts) == 1 and adopts[0].levelno == logging.INFO
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING and "0x33" in r.message]
    # Post-heal settling: cells drift back ~10 mV/poll vs the new 3880 baseline → clean → commits.
    settle = _coherent_battery_bank({60: 3870, 65: 3870})
    _feed_bank(plant, settle, device_address=_BATT, received_at=_T0 + timedelta(seconds=35 * 11))
    assert plant.register_caches[_BATT][IR(60)] == 3870, "settling commits clean against the healed baseline"


def test_splice_temp_step_never_heal_eligible_even_when_enabled(plant: Plant):
    """A temp-zero ≥2 reject (incl. the IR103/104 pair) stays terminal even with the heal on (#299).

    The class restriction is the safety spine: heal-eligibility is limited to voltage/capacity-class
    surges. The corpus's IR(103) t_max / IR(104) t_min temp-zero corruption is 2 physics trips that
    ``is_corruption_cohort`` (IR76-79 only) does NOT catch — but it's ``cell_temp_deci`` class, so it
    is never heal-eligible and stays hard-rejected no matter how long it persists.
    """
    plant.splice_reject_heal_seconds = 300.0  # heal enabled
    _establish_baseline(plant, device_address=_BATT, received_at=_T0)  # t_max 250, t_min 240
    for n in range(1, 13):  # 12 polls @ 35 s = 420 s — past both gates, yet must never heal
        corrupt = _coherent_battery_bank({103: 0, 104: 11})  # the corpus IR103/104 temp-zero shape
        _feed_bank(plant, corrupt, device_address=_BATT, received_at=_T0 + timedelta(seconds=35 * n))
    assert plant.register_caches[_BATT][IR(103)] == 250  # held — never adopted
    assert plant.splice_reject_count[_BATT] == 12  # hard-rejected every poll (class restriction)


def test_splice_out_of_range_surge_never_healed(plant: Plant):
    """A smooth voltage-class walk at a physically impossible value never heals (range gate, #299)."""
    plant.splice_reject_heal_seconds = 300.0
    _establish_baseline(plant, device_address=_BATT, received_at=_T0)
    for n in range(1, 13):  # smooth + in cell_mV class, but >5.0 V (raw >5000) → out of absolute range
        v = 5200 + 10 * (n - 1)
        surge = _coherent_battery_bank({60: v, 65: v})
        _feed_bank(plant, surge, device_address=_BATT, received_at=_T0 + timedelta(seconds=35 * n))
    assert plant.register_caches[_BATT][IR(60)] == 3300  # never adopted — impossible value
    assert plant.splice_reject_count[_BATT] == 12


def test_splice_non_smooth_surge_never_heals(plant: Plant):
    """A jumpy (non-smooth) in-range ≥2 surge never heals — the streak restarts every poll (#299)."""
    plant.splice_reject_heal_seconds = 1.0  # make the 10-poll floor the operative gate
    _establish_baseline(plant, device_address=_BATT, received_at=_T0)
    for n in range(1, 15):  # alternate 3700/4200: |delta| 500 > 300 vs previous incoming → not smooth
        v = 3700 if n % 2 else 4200
        surge = _coherent_battery_bank({60: v, 65: v})
        _feed_bank(plant, surge, device_address=_BATT, received_at=_T0 + timedelta(seconds=35 * n))
    assert plant.register_caches[_BATT][IR(60)] == 3300  # streak never reaches 10 — held throughout


def test_splice_surge_reverting_to_baseline_resets_streak(plant: Plant):
    """A surge that reverts to baseline (corruption signature) clears the streak — no heal (#299)."""
    plant.splice_reject_heal_seconds = 1.0  # 10-poll floor operative
    _establish_baseline(plant, device_address=_BATT, received_at=_T0)
    for n in range(1, 6):  # 5 smooth surge polls — streak builds to 5
        v = 3700 + 20 * (n - 1)
        _feed_bank(
            plant,
            _coherent_battery_bank({60: v, 65: v}),
            device_address=_BATT,
            received_at=_T0 + timedelta(seconds=35 * n),
        )
    # reverts to the exact baseline → clean transition → streak popped
    _feed_bank(plant, _coherent_battery_bank(), device_address=_BATT, received_at=_T0 + timedelta(seconds=35 * 6))
    assert plant.register_caches[_BATT][IR(60)] == 3300
    # a fresh single surge poll: streak restarts at 1, far short of 10 → still held
    _feed_bank(
        plant,
        _coherent_battery_bank({60: 3700, 65: 3700}),
        device_address=_BATT,
        received_at=_T0 + timedelta(seconds=35 * 7),
    )
    assert plant.register_caches[_BATT][IR(60)] == 3300  # held — the revert reset the streak


def test_splice_surge_streak_popped_on_stale_bypass(plant: Plant):
    """A >STALE_BYPASS_SECONDS gap mid-surge: the stale-bypass governs and the streak is popped (#299)."""
    plant.splice_reject_heal_seconds = 300.0
    _establish_baseline(plant, device_address=_BATT, received_at=_T0)
    for n in range(1, 4):  # 3 surge polls — streak building, last observed at 105 s
        v = 3700 + 20 * (n - 1)
        _feed_bank(
            plant,
            _coherent_battery_bank({60: v, 65: v}),
            device_address=_BATT,
            received_at=_T0 + timedelta(seconds=35 * n),
        )
    # 400 s gap (> 300 s) → next frame hits the stale-bypass and adopts outright (non-cohort).
    after_gap = _coherent_battery_bank({60: 3760, 65: 3760})
    _feed_bank(plant, after_gap, device_address=_BATT, received_at=_T0 + timedelta(seconds=105 + 400))
    assert plant.register_caches[_BATT][IR(60)] == 3760  # stale-bypass adopted; streak did not gate it


def test_splice_phys_heal_eligible_resets_scalar_immut_streak(plant: Plant):
    """A heal-eligible >=2-physics frame clears the scalar-immutable streak, interrupting the count (#299).

    Without the fix, the scalar streak survived the >=2-physics pass and could satisfy its
    "uninterrupted" count/time gates despite the interruption — allowing a poison baseline to heal
    sooner than intended (or at all when the count was nearly at the threshold).
    """
    plant.splice_heal_seconds = 1.0  # make the 10-poll floor the operative gate for scalar heal
    plant.splice_reject_heal_seconds = 300.0  # enable the >=2-physics heal path
    poisoned = _coherent_battery_bank({98: 9999})  # IR98 bms_firmware_version poison in baseline
    _establish_baseline(plant, poisoned, device_address=_BATT, received_at=_T0)
    drift = _coherent_battery_bank({98: 3005, 60: 3600})  # scalar trip (IR98) + 1 physics (IR60)
    for n in range(1, 10):  # 9 drift polls: scalar-immut streak reaches count=9 (one short of 10)
        _feed_bank(plant, drift, device_address=_BATT, received_at=_T0 + timedelta(seconds=10 * n))
    assert plant.register_caches[_BATT][IR(98)] == 9999  # still holding the poison

    # >=2-physics heal-eligible frame: cell_mV surges on two cells vs the frozen baseline.
    # IR98 must match the baseline (9999) so there is no scalar_immut trip — pure >=2-physics.
    # This must clear _splice_immut_streak, resetting the scalar streak to zero.
    surge = _coherent_battery_bank({60: 3880, 65: 3880, 98: 9999})  # 580 mV surge > 300 mV threshold, in-range
    _feed_bank(plant, surge, device_address=_BATT, received_at=_T0 + timedelta(seconds=100))
    assert plant.register_caches[_BATT][IR(98)] == 9999  # still holding; streak interrupted, not adopted

    # 9 more scalar-immut drift polls: streak must restart from 1 (not resume from 9), so no heal.
    for n in range(11, 20):
        _feed_bank(plant, drift, device_address=_BATT, received_at=_T0 + timedelta(seconds=10 * n))
    assert plant.register_caches[_BATT][IR(98)] == 9999  # never adopted — streak was reset by the interrupt


def test_cold_start_first_frame_held_pending(plant: Plant, caplog):
    """The first bank against an empty cache is held pending a corroborating read, not adopted (#289).

    A transient sub-bus splice in the very first frame would otherwise poison the baseline. The frame
    is held (the cache stays empty, the device serves "unknown") at INFO — normal startup, not
    corruption, so no WARNING.
    """
    import logging

    with caplog.at_level(logging.INFO, logger="givenergy_modbus.model.plant"):
        _feed_bank(plant, _coherent_battery_bank(), device_address=_BATT, received_at=_T0)
    assert IR(60) not in plant.register_caches[_BATT], "first cold-start frame must be held, not committed"
    assert plant.cold_start_held_count == {_BATT: 1}
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING and "0x33" in r.message]
    assert [r for r in caplog.records if "first cold-start frame" in r.message and "0x33" in r.message]


def test_cold_start_baseline_adopted_on_corroborating_read(plant: Plant, caplog):
    """A cold-start baseline is adopted once a second poll reads it the same (#289)."""
    import logging

    bank = _coherent_battery_bank()
    with caplog.at_level(logging.INFO, logger="givenergy_modbus.model.plant"):
        _feed_bank(plant, bank, device_address=_BATT, received_at=_T0)  # held
        _feed_bank(plant, bank, device_address=_BATT, received_at=_T0 + timedelta(seconds=30))  # corroborates
    assert plant.register_caches[_BATT][IR(60)] == 3300  # committed after corroboration
    assert plant.register_caches[_BATT][IR(98)] == 3005
    assert [r for r in caplog.records if "corroborated on re-read" in r.message and "0x33" in r.message]
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING and "0x33" in r.message]


def test_cold_start_transient_splice_first_frame_not_adopted(plant: Plant, caplog):
    """A transient splice in the first cold-start frame never becomes the baseline (#289 — core anti-poison).

    Frame 1 is a temp-zero cohort splice; frame 2 is clean. They disagree, so the splice is never
    corroborated; the most-recent (clean) frame becomes the candidate and is adopted once it reads the
    same again. The corrupt zeros must never reach the cache.
    """
    import logging

    splice = _coherent_battery_bank({76 + i: 0 for i in range(4)})  # 4 temp-zeros — a #256 splice shape
    clean = _coherent_battery_bank()
    with caplog.at_level(logging.INFO, logger="givenergy_modbus.model.plant"):
        _feed_bank(plant, splice, device_address=_BATT, received_at=_T0)  # held (frame 1)
        _feed_bank(plant, clean, device_address=_BATT, received_at=_T0 + timedelta(seconds=30))  # disagree → re-hold
        assert IR(76) not in plant.register_caches[_BATT], "must not adopt with only one clean read seen"
        _feed_bank(plant, clean, device_address=_BATT, received_at=_T0 + timedelta(seconds=60))  # corroborates clean
    assert plant.register_caches[_BATT][IR(76)] == 250, "clean baseline adopted; splice zeros never committed"
    assert plant.register_caches[_BATT][IR(60)] == 3300
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING and "0x33" in r.message]


def test_cold_start_most_recent_wins_recovers_from_corrupt_first(plant: Plant):
    """When cold-start reads disagree, the most-recent frame becomes the candidate (#289).

    corrupt, clean, clean → the corrupt first frame is discarded and the clean value adopted.
    """
    corrupt = _coherent_battery_bank({98: 9999, 60: 3600})  # immutable + physics trip vs clean
    clean = _coherent_battery_bank()
    _feed_bank(plant, corrupt, device_address=_BATT, received_at=_T0)  # held
    _feed_bank(plant, clean, device_address=_BATT, received_at=_T0 + timedelta(seconds=30))  # disagree → re-hold clean
    _feed_bank(plant, clean, device_address=_BATT, received_at=_T0 + timedelta(seconds=60))  # corroborate clean
    assert plant.register_caches[_BATT][IR(98)] == 3005  # corrupt first frame discarded
    assert plant.register_caches[_BATT][IR(60)] == 3300


def test_cold_start_stale_pending_reset(plant: Plant):
    """A pending cold-start frame older than the stale-bypass window isn't corroborated across the gap (#289).

    The first frame is held; the next arrives after > STALE_BYPASS_SECONDS (a genuine outage). It is
    treated as a fresh first read (re-held), not corroborated against the stale pending, so a further
    matching read is needed to adopt.
    """
    bank = _coherent_battery_bank()
    _feed_bank(plant, bank, device_address=_BATT, received_at=_T0)  # held
    # 400 s later (> 300 s): the pending is stale → treated as a fresh first, re-held (not adopted).
    _feed_bank(plant, bank, device_address=_BATT, received_at=_T0 + timedelta(seconds=400))
    assert IR(60) not in plant.register_caches[_BATT], "stale pending must not corroborate across the gap"
    assert plant.cold_start_held_count[_BATT] == 2  # both reads held
    # A further matching read now corroborates the fresh pending and commits.
    _feed_bank(plant, bank, device_address=_BATT, received_at=_T0 + timedelta(seconds=430))
    assert plant.register_caches[_BATT][IR(60)] == 3300


def test_cold_start_persistent_value_corroborates(plant: Plant):
    """A persistently-identical value corroborates and is adopted — #289 targets transient splices, not it.

    Two identical poisoned reads read the same, so they corroborate into the baseline; recovering a
    *persistent* poison is the #286 heal's job, not the cold-start guard's. Documents the boundary.
    """
    poisoned = _coherent_battery_bank({98: 9999})
    _feed_bank(plant, poisoned, device_address=_BATT, received_at=_T0)  # held
    _feed_bank(plant, poisoned, device_address=_BATT, received_at=_T0 + timedelta(seconds=30))  # corroborates
    assert plant.register_caches[_BATT][IR(98)] == 9999  # adopted — #286 heal recovers this later


def test_cold_start_corroborated_temp_zero_cohort_not_adopted(plant: Plant, caplog):
    """A temp-zero corruption cohort is refused as a baseline even when two reads corroborate it (#289 review).

    Codex's case: two identical IR76-79=0 frames corroborate, but baselining them would hard-reject
    every healthy frame forever (physics-only poison the #286 scalar heal can't recover). The cohort
    is refused (held, surfaced at WARNING); sustained healthy reads then corroborate and adopt.
    """
    import logging

    splice = _coherent_battery_bank({76 + i: 0 for i in range(4)})  # IR76-79 = 0 — the temp-zero cohort
    healthy = _coherent_battery_bank()
    with caplog.at_level(logging.INFO, logger="givenergy_modbus.model.plant"):
        _feed_bank(plant, splice, device_address=_BATT, received_at=_T0)  # held
        _feed_bank(
            plant, splice, device_address=_BATT, received_at=_T0 + timedelta(seconds=30)
        )  # corroborates → refused
        assert IR(76) not in plant.register_caches[_BATT], "corroborated temp-zero cohort must not be baselined"
        # Sustained healthy reads: the first disagrees with the held cohort, the second corroborates → adopt.
        _feed_bank(plant, healthy, device_address=_BATT, received_at=_T0 + timedelta(seconds=60))
        _feed_bank(plant, healthy, device_address=_BATT, received_at=_T0 + timedelta(seconds=90))
    assert plant.register_caches[_BATT][IR(76)] == 250, "healthy baseline finally adopted; cohort never committed"
    assert plant.register_caches[_BATT][IR(60)] == 3300
    assert plant.splice_reject_count == {}, "the cohort was held at cold start, never hard-rejected"
    warns = [r for r in caplog.records if "temp-zero corruption cohort" in r.message and "0x33" in r.message]
    assert warns and warns[0].levelno == logging.WARNING


def test_splice_ir115_usb_change_alone_commits(plant: Plant, caplog):
    """IR(115) usb_device_inserted is mutable (exempt from IMMUTABLE); a change alone must commit."""
    import logging

    _establish_baseline(plant, device_address=_BATT, received_at=_T0)
    with caplog.at_level(logging.WARNING, logger="givenergy_modbus.model.plant"):
        _feed_bank(
            plant,
            _coherent_battery_bank({115: 11}),  # 8 → 11, no other changes
            device_address=_BATT,
            received_at=_T0 + timedelta(seconds=30),
        )
    warns = [r for r in caplog.records if "splice" in r.message.lower() or "Held battery bank" in r.message]
    assert not warns
    assert plant.register_caches[_BATT][IR(115)] == 11


def test_splice_short_read_skips_guard(plant: Plant, caplog):
    """A register_count < 60 frame bypasses the splice guard even if values would trip battery physics."""
    import logging

    _establish_baseline(plant, device_address=_BATT, received_at=_T0)
    # IR76 dropping to 0 would be a temp-zero physics trip on a full 60-register bank.
    # With count=1 the guard gates off and the value commits normally.
    with caplog.at_level(logging.WARNING, logger="givenergy_modbus.model.plant"):
        _feed_bank(plant, {76: 0}, device_address=_BATT, count=1, received_at=_T0 + timedelta(seconds=30))
    warns = [r for r in caplog.records if "splice" in r.message.lower() or "Held battery bank" in r.message]
    assert not warns
    assert plant.register_caches[_BATT][IR(76)] == 0  # committed


def test_splice_short_read_refuses_temp_zero_cohort(plant: Plant, caplog):
    """A short read carrying the temp-zero cohort (>=2 cell-mass temps at 0) is held, not committed (#294).

    The short-read fast-path commits a partial bank without a physics comparison, so a spliced
    short read that zeroes >=2 temps would otherwise seed an unrecoverable poisoned baseline. The
    cohort is refused (held last-good); a lone temp-zero (<2) still commits as before.
    """
    import logging

    _establish_baseline(plant, device_address=_BATT, received_at=_T0)
    with caplog.at_level(logging.WARNING, logger="givenergy_modbus.model.plant"):
        _feed_bank(plant, {76: 0, 77: 0}, device_address=_BATT, count=20, received_at=_T0 + timedelta(seconds=30))
    assert plant.register_caches[_BATT][IR(76)] == 250  # held — baseline temp, not the zeroed cohort
    assert plant.splice_reject_count == {_BATT: 1}
    assert [r for r in caplog.records if "corruption cohort" in r.message and "0x33" in r.message]

    # A lone temp-zero is not the cohort — short read still commits (recoverable single trip).
    _feed_bank(plant, {76: 0}, device_address=_BATT, count=1, received_at=_T0 + timedelta(seconds=60))
    assert plant.register_caches[_BATT][IR(76)] == 0


def test_splice_non_battery_device_skips_guard(plant: Plant, caplog):
    """On a bare Plant, 0x32 → inverter getter; the splice guard is not applied there."""
    import logging

    # Seed 0x32 with a battery-shaped bank (committed under the inverter getter).
    _feed_bank(plant, _coherent_battery_bank(), device_address=0x32, received_at=_T0)
    # Two battery-physics trips — would be rejected on 0x33, but 0x32 is not BatteryRegisterGetter.
    wild = _coherent_battery_bank({60: 3700, 76: 0})
    with caplog.at_level(logging.WARNING, logger="givenergy_modbus.model.plant"):
        _feed_bank(plant, wild, device_address=0x32, received_at=_T0 + timedelta(seconds=30))
    warns = [r for r in caplog.records if "splice" in r.message.lower() or "Held battery bank" in r.message]
    assert not warns
    assert plant.register_caches[0x32][IR(60)] == 3700  # committed


def test_splice_escrow_isolated_per_device(plant: Plant):
    """The splice escrow is keyed per device; confirming 0x33 must not affect 0x34's held state."""
    _establish_baseline(plant, device_address=0x33, received_at=_T0)
    _establish_baseline(plant, device_address=0x34, received_at=_T0)
    t1 = _T0 + timedelta(seconds=30)
    t2 = _T0 + timedelta(seconds=60)
    # Hold 0x33 on IR60; hold 0x34 on IR61.
    _feed_bank(plant, _coherent_battery_bank({60: 3700}), device_address=0x33, received_at=t1)
    _feed_bank(plant, _coherent_battery_bank({61: 3700}), device_address=0x34, received_at=t1)
    # Confirm 0x33 by re-reading IR60=3700.
    _feed_bank(plant, _coherent_battery_bank({60: 3700}), device_address=0x33, received_at=t2)
    assert plant.register_caches[0x33][IR(60)] == 3700, "0x33 confirmed and committed"
    assert plant.register_caches[0x34][IR(61)] == 3300, "0x34 still held; 0x33 confirm must not clear it"


def test_splice_rejected_bank_preserves_staleness(plant: Plant):
    """A splice-rejected bank records no ingestion timestamp; block_age keeps growing (#65/#256)."""
    _establish_baseline(plant, device_address=_BATT, received_at=_T0)
    # ≥2 physics trips → rejected → _stamp_block never called.
    corrupted = _coherent_battery_bank({60: 3700, 76: 0})
    _feed_bank(plant, corrupted, device_address=_BATT, received_at=_T0 + timedelta(seconds=30))
    # Age at t0 + 45 s must reflect the last *committed* bank at t0, not the rejected one.
    assert plant.block_age(_BATT, "IR", 60, 60, now=_T0 + timedelta(seconds=45)) == 45.0


def test_splice_stale_baseline_bypass(plant: Plant, caplog):
    """After a long gap the guard bypasses physics checks and adopts the incoming bank.

    Per-poll thresholds are calibrated for ~30 s intervals. After a network outage or
    prolonged refresh failure, a legitimate multi-field change (SOC/temp/cap drift) would
    exceed them. Without this bypass, the guard would reject the first post-reconnect bank
    and then pin the cache forever — rejected banks never advance the timestamp so every
    subsequent poll also compares against the same stale baseline.
    """
    import logging

    _establish_baseline(plant, device_address=_BATT, received_at=_T0)
    # Simulate a 400 s gap (> STALE_BYPASS_SECONDS=300): values that would be >=2 physics
    # trips on a fresh baseline must commit unconditionally after a stale one.
    t_reconnect = _T0 + timedelta(seconds=400)
    post_outage = _coherent_battery_bank({60: 3700, 76: 0})  # 2 battery-physics trips
    with caplog.at_level(logging.INFO, logger="givenergy_modbus.model.plant"):
        _feed_bank(plant, post_outage, device_address=_BATT, received_at=t_reconnect)
    # Values committed (guard bypassed).
    assert plant.register_caches[_BATT][IR(60)] == 3700
    assert plant.register_caches[_BATT][IR(76)] == 0
    # Bypass emits an INFO log; no splice rejection WARNING.
    infos = [r for r in caplog.records if "stale baseline" in r.message and "0x33" in r.message]
    assert len(infos) == 1 and infos[0].levelno == logging.INFO
    warns = [r for r in caplog.records if "Rejected battery bank" in r.message]
    assert not warns


def test_splice_stale_bypass_refuses_temp_zero_cohort(plant: Plant, caplog):
    """The stale-baseline bypass must not adopt the temp-zero corruption cohort post-gap (#294).

    A gap > STALE_BYPASS_SECONDS normally adopts the next bank unconditionally, but the temp-zero
    cohort would seed an unrecoverable poisoned baseline. It's held instead; crucially the bypass
    stays armed (the observation clock is not consumed) so the next healthy frame still recovers.
    """
    import logging

    _establish_baseline(plant, device_address=_BATT, received_at=_T0)
    cohort = _coherent_battery_bank({76: 0, 77: 0, 78: 0, 79: 0})  # temp-zero cohort
    with caplog.at_level(logging.WARNING, logger="givenergy_modbus.model.plant"):
        _feed_bank(plant, cohort, device_address=_BATT, received_at=_T0 + timedelta(seconds=400))
    assert plant.register_caches[_BATT][IR(76)] == 250  # held — not adopted
    assert plant.splice_reject_count == {_BATT: 1}
    assert [r for r in caplog.records if "corruption cohort post-gap" in r.message and "0x33" in r.message]

    # Bypass stayed armed: a healthy frame one poll later still sees the gap and adopts.
    healthy = _coherent_battery_bank({60: 3400})
    _feed_bank(plant, healthy, device_address=_BATT, received_at=_T0 + timedelta(seconds=430))
    assert plant.register_caches[_BATT][IR(60)] == 3400  # recovered via bypass
    assert plant.register_caches[_BATT][IR(76)] == 250


def test_splice_sustained_corruption_never_bypassed(plant: Plant, caplog):
    """A sustained corruption run stays rejected indefinitely — never adopted via the stale bypass.

    The bypass keys off the last *observed* bank, not the last accepted commit. A continuous
    temp-zero stream (an observed #256 corruption shape) keeps arriving each poll and is rejected
    each poll: the last good commit ages past STALE_BYPASS_SECONDS, but the observation clock stays
    one poll old, so the bypass never fires. Regression for the re-review P1: keying off commit age
    alone would adopt the still-corrupt bank after 5 minutes.
    """
    import logging

    _establish_baseline(plant, device_address=_BATT, received_at=_T0)
    corrupt = _coherent_battery_bank({76 + i: 0 for i in range(4)})  # 4 temp-zero physics trips
    with caplog.at_level(logging.INFO, logger="givenergy_modbus.model.plant"):
        # 20 consecutive polls × 30 s = 600 s, well past the 300 s bypass window.
        for n in range(1, 21):
            _feed_bank(plant, corrupt, device_address=_BATT, received_at=_T0 + timedelta(seconds=30 * n))
    # Last-good temps retained the whole time; the corrupt zeros never committed.
    assert plant.register_caches[_BATT][IR(76)] == 250
    # The bypass must never have fired (it would have adopted a corrupt bank).
    assert not [r for r in caplog.records if "stale baseline" in r.message]
    # Every corrupt poll was rejected.
    rejects = [r for r in caplog.records if "Rejected battery bank" in r.message and "0x33" in r.message]
    assert len(rejects) == 20


def test_splice_bypass_only_after_genuine_gap_not_rejection_streak(plant: Plant, caplog):
    """An intervening (rejected) bank resets the observation clock, so a later gap is measured fresh.

    A corruption bank at t+30 is rejected but still counts as an observation. A genuine bank at
    t+400 is then only ~370 s after that rejected one (> window → bypass), confirming the clock
    tracks every observation, not just commits. The complement of the sustained-run test.
    """
    import logging

    _establish_baseline(plant, device_address=_BATT, received_at=_T0)
    # A rejected corruption bank shortly after seed: advances the observation clock to _T0+30.
    _feed_bank(
        plant,
        _coherent_battery_bank({60: 3700, 76: 0}),
        device_address=_BATT,
        received_at=_T0 + timedelta(seconds=30),
    )
    assert plant.register_caches[_BATT][IR(76)] == 250  # rejected, last-good kept
    # Then a real gap to _T0+400: 370 s since the last observation (the rejected bank) → bypass.
    with caplog.at_level(logging.INFO, logger="givenergy_modbus.model.plant"):
        _feed_bank(
            plant,
            _coherent_battery_bank({60: 3700, 76: 0}),
            device_address=_BATT,
            received_at=_T0 + timedelta(seconds=400),
        )
    assert plant.register_caches[_BATT][IR(76)] == 0  # adopted via bypass
    assert [r for r in caplog.records if "stale baseline" in r.message and "0x33" in r.message]


def test_splice_guard_normalises_naive_received_at(plant: Plant, caplog):
    """A tz-naive received_at is normalised to UTC in the guard, so the gap still computes (#256).

    Mirrors block_age()'s posture: ingestion timestamps may arrive naive. The observation clock
    must normalise them, or subtracting a naive from an aware datetime would raise.
    """
    import logging

    naive_t0 = datetime(2026, 6, 9, 12, 0, 0)  # no tzinfo
    _establish_baseline(plant, device_address=_BATT, received_at=naive_t0)
    assert plant.register_caches[_BATT][IR(60)] == 3300  # corroborated commit, no crash on naive

    naive_later = datetime(2026, 6, 9, 12, 6, 40)  # +400 s, still naive (> bypass window)
    with caplog.at_level(logging.INFO, logger="givenergy_modbus.model.plant"):
        _feed_bank(
            plant,
            _coherent_battery_bank({60: 3700, 76: 0}),  # would be >=2 trips on a fresh baseline
            device_address=_BATT,
            received_at=naive_later,
        )
    # The 400 s gap across two naive timestamps was computed correctly → bypass fired.
    assert plant.register_caches[_BATT][IR(76)] == 0
    assert [r for r in caplog.records if "stale baseline" in r.message and "0x33" in r.message]


def test_splice_guard_defaults_now_when_received_at_missing(plant: Plant):
    """With no received_at, the guard stamps the observation with the current time (#256).

    The `now is None` fallback must produce a tz-aware timestamp so consecutive observations
    still subtract cleanly; a near-instant second poll has a ~0 s gap and commits normally.
    """
    _establish_baseline(plant, device_address=_BATT, received_at=None)  # both reads default now()
    assert plant.register_caches[_BATT][IR(60)] == 3300  # corroborated commit, no crash
    # Second bank moments later: gap ~0 s (no bypass), single in-threshold change commits.
    _feed_bank(plant, _coherent_battery_bank({60: 3350}), device_address=_BATT)
    assert plant.register_caches[_BATT][IR(60)] == 3350
