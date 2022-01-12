"""Data model."""
from pydantic import BaseModel

from givenergy_modbus.model.register_getter import RegisterGetter


class GivEnergyBaseModel(BaseModel):
    """Structured format for all other attributes."""

    class Config:  # noqa: D106
        orm_mode = True
        getter_dict = RegisterGetter
        allow_mutation = False
