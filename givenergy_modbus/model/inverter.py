from enum import Enum

from pydantic import BaseModel


class Model(Enum):
    """Inverter models, as determined from their serial number prefix."""

    AC = "CE"
    GEN2 = "ED"
    HYBRID = "SA"


class Inverter(BaseModel):
    """Models an inverter device."""

    serial_number: str
    model: Model
    _registers: dict[str, list[int]]  # raw register values cache

    # def update_registers(self, ):
