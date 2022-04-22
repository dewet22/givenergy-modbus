from typing import Dict
from unittest.mock import MagicMock as Mock
from unittest.mock import NonCallableMock, call

import pytest

from givenergy_modbus.decoder import ClientDecoder, Decoder, ServerDecoder


class TestDecoder(Decoder):
    """Dummy factory implementation for testing factory correctness."""

    __test__ = False  # squelch PytestCollectionWarning
    _pdu5 = NonCallableMock(name='pdu5', **{'method.decode': None})  # type: ignore
    _pdu9 = NonCallableMock(name='pdu9', **{'method.decode': None})  # type: ignore
    _pdu5_class = Mock(inner_function_code=5, return_value=_pdu5)
    _pdu9_class = Mock(inner_function_code=9, return_value=_pdu9)
    _function_table = [
        _pdu5_class,
        _pdu9_class,
    ]
    _lookup: Dict[int, Mock]  # type: ignore


@pytest.fixture
def mocked_decoder():
    """Generate a safely-mocked decoder consistently."""
    yield TestDecoder()
    TestDecoder._pdu5.reset_mock()
    TestDecoder._pdu9.reset_mock()
    TestDecoder._function_table[0].reset_mock()
    TestDecoder._function_table[1].reset_mock()


def test_lookup_pdu_class(mocked_decoder):
    """Ensure the class lookup can translate function codes to handler classes."""
    assert set(mocked_decoder._lookup.keys()) == {5, 9}
    assert mocked_decoder.lookup_pdu_class(3) is None
    assert mocked_decoder.lookup_pdu_class(9) is TestDecoder._pdu9_class


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


def test_decode(mocked_decoder):
    """Ensure the decoder works for claimed function codes, and not for unclaimed ones."""
    assert mocked_decoder.decode(0x02, _msg(b'\x05')) is not None
    assert mocked_decoder.decode(0x02, _msg(b'\x09')) is not None
    with pytest.raises(ValueError) as e:
        mocked_decoder.decode(0x02, _msg(b'\x07'))
    assert e.value.args[0] == 'No decoder for inner function code 7'


def test_decode_wiring(mocked_decoder):
    """Ensure the dynamic coding of the Decoder factory is intact."""
    # patch the decoder to bypass the lookup function
    mocked_decoder.lookup_pdu_class = Mock(return_value=mocked_decoder._pdu5_class)

    # ensure the decoder returns the actual instance
    ret = mocked_decoder.decode(0x02, _msg(b'\x05'))

    # verify wiring
    assert ret is mocked_decoder._pdu5
    mocked_decoder.lookup_pdu_class.assert_called_once_with(5)
    assert mocked_decoder._pdu5.mock_calls == [call.decode(_msg(b'\x05'))]
    assert mocked_decoder._lookup[5].call_args_list == [call(error=False)]  # _pdu5_class constructor
    assert ret == mocked_decoder._pdu5


IMPLEMENTED_REQUEST_FUNCTIONS = {3, 4, 6}
IMPLEMENTED_RESPONSE_FUNCTIONS = {0, 3, 4, 6}


def test_client_decoder():
    """Ensure ClientDecoder can produce Response decoders for all known/implemented functions."""
    decoder = ClientDecoder()
    assert set(decoder._lookup.keys()) == IMPLEMENTED_RESPONSE_FUNCTIONS
    for fn_id in range(254):
        if fn_id & 0x7F in IMPLEMENTED_RESPONSE_FUNCTIONS:
            fn = decoder.lookup_pdu_class(fn_id)
            assert fn is not None
            assert callable(fn.decode)

            # mirrors Decoder.decode()
            pdu = fn(error=bool(fn_id & 0x80))

            if fn_id >= 0x80:
                assert pdu.error
                fn_id &= 0x7F

            if fn_id != 0:
                with pytest.raises(ValueError, match=f'Expected inner_function_code 0x{fn_id:02x}, found 0x30 instead'):
                    assert pdu.decode(b"10101010101010101010101010101010101010")
        else:
            assert decoder.lookup_pdu_class(fn_id) is None, f'fn_id={fn_id} should not return anything'


def test_server_decoder():
    """Ensure ServerDecoder can produce Request decoders for all known/implemented functions."""
    decoder = ServerDecoder()
    assert set(decoder._lookup.keys()) == IMPLEMENTED_REQUEST_FUNCTIONS
    for fn_id in range(254):
        if fn_id & 0x7F in IMPLEMENTED_REQUEST_FUNCTIONS:
            fn = decoder.lookup_pdu_class(fn_id)
            assert fn is not None, f'fn_id={fn_id} should return a class'
            assert callable(fn.decode)

            # mirrors Decoder.decode()
            pdu = fn(error=bool(fn_id & 0x80))

            if fn_id >= 0x80:
                assert pdu.error
                fn_id &= 0x7F

            with pytest.raises(ValueError, match=f"Expected inner_function_code 0x{fn_id:02x}, found 0x30 instead"):
                pdu.decode(b"10101010101010101010101010101010101010")
        else:
            assert decoder.lookup_pdu_class(fn_id) is None, f'fn_id={fn_id} should not return anything'
