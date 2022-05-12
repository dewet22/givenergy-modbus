from __future__ import annotations


class ExceptionBase(Exception):
    """Base exception."""

    message: str
    quirk: bool

    def __init__(self, message: str, quirk: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.quirk = quirk
