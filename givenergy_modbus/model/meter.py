"""GivEnergy meter data model."""

from enum import IntEnum


class MeterStatus(IntEnum):
    """External meter online status."""

    DISABLED = 0
    ONLINE = 1
    OFFLINE = 2

    @classmethod
    def _missing_(cls, value):
        return cls.DISABLED
