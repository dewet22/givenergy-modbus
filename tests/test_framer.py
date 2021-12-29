"""Tests for GivModbusFramer."""

from unittest.mock import MagicMock

from givenergy_modbus.framer import GivModbusFramer


def test_framer_constructor():
    """Test constructor."""
    client_decoder = MagicMock()
    framer = GivModbusFramer(client_decoder)
    assert framer.client is None
    assert framer._buffer == b""
    assert framer.decoder == client_decoder
    assert framer._header == {"pid": 0, "tid": 0, "len": 0, "uid": 0, "fid": 0}
    assert framer._hsize == 0x08
    client_decoder.assert_not_called()
