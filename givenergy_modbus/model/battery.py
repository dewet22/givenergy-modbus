from typing import Tuple

from givenergy_modbus.model import GivEnergyBaseModel


class Battery(GivEnergyBaseModel):
    """Structured format for BMS attributes."""

    battery_serial_number: str
    v_cell_01: float
    v_cell_02: float
    v_cell_03: float
    v_cell_04: float
    v_cell_05: float
    v_cell_06: float
    v_cell_07: float
    v_cell_08: float
    v_cell_09: float
    v_cell_10: float
    v_cell_11: float
    v_cell_12: float
    v_cell_13: float
    v_cell_14: float
    v_cell_15: float
    v_cell_16: float
    temp_cells_1: float
    temp_cells_2: float
    temp_cells_3: float
    temp_cells_4: float
    v_cells_sum: float
    temp_bms_mos: float
    v_battery_out: float
    full_capacity: float
    design_capacity: float
    remaining_capacity: float
    e_charge_total: float
    e_discharge_total: float
    status_1_2: Tuple[int, int]
    status_3_4: Tuple[int, int]
    status_5_6: Tuple[int, int]
    status_7: Tuple[int, int]
    warning_1_2: Tuple[int, int]
    num_cycles: int
    num_cells: int
    bms_firmware_version: int
    soc: int
    design_capacity_2: float
    temp_max: float
    temp_min: float
    usb_inserted: int

    def is_valid(self) -> bool:
        return self.battery_serial_number and self.battery_serial_number not in (
            '',
            '\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00',
        )
