"""Helper utilities for the client."""

from __future__ import annotations

import asyncio
import datetime
import logging
from asyncio import Future
from dataclasses import dataclass, field

from givenergy_modbus.pdu import BasePDU

_logger = logging.getLogger(__name__)


@dataclass
class Message:
    """Encapsulation for messages in a queue, containing data for debugging, expiry, retries, and prioritisation."""

    pdu: BasePDU
    provenance: Message | None = None
    raw_frame: bytes = b''
    created: datetime.datetime = field(default_factory=datetime.datetime.now)
    transceived: datetime.datetime | None = None
    ttl: float = 4.5
    retries_remaining: int = 0
    future: Future[Message] = field(default_factory=lambda: asyncio.get_event_loop().create_future())

    def __str__(self) -> str:
        return (
            f'{self.__class__.__name__}({self.pdu} '
            f'provenance={"None" if not self.provenance else f"Message({self.provenance.pdu} ...)"} '
            f'raw_frame={self.raw_frame.hex(bytes_per_sep=2)} '
            f'created={self.created.isoformat()} '
            f'transceived={self.transceived.isoformat() if self.transceived else "None"} '
            f'ttl={self.ttl} '
            f'retries_remaining={self.retries_remaining} '
            f'future={self.future._state})'
        )

    def __repr__(self) -> str:
        return self.__str__()

    @property
    def age(self) -> datetime.timedelta:
        """Calculate time elapsed since message creation."""
        return datetime.datetime.now() - self.created

    @property
    def network_roundtrip(self) -> datetime.timedelta:
        """Calculate time elapsed between transmitting request and receiving a response."""
        if not self.transceived or not self.provenance or not self.provenance.transceived:
            return datetime.timedelta.min
        return self.transceived - self.provenance.transceived

    @property
    def expiry(self) -> datetime.datetime:
        """Calculate expiry time."""
        res = self.created + datetime.timedelta(seconds=self.ttl)
        _logger.debug(
            f'Expiry: created={self.created.isoformat()} delta={datetime.timedelta(seconds=self.ttl)} '
            f'res={res.isoformat()}'
        )
        return res

    @property
    def expired(self) -> bool:
        """Returns whether an item has passed its expiry time."""
        now = datetime.datetime.now()
        res = now > self.expiry
        _logger.debug(f'Expired: now={now.isoformat()} expiry={self.expiry} res={res}')
        return res


@dataclass
class Timeslot:
    """Dataclass to represent a time slot, with a start and end time."""

    start: datetime.time
    end: datetime.time

    @classmethod
    def from_components(cls, start_hour: int, start_minute: int, end_hour: int, end_minute: int):
        """Shorthand for the individual datetime.time constructors."""
        return cls(datetime.time(start_hour, start_minute), datetime.time(end_hour, end_minute))

    @classmethod
    def from_repr(cls, start: int | str, end: int | str):
        """Converts from human-readable/ASCII representation: '0034' -> 00:34."""
        start = str(start)
        start_hour = int(start[:-2])
        start_minute = int(start[-2:])
        end = str(end)
        end_hour = int(end[:-2])
        end_minute = int(end[-2:])
        return cls(datetime.time(start_hour, start_minute), datetime.time(end_hour, end_minute))
