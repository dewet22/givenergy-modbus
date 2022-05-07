from __future__ import annotations


class ExceptionBase(Exception):
    """Base exception."""

    message: str
    quirk: bool

    def __init__(self, message: str, quirk: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.quirk = quirk


class InvalidPduState(ExceptionBase):
    """Thrown during PDU self-validation."""

    def __init__(self, message: str, pdu=None, quirk: bool = False) -> None:
        super().__init__(message=message, quirk=quirk)
        self.pdu = pdu


class InvalidFrame(ExceptionBase):
    """Thrown during framing when a message cannot be extracted from a frame buffer."""

    frame: bytes

    def __init__(self, message: str, frame: bytes) -> None:
        super().__init__(message=message)
        self.frame = frame
