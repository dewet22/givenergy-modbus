from __future__ import annotations

from givenergy_modbus.pdu import BasePDU


class ExceptionBase(Exception):
    """Base exception."""


class InvalidPduState(ExceptionBase):
    """Thrown during PDU self-validation."""

    def __init__(self, message: str, pdu: BasePDU = None, quirk: bool = False) -> None:
        self.message = message
        self.pdu = pdu
        self.quirk = quirk
        super().__init__(self.message)


class InvalidFrame(ExceptionBase):
    """Thrown during framing when a message cannot be extracted from a frame buffer."""
