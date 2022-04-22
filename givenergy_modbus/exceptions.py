from __future__ import annotations

from givenergy_modbus.pdu import BasePDU


class InvalidPduState(Exception):
    def __init__(self, pdu: BasePDU, message: str, quirk: bool) -> None:
        self.pdu = pdu
        self.message = message
        self.quirk = quirk
        super().__init__(self.message)


class InvalidFrame(Exception):
    pass
