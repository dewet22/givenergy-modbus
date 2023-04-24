import struct

import pytest

from givenergy_modbus.codec import PayloadDecoder, PayloadEncoder


def test_decoder_uints():
    d = PayloadDecoder(b'\x01\x02\x03\x04')
    assert d.decode_8bit_uint() == 0x01
    assert d.decode_8bit_uint() == 0x02
    assert d.decode_8bit_uint() == 0x03
    assert d.decode_8bit_uint() == 0x04
    with pytest.raises(struct.error, match='unpack requires a buffer of 1 bytes'):
        d.decode_8bit_uint()

    d = PayloadDecoder(b'\x01\x02\x03\x04')
    assert d.decode_16bit_uint() == 0x0102
    assert d.decode_16bit_uint() == 0x0304
    with pytest.raises(struct.error, match='unpack requires a buffer of 2 bytes'):
        d.decode_16bit_uint()

    d = PayloadDecoder(b'\x01\x02\x03\x04')
    assert d.decode_32bit_uint() == 0x01020304
    with pytest.raises(struct.error, match='unpack requires a buffer of 4 bytes'):
        d.decode_32bit_uint()

    d = PayloadDecoder(b'\x01\x02\x03\x04\x05\x06\x07\x08')
    assert d.decode_64bit_uint() == 0x0102030405060708
    with pytest.raises(struct.error, match='unpack requires a buffer of 8 bytes'):
        d.decode_64bit_uint()


def test_decoder_strings():
    d = PayloadDecoder(b'abc')
    assert d.decode_string(3) == 'abc'
    with pytest.raises(struct.error, match='unpack requires a buffer of 1 bytes'):
        d.decode_string(1)

    d = PayloadDecoder(b'\x01\x02\x03\x04')
    assert d.decode_16bit_uint() == 0x0102
    assert d.decode_16bit_uint() == 0x0304
    with pytest.raises(struct.error, match='unpack requires a buffer of 2 bytes'):
        d.decode_16bit_uint()

    d = PayloadDecoder(b'\x01\x02\x03\x04')
    assert d.decode_32bit_uint() == 0x01020304
    with pytest.raises(struct.error, match='unpack requires a buffer of 4 bytes'):
        d.decode_32bit_uint()

    d = PayloadDecoder(b'\x01\x02\x03\x04\x05\x06\x07\x08')
    assert d.decode_64bit_uint() == 0x0102030405060708
    with pytest.raises(struct.error, match='unpack requires a buffer of 8 bytes'):
        d.decode_64bit_uint()


def test_encoder_uints():
    e = PayloadEncoder()
    e.add_8bit_uint(0x1)
    e.add_8bit_uint(0x2)
    e.add_8bit_uint(0x3)
    e.add_8bit_uint(0x4)
    assert e.payload == b'\x01\x02\x03\x04'
    assert e.crc == 11169

    e.reset()
    e.add_16bit_uint(0x1)
    e.add_16bit_uint(0x2)
    e.add_16bit_uint(0x3)
    e.add_16bit_uint(0x4)
    assert e.payload == b'\x00\x01\x00\x02\x00\x03\x00\x04'
    assert e.crc == 51416

    e.reset()
    e.add_32bit_uint(0x1)
    e.add_32bit_uint(0x2)
    assert e.payload == b'\x00\x00\x00\x01\x00\x00\x00\x02'
    assert e.crc == 2812

    e.reset()
    e.add_64bit_uint(0x1)
    e.add_64bit_uint(0x2)
    assert e.payload == b'\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x02'
    assert e.crc == 41266


def test_encoder_strings():
    e = PayloadEncoder()
    e.add_string('abc', 3)
    e.add_string('AB123G4567', 10)
    assert e.payload == b'abcAB123G4567'
    assert e.crc == 58715

    e = PayloadEncoder()
    e.add_string('abc', 5)
    assert e.payload == b'**abc'
    assert e.crc == 18701

    e = PayloadEncoder()
    e.add_string('abc', 1)
    assert e.payload == b'c'
    assert e.crc == 27135
