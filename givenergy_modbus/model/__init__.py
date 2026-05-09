"""Data model."""

from datetime import time
from enum import IntEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from givenergy_modbus.model.register_cache import RegisterCache


class GivEnergyBaseModel(BaseModel):
    """Structured format for all other attributes."""

    model_config = ConfigDict(frozen=True, use_enum_values=True)

    @classmethod
    def from_registers(cls, register_cache: "RegisterCache"):
        """Constructor parsing registers directly."""
        raise NotImplementedError()


class DefaultUnknownIntEnum(IntEnum):
    """Enum that returns unknown instead of blowing up."""

    @classmethod
    def _missing_(cls, value):
        return cls.UNKNOWN  # type: ignore[attr-defined] # must be defined in subclasses because of Enum limits


class TimeSlot:
    """Represents a time slot with a start and end time."""

    def __init__(self, start: time, end: time) -> None:
        self.start = start
        self.end = end

    def __eq__(self, other: object) -> bool:
        return isinstance(other, TimeSlot) and self.start == other.start and self.end == other.end

    def __repr__(self) -> str:
        return f"TimeSlot(start={self.start!r}, end={self.end!r})"

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        """Keep TimeSlot instances as-is in model_dump(mode='python')."""
        from pydantic_core import core_schema

        def _serialize(v, info):
            if hasattr(info, "mode") and info.mode != "python":
                return {"start": v.start, "end": v.end}
            return v

        return core_schema.no_info_plain_validator_function(
            lambda v: v if isinstance(v, cls) else cls(**v),
            serialization=core_schema.plain_serializer_function_ser_schema(
                _serialize,
                info_arg=True,
            ),
        )

    @classmethod
    def from_components(cls, start_hour: int, start_minute: int, end_hour: int, end_minute: int):
        """Shorthand for the individual datetime.time constructors."""
        return cls(time(start_hour, start_minute), time(end_hour, end_minute))

    @classmethod
    def from_repr(cls, start: int | str, end: int | str):
        """Converts from human-readable/ASCII representation: '0034' -> 00:34."""
        if isinstance(start, int):
            start = f"{start:04d}"
        start_hour = int(start[:-2])
        start_minute = int(start[-2:])
        if isinstance(end, int):
            end = f"{end:04d}"
        end_hour = int(end[:-2])
        end_minute = int(end[-2:])
        return cls(time(start_hour, start_minute), time(end_hour, end_minute))


# from givenergy_modbus.model import battery, inverter, plant, register_cache
#
# Plant = plant.Plant
# Inverter = inverter.Inverter
# Battery = battery.Battery
# RegisterCache = register_cache.RegisterCache
