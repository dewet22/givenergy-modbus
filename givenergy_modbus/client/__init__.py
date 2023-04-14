"""Helper utilities for the client."""
import logging
from dataclasses import dataclass
from datetime import time
from typing import Union

_logger = logging.getLogger(__name__)


@dataclass
class TimeSlot:
    """Dataclass to represent a time slot, with a start and end time."""

    start: time
    end: time

    @classmethod
    def from_components(cls, start_hour: int, start_minute: int, end_hour: int, end_minute: int):
        """Shorthand for the individual datetime.time constructors."""
        return cls(time(start_hour, start_minute), time(end_hour, end_minute))

    @classmethod
    def from_repr(cls, start: Union[int, str], end: Union[int, str]):
        """Converts from human-readable/ASCII representation: '0034' -> 00:34."""
        if isinstance(start, int):
            start = f'{start:04d}'
        start_hour = int(start[:-2])
        start_minute = int(start[-2:])
        if isinstance(end, int):
            end = f'{end:04d}'
        end_hour = int(end[:-2])
        end_minute = int(end[-2:])
        return cls(time(start_hour, start_minute), time(end_hour, end_minute))
