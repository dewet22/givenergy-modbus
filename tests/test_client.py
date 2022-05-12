# type: ignore[attr-defined]

import asyncio
import datetime
from asyncio import AbstractEventLoop
from collections import deque
from typing import AsyncGenerator

import pytest

from givenergy_modbus.client import Message, Timeslot
from givenergy_modbus.client.asynchronous import Client
from givenergy_modbus.model.battery import Battery
from givenergy_modbus.model.inverter import Inverter
from givenergy_modbus.model.plant import Plant
from givenergy_modbus.model.register import HoldingRegister, InputRegister
from givenergy_modbus.pdu.read_registers import (
    ReadHoldingRegistersResponse,
    ReadInputRegistersRequest,
    ReadInputRegistersResponse,
)
from givenergy_modbus.pdu.transparent import TransparentRequest, TransparentResponse
from givenergy_modbus.pdu.write_registers import WriteHoldingRegisterRequest
from tests.model.test_register import HOLDING_REGISTERS, INPUT_REGISTERS


@pytest.fixture()
async def client() -> AsyncGenerator[Client, None]:
    """Supply an async client."""
    c = Client()
    c.connected = True
    await c.connect_with_retry()
    await c.reset_tasks()
    c.run_tasks_forever(
        (c.dispatch_next_incoming_message, 0),
        (c.generate_retries_for_expired_expected_responses, 0),
    )
    yield c
    await c.disconnect_and_reset()
    await c.reset_tasks()


async def loopback_next_outbound_message(c: Client, error: bool = False):
    """Helper simulating transmitting the next queued request and receiving a matching response."""
    item: Message = await c.tx_messages.get()
    item.transceived = datetime.datetime.now() - datetime.timedelta(seconds=1.5)
    await c.track_expected_response(item)
    if isinstance(item.pdu, TransparentRequest):
        response_pdu = item.pdu.expected_response()
        assert isinstance(response_pdu, TransparentResponse)
        response_pdu.error = error
        response_pdu.inverter_serial_number = 'AB1234'
        response_pdu.data_adapter_serial_number = 'ZY9876'
        response_message = Message(response_pdu, transceived=datetime.datetime.now(), provenance=item)
        await c.rx_messages.put(response_message)
    return item


@pytest.fixture()
async def loopback_client(client: Client) -> Client:
    """Supply an async client that immediately short-circuits outgoing requests to incoming responses."""

    async def loopback_messages():
        item = await loopback_next_outbound_message(client)
        client._all_tx_messages.append(item)

    client._all_tx_messages = []
    client.run_tasks_forever(
        (loopback_messages, 0),
    )
    assert client.plant.register_caches == {0x32: {}}
    return client


async def test_refresh_with_battery_discovery(client: Client):
    """Ensure we can refresh data and obtain an Inverter DTO."""
    assert client.tx_messages.empty()
    assert client.refresh_count == 0

    messages = await client.request_data_refresh()
    assert messages == list(client.tx_messages._queue)

    # the first time this is called we get a full refresh
    assert [str(m.pdu) for m in client.tx_messages._queue] == [
        '2:4/ReadInputRegistersRequest(slave_address=0x32 base_register=0 register_count=60)',
        '2:4/ReadInputRegistersRequest(slave_address=0x32 base_register=180 register_count=60)',
        '2:3/ReadHoldingRegistersRequest(slave_address=0x32 base_register=0 register_count=60)',
        '2:3/ReadHoldingRegistersRequest(slave_address=0x32 base_register=60 register_count=60)',
        '2:3/ReadHoldingRegistersRequest(slave_address=0x32 base_register=120 register_count=60)',
        '2:4/ReadInputRegistersRequest(slave_address=0x32 base_register=120 register_count=60)',
        # try to discover how many batteries are attached by probing following BMS slave addresses
        '2:4/ReadInputRegistersRequest(slave_address=0x32 base_register=60 register_count=60)',
        '2:4/ReadInputRegistersRequest(slave_address=0x33 base_register=60 register_count=60)',
        '2:4/ReadInputRegistersRequest(slave_address=0x34 base_register=60 register_count=60)',
        '2:4/ReadInputRegistersRequest(slave_address=0x35 base_register=60 register_count=60)',
        '2:4/ReadInputRegistersRequest(slave_address=0x36 base_register=60 register_count=60)',
        '2:4/ReadInputRegistersRequest(slave_address=0x37 base_register=60 register_count=60)',
    ]
    client.tx_messages._queue = deque()
    assert client.refresh_count == 1

    await client.request_data_refresh()
    # the next time this is called we get a quick refresh
    # because no BMS data has been read back batteries are not queried
    assert [str(m.pdu) for m in client.tx_messages._queue] == [
        '2:4/ReadInputRegistersRequest(slave_address=0x32 base_register=0 register_count=60)',
        '2:4/ReadInputRegistersRequest(slave_address=0x32 base_register=180 register_count=60)',
    ]
    client.tx_messages._queue = deque()
    assert client.refresh_count == 2

    # internal state is still empty and inconsistent
    assert client.plant == Plant()
    with pytest.raises(KeyError, match=r'HoldingRegister\(13\)'):
        client.plant.inverter

    # read all non-BMS registers
    client.rx_messages._queue = deque(
        [
            Message(
                ReadHoldingRegistersResponse(
                    inverter_serial_number='AB1234',
                    data_adapter_serial_number='XZ9876',
                    register_values=HOLDING_REGISTERS.values(),
                )
            ),
            Message(
                ReadInputRegistersResponse(
                    inverter_serial_number='AB1234',
                    data_adapter_serial_number='XZ9876',
                    base_register=0,
                    register_values=[v for k, v in INPUT_REGISTERS.items() if 0 <= k < 60],
                )
            ),
            Message(
                ReadInputRegistersResponse(
                    inverter_serial_number='AB1234',
                    data_adapter_serial_number='XZ9876',
                    base_register=120,
                    register_values=[v for k, v in INPUT_REGISTERS.items() if 120 <= k],
                )
            ),
        ]
    )
    await client.dispatch_next_incoming_message()
    await client.dispatch_next_incoming_message()
    await client.dispatch_next_incoming_message()

    expected_plant = Plant(
        inverter_serial_number='AB1234',
        data_adapter_serial_number='XZ9876',
        register_caches={
            50: {
                HoldingRegister(0): 8193,
                HoldingRegister(1): 3,
                HoldingRegister(2): 2098,
                HoldingRegister(3): 513,
                HoldingRegister(4): 0,
                HoldingRegister(5): 50000,
                HoldingRegister(6): 3600,
                HoldingRegister(7): 1,
                HoldingRegister(8): 16967,
                HoldingRegister(9): 12594,
                HoldingRegister(10): 13108,
                HoldingRegister(11): 18229,
                HoldingRegister(12): 13879,
                HoldingRegister(13): 21313,
                HoldingRegister(14): 12594,
                HoldingRegister(15): 13108,
                HoldingRegister(16): 18229,
                HoldingRegister(17): 13879,
                HoldingRegister(18): 3005,
                HoldingRegister(19): 449,
                HoldingRegister(20): 1,
                HoldingRegister(21): 449,
                HoldingRegister(22): 2,
                HoldingRegister(23): 0,
                HoldingRegister(24): 32768,
                HoldingRegister(25): 30235,
                HoldingRegister(26): 6000,
                HoldingRegister(27): 1,
                HoldingRegister(28): 0,
                HoldingRegister(29): 0,
                HoldingRegister(30): 17,
                HoldingRegister(31): 0,
                HoldingRegister(32): 4,
                HoldingRegister(33): 7,
                HoldingRegister(34): 140,
                HoldingRegister(35): 22,
                HoldingRegister(36): 1,
                HoldingRegister(37): 1,
                HoldingRegister(38): 23,
                HoldingRegister(39): 57,
                HoldingRegister(40): 19,
                HoldingRegister(41): 1,
                HoldingRegister(42): 2,
                HoldingRegister(43): 0,
                HoldingRegister(44): 0,
                HoldingRegister(45): 0,
                HoldingRegister(46): 101,
                HoldingRegister(47): 1,
                HoldingRegister(48): 0,
                HoldingRegister(49): 0,
                HoldingRegister(50): 100,
                HoldingRegister(51): 0,
                HoldingRegister(52): 0,
                HoldingRegister(53): 1,
                HoldingRegister(54): 1,
                HoldingRegister(55): 160,
                HoldingRegister(56): 0,
                HoldingRegister(57): 0,
                HoldingRegister(58): 1,
                HoldingRegister(59): 0,
                HoldingRegister(60): 1500,
                HoldingRegister(61): 30,
                HoldingRegister(62): 30,
                HoldingRegister(63): 1840,
                HoldingRegister(64): 2740,
                HoldingRegister(65): 4700,
                HoldingRegister(66): 5198,
                HoldingRegister(67): 126,
                HoldingRegister(68): 27,
                HoldingRegister(69): 24,
                HoldingRegister(70): 28,
                HoldingRegister(71): 1840,
                HoldingRegister(72): 2620,
                HoldingRegister(73): 4745,
                HoldingRegister(74): 5200,
                HoldingRegister(75): 126,
                HoldingRegister(76): 52,
                HoldingRegister(77): 1,
                HoldingRegister(78): 28,
                HoldingRegister(79): 1755,
                HoldingRegister(80): 2837,
                HoldingRegister(81): 4700,
                HoldingRegister(82): 5200,
                HoldingRegister(83): 2740,
                HoldingRegister(84): 0,
                HoldingRegister(85): 0,
                HoldingRegister(86): 0,
                HoldingRegister(87): 0,
                HoldingRegister(88): 0,
                HoldingRegister(89): 0,
                HoldingRegister(90): 0,
                HoldingRegister(91): 0,
                HoldingRegister(92): 0,
                HoldingRegister(93): 0,
                HoldingRegister(94): 30,
                HoldingRegister(95): 430,
                HoldingRegister(96): 1,
                HoldingRegister(97): 4320,
                HoldingRegister(98): 5850,
                HoldingRegister(99): 0,
                HoldingRegister(100): 0,
                HoldingRegister(101): 0,
                HoldingRegister(102): 0,
                HoldingRegister(103): 0,
                HoldingRegister(104): 0,
                HoldingRegister(105): 0,
                HoldingRegister(106): 0,
                HoldingRegister(107): 0,
                HoldingRegister(108): 6,
                HoldingRegister(109): 1,
                HoldingRegister(110): 4,
                HoldingRegister(111): 50,
                HoldingRegister(112): 50,
                HoldingRegister(113): 0,
                HoldingRegister(114): 4,
                HoldingRegister(115): 0,
                HoldingRegister(116): 100,
                HoldingRegister(117): 0,
                HoldingRegister(118): 0,
                HoldingRegister(119): 0,
                HoldingRegister(120): 0,
                HoldingRegister(121): 0,
                HoldingRegister(122): 0,
                HoldingRegister(123): 0,
                HoldingRegister(124): 0,
                HoldingRegister(125): 0,
                HoldingRegister(126): 0,
                HoldingRegister(127): 0,
                HoldingRegister(128): 0,
                HoldingRegister(129): 0,
                HoldingRegister(130): 0,
                HoldingRegister(131): 0,
                HoldingRegister(132): 0,
                HoldingRegister(133): 0,
                HoldingRegister(134): 0,
                HoldingRegister(135): 0,
                HoldingRegister(136): 0,
                HoldingRegister(137): 0,
                HoldingRegister(138): 0,
                HoldingRegister(139): 0,
                InputRegister(0): 0,
                InputRegister(1): 14,
                InputRegister(2): 10,
                InputRegister(3): 70,
                InputRegister(4): 0,
                InputRegister(5): 2367,
                InputRegister(6): 0,
                InputRegister(7): 1832,
                InputRegister(8): 0,
                InputRegister(9): 0,
                InputRegister(10): 0,
                InputRegister(11): 0,
                InputRegister(12): 159,
                InputRegister(13): 4990,
                InputRegister(14): 0,
                InputRegister(15): 12,
                InputRegister(16): 4790,
                InputRegister(17): 4,
                InputRegister(18): 0,
                InputRegister(19): 5,
                InputRegister(20): 0,
                InputRegister(21): 0,
                InputRegister(22): 6,
                InputRegister(23): 0,
                InputRegister(24): 0,
                InputRegister(25): 0,
                InputRegister(26): 209,
                InputRegister(27): 0,
                InputRegister(28): 946,
                InputRegister(29): 0,
                InputRegister(30): 65194,
                InputRegister(31): 0,
                InputRegister(32): 0,
                InputRegister(33): 3653,
                InputRegister(34): 0,
                InputRegister(35): 93,
                InputRegister(36): 90,
                InputRegister(37): 89,
                InputRegister(38): 30,
                InputRegister(39): 0,
                InputRegister(40): 0,
                InputRegister(41): 222,
                InputRegister(42): 342,
                InputRegister(43): 680,
                InputRegister(44): 81,
                InputRegister(45): 0,
                InputRegister(46): 930,
                InputRegister(47): 0,
                InputRegister(48): 213,
                InputRegister(49): 1,
                InputRegister(50): 4991,
                InputRegister(51): 0,
                InputRegister(52): 0,
                InputRegister(53): 2356,
                InputRegister(54): 4986,
                InputRegister(55): 223,
                InputRegister(56): 170,
                InputRegister(57): 0,
                InputRegister(58): 292,
                InputRegister(59): 4,
                InputRegister(120): 0,
                InputRegister(121): 0,
                InputRegister(122): 0,
                InputRegister(123): 0,
                InputRegister(124): 0,
                InputRegister(125): 0,
                InputRegister(126): 0,
                InputRegister(127): 0,
                InputRegister(128): 0,
                InputRegister(129): 0,
                InputRegister(130): 0,
                InputRegister(131): 0,
                InputRegister(132): 0,
                InputRegister(133): 0,
                InputRegister(134): 0,
                InputRegister(135): 0,
                InputRegister(136): 0,
                InputRegister(137): 0,
                InputRegister(138): 0,
                InputRegister(139): 0,
                InputRegister(140): 0,
                InputRegister(141): 0,
                InputRegister(142): 0,
                InputRegister(143): 0,
                InputRegister(144): 0,
                InputRegister(145): 0,
                InputRegister(146): 0,
                InputRegister(147): 0,
                InputRegister(148): 0,
                InputRegister(149): 0,
                InputRegister(150): 0,
                InputRegister(151): 0,
                InputRegister(152): 0,
                InputRegister(153): 0,
                InputRegister(154): 0,
                InputRegister(155): 0,
                InputRegister(156): 0,
                InputRegister(157): 0,
                InputRegister(158): 0,
                InputRegister(159): 0,
                InputRegister(160): 0,
                InputRegister(161): 0,
                InputRegister(162): 0,
                InputRegister(163): 0,
                InputRegister(164): 0,
                InputRegister(165): 0,
                InputRegister(166): 0,
                InputRegister(167): 0,
                InputRegister(168): 0,
                InputRegister(169): 0,
                InputRegister(170): 0,
                InputRegister(171): 0,
                InputRegister(172): 0,
                InputRegister(173): 0,
                InputRegister(174): 0,
                InputRegister(175): 0,
                InputRegister(176): 0,
                InputRegister(177): 0,
                InputRegister(178): 0,
                InputRegister(179): 0,
                InputRegister(180): 1696,
                InputRegister(181): 1744,
                InputRegister(182): 89,
                InputRegister(183): 90,
                InputRegister(184): 0,
                InputRegister(185): 0,
                InputRegister(186): 0,
                InputRegister(187): 0,
                InputRegister(188): 0,
                InputRegister(189): 0,
                InputRegister(190): 0,
                InputRegister(191): 0,
                InputRegister(192): 0,
                InputRegister(193): 0,
                InputRegister(194): 0,
                InputRegister(195): 0,
                InputRegister(196): 0,
                InputRegister(197): 0,
                InputRegister(198): 0,
                InputRegister(199): 0,
                InputRegister(200): 0,
                InputRegister(201): 0,
                InputRegister(202): 0,
                InputRegister(203): 0,
                InputRegister(204): 0,
                InputRegister(205): 0,
                InputRegister(206): 0,
                InputRegister(207): 0,
                InputRegister(208): 0,
                InputRegister(209): 0,
                InputRegister(210): 0,
                InputRegister(211): 0,
                InputRegister(212): 0,
                InputRegister(213): 0,
                InputRegister(214): 0,
                InputRegister(215): 0,
                InputRegister(216): 0,
                InputRegister(217): 0,
                InputRegister(218): 0,
                InputRegister(219): 0,
                InputRegister(220): 0,
                InputRegister(221): 0,
                InputRegister(222): 0,
                InputRegister(223): 0,
                InputRegister(224): 0,
                InputRegister(225): 0,
                InputRegister(226): 0,
                InputRegister(227): 0,
                InputRegister(228): 0,
                InputRegister(229): 0,
                InputRegister(230): 0,
                InputRegister(231): 0,
                InputRegister(232): 0,
                InputRegister(233): 0,
                InputRegister(234): 0,
                InputRegister(235): 0,
                InputRegister(236): 0,
                InputRegister(237): 0,
                InputRegister(238): 0,
                InputRegister(239): 0,
            }
        },
    )
    assert client.plant == expected_plant
    expected_inverter = Inverter(
        inverter_serial_number='SA1234G567',
        device_type_code='2001',
        inverter_module=198706,
        inverter_firmware_version='D0.449-A0.449',
        dsp_firmware_version=449,
        arm_firmware_version=449,
        usb_device_inserted=2,
        select_arm_chip=False,
        meter_type=1,
        reverse_115_meter_direct=False,
        reverse_418_meter_direct=False,
        enable_drm_rj45_port=True,
        ct_adjust=2,
        enable_buzzer=False,
        bms_chip_version=101,
        num_mppt=2,
        num_phases=1,
        enable_ammeter=True,
        grid_port_max_power_output=6000,
        enable_60hz_freq_mode=False,
        enable_above_6kw_system=False,
        enable_frequency_derating=False,
        enable_low_voltage_fault_ride_through=False,
        enable_spi=False,
        inverter_modbus_address=17,
        modbus_version=1.4,
        pv1_voltage_adjust=0,
        pv2_voltage_adjust=0,
        grid_r_voltage_adjust=0,
        grid_s_voltage_adjust=0,
        grid_t_voltage_adjust=0,
        grid_power_adjust=0,
        battery_voltage_adjust=0,
        pv1_power_adjust=0,
        pv2_power_adjust=0,
        system_time=datetime.datetime(2022, 1, 1, 23, 57, 19),
        active_power_rate=100,
        reactive_power_rate=0,
        power_factor=-1,
        power_factor_function_model=0,
        inverter_state=(0, 1),
        inverter_start_time=30,
        inverter_restart_delay_time=30,
        dci_1_i=0.0,
        dci_1_time=0,
        dci_2_i=0.0,
        dci_2_time=0,
        f_ac_high_c=52.0,
        f_ac_high_in=52.0,
        f_ac_high_in_time=28,
        f_ac_high_out=51.98,
        f_ac_high_out_time=28,
        f_ac_low_c=47.0,
        f_ac_low_in=47.45,
        f_ac_low_in_time=1,
        f_ac_low_out=47.0,
        f_ac_low_out_time=24,
        gfci_1_i=0.0,
        gfci_1_time=0,
        gfci_2_i=0.0,
        gfci_2_time=0,
        v_ac_high_c=283.7,
        v_ac_high_in=262.0,
        v_ac_high_in_time=52,
        v_ac_high_out=274.0,
        v_ac_high_out_time=27,
        v_ac_low_c=175.5,
        v_ac_low_in=184.0,
        v_ac_low_in_time=126,
        v_ac_low_out=184.0,
        v_ac_low_out_time=126,
        iso_fault_value=0.0,
        gfci_fault_value=0.0,
        dci_fault_value=0.0,
        v_pv_fault_value=0.0,
        v_ac_fault_value=0.0,
        f_ac_fault_value=0.0,
        temp_fault_value=0.0,
        iso1=0,
        iso2=0,
        local_command_test=False,
        inverter_battery_serial_number='BG1234G567',
        inverter_battery_bms_firmware_version=3005,
        enable_bms_read=True,
        battery_type=1,
        battery_nominal_capacity=160.0,
        enable_auto_judge_battery_type=True,
        v_pv_input_start=150.0,
        v_battery_under_protection_limit=43.2,
        v_battery_over_protection_limit=58.5,
        enable_discharge=False,
        enable_charge=True,
        enable_charge_target=True,
        battery_power_mode=1,
        soc_force_adjust=0,
        charge_slot_1=(datetime.time(0, 30), datetime.time(4, 30)),
        charge_slot_2=(datetime.time(0, 0), datetime.time(0, 4)),
        discharge_slot_1=(datetime.time(0, 0), datetime.time(0, 0)),
        discharge_slot_2=(datetime.time(0, 0), datetime.time(0, 0)),
        charge_and_discharge_soc=(0, 0),
        battery_low_force_charge_time=6,
        battery_soc_reserve=4,
        battery_charge_limit=50,
        battery_discharge_limit=50,
        island_check_continue=0,
        battery_discharge_min_power_reserve=4,
        charge_target_soc=100,
        charge_soc_stop_2=0,
        discharge_soc_stop_2=0,
        charge_soc_stop_1=0,
        discharge_soc_stop_1=0,
        inverter_status=0,
        system_mode=1,
        inverter_countdown=30,
        charge_status=0,
        battery_percent=4,
        charger_warning_code=0,
        work_time_total=213,
        fault_code=0,
        e_battery_charge_day=9.0,
        e_battery_charge_day_2=9.0,
        e_battery_charge_total=174.4,
        e_battery_discharge_day=8.9,
        e_battery_discharge_day_2=8.9,
        e_battery_discharge_total=169.6,
        e_battery_throughput_total=183.2,
        e_discharge_year=0.0,
        e_inverter_out_day=8.1,
        e_inverter_out_total=93.0,
        e_grid_out_day=0.0,
        e_grid_in_day=20.9,
        e_grid_in_total=365.3,
        e_grid_out_total=0.6,
        e_inverter_in_day=9.3,
        e_inverter_in_total=94.6,
        e_pv1_day=0.4,
        e_pv2_day=0.5,
        e_solar_diverter=0.0,
        f_ac1=49.9,
        f_eps_backup=49.86,
        i_ac1=0.0,
        i_battery=0.0,
        i_grid_port=2.92,
        i_pv1=0.0,
        i_pv2=0.0,
        p_battery=0,
        p_eps_backup=0,
        p_grid_apparent=680,
        p_grid_out=-342,
        p_inverter_out=0,
        p_load_demand=342,
        p_pv1=0,
        p_pv2=0,
        e_pv_total=15.9,
        pf_inverter_out=-0.521,
        temp_battery=17.0,
        temp_charger=22.3,
        temp_inverter_heatsink=22.2,
        v_ac1=236.7,
        v_battery=49.91,
        v_eps_backup=235.6,
        v_highbrigh_bus=12,
        v_n_bus=0.0,
        v_p_bus=7.0,
        v_pv1=1.4,
        v_pv2=1.0,
        pf_cmd_memory_state=False,
        pf_limit_lp1_lp=0,
        pf_limit_lp1_pf=-1.0,
        pf_limit_lp2_lp=0,
        pf_limit_lp2_pf=-1.0,
        pf_limit_lp3_lp=0,
        pf_limit_lp3_pf=-1.0,
        pf_limit_lp4_lp=0,
        pf_limit_lp4_pf=-1.0,
        frequency_load_limit_rate=0,
        real_v_f_value=0.0,
        remote_bms_restart=False,
        safety_time_limit=0.0,
        safety_v_f_limit=0.0,
        start_system_auto_test=False,
        test_treat_time=0,
        test_treat_value=0.0,
        test_value=0.0,
        user_code=7,
        v_10_min_protection=274.0,
        variable_address=32768,
        variable_value=30235,
        inverter_model='Hybrid',
    )
    assert client.plant.inverter == expected_inverter
    assert client.plant.register_caches.keys() == {0x32}
    assert len(client.plant.register_caches[0x32]) == 320

    await client.request_data_refresh()
    # another quick refresh, still unaware of any batteries existing
    assert [str(m.pdu) for m in client.tx_messages._queue] == [
        '2:4/ReadInputRegistersRequest(slave_address=0x32 base_register=0 register_count=60)',
        '2:4/ReadInputRegistersRequest(slave_address=0x32 base_register=180 register_count=60)',
    ]
    client.tx_messages._queue = deque()
    assert client.refresh_count == 3

    assert client.plant.register_caches.keys() == {0x32}
    assert len(client.plant.register_caches[0x32]) == 320

    assert client.plant.inverter == expected_inverter
    assert client.plant.batteries == []

    # read in BMS registers - add three identical batteries
    client.rx_messages._queue = deque(
        [
            Message(
                ReadInputRegistersResponse(
                    inverter_serial_number='AB1234',
                    data_adapter_serial_number='XZ9876',
                    base_register=60,
                    register_values=[v for k, v in INPUT_REGISTERS.items() if 60 <= k < 120],
                    slave_address=0x32,
                )
            ),
            Message(
                ReadInputRegistersResponse(
                    inverter_serial_number='AB1234',
                    data_adapter_serial_number='XZ9876',
                    base_register=60,
                    register_values=[v for k, v in INPUT_REGISTERS.items() if 60 <= k < 120],
                    slave_address=0x33,
                )
            ),
            Message(
                ReadInputRegistersResponse(
                    inverter_serial_number='AB1234',
                    data_adapter_serial_number='XZ9876',
                    base_register=60,
                    register_values=[v for k, v in INPUT_REGISTERS.items() if 60 <= k < 120],
                    slave_address=0x34,
                )
            ),
        ]
    )
    await client.dispatch_next_incoming_message()
    await client.dispatch_next_incoming_message()
    await client.dispatch_next_incoming_message()

    assert client.plant.register_caches.keys() == {0x32, 0x33, 0x34}
    assert len(client.plant.register_caches[0x32]) == 380
    assert len(client.plant.register_caches[0x33]) == 60
    assert len(client.plant.register_caches[0x34]) == 60
    assert client.plant.inverter == expected_inverter
    expected_battery = Battery(
        battery_serial_number='BG1234G567',
        v_cell_01=3.117,
        v_cell_02=3.124,
        v_cell_03=3.129,
        v_cell_04=3.129,
        v_cell_05=3.125,
        v_cell_06=3.13,
        v_cell_07=3.122,
        v_cell_08=3.116,
        v_cell_09=3.111,
        v_cell_10=3.105,
        v_cell_11=3.119,
        v_cell_12=3.134,
        v_cell_13=3.146,
        v_cell_14=3.116,
        v_cell_15=3.135,
        v_cell_16=3.119,
        temp_cells_1=17.5,
        temp_cells_2=16.7,
        temp_cells_3=17.1,
        temp_cells_4=16.1,
        v_cells_sum=49.97,
        temp_bms_mos=17.2,
        v_battery_out=50.029,
        full_capacity=190.97,
        design_capacity=160.0,
        remaining_capacity=18.04,
        e_charge_total=174.4,
        e_discharge_total=169.6,
        status_1_2=(0, 0),
        status_3_4=(6, 16),
        status_5_6=(1, 0),
        status_7=(0, 0),
        warning_1_2=(0, 0),
        num_cycles=12,
        num_cells=16,
        bms_firmware_version=3005,
        soc=9,
        design_capacity_2=160.0,
        temp_max=17.4,
        temp_min=16.7,
        usb_inserted=8,
    )
    assert client.plant.batteries == [expected_battery, expected_battery, expected_battery]

    await client.request_data_refresh()
    # another quick refresh, but this time also queries the three newly discovered BMS registers too
    assert [str(m.pdu) for m in client.tx_messages._queue] == [
        '2:4/ReadInputRegistersRequest(slave_address=0x32 base_register=0 ' 'register_count=60)',
        '2:4/ReadInputRegistersRequest(slave_address=0x32 base_register=180 ' 'register_count=60)',
        '2:4/ReadInputRegistersRequest(slave_address=0x32 base_register=60 ' 'register_count=60)',
        '2:4/ReadInputRegistersRequest(slave_address=0x33 base_register=60 ' 'register_count=60)',
        '2:4/ReadInputRegistersRequest(slave_address=0x34 base_register=60 ' 'register_count=60)',
    ]
    client.tx_messages._queue = deque()
    assert client.refresh_count == 4


async def test_configure_charge_target(client: Client):
    """Ensure we can set and disable a charge target."""
    assert [str(m.pdu) for m in await client.set_charge_target(45)] == [
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(96)/ENABLE_CHARGE -> True/0x0001)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(20)/ENABLE_CHARGE_TARGET -> True/0x0001)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(116)/CHARGE_TARGET_SOC -> 45%/0x002d)',
    ]
    assert [str(m.pdu) for m in await client.set_charge_target(100)] == [
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(96)/ENABLE_CHARGE -> True/0x0001)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(20)/ENABLE_CHARGE_TARGET -> False/0x0000)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(116)/CHARGE_TARGET_SOC -> 100%/0x0064)',
    ]
    with pytest.raises(ValueError, match=r'Charge Target SOC \(0\) must be in \[4-100\]\%'):
        await client.set_charge_target(0)
    with pytest.raises(ValueError, match=r'Charge Target SOC \(1\) must be in \[4-100\]\%'):
        await client.set_charge_target(1)
    with pytest.raises(ValueError, match=r'Charge Target SOC \(101\) must be in \[4-100\]\%'):
        await client.set_charge_target(101)

    assert [str(m.pdu) for m in await client.disable_charge_target()] == [
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(20)/ENABLE_CHARGE_TARGET -> False/0x0000)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(116)/CHARGE_TARGET_SOC -> 100%/0x0064)',
    ]


async def test_set_charge(client: Client):
    """Ensure we can toggle charging."""
    message = await client.enable_charge()
    message.created = datetime.datetime(1, 2, 3, 4, 5, 6)
    assert str(message.pdu) == '2:6/WriteHoldingRegisterRequest(HoldingRegister(96)/ENABLE_CHARGE -> True/0x0001)'
    assert str(message) == (
        'Message(2:6/WriteHoldingRegisterRequest(HoldingRegister(96)/ENABLE_CHARGE -> True/0x0001) '
        'provenance=None '
        'raw_frame= '
        'created=0001-02-03T04:05:06 '
        'transceived=None '
        'ttl=4.5 '
        'retries_remaining=2 '
        'future=PENDING)'
    )

    message = await client.disable_charge()
    message.created = datetime.datetime(7, 6, 5, 4, 3, 2, 1)
    assert str(message.pdu) == '2:6/WriteHoldingRegisterRequest(HoldingRegister(96)/ENABLE_CHARGE -> False/0x0000)'
    assert str(message) == (
        'Message(2:6/WriteHoldingRegisterRequest(HoldingRegister(96)/ENABLE_CHARGE -> False/0x0000) '
        'provenance=None '
        'raw_frame= '
        'created=0007-06-05T04:03:02.000001 '
        'transceived=None '
        'ttl=4.5 '
        'retries_remaining=2 '
        'future=PENDING)'
    )


async def test_set_discharge(client: Client):
    """Ensure we can toggle discharging."""
    message = await client.enable_discharge()
    message.created = datetime.datetime(7, 6, 5, 4, 3, 2, 1)
    assert str(message.pdu) == '2:6/WriteHoldingRegisterRequest(HoldingRegister(59)/ENABLE_DISCHARGE -> True/0x0001)'
    assert str(message) == (
        'Message(2:6/WriteHoldingRegisterRequest(HoldingRegister(59)/ENABLE_DISCHARGE -> True/0x0001) '
        'provenance=None '
        'raw_frame= '
        'created=0007-06-05T04:03:02.000001 '
        'transceived=None '
        'ttl=4.5 '
        'retries_remaining=2 '
        'future=PENDING)'
    )

    message = await client.disable_discharge()
    message.created = datetime.datetime(7, 6, 5, 4, 3, 2, 1)
    assert str(message.pdu) == '2:6/WriteHoldingRegisterRequest(HoldingRegister(59)/ENABLE_DISCHARGE -> False/0x0000)'
    assert str(message) == (
        'Message(2:6/WriteHoldingRegisterRequest(HoldingRegister(59)/ENABLE_DISCHARGE -> False/0x0000) '
        'provenance=None '
        'raw_frame= '
        'created=0007-06-05T04:03:02.000001 '
        'transceived=None '
        'ttl=4.5 '
        'retries_remaining=2 '
        'future=PENDING)'
    )


async def test_set_battery_discharge_mode(client: Client):
    """Ensure we can set a discharge mode."""
    message = await client.set_discharge_mode_max_power()
    message.created = datetime.datetime(7, 6, 5, 4, 3, 2, 1)
    assert str(message.pdu) == '2:6/WriteHoldingRegisterRequest(HoldingRegister(27)/BATTERY_POWER_MODE -> 0/0x0000)'
    assert str(message) == (
        'Message(2:6/WriteHoldingRegisterRequest(HoldingRegister(27)/BATTERY_POWER_MODE -> 0/0x0000) '
        'provenance=None '
        'raw_frame= '
        'created=0007-06-05T04:03:02.000001 '
        'transceived=None '
        'ttl=4.5 '
        'retries_remaining=2 '
        'future=PENDING)'
    )

    message = await client.set_discharge_mode_to_match_demand()
    message.created = datetime.datetime(7, 6, 5, 4, 3, 2, 1)
    assert str(message.pdu) == '2:6/WriteHoldingRegisterRequest(HoldingRegister(27)/BATTERY_POWER_MODE -> 1/0x0001)'
    assert str(message) == (
        'Message(2:6/WriteHoldingRegisterRequest(HoldingRegister(27)/BATTERY_POWER_MODE -> 1/0x0001) '
        'provenance=None raw_frame= created=0007-06-05T04:03:02.000001 '
        'transceived=None ttl=4.5 retries_remaining=2 future=PENDING)'
    )


@pytest.mark.parametrize("action", ("charge", "discharge"))
@pytest.mark.parametrize("slot", (1, 2))
@pytest.mark.parametrize("hour1", (0, 23))
@pytest.mark.parametrize("min1", (0, 59))
@pytest.mark.parametrize("hour2", (0, 23))
@pytest.mark.parametrize("min2", (0, 59))
async def test_set_charge_slots(client: Client, action: str, slot: int, hour1: int, min1: int, hour2: int, min2: int):
    """Ensure we can set charge time slots correctly."""
    # test set and reset functions for the relevant {action} and {slot}
    messages = await getattr(client, f'set_{action}_slot_{slot}')(Timeslot.from_components(hour1, min1, hour2, min2))
    hr_start = HoldingRegister[f'{"CHARGE" if action == "charge" else "DISCHARGE"}_SLOT_{slot}_START']
    hr_end = HoldingRegister[f'{"CHARGE" if action == "charge" else "DISCHARGE"}_SLOT_{slot}_END']
    assert [str(m.pdu) for m in messages] == [
        f'2:6/WriteHoldingRegisterRequest(HoldingRegister({hr_start.value})/{hr_start.name} '
        f'-> {hour1:02}:{min1:02}/0x{100 * hour1 + min1 :04x})',
        f'2:6/WriteHoldingRegisterRequest(HoldingRegister({hr_end.value})/{hr_end.name} '
        f'-> {hour2:02}:{min2:02}/0x{100 * hour2 + min2 :04x})',
    ]

    messages = await getattr(client, f'reset_{action}_slot_{slot}')()
    assert [str(m.pdu) for m in messages] == [
        f'2:6/WriteHoldingRegisterRequest(HoldingRegister({hr_start.value})/{hr_start.name} -> 00:00/0x0000)',
        f'2:6/WriteHoldingRegisterRequest(HoldingRegister({hr_end.value})/{hr_end.name} -> 00:00/0x0000)',
    ]


async def test_set_mode_dynamic(client: Client):
    """Ensure we can set the inverter to dynamic mode."""
    messages = await client.set_mode_dynamic()
    assert [str(m.pdu) for m in messages] == [
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(27)/BATTERY_POWER_MODE -> 1/0x0001)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(110)/BATTERY_SOC_RESERVE -> 4%/0x0004)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(59)/ENABLE_DISCHARGE -> False/0x0000)',
    ]


async def test_set_mode_storage(client: Client):
    """Ensure we can set the inverter to a storage mode with discharge slots."""
    messages = await client.set_mode_storage(Timeslot.from_components(1, 2, 3, 4))
    assert [str(m.pdu) for m in messages] == [
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(27)/BATTERY_POWER_MODE -> 1/0x0001)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(110)/BATTERY_SOC_RESERVE -> 100%/0x0064)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(59)/ENABLE_DISCHARGE -> True/0x0001)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(56)/DISCHARGE_SLOT_1_START -> 01:02/0x0066)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(57)/DISCHARGE_SLOT_1_END -> 03:04/0x0130)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(44)/DISCHARGE_SLOT_2_START -> 00:00/0x0000)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(45)/DISCHARGE_SLOT_2_END -> 00:00/0x0000)',
    ]

    messages = await client.set_mode_storage(
        Timeslot.from_components(5, 6, 7, 8), Timeslot.from_components(9, 10, 11, 12)
    )
    assert [str(m.pdu) for m in messages] == [
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(27)/BATTERY_POWER_MODE -> 1/0x0001)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(110)/BATTERY_SOC_RESERVE -> 100%/0x0064)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(59)/ENABLE_DISCHARGE -> True/0x0001)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(56)/DISCHARGE_SLOT_1_START -> 05:06/0x01fa)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(57)/DISCHARGE_SLOT_1_END -> 07:08/0x02c4)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(44)/DISCHARGE_SLOT_2_START -> 09:10/0x038e)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(45)/DISCHARGE_SLOT_2_END -> 11:12/0x0458)',
    ]

    messages = await client.set_mode_storage(Timeslot.from_repr(1314, 1516), discharge_for_export=True)
    assert [str(m.pdu) for m in messages] == [
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(27)/BATTERY_POWER_MODE -> 0/0x0000)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(110)/BATTERY_SOC_RESERVE -> 100%/0x0064)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(59)/ENABLE_DISCHARGE -> True/0x0001)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(56)/DISCHARGE_SLOT_1_START -> 13:14/0x0522)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(57)/DISCHARGE_SLOT_1_END -> 15:16/0x05ec)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(44)/DISCHARGE_SLOT_2_START -> 00:00/0x0000)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(45)/DISCHARGE_SLOT_2_END -> 00:00/0x0000)',
    ]


async def test_set_charge_and_discharge_limits(client: Client):
    """Ensure we can set a charge limit."""
    message = await client.set_battery_charge_limit(1)
    assert str(message.pdu) == '2:6/WriteHoldingRegisterRequest(HoldingRegister(111)/BATTERY_CHARGE_LIMIT -> 1%/0x0001)'

    message = await client.set_battery_discharge_limit(1)
    assert str(message.pdu) == (
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(112)/BATTERY_DISCHARGE_LIMIT -> 1%/0x0001)'
    )

    message = await client.set_battery_charge_limit(50)
    assert str(message.pdu) == (
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(111)/BATTERY_CHARGE_LIMIT -> 50%/0x0032)'
    )

    message = await client.set_battery_discharge_limit(50)
    assert str(message.pdu) == (
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(112)/BATTERY_DISCHARGE_LIMIT -> 50%/0x0032)'
    )

    with pytest.raises(ValueError, match=r'Specified Charge Limit \(51%\) is not in \[0-50\]\%'):
        await client.set_battery_charge_limit(51)
    with pytest.raises(ValueError, match=r'Specified Discharge Limit \(51%\) is not in \[0-50\]\%'):
        await client.set_battery_discharge_limit(51)


async def test_set_system_time(client: Client):
    """Ensure set_system_time emits the correct requests."""
    messages = await client.set_system_date_time(
        datetime.datetime(year=2022, month=11, day=23, hour=4, minute=34, second=59)
    )
    assert [str(m.pdu) for m in messages] == [
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(35)/SYSTEM_TIME_YEAR -> 22/0x0016)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(36)/SYSTEM_TIME_MONTH -> 11/0x000b)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(37)/SYSTEM_TIME_DAY -> 23/0x0017)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(38)/SYSTEM_TIME_HOUR -> 4/0x0004)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(39)/SYSTEM_TIME_MINUTE -> 34/0x0022)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(40)/SYSTEM_TIME_SECOND -> 59/0x003b)',
    ]
    assert {m.pdu.slave_address for m in messages} == {0x11}


async def test_client_internal_wiring_async(loopback_client: Client):
    """Validate internal client API & behaviour."""
    requested_datetime = datetime.datetime(year=2022, month=11, day=23, hour=4, minute=34, second=59)
    messages = await loopback_client.set_system_date_time(requested_datetime)
    assert [str(m.pdu) for m in messages] == [
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(35)/SYSTEM_TIME_YEAR -> 22/0x0016)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(36)/SYSTEM_TIME_MONTH -> 11/0x000b)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(37)/SYSTEM_TIME_DAY -> 23/0x0017)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(38)/SYSTEM_TIME_HOUR -> 4/0x0004)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(39)/SYSTEM_TIME_MINUTE -> 34/0x0022)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(40)/SYSTEM_TIME_SECOND -> 59/0x003b)',
    ]

    futures = [m.future for m in messages]
    assert {f._state for f in futures} == {'PENDING'}
    await asyncio.gather(*[loopback_client.enqueue_message_for_sending(m) for m in messages])
    res = await asyncio.wait_for(asyncio.gather(*futures, return_exceptions=True), timeout=Message.ttl * 3)
    assert {f._state for f in futures} == {'FINISHED'}

    assert {m.pdu.slave_address for m in res} == {0x11}
    assert {m.provenance.pdu.slave_address for m in res} == {0x11}
    assert messages == loopback_client._all_tx_messages
    for i in range(6):
        assert res[i].provenance.pdu == messages[i].pdu

    assert loopback_client.expected_responses == {}
    assert loopback_client.tx_messages.empty()
    assert loopback_client.rx_messages.empty()
    assert loopback_client.plant.register_caches == {
        0x32: {
            HoldingRegister.SYSTEM_TIME_YEAR: 22,
            HoldingRegister.SYSTEM_TIME_MONTH: 11,
            HoldingRegister.SYSTEM_TIME_DAY: 23,
            HoldingRegister.SYSTEM_TIME_HOUR: 4,
            HoldingRegister.SYSTEM_TIME_MINUTE: 34,
            HoldingRegister.SYSTEM_TIME_SECOND: 59,
        }
    }
    # assert loopback_client.plant.inverter.system_time == requested_datetime  FIXME


async def test_client_internal_wiring(client: Client):
    """Validate internal client API & behaviour in synchronous steps."""
    # ensure the internal model starts out empty
    assert client.plant.register_caches == {0x32: {}}

    # generate some messages onto the tx_queue and verify internal state
    requested_datetime = datetime.datetime(2021, 10, 22, 3, 33, 58)
    messages = await client.set_system_date_time(requested_datetime)
    futures = [m.future for m in messages]
    assert {f._state for f in futures} == {'PENDING'}
    await asyncio.gather(*[client.enqueue_message_for_sending(m) for m in messages])

    assert len(messages) == 6
    assert len(futures) == 6
    assert [f.done() for f in futures] == [False] * 6
    assert client.tx_messages.qsize() == 6
    assert client.tx_messages._queue == deque(messages)
    assert client.rx_messages.qsize() == 0
    assert client.expected_responses == {}

    # use our loopback helper to simulate sending two messages and receiving two corresponding responses
    await loopback_next_outbound_message(client)
    await loopback_next_outbound_message(client)

    assert client.tx_messages.qsize() == 4
    assert client.tx_messages._queue == deque(messages[2:])
    assert tuple(client.expected_responses.keys()) == (
        messages[0].pdu.expected_response().shape_hash(),
        messages[1].pdu.expected_response().shape_hash(),
    )
    assert client.rx_messages.qsize() == 2
    assert [f.done() for f in futures] == [False] * 6

    # dispatch a single message from the incoming message queue
    await client.dispatch_next_incoming_message()

    assert client.tx_messages.qsize() == 4
    assert client.tx_messages._queue == deque(messages[2:])
    assert len(client.expected_responses) == 1
    assert tuple(client.expected_responses.keys()) == (messages[1].pdu.expected_response().shape_hash(),)
    assert client.rx_messages.qsize() == 1
    assert [f.done() for f in futures] == [True] + [False] * 5

    # run through the remainder of the messages and verify internal state
    for _ in range(4):
        await loopback_next_outbound_message(client)
        await client.dispatch_next_incoming_message()

    await client.dispatch_next_incoming_message()

    assert client.tx_messages.qsize() == 0
    assert client.expected_responses == {}
    assert client.rx_messages.qsize() == 0
    assert [f.done() for f in futures] == [True] * 6

    # ensure our internal models are updated when the futures are awaited
    res = await asyncio.wait_for(asyncio.gather(*futures, return_exceptions=True), timeout=Message.ttl * 3)
    assert {f._state for f in futures} == {'FINISHED'}
    assert client.plant.register_caches == {
        0x32: {
            HoldingRegister(35): 21,
            HoldingRegister(36): 10,
            HoldingRegister(37): 22,
            HoldingRegister(38): 3,
            HoldingRegister(39): 33,
            HoldingRegister(40): 58,
        }
    }
    assert {m.pdu.slave_address for m in res} == {0x11}
    assert {m.provenance.pdu.slave_address for m in res} == {0x11}
    assert [str(m.pdu) for m in res] == [
        '2:6/WriteHoldingRegisterResponse(HoldingRegister(35)/SYSTEM_TIME_YEAR -> 21/0x0015)',
        '2:6/WriteHoldingRegisterResponse(HoldingRegister(36)/SYSTEM_TIME_MONTH -> 10/0x000a)',
        '2:6/WriteHoldingRegisterResponse(HoldingRegister(37)/SYSTEM_TIME_DAY -> 22/0x0016)',
        '2:6/WriteHoldingRegisterResponse(HoldingRegister(38)/SYSTEM_TIME_HOUR -> 3/0x0003)',
        '2:6/WriteHoldingRegisterResponse(HoldingRegister(39)/SYSTEM_TIME_MINUTE -> 33/0x0021)',
        '2:6/WriteHoldingRegisterResponse(HoldingRegister(40)/SYSTEM_TIME_SECOND -> 58/0x003a)',
    ]
    assert [str(m.provenance.pdu) for m in res] == [
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(35)/SYSTEM_TIME_YEAR -> 21/0x0015)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(36)/SYSTEM_TIME_MONTH -> 10/0x000a)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(37)/SYSTEM_TIME_DAY -> 22/0x0016)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(38)/SYSTEM_TIME_HOUR -> 3/0x0003)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(39)/SYSTEM_TIME_MINUTE -> 33/0x0021)',
        '2:6/WriteHoldingRegisterRequest(HoldingRegister(40)/SYSTEM_TIME_SECOND -> 58/0x003a)',
    ]
    # assert client.plant.inverter.system_time == requested_datetime  # FIXME


async def test_expected_responses(client: Client, event_loop: AbstractEventLoop):
    m1 = Message(
        ReadInputRegistersResponse(
            inverter_serial_number='AB1234',
            data_adapter_serial_number='XZ9876',
            base_register=24,
            register_count=3,
            slave_address=0x44,
        ),
        future=event_loop.create_future(),
        provenance=Message(
            ReadInputRegistersRequest(base_register=24, register_count=3, slave_address=0x44),
            transceived=datetime.datetime.now() - datetime.timedelta(seconds=0.8),
            future=event_loop.create_future(),
        ),
    )
    client.expected_responses = {m1.pdu.shape_hash(): m1}

    rx_m1 = Message(
        ReadInputRegistersResponse(
            inverter_serial_number='AB1234',
            data_adapter_serial_number='XZ9876',
            base_register=2,
            register_count=7,
            register_values=[9, 8, 7, 6, 5, 4, 3],
            slave_address=0x33,
        ),
        transceived=datetime.datetime.now(),
    )
    client.rx_messages.put_nowait(rx_m1)
    assert rx_m1.pdu.shape_hash() != m1.pdu.shape_hash()

    rx_m2 = Message(
        ReadInputRegistersResponse(
            inverter_serial_number='AB1234',
            data_adapter_serial_number='XZ9876',
            base_register=24,
            register_count=3,
            register_values=[5, 6, 7],
            slave_address=0x44,
        ),
        transceived=datetime.datetime.now(),
    )
    client.rx_messages.put_nowait(rx_m2)
    assert rx_m2.pdu.shape_hash() == m1.pdu.shape_hash()

    assert not m1.future.done()
    assert client.rx_messages.qsize() == 2

    # consume first received message
    await client.dispatch_next_incoming_message()

    assert client.rx_messages.qsize() == 1
    assert not m1.future.done()
    with pytest.raises(asyncio.InvalidStateError, match='Result is not set'):
        m1.future.result()
    assert client.expected_responses == {m1.pdu.shape_hash(): m1}

    # consume next received message
    await client.dispatch_next_incoming_message()

    assert client.expected_responses == {}
    assert client.rx_messages.empty()
    assert m1.future.done()
    assert m1.future.result() == rx_m2
    assert rx_m2.provenance == m1.provenance
    assert rx_m2.raw_frame == m1.raw_frame
    assert rx_m2.created == m1.created
    assert rx_m2.ttl == m1.ttl
    assert rx_m2.retries_remaining == m1.retries_remaining
    assert rx_m2.future == m1.future
    assert rx_m2.pdu != m1.pdu
    assert rx_m2.transceived != m1.transceived
    assert 0.7 < rx_m2.network_roundtrip.total_seconds() < 1

    assert m1.future.result() != rx_m1
    assert rx_m1 != m1


async def test_record_expected_response(client: Client):
    assert client.expected_responses == {}
    assert client.tx_messages.qsize() == 0
    req = WriteHoldingRegisterRequest(register=HoldingRegister(35), value=20)
    res = req.expected_response()
    req_msg = Message(req, retries_remaining=2, ttl=0)

    await client.track_expected_response(req_msg)

    assert len(client.expected_responses) == 1
    assert res.shape_hash() in client.expected_responses.keys()
    expected_msg = client.expected_responses[res.shape_hash()]
    assert expected_msg.pdu.has_same_shape(res)
    assert expected_msg.provenance.pdu == req
    assert expected_msg.retries_remaining == 2
    assert client.tx_messages.qsize() == 0

    await client.generate_retries_for_expired_expected_responses()

    assert client.tx_messages.qsize() == 1
    retry = await client.tx_messages.get()
    assert retry.pdu == req
    assert retry.retries_remaining == 1


def test_message(event_loop: AbstractEventLoop):
    req = Message(
        ReadInputRegistersRequest(),
        created=datetime.datetime(2020, 2, 20, 20, 20, 20, 202020),
        transceived=datetime.datetime(2020, 2, 20, 20, 20, 20, 202020),
        future=event_loop.create_future(),
    )
    assert str(req) == (
        'Message(2:4/ReadInputRegistersRequest(base_register=0 register_count=0) '
        'provenance=None '
        'raw_frame= created=2020-02-20T20:20:20.202020 transceived=2020-02-20T20:20:20.202020 '
        'ttl=4.5 retries_remaining=0 future=PENDING)'
    )
    assert req.age > datetime.timedelta(days=804)
    assert req.expiry == datetime.datetime(2020, 2, 20, 20, 20, 24, 702020)
    assert req.expired is True
    assert req.network_roundtrip == datetime.timedelta(days=-999999999)

    res = Message(
        ReadInputRegistersResponse(),
        created=datetime.datetime(2022, 4, 10, 10, 10, 10, 101010),
        provenance=req,
        transceived=datetime.datetime(2023, 3, 21, 21, 21, 21, 212121),
        ttl=3.154e9,  # 100 years
        future=event_loop.create_future(),
    )
    assert str(res) == (
        'Message(2:4/ReadInputRegistersResponse(base_register=0 register_count=0) '
        'provenance=Message(2:4/ReadInputRegistersRequest(base_register=0 register_count=0) ...) '
        'raw_frame= created=2022-04-10T10:10:10.101010 transceived=2023-03-21T21:21:21.212121 '
        'ttl=3154000000.0 retries_remaining=0 future=PENDING)'
    )
    assert res.age > datetime.timedelta(days=24)
    assert res.expiry == datetime.datetime(2122, 3, 22, 1, 16, 50, 101010)
    assert res.expired is False
    assert res.network_roundtrip == datetime.timedelta(days=1125, seconds=3661, microseconds=10101)

    req.future.set_result(res)
    assert str(req) == (
        'Message(2:4/ReadInputRegistersRequest(base_register=0 register_count=0) '
        'provenance=None '
        'raw_frame= created=2020-02-20T20:20:20.202020 transceived=2020-02-20T20:20:20.202020 '
        'ttl=4.5 retries_remaining=0 future=FINISHED)'
    )


def test_timeslot():
    ts = Timeslot(datetime.time(4, 5), datetime.time(9, 8))
    assert ts == Timeslot(start=datetime.time(4, 5), end=datetime.time(9, 8))
    assert ts == Timeslot(datetime.time(4, 5), datetime.time(9, 8))
    assert ts == Timeslot.from_components(4, 5, 9, 8)
    assert ts == Timeslot.from_repr(405, 908)
    assert ts == Timeslot.from_repr('405', '908')
    with pytest.raises(ValueError, match='invalid literal'):
        Timeslot.from_repr(2, 2)
    with pytest.raises(ValueError, match='hour must be in 0..23'):
        Timeslot.from_repr(999999, 999999)
    with pytest.raises(ValueError, match='minute must be in 0..59'):
        Timeslot.from_repr(999, 888)
    with pytest.raises(ValueError, match='hour must be in 0..23'):
        Timeslot.from_components(99, 88, 77, 66)
    with pytest.raises(ValueError, match='minute must be in 0..59'):
        Timeslot.from_components(11, 22, 11, 66)

    ts = Timeslot(datetime.time(12, 34), datetime.time(23, 45))
    assert ts == Timeslot(start=datetime.time(12, 34), end=datetime.time(23, 45))
    assert ts == Timeslot(datetime.time(12, 34), datetime.time(23, 45))
    assert ts == Timeslot.from_components(12, 34, 23, 45)
    assert ts == Timeslot.from_repr(1234, 2345)
    assert ts == Timeslot.from_repr('1234', '2345')
    with pytest.raises(ValueError, match='hour must be in 0..23'):
        assert ts == Timeslot.from_components(43, 21, 54, 32)
    with pytest.raises(ValueError, match='hour must be in 0..23'):
        assert ts == Timeslot.from_repr(4321, 5432)
    with pytest.raises(ValueError, match='hour must be in 0..23'):
        assert ts == Timeslot.from_repr('4321', '5432')
