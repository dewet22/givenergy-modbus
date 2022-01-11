from pydantic import BaseModel, Field

from .register_getter import RegisterGetter


class Battery(BaseModel):
    """Structured format for all inverter attributes."""

    class Config:  # noqa: D106
        orm_mode = True
        getter_dict = RegisterGetter
        allow_mutation = False

    serial_number: str = Field(alias='battery_serial_number')
    v_cell_01: float = Field(alias='v_battery_cell_01')
    v_cell_02: float = Field(alias='v_battery_cell_02')
    v_cell_03: float = Field(alias='v_battery_cell_03')
    v_cell_04: float = Field(alias='v_battery_cell_04')
    v_cell_05: float = Field(alias='v_battery_cell_05')
    v_cell_06: float = Field(alias='v_battery_cell_06')
    v_cell_07: float = Field(alias='v_battery_cell_07')
    v_cell_08: float = Field(alias='v_battery_cell_08')
    v_cell_09: float = Field(alias='v_battery_cell_09')
    v_cell_10: float = Field(alias='v_battery_cell_10')
    v_cell_11: float = Field(alias='v_battery_cell_11')
    v_cell_12: float = Field(alias='v_battery_cell_12')
    v_cell_13: float = Field(alias='v_battery_cell_13')
    v_cell_14: float = Field(alias='v_battery_cell_14')
    v_cell_15: float = Field(alias='v_battery_cell_15')
    v_cell_16: float = Field(alias='v_battery_cell_16')
    temp_cell_block_1: float = Field(alias='temp_battery_block_1')
    temp_cell_block_2: float = Field(alias='temp_battery_block_2')
    temp_cell_block_3: float = Field(alias='temp_battery_block_3')
    temp_cell_block_4: float = Field(alias='temp_battery_block_4')
    v_cells_sum: float = Field(alias='v_battery_cells_sum')
    temp_bms_mos: float
    v_out: float = Field(alias='v_battery_out')
    full_capacity: float = Field(alias='battery_full_capacity')
    design_capacity: float = Field(alias='battery_design_capacity')
    remaining_capacity: float = Field(alias='battery_remaining_capacity')
    status_1_2: tuple[int, int] = Field(alias='battery_status_1_2')
    status_3_4: tuple[int, int] = Field(alias='battery_status_3_4')
    status_5_6: tuple[int, int] = Field(alias='battery_status_5_6')
    status_7: tuple[int, int] = Field(alias='battery_status_7')
    warning_1_2: tuple[int, int] = Field(alias='battery_warning_1_2')
    num_cycles: int = Field(alias='battery_num_cycles')
    num_cells: int = Field(alias='battery_num_cells')
    bms_firmware_version: int
    soc: int = Field(alias='battery_soc')
    design_capacity_2: float = Field(alias='battery_design_capacity_2')
    temp_max_now: float = Field(alias='temp_battery_max_now')
    temp_min_now: float = Field(alias='temp_battery_min_now')
    usb_inserted: bool
