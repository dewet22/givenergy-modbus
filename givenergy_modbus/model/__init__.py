"""Data model."""
from enum import IntEnum

from pydantic import BaseModel

from givenergy_modbus.model.register_cache import RegisterCache


class GivEnergyBaseModel(BaseModel):
    """Structured format for all other attributes."""

    class Config:  # noqa: D106
        allow_mutation = False
        frozen = True
        use_enum_values = True

    @classmethod
    def from_registers(cls, register_cache: RegisterCache):
        """Constructor parsing registers directly."""
        raise NotImplementedError()


class DefaultUnknownIntEnum(IntEnum):
    """Enum that returns unknown instead of blowing up."""

    @classmethod
    def _missing_(cls, value):
        return cls.UNKNOWN


# from givenergy_modbus.model import battery, inverter, plant, register_cache
#
# Plant = plant.Plant
# Inverter = inverter.Inverter
# Battery = battery.Battery
# RegisterCache = register_cache.RegisterCache
