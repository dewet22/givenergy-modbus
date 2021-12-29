from unittest.mock import MagicMock as Mock
from unittest.mock import NonCallableMock, call

import pytest

from givenergy_modbus.decoder import GivEnergyDecoder


class TestDecoder(GivEnergyDecoder):
    """Dummy factory implementation for testing factory correctness."""

    __test__ = False  # squelch PytestCollectionWarning
    _pdu5 = NonCallableMock(name='pdu5', **{'method.decode': None})
    _pdu9 = NonCallableMock(name='pdu9', **{'method.decode': None})
    _function_table = [
        Mock(function_code=5, return_value=_pdu5),
        Mock(function_code=9, return_value=_pdu9),
    ]
    _lookup: dict[int, Mock]


@pytest.fixture
def decoder():
    """Generate a safely-mocked decoder consistently."""
    yield TestDecoder()
    TestDecoder._pdu5.reset_mock()
    TestDecoder._pdu9.reset_mock()
    TestDecoder._function_table[0].reset_mock()
    TestDecoder._function_table[1].reset_mock()


def test_lookup_pdu_class(decoder):
    """Ensure the class lookup can translate function codes to handler classes."""
    assert set(decoder._lookup.keys()) == {5, 9}
    assert decoder.lookupPduClass(3) is None
    assert decoder.lookupPduClass(9) is TestDecoder._pdu9


def _msg(fn: bytes) -> bytes:
    return (b'\xaa' * 19) + bytes(fn) + (b'\xcc' * 10)


def test_msg():
    """Ensure our little test helper generates valid-like byte streams."""
    assert _msg(b'\x22') == (
        b'\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa'
        b'\x22\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc'
    )
    assert _msg(b'\xee') == (
        b'\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa'
        b'\xee\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc'
    )


def test_decode(decoder):
    """Ensure the decoder works for claimed function codes, and not for unclaimed ones."""
    assert decoder.decode(_msg(b'\x05')) is not None
    assert decoder.decode(_msg(b'\x07')) is None
    assert decoder.decode(_msg(b'\x09')) is not None


def test_decode_wiring(decoder):
    """Ensure the dynamic coding of the Decoder factory is intact."""
    # patch the decoder to bypass the lookup function
    decoder.lookupPduClass = Mock(return_value=decoder._pdu5)

    # ensure the decoder returns the actual instance
    ret = decoder.decode(_msg(b'\x05'))

    # verify wiring
    assert ret is decoder._pdu5
    decoder.lookupPduClass.assert_called_once_with(5)
    assert decoder._pdu5.mock_calls == [call.decode(_msg(b'\x05'))]
    decoder._lookup[5].assert_not_called()  # lookup patched out
    assert ret == decoder._pdu5
