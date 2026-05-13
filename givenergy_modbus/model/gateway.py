"""GivEnergy Gateway data model.

Two variants are needed: Gateway (firmware GA000009 and before) and Gateway2
(GA000010 and after). The only differences are the register byte order for
uint32 energy totals and the AIO serial number register addresses.

Use `select_gateway(register_cache)` to get the right class from a live cache.
"""

from pydantic import ConfigDict, create_model

from givenergy_modbus.model.battery import State
from givenergy_modbus.model.inverter import WorkMode
from givenergy_modbus.model.register import IR, RegisterGetter
from givenergy_modbus.model.register import Converter as C
from givenergy_modbus.model.register import RegisterDefinition as Def

# Registers shared by both firmware variants (no byte-order differences)
_GATEWAY_COMMON_LUT = {
    #
    # Input Registers 1600–1631 — System state
    #
    # IR(1603) carries the firmware version suffix; gateway_version spans 1600–1603
    "software_version": Def(C.gateway_version, None, IR(1600), IR(1601), IR(1602), IR(1603)),
    "work_mode": Def(C.uint16, WorkMode, IR(1604)),
    "v_grid": Def(C.int16, C.deci, IR(1608), min=0.0, max=500.0),
    "i_grid": Def(C.int16, C.deci, IR(1609), min=-500.0, max=500.0),
    "v_load": Def(C.deci, None, IR(1610), min=0.0, max=500.0),
    "i_load": Def(C.deci, None, IR(1611), min=0.0, max=500.0),
    "i_pv": Def(C.int16, C.deci, IR(1612), min=0.0, max=500.0),
    "p_ac1": Def(C.int16, None, IR(1616)),
    "p_pv": Def(C.uint16, None, IR(1617), max=50000),
    "p_load": Def(C.uint16, None, IR(1618), max=50000),
    "p_liberty": Def(C.int16, None, IR(1619)),
    "fault_protection": Def(C.uint32, None, IR(1620), IR(1621)),
    # gateway_fault_codes: raw uint32; fork-specific decoder omitted
    "gateway_fault_codes": Def(C.uint32, None, IR(1622), IR(1623)),
    "v_grid_relay": Def(C.deci, None, IR(1624), min=0.0, max=500.0),
    "v_inverter_relay": Def(C.deci, None, IR(1625), min=0.0, max=500.0),
    "first_inverter_serial_number": Def(C.string, None, IR(1627), IR(1628), IR(1629), IR(1630), IR(1631)),
    #
    # Input Registers 1640 — Daily / today energy (same in both variants)
    #
    "e_grid_import_today": Def(C.deci, None, IR(1640)),
    "e_pv_today": Def(C.deci, None, IR(1643)),
    "e_grid_export_today": Def(C.deci, None, IR(1646)),
    "e_aio_charge_today": Def(C.deci, None, IR(1649)),
    "e_aio_discharge_today": Def(C.deci, None, IR(1652)),
    "e_load_today": Def(C.deci, None, IR(1655)),
    #
    # Input Registers 1700–1704 — AIO summary
    #
    "parallel_aio_num": Def(C.uint16, None, IR(1700)),
    "parallel_aio_online_num": Def(C.uint16, None, IR(1701)),
    "p_aio_total": Def(C.int16, None, IR(1702)),
    "aio_state": Def(C.uint16, State, IR(1703)),
    "battery_firmware_version": Def(C.uint16, None, IR(1704)),
    #
    # Input Registers 1705–1758 — Per-AIO energy (today; same in both variants)
    #
    "e_aio1_charge_today": Def(C.deci, None, IR(1705)),
    "e_aio2_charge_today": Def(C.deci, None, IR(1708)),
    "e_aio3_charge_today": Def(C.deci, None, IR(1711)),
    "e_aio1_discharge_today": Def(C.deci, None, IR(1750)),
    "e_aio2_discharge_today": Def(C.deci, None, IR(1753)),
    "e_aio3_discharge_today": Def(C.deci, None, IR(1756)),
    #
    # Input Registers 1795–1803 — Battery / AIO SOC
    #
    "e_battery_charge_today": Def(C.deci, None, IR(1795)),
    "e_battery_discharge_today": Def(C.deci, None, IR(1798)),
    "aio1_soc": Def(C.uint16, None, IR(1801), min=0, max=100),
    "aio2_soc": Def(C.uint16, None, IR(1802), min=0, max=100),
    "aio3_soc": Def(C.uint16, None, IR(1803), min=0, max=100),
    "p_aio1_inverter": Def(C.int16, None, IR(1816)),
    "p_aio2_inverter": Def(C.int16, None, IR(1817)),
    "p_aio3_inverter": Def(C.int16, None, IR(1818)),
}

# Energy totals — high/low register order used by GA000009 and earlier
_GATEWAY_V1_ENERGY_TOTALS = {
    "e_grid_import_total": Def(C.uint32, C.deci, IR(1641), IR(1642)),
    "e_pv_total": Def(C.uint32, C.deci, IR(1644), IR(1645)),
    "e_grid_export_total": Def(C.uint32, C.deci, IR(1647), IR(1648)),
    "e_aio_charge_total": Def(C.uint32, C.deci, IR(1650), IR(1651)),
    "e_aio_discharge_total": Def(C.uint32, C.deci, IR(1653), IR(1654)),
    "e_load_total": Def(C.uint32, C.deci, IR(1656), IR(1657)),
    "e_aio1_charge_total": Def(C.uint32, C.deci, IR(1706), IR(1707)),
    "e_aio2_charge_total": Def(C.uint32, C.deci, IR(1709), IR(1710)),
    "e_aio3_charge_total": Def(C.uint32, C.deci, IR(1712), IR(1713)),
    "e_aio1_discharge_total": Def(C.uint32, C.deci, IR(1751), IR(1752)),
    "e_aio2_discharge_total": Def(C.uint32, C.deci, IR(1754), IR(1755)),
    "e_aio3_discharge_total": Def(C.uint32, C.deci, IR(1757), IR(1758)),
    "e_battery_charge_total": Def(C.uint32, C.deci, IR(1796), IR(1797)),
    "e_battery_discharge_total": Def(C.uint32, C.deci, IR(1799), IR(1800)),
}

# Energy totals — high/low swapped in GA000010+
_GATEWAY_V2_ENERGY_TOTALS = {
    "e_grid_import_total": Def(C.uint32, C.deci, IR(1642), IR(1641)),
    "e_pv_total": Def(C.uint32, C.deci, IR(1645), IR(1644)),
    "e_grid_export_total": Def(C.uint32, C.deci, IR(1648), IR(1647)),
    "e_aio_charge_total": Def(C.uint32, C.deci, IR(1651), IR(1650)),
    "e_aio_discharge_total": Def(C.uint32, C.deci, IR(1654), IR(1653)),
    "e_load_total": Def(C.uint32, C.deci, IR(1657), IR(1656)),
    "e_aio1_charge_total": Def(C.uint32, C.deci, IR(1707), IR(1706)),
    "e_aio2_charge_total": Def(C.uint32, C.deci, IR(1710), IR(1709)),
    "e_aio3_charge_total": Def(C.uint32, C.deci, IR(1713), IR(1712)),
    "e_aio1_discharge_total": Def(C.uint32, C.deci, IR(1752), IR(1751)),
    "e_aio2_discharge_total": Def(C.uint32, C.deci, IR(1755), IR(1754)),
    "e_aio3_discharge_total": Def(C.uint32, C.deci, IR(1758), IR(1757)),
    "e_battery_charge_total": Def(C.uint32, C.deci, IR(1797), IR(1796)),
    "e_battery_discharge_total": Def(C.uint32, C.deci, IR(1800), IR(1799)),
}

# AIO serial number addresses differ between v1 and v2 firmware
_GATEWAY_V1_SERIALS = {
    "aio1_serial_number": Def(C.string, None, IR(1831), IR(1832), IR(1833), IR(1834), IR(1835)),
    "aio2_serial_number": Def(C.string, None, IR(1838), IR(1839), IR(1840), IR(1841), IR(1842)),
    "aio3_serial_number": Def(C.string, None, IR(1845), IR(1846), IR(1847), IR(1848), IR(1849)),
}

_GATEWAY_V2_SERIALS = {
    "aio1_serial_number": Def(C.string, None, IR(1841), IR(1842), IR(1843), IR(1844), IR(1845)),
    "aio2_serial_number": Def(C.string, None, IR(1848), IR(1849), IR(1850), IR(1851), IR(1852)),
    "aio3_serial_number": Def(C.string, None, IR(1855), IR(1856), IR(1857), IR(1858), IR(1859)),
}


class GatewayRegisterGetter(RegisterGetter):
    """Register getter for Gateway firmware GA000009 and earlier."""

    REGISTER_LUT = dict(_GATEWAY_COMMON_LUT, **_GATEWAY_V1_ENERGY_TOTALS, **_GATEWAY_V1_SERIALS)


class Gateway2RegisterGetter(RegisterGetter):
    """Register getter for Gateway firmware GA000010 and later (swapped uint32 byte order)."""

    REGISTER_LUT = dict(_GATEWAY_COMMON_LUT, **_GATEWAY_V2_ENERGY_TOTALS, **_GATEWAY_V2_SERIALS)


_GatewayBase = create_model(  # type: ignore[call-overload]
    "Gateway",
    __config__=ConfigDict(frozen=True, use_enum_values=True),
    **GatewayRegisterGetter.to_fields(),
)

_Gateway2Base = create_model(  # type: ignore[call-overload]
    "Gateway2",
    __config__=ConfigDict(frozen=True, use_enum_values=True),
    **Gateway2RegisterGetter.to_fields(),
)


class Gateway(_GatewayBase):  # type: ignore[misc,valid-type]
    """GivEnergy Gateway data model (firmware GA000009 and earlier)."""

    @classmethod
    def from_register_cache(cls, register_cache) -> "Gateway":
        """Construct a Gateway from a RegisterCache."""
        return cls.model_validate(GatewayRegisterGetter(register_cache).build())

    def is_valid(self) -> bool:
        """Try to detect if a gateway is present based on its attributes."""
        return self.software_version is not None  # type: ignore[attr-defined]


class Gateway2(_Gateway2Base):  # type: ignore[misc,valid-type]
    """GivEnergy Gateway data model (firmware GA000010 and later)."""

    @classmethod
    def from_register_cache(cls, register_cache) -> "Gateway2":
        """Construct a Gateway2 from a RegisterCache."""
        return cls.model_validate(Gateway2RegisterGetter(register_cache).build())

    def is_valid(self) -> bool:
        """Try to detect if a gateway is present based on its attributes."""
        return self.software_version is not None  # type: ignore[attr-defined]


def select_gateway(register_cache) -> "Gateway | Gateway2":
    """Return the appropriate Gateway variant based on firmware version.

    Reads IR(1603) — the last register of the version string — and compares its
    raw value against 10. GA000009 and earlier have a raw value < 10; GA000010
    and later have a value >= 10.
    """
    fw_raw = register_cache.get(IR(1603))
    if fw_raw is not None and fw_raw >= 10:
        return Gateway2.from_register_cache(register_cache)
    return Gateway.from_register_cache(register_cache)
