from datetime import datetime, time

from .modbus import GivEnergyModbusTcpClient
from .model.inverter import Inverter
from .model.register_banks import HoldingRegister


class GivEnergyClient:
    """Client for end users to conveniently access GivEnergy inverters."""

    inverter: Inverter

    def __init__(self, host: str, port: int = 8899, batteries=(1,)):
        """Constructor."""
        self.host = host
        self.port = port
        self.batteries = batteries
        self.modbus_client = GivEnergyModbusTcpClient(host=self.host, port=self.port)

    def __repr__(self):
        """Return a useful representation."""
        return f"GivEnergyClient({self.host}:{self.port}))"

    def refresh(self):
        """Reload all data from the inverter."""
        self.inverter = Inverter(
            holding_registers=self.modbus_client.read_all_holding_registers(),
            input_registers=self.modbus_client.read_all_input_registers(),
        )

    def set_winter_mode(self, mode: bool):
        """Set winter mode."""
        self.modbus_client.write_holding_register(HoldingRegister.WINTER_MODE, int(mode))

    def set_battery_power_mode(self, mode: int):
        """Set the battery power mode."""
        # TODO what are valid modes?
        self.modbus_client.write_holding_register(HoldingRegister.BATTERY_POWER_MODE, mode)

    def set_charge_slot_1(self, start: time, end: time):
        """Set first charge slot times."""
        self.modbus_client.write_holding_register(HoldingRegister.CHARGE_SLOT_1_START, int(start.strftime('%H%M')))
        self.modbus_client.write_holding_register(HoldingRegister.CHARGE_SLOT_1_END, int(end.strftime('%H%M')))

    def set_charge_slot_2(self, start: time, end: time):
        """Set second charge slot times."""
        self.modbus_client.write_holding_register(HoldingRegister.CHARGE_SLOT_2_START, int(start.strftime('%H%M')))
        self.modbus_client.write_holding_register(HoldingRegister.CHARGE_SLOT_2_END, int(end.strftime('%H%M')))

    def set_discharge_slot_1(self, start: time, end: time):
        """Set first discharge slot times."""
        self.modbus_client.write_holding_register(HoldingRegister.DISCHARGE_SLOT_1_START, int(start.strftime('%H%M')))
        self.modbus_client.write_holding_register(HoldingRegister.DISCHARGE_SLOT_1_END, int(end.strftime('%H%M')))

    def set_discharge_slot_2(self, start: time, end: time):
        """Set second discharge slot times."""
        self.modbus_client.write_holding_register(HoldingRegister.DISCHARGE_SLOT_2_START, int(start.strftime('%H%M')))
        self.modbus_client.write_holding_register(HoldingRegister.DISCHARGE_SLOT_2_END, int(end.strftime('%H%M')))

    def set_system_time(self, dt: datetime):
        """Set the system time of the inverter."""
        self.modbus_client.write_holding_register(HoldingRegister.SYSTEM_TIME_YEAR, dt.year)
        self.modbus_client.write_holding_register(HoldingRegister.SYSTEM_TIME_MONTH, dt.month)
        self.modbus_client.write_holding_register(HoldingRegister.SYSTEM_TIME_DAY, dt.day)
        self.modbus_client.write_holding_register(HoldingRegister.SYSTEM_TIME_HOUR, dt.hour)
        self.modbus_client.write_holding_register(HoldingRegister.SYSTEM_TIME_MINUTE, dt.minute)
        self.modbus_client.write_holding_register(HoldingRegister.SYSTEM_TIME_SECOND, dt.second)

    def set_discharge_enable(self, mode: bool):
        """Set the battery to discharge."""
        self.modbus_client.write_holding_register(HoldingRegister.DISCHARGE_ENABLE, int(mode))

    def set_battery_smart_charge(self, mode: bool):
        """Set the smart charge mode to manage the battery."""
        self.modbus_client.write_holding_register(HoldingRegister.BATTERY_SMART_CHARGE, int(mode))

    def set_shallow_charge(self, val: int):
        """Set the minimum level of charge to keep."""
        # TODO what are valid values? 4-100?
        self.modbus_client.write_holding_register(HoldingRegister.SHALLOW_CHARGE, val)

    def set_battery_charge_limit(self, val: int):
        """Set the battery charge limit."""
        # TODO what are valid values?
        self.modbus_client.write_holding_register(HoldingRegister.BATTERY_CHARGE_LIMIT, val)

    def set_battery_discharge_limit(self, val: int):
        """Set the battery discharge limit."""
        # TODO what are valid values?
        self.modbus_client.write_holding_register(HoldingRegister.BATTERY_DISCHARGE_LIMIT, val)

    def set_battery_power_reserve(self, val: int):
        """Set the battery power reserve to maintain."""
        # TODO what are valid values?
        self.modbus_client.write_holding_register(HoldingRegister.BATTERY_POWER_RESERVE, val)

    def set_battery_target_soc(self, val: int):
        """Set the target SOC when the battery charges."""
        # TODO what are valid values?
        self.modbus_client.write_holding_register(HoldingRegister.BATTERY_TARGET_SOC, val)
