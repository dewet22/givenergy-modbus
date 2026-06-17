"""Tests for #192 — per-module AIO battery data (AioBatteryModule).

The AIO stores each battery module in its own device-address cache (0x50-0x53), each a
plain IR(60-119) block: 24 cell voltages (IR 60-83), temperatures (IR 90-113; only the
first ~12 are populated on known hardware), and the module serial (IR 114-118). Decoded
against the real aio_a fixture.
"""

import pytest

from givenergy_modbus.model.aio_battery import AioBatteryModule, AioBatteryModuleRegisterGetter
from givenergy_modbus.model.devices import DeviceType
from givenergy_modbus.model.hv_bcu import decode_cells_temps_serial
from givenergy_modbus.model.inverter import Model
from givenergy_modbus.model.plant import PlantCapabilities
from givenergy_modbus.model.register import IR
from givenergy_modbus.model.register_cache import RegisterCache
from tests.model.test_fixture_golden_master import _replay

_AIO_MODULE_ADDRS = [0x50, 0x51, 0x52, 0x53]


async def _aio_plant_with_caps():
    """Replay the aio_a fixture and attach AIO capabilities (as detect() would)."""
    plant = await _replay("aio_a/aio_arm612_5min.log")
    plant.capabilities = PlantCapabilities(
        device_type=Model.ALL_IN_ONE,
        inverter_address=0x11,
        bcu_stacks=[(0, 4)],
        aio_battery_module_addresses=_AIO_MODULE_ADDRS,
    )
    return plant


@pytest.mark.timeout(20)
async def test_aio_module_decodes_cells_temps_serial_from_own_cache():
    """A module's own 0x50 cache decodes to 24 cell voltages, temps, and an HX serial."""
    plant = await _replay("aio_a/aio_arm612_5min.log")
    cache = plant.register_caches[0x50]

    module = AioBatteryModule.from_register_cache(cache, 0x50)

    assert module.module_address == 0x50
    # 24 cell voltages, all ~3.28 V on this capture
    assert module.v_cell_01 == pytest.approx(3.28, abs=0.01)
    assert module.v_cell_24 == pytest.approx(3.28, abs=0.01)
    # temperatures present on the first sensors (IR 90-101 ≈ 20 °C)
    assert module.t_cell_01 == pytest.approx(20.2, abs=0.5)
    # serial is the module's own HX-prefixed hardware serial
    assert module.serial_number is not None
    assert module.serial_number.startswith("HX")


def test_aio_module_empty_cache_has_no_serial():
    """An empty cache yields a module with no serial (is_valid False)."""
    module = AioBatteryModule.from_register_cache(RegisterCache(), 0x50)
    assert module.serial_number is None
    assert not module.is_valid()


def test_aio_module_serial_decodes_from_ir_114():
    """Serial decodes from IR(114-118) of the module's own cache."""
    # "HX2414G832" encoded big-endian into IR(114-118)
    serial = "HX2414G832"
    regs = {IR(114 + i): int.from_bytes(serial[i * 2 : i * 2 + 2].encode("latin1"), "big") for i in range(5)}
    module = AioBatteryModule.from_register_cache(RegisterCache(regs), 0x52)
    assert module.serial_number == "HX2414G832"
    assert module.module_address == 0x52
    assert module.is_valid()


# ---------------------------------------------------------------------------
# Register-getter metadata (#273) — field→register map for staleness gating
# ---------------------------------------------------------------------------


def _regs(name: str) -> list[tuple[str, int]]:
    return [(r.reg_type, r.index) for r in AioBatteryModule.REGISTER_GETTER.registers_of(name)]


def test_aio_registers_of_resolves_boundary_fields():
    """registers_of() maps each per-cell field to its backing IR register(s)."""
    assert _regs("v_cell_01") == [("IR", 60)]
    assert _regs("v_cell_24") == [("IR", 83)]
    assert _regs("t_cell_01") == [("IR", 90)]
    assert _regs("t_cell_24") == [("IR", 113)]
    assert _regs("serial_number") == [("IR", 114), ("IR", 115), ("IR", 116), ("IR", 117), ("IR", 118)]


def test_aio_registers_of_unknown_or_unbacked_is_empty():
    """Non-register-backed (module_address) and unknown fields yield an empty tuple."""
    assert AioBatteryModule.REGISTER_GETTER.registers_of("module_address") == ()
    assert AioBatteryModule.REGISTER_GETTER.registers_of("nope") == ()


def test_aio_precision_of_matches_scaling():
    """precision_of() reflects the converter scaling (milli=3, deci=1)."""
    assert AioBatteryModule.precision_of("v_cell_01") == 3
    assert AioBatteryModule.precision_of("t_cell_01") == 1


def test_aio_lut_field_set_matches_decode():
    """Drift guard: the LUT's fields track exactly what decode_cells_temps_serial produces.

    Adding/removing a cell in the decode loop without updating the LUT (or vice versa) fails here.
    """
    primed = RegisterCache({IR(i): 1 for i in range(60, 119)})
    decoded = decode_cells_temps_serial(primed, base=0)
    assert set(AioBatteryModuleRegisterGetter.REGISTER_LUT) == set(decoded)


@pytest.mark.timeout(20)
async def test_aio_registers_of_feeds_register_age():
    """End-to-end: registers_of() yields a register that Plant.register_age() can age (the hass use-case)."""
    plant = await _aio_plant_with_caps()
    reg = AioBatteryModule.REGISTER_GETTER.registers_of("v_cell_01")[0]
    age = plant.register_age(0x50, reg)
    assert age is not None and age >= 0


# ---------------------------------------------------------------------------
# Plant enumeration
# ---------------------------------------------------------------------------


@pytest.mark.timeout(20)
async def test_plant_aio_battery_modules_lists_four_modules():
    """Plant.aio_battery_modules decodes one module per address from its own cache."""
    plant = await _aio_plant_with_caps()
    modules = plant.aio_battery_modules

    assert [m.module_address for m in modules] == _AIO_MODULE_ADDRS
    assert all(m.serial_number and m.serial_number.startswith("HX") for m in modules)
    # The fixture is redacted to a common HX0000G000 serial, but the per-module
    # temperatures differ — proof each module is decoded from its own separate cache
    # (0x50-0x53), not re-read from one shared cache.
    assert len({m.t_cell_01 for m in modules}) > 1, "modules decode from distinct caches"


@pytest.mark.timeout(20)
async def test_plant_aio_battery_modules_empty_without_caps():
    """No AIO module addresses in caps → empty list (additive, non-AIO unaffected)."""
    plant = await _replay("aio_a/aio_arm612_5min.log")
    plant.capabilities = PlantCapabilities(device_type=Model.ALL_IN_ONE, inverter_address=0x11)
    assert plant.aio_battery_modules == []


@pytest.mark.timeout(20)
async def test_plant_aio_battery_modules_skips_on_decode_error(monkeypatch):
    """A decode error for one module is caught; the remaining modules are still returned."""
    from givenergy_modbus.model.aio_battery import AioBatteryModule

    plant = await _aio_plant_with_caps()
    call_count = 0

    original = AioBatteryModule.from_register_cache

    def _raise_on_first(cache, addr):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("simulated decode failure")
        return original(cache, addr)

    monkeypatch.setattr(AioBatteryModule, "from_register_cache", staticmethod(_raise_on_first))
    modules = plant.aio_battery_modules

    assert len(modules) == 3  # first module skipped, remaining 3 returned


@pytest.mark.timeout(20)
async def test_plant_devices_emits_battery_module_rows_under_inverter():
    """Plant.devices emits 4 BATTERY_MODULE rows, and they ride on the inverter facade too."""
    plant = await _aio_plant_with_caps()
    rows = plant.devices

    module_rows = [r for r in rows if r.device_type is DeviceType.BATTERY_MODULE]
    assert len(module_rows) == 4
    assert all(r.serial_number and r.serial_number.startswith("HX") for r in module_rows)

    # The AIO inverter row carries the same modules on its facade (#106 ownership).
    inverter_rows = [r for r in rows if r.device_type is DeviceType.INVERTER]
    assert len(inverter_rows) == 1
    assert len(inverter_rows[0].device.battery_modules) == 4
