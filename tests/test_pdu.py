import struct
from typing import Any

import pytest

from givenergy_modbus.codec import PayloadDecoder
from givenergy_modbus.exceptions import ExceptionBase, InvalidFrame, InvalidPduState
from givenergy_modbus.pdu import (
    BasePDU,
    ClientIncomingMessage,
    ClientOutgoingMessage,
    HeartbeatMessage,
    HeartbeatRequest,
    HeartbeatResponse,
    NullResponse,
    ReadHoldingRegistersRequest,
    ReadHoldingRegistersResponse,
    ReadInputRegistersRequest,
    ReadInputRegistersResponse,
    ReadMeterProductRegisters,
    ReadMeterProductRegistersRequest,
    ReadMeterProductRegistersResponse,
    ReadRegistersMessage,
    ReadRegistersRequest,
    TransparentMessage,
    TransparentRequest,
    TransparentResponse,
    WriteHoldingRegisterRequest,
    WriteHoldingRegisterResponse,
)
from tests.conftest import ALL_MESSAGES, PduTestCaseSig


def test_str():
    """Ensure human-friendly string representations."""
    # ABCs before main function definitions
    assert "/BasePDU(" not in str(BasePDU())
    assert "/Request(" not in str(ClientIncomingMessage())
    assert "/Response(" not in str(ClientOutgoingMessage())
    assert str(BasePDU()).startswith("<givenergy_modbus.pdu.base.BasePDU object at ")
    assert str(ClientIncomingMessage()).startswith("<givenergy_modbus.pdu.base.ClientIncomingMessage object at ")
    assert str(ClientIncomingMessage(foo=1)).startswith("<givenergy_modbus.pdu.base.ClientIncomingMessage object at ")

    # __str__() gets defined at the main function ABC
    assert str(HeartbeatMessage(foo=3, bar=6)) == (
        "1/HeartbeatMessage(data_adapter_serial_number='AB1234G567' data_adapter_type=0)"
    )
    assert str(HeartbeatMessage(data_adapter_serial_number="xxx", data_adapter_type=33)) == (
        "1/HeartbeatMessage(data_adapter_serial_number='xxx' data_adapter_type=33)"
    )
    assert str(HeartbeatRequest(foo=3, bar=6)) == (
        "1/HeartbeatRequest(data_adapter_serial_number='AB1234G567' data_adapter_type=0)"
    )
    assert str(HeartbeatResponse(data_adapter_serial_number="xxx", data_adapter_type=33)) == (
        "1/HeartbeatResponse(data_adapter_serial_number='xxx' data_adapter_type=33)"
    )

    assert str(TransparentMessage(foo=3, bar=6)) == "2:_/TransparentMessage(device_address=0x32)"
    assert str(TransparentRequest(foo=3, bar=6)) == "2:_/TransparentRequest(device_address=0x32)"
    assert str(TransparentRequest(inner_function_code=44)) == "2:_/TransparentRequest(device_address=0x32)"
    assert str(TransparentResponse(foo=3, bar=6)) == "2:_/TransparentResponse(device_address=0x32)"
    assert str(TransparentResponse(inner_function_code=44)) == "2:_/TransparentResponse(device_address=0x32)"

    assert str(ReadRegistersMessage()) == (
        "2:_/ReadRegistersMessage(device_address=0x32 base_register=0 register_count=0)"
    )
    assert str(ReadRegistersMessage(foo=1)) == (
        "2:_/ReadRegistersMessage(device_address=0x32 base_register=0 register_count=0)"
    )
    assert str(ReadRegistersMessage(base_register=50)) == (
        "2:_/ReadRegistersMessage(device_address=0x32 base_register=50 register_count=0)"
    )

    assert str(ReadRegistersRequest(base_register=3, register_count=6)) == (
        "2:_/ReadRegistersRequest(device_address=0x32 base_register=3 register_count=6)"
    )
    assert str(NullResponse(foo=1)) == "2:0/NullResponse(device_address=0x32 nulls=[0]*62)"

    assert str(ReadHoldingRegistersRequest(foo=1)) == (
        "2:3/ReadHoldingRegistersRequest(device_address=0x32 base_register=0 register_count=0)"
    )

    with pytest.raises(TypeError, match="missing 2 required positional arguments: 'register' and 'value'"):
        WriteHoldingRegisterRequest(foo=1)
    with pytest.raises(TypeError, match="missing 2 required positional arguments: 'register' and 'value'"):
        WriteHoldingRegisterResponse(foo=1)
    assert str(WriteHoldingRegisterResponse(register=18, value=7)) == (
        "2:6/WriteHoldingRegisterResponse(18 -> 7/0x0007)"
    )
    assert str(WriteHoldingRegisterResponse(error=True, register=7, value=6)) == (
        "2:6/WriteHoldingRegisterResponse(ERROR 7 -> 6/0x0006)"
    )
    assert str(WriteHoldingRegisterResponse(error=True, inverter_serial_number="SA1234G567", register=18, value=5)) == (
        "2:6/WriteHoldingRegisterResponse(ERROR 18 -> 5/0x0005)"
    )

    assert str(HeartbeatRequest(foo=1)) == (
        "1/HeartbeatRequest(data_adapter_serial_number='AB1234G567' data_adapter_type=0)"
    )
    assert str(HeartbeatResponse(foo=1)) == (
        "1/HeartbeatResponse(data_adapter_serial_number='AB1234G567' data_adapter_type=0)"
    )


@pytest.mark.parametrize(PduTestCaseSig, ALL_MESSAGES)
def test_str_actual_messages(
    str_repr: str,
    pdu_class: type[BasePDU],
    constructor_kwargs: dict[str, Any],
    mbap_header: bytes,
    inner_frame: bytes,
    ex: ExceptionBase | None,
):
    assert str(pdu_class(**constructor_kwargs)) == str_repr


def test_class_equivalence():
    """Confirm some behaviours on subclassing."""
    assert issubclass(ReadHoldingRegistersRequest, ReadRegistersRequest)
    assert issubclass(ReadInputRegistersRequest, ReadRegistersRequest)
    assert not issubclass(ReadHoldingRegistersRequest, ReadInputRegistersRequest)
    assert isinstance(ReadHoldingRegistersRequest(), ReadRegistersRequest)
    assert isinstance(ReadInputRegistersRequest(), ReadRegistersRequest)
    assert not isinstance(ReadInputRegistersRequest(), ReadHoldingRegistersRequest)
    assert ReadInputRegistersRequest is ReadInputRegistersRequest


def test_meter_pdu_classes():
    """ReadMeterProductRegisters* are separate from the battery/input register hierarchy."""
    assert issubclass(ReadMeterProductRegistersRequest, ReadRegistersRequest)
    assert issubclass(ReadMeterProductRegistersResponse, ReadRegistersMessage)
    assert not issubclass(ReadMeterProductRegistersRequest, ReadInputRegistersRequest)
    assert isinstance(ReadMeterProductRegistersRequest(), ReadRegistersRequest)
    assert ReadMeterProductRegisters.transparent_function_code == 0x16
    assert ReadMeterProductRegistersRequest().transparent_function_code == 0x16
    assert ReadMeterProductRegistersResponse().transparent_function_code == 0x16


def test_cannot_change_function_code():
    """Disabuse any use of function_code in PDU constructors."""
    assert not hasattr(ClientIncomingMessage, "function_code")
    assert not hasattr(ClientIncomingMessage, "function_code")
    assert not hasattr(ClientIncomingMessage, "transparent_function_code")
    assert not hasattr(ClientIncomingMessage(), "function_code")
    assert not hasattr(ClientIncomingMessage(), "function_code")
    assert not hasattr(ClientIncomingMessage(), "transparent_function_code")

    assert ReadHoldingRegistersRequest(error=True).transparent_function_code == 3

    assert ReadHoldingRegistersRequest(function_code=12).function_code != 12
    assert ReadHoldingRegistersRequest(main_function_code=12).function_code != 12
    assert ReadHoldingRegistersRequest(transparent_function_code=12).function_code != 12
    assert ReadHoldingRegistersRequest(function_code=12).transparent_function_code != 12
    assert ReadHoldingRegistersRequest(main_function_code=12).transparent_function_code != 12
    assert ReadHoldingRegistersRequest(transparent_function_code=12).transparent_function_code != 12


@pytest.mark.parametrize(PduTestCaseSig, ALL_MESSAGES)
def test_encoding(
    str_repr: str,
    pdu_class: type[BasePDU],
    constructor_kwargs: dict[str, Any],
    mbap_header: bytes,
    inner_frame: bytes,
    ex: ExceptionBase | None,
):
    """Ensure PDU objects can be encoded to the correct wire format."""
    pdu = pdu_class(**constructor_kwargs)
    if ex:
        with pytest.raises(type(ex), match=ex.message):
            pdu.encode()
    else:
        assert pdu.encode().hex() == (mbap_header + inner_frame).hex()


@pytest.mark.parametrize(PduTestCaseSig, ALL_MESSAGES)
def test_decoding(
    str_repr: str,
    pdu_class: type[BasePDU],
    constructor_kwargs: dict[str, Any],
    mbap_header: bytes,
    inner_frame: bytes,
    ex: ExceptionBase | None,
):
    """Ensure we correctly decode Request messages to their unencapsulated PDU."""
    assert mbap_header[-1] == pdu_class.function_code
    frame = mbap_header + inner_frame

    if issubclass(pdu_class, ClientIncomingMessage):
        decoder = ClientIncomingMessage.decode_bytes
    else:
        decoder = ClientOutgoingMessage.decode_bytes

    if ex:
        with pytest.raises(type(ex), match=ex.message):
            decoder(frame)
    else:
        constructor_kwargs["raw_frame"] = mbap_header + inner_frame
        pdu = decoder(frame)
        assert isinstance(pdu, pdu_class)
        assert pdu.__dict__ == constructor_kwargs
        assert str(pdu) == str_repr


@pytest.mark.parametrize(PduTestCaseSig, ALL_MESSAGES)
def test_decoding_wrong_streams(
    str_repr: str,
    pdu_class: type[BasePDU],
    constructor_kwargs: dict[str, Any],
    mbap_header: bytes,
    inner_frame: bytes,
    ex: ExceptionBase | None,
):
    """Ensure we correctly decode Request messages to their unencapsulated PDU."""
    if ex:
        return
    frame = mbap_header + inner_frame

    if issubclass(pdu_class, ClientIncomingMessage):
        decoder = ClientIncomingMessage.decode_bytes
    else:
        decoder = ClientOutgoingMessage.decode_bytes

    with pytest.raises(InvalidFrame, match="Transaction ID 0x[0-9a-f]{4} != 0x5959"):
        decoder(frame[2:])
    with pytest.raises(
        InvalidFrame, match=f"Header length {len(frame) - 6} != remaining frame length {len(frame) - 8}"
    ):
        decoder(frame[:-2])
    with pytest.raises(
        InvalidFrame, match=f"Header length {len(frame) - 6} != remaining frame length {len(frame) - 4}"
    ):
        decoder(frame + b"\x22\x22")
    with pytest.raises(InvalidFrame, match="Transaction ID 0x[0-9a-f]{4} != 0x5959"):
        decoder(frame[-10:])
    with pytest.raises(InvalidFrame, match="Transaction ID 0x[0-9a-f]{4} != 0x5959"):
        decoder(frame[::-1])


def test_writable_registers_equality():
    req = WriteHoldingRegisterRequest(register=35, value=22)
    assert req.register == 35
    assert str(req) == "2:6/WriteHoldingRegisterRequest(35 -> 22/0x0016)"
    assert req == WriteHoldingRegisterRequest(register=35, value=22)
    assert req != WriteHoldingRegisterRequest(register=35, value=32)
    assert req != WriteHoldingRegisterRequest(register=36, value=22)
    assert req != WriteHoldingRegisterResponse(register=35, value=22)

    req = WriteHoldingRegisterResponse(register=35, value=33)
    assert req.register == 35
    assert str(req) == "2:6/WriteHoldingRegisterResponse(35 -> 33/0x0021)"
    assert req != WriteHoldingRegisterRequest(register=35, value=22)

    req = WriteHoldingRegisterResponse(register=36, value=55, error=True)
    assert req.register == 36
    assert str(req) == "2:6/WriteHoldingRegisterResponse(ERROR 36 -> 55/0x0037)"
    assert req != WriteHoldingRegisterRequest(register=36, value=55)
    assert req != WriteHoldingRegisterResponse(register=36, value=55)
    assert req == WriteHoldingRegisterResponse(register=36, value=55, error=True)


def test_read_registers_response_as_dict():
    """Ensure a ReadRegistersResponse can be turned into a dict representation."""
    r = ReadHoldingRegistersResponse(base_register=100, register_count=10, register_values=list(range(10))[::-1])
    assert r.to_dict() == {100: 9, 101: 8, 102: 7, 103: 6, 104: 5, 105: 4, 106: 3, 107: 2, 108: 1, 109: 0}

    r = ReadHoldingRegistersResponse(base_register=1000, register_count=10, register_values=["a"] * 10)
    assert r.to_dict() == {
        1000: "a",
        1001: "a",
        1002: "a",
        1003: "a",
        1004: "a",
        1005: "a",
        1006: "a",
        1007: "a",
        1008: "a",
        1009: "a",
    }


def test_has_same_shape():
    """Ensure we can compare PDUs sensibly."""
    r1 = ReadInputRegistersResponse()
    r2 = ReadInputRegistersResponse()
    assert r1.shape_hash() == r2.shape_hash()
    assert r1.has_same_shape(r2)
    assert r1 != r2
    assert r1.has_same_shape(ReadInputRegistersRequest()) is False
    with pytest.raises(NotImplementedError):
        r1.has_same_shape(object())
    r2 = ReadInputRegistersResponse(device_address=3)
    assert r1.has_same_shape(r2) is False
    r2 = ReadInputRegistersResponse(base_register=1)
    assert r1.has_same_shape(r2) is False

    r1 = ReadInputRegistersResponse(base_register=1, register_count=2, register_values=[33, 45])
    r2 = ReadInputRegistersResponse(base_register=1, register_count=2, register_values=[10, 11])
    assert r1.has_same_shape(r2)
    assert r1 != r2
    r2 = ReadInputRegistersResponse(error=True, base_register=1, register_count=2, register_values=[3])
    assert r1.has_same_shape(r2)
    assert r1 != r2
    r2 = ReadInputRegistersResponse(error=True, register_count=2, register_values=[])
    assert r1.has_same_shape(r2) is False
    assert r1 != r2

    r = WriteHoldingRegisterResponse(register=2, value=0)
    assert r.has_same_shape(WriteHoldingRegisterResponse(register=2, value=0))
    assert r.has_same_shape(WriteHoldingRegisterResponse(register=2, value=10))
    assert r.has_same_shape(WriteHoldingRegisterRequest(register=2, value=0)) is False
    assert r.has_same_shape(ReadInputRegistersResponse(register=2)) is False
    assert r.has_same_shape(ReadInputRegistersRequest(register=2)) is False
    assert r.has_same_shape(WriteHoldingRegisterResponse(register=2, value=0, device_address=3)) is False
    assert r.has_same_shape(WriteHoldingRegisterResponse(register=1, value=0)) is False
    assert r.has_same_shape(WriteHoldingRegisterResponse(register=3, value=10)) is False

    r1 = WriteHoldingRegisterResponse(register=2, value=42)
    r2 = WriteHoldingRegisterResponse(register=2, value=10)
    assert r1.has_same_shape(r2)
    assert r1 != r2


def test_write_holding_register_pdus_are_unhashable():
    # WriteHoldingRegister overrides __eq__, so Python auto-removes __hash__ from this class hierarchy.
    r1 = WriteHoldingRegisterResponse(register=2, value=10)
    r2 = WriteHoldingRegisterResponse(register=2, value=10)
    assert r1 == r2

    with pytest.raises(TypeError, match="unhashable"):
        hash(r1)
    with pytest.raises(TypeError, match="unhashable"):
        {WriteHoldingRegisterResponse(register=2, value=10)}


def test_expected_response():
    req = ReadInputRegistersRequest(base_register=34, register_count=2)
    res = req.expected_response()
    assert isinstance(res, ReadInputRegistersResponse)
    assert res.base_register == req.base_register
    assert res.register_count == req.register_count
    assert res.device_address == req.device_address

    assert res != req
    assert req.has_same_shape(res) is False
    assert req.expected_response().has_same_shape(res)
    assert res.has_same_shape(req) is False


# ── Security fix tests ────────────────────────────────────────────────────────


def test_write_register_value_bounds():
    """ensure_valid_state must reject values outside [0, 0xFFFF]."""
    with pytest.raises(InvalidPduState, match="must be an unsigned 16-bit int"):
        WriteHoldingRegisterResponse(register=20, value=-1).ensure_valid_state()
    with pytest.raises(InvalidPduState, match="must be an unsigned 16-bit int"):
        WriteHoldingRegisterResponse(register=20, value=0x10000).ensure_valid_state()
    # Boundary values must be accepted without raising.
    WriteHoldingRegisterResponse(register=20, value=0).ensure_valid_state()
    WriteHoldingRegisterResponse(register=20, value=0xFFFF).ensure_valid_state()


def test_null_response_preserves_nulls_kwarg():
    """NullResponse must store the supplied 'nulls' list, not silently use a default."""
    custom = [1] + [0] * 61
    assert NullResponse(nulls=custom).nulls == custom
    assert NullResponse().nulls == [0] * 62


def test_read_registers_response_caps_decode_at_60():
    """A crafted register_count > 60 must not exhaust the decoder buffer."""
    # Payload: base_register=0, register_count=100, then exactly 60 values, then check.
    payload = struct.pack(">HH", 0, 100)
    payload += struct.pack(">" + "H" * 60, *range(60))
    payload += struct.pack(">H", 0)  # check
    decoder = PayloadDecoder(payload)
    result = ReadHoldingRegistersResponse.decode_transparent_function(decoder, error=False)
    assert result.register_count == 100
    assert len(result.register_values) == 60
    assert result.register_values == list(range(60))


def test_null_response_short_frame_raises_invalid_frame():
    """A truncated null frame must surface as InvalidFrame, not a raw struct.error (audit L6)."""
    decoder = PayloadDecoder(b"\x00" * 40)  # < 126 bytes: too short for 62 nulls + check
    with pytest.raises(InvalidFrame):
        NullResponse.decode_transparent_function(decoder)


def test_decode_bytes_wraps_unexpected_decode_error_as_invalid_frame():
    """An unexpected decode error surfaces as InvalidFrame for every caller (audit L6).

    A decode-time error other than InvalidPduState must not leak a raw struct.error out of
    decode_bytes (the restored broad catch). An input-register response claims 60 registers but
    carries only 2; decoding the register block overruns the buffer inside decode_main_function.
    """
    body = (
        b"DA1234G567"  # data_adapter_serial (10)
        + (0x8A).to_bytes(8, "big")  # padding (8)
        + b"\x32"  # device_address
        + b"\x04"  # transparent_function_code = input registers
        + b"SA1234G567"  # inverter_serial (10)
        + struct.pack(">HH", 0, 60)  # base_register=0, register_count=60
        + struct.pack(">HH", 1, 2)  # only 2 register values supplied
        + b"\x00\x00"  # check
    )
    tail = b"\x01\x02" + body  # uid + main function code (transparent = 2)
    frame = b"\x59\x59\x00\x01" + len(tail).to_bytes(2, "big") + tail
    with pytest.raises(InvalidFrame):
        ClientIncomingMessage.decode_bytes(frame)


def test_is_lan_config_rejects_nonzero_padding():
    """The LAN-config discriminator requires the 6 preceding pad bytes to be zero (audit L6).

    Otherwise a crafted padding field can false-positive and drop a valid response.
    """
    from givenergy_modbus.pdu.lan_config import LanConfigBroadcast

    # Real shape: 6 zero bytes + 0x00 + ',' → recognised.
    assert LanConfigBroadcast.is_lan_config(b"\x00\x00\x00\x00\x00\x00\x00,rest")
    # A non-zero byte in the 6-byte pad prefix → not a LAN-config frame.
    assert not LanConfigBroadcast.is_lan_config(b"\x00\x00\x2c\x00\x00\x00\x00,rest")


def test_strict_crc_mode_raises_on_mismatch(monkeypatch):
    """Opt-in strict CRC mode raises InvalidPduState on a mismatch (audit H1-better).

    The lenient default only warns and accepts the data.
    """
    resp = ReadHoldingRegistersResponse(base_register=0, register_count=1, register_values=[0], check=0x0000)
    resp.raw_frame = b"\x00" * 30  # CRC of raw_frame[26:-2] won't be 0x0000 → guaranteed mismatch

    # Lenient default: warns, never raises.
    assert ReadHoldingRegistersResponse.strict_crc is False
    resp._validate_check_code()

    # Strict: raises InvalidPduState on the same mismatch.
    monkeypatch.setattr(ReadHoldingRegistersResponse, "strict_crc", True)
    with pytest.raises(InvalidPduState, match="CRC"):
        resp._validate_check_code()


def test_request_crc_includes_device_address_matches_real_wire():
    """Request CRC must cover the device-address byte — pinned to a real GivTCP frame (#105).

    GivTCP and the GivEnergy app both compute the request check code over
    device_address + function_code + base + count; omitting the device byte produces a
    frame a strict inverter (All-in-One) silently drops. This value (0x474b) is the exact
    CRC GivTCP put on the wire for ReadHoldingRegisters(device=0x11, base=0, count=60),
    captured during the #105 investigation — external ground truth, not just internal
    consistency.
    """
    req = ReadHoldingRegistersRequest(device_address=0x11, base_register=0, register_count=60)
    raw = req.encode()
    # 0x474b is both the stored check and the on-wire trailing bytes (the CRC is
    # byte-swapped on emit, matching GivTCP/app frames — the old code emitted 0x1160).
    assert req.check == 0x474B
    assert raw[-2:] == b"\x47\x4b"
    # Same logical read at a different device address must produce a different CRC —
    # proving the device byte actually participates (regression guard for the old bug).
    other = ReadHoldingRegistersRequest(device_address=0x32, base_register=0, register_count=60)
    other.encode()
    assert other.check != req.check


def test_write_request_crc_includes_device_address():
    """Write request CRC also covers the device byte (#105).

    Uses a write-safe register so ensure_valid_state() doesn't reject the encode.
    """
    from givenergy_modbus.client.commands import RegisterMap

    # ENABLE_CHARGE (96) is in WRITE_SAFE_REGISTERS.
    req = WriteHoldingRegisterRequest(register=RegisterMap.ENABLE_CHARGE, value=1, device_address=0x11)
    req.encode()
    at_other = WriteHoldingRegisterRequest(register=RegisterMap.ENABLE_CHARGE, value=1, device_address=0x32)
    at_other.encode()
    assert req.check != at_other.check, "device address must participate in the write CRC"


def test_crc_mismatch_logs_at_warning(caplog):
    """A CRC integrity-check failure on a register response is logged at WARNING (audit H1).

    The check stays non-fatal — the data is still accepted (incoming inverter frames are the
    source of truth) — but a mismatch must be visible to operators, not buried at DEBUG.
    """
    import logging

    resp = ReadInputRegistersResponse(base_register=0, register_count=2, register_values=[1, 2])
    resp.raw_frame = b"\x00" * 30  # >= 28 bytes; CRC over the middle won't equal the forced check
    resp.check = 0xFFFF  # deliberately wrong

    with caplog.at_level(logging.WARNING, logger="givenergy_modbus.pdu.read_registers"):
        resp._validate_check_code()  # must not raise — non-fatal

    assert any("integrity check" in r.message.lower() for r in caplog.records), (
        f"expected a WARNING about the integrity check, got: {[r.message for r in caplog.records]}"
    )


def test_null_response_warning_escapes_serial(caplog):
    """A non-null inverter serial in a NullResponse is logged repr-escaped, not raw (audit M2).

    Serials are latin-1 decoded, so any byte passes through — a control char in a spoofed
    frame would otherwise forge or split log lines.
    """
    import logging

    resp = NullResponse(inverter_serial_number="AB\nCDEF012")  # 10 chars including a newline
    with caplog.at_level(logging.WARNING, logger="givenergy_modbus.pdu.null"):
        resp.ensure_valid_state()

    msg = caplog.records[0].message
    assert "\n" not in msg, f"raw control char leaked into the log line: {msg!r}"
    assert "\\n" in msg, f"serial should be repr-escaped: {msg!r}"


def test_heartbeat_str_escapes_serial():
    """HeartbeatMessage.__str__ repr-escapes the device-supplied serial (audit M2)."""
    hb = HeartbeatRequest(data_adapter_serial_number="WF\n123G045")  # 10 chars including a newline
    s = str(hb)
    assert "\n" not in s, f"raw control char leaked into __str__: {s!r}"
    assert "\\n" in s, f"serial should be repr-escaped: {s!r}"


def test_write_request_rejects_bool_value():
    """A bool write value is rejected, not silently coerced to 0/1 (audit L1).

    bool subclasses int, so isinstance(value, int) alone accepts True/False — a bool reaching
    a numeric register (e.g. ACTIVE_POWER_RATE) is almost certainly a caller bug. Boolean
    command helpers pass int(enabled) explicitly.
    """
    with pytest.raises(ValueError, match="unacceptable"):
        WriteHoldingRegisterRequest(register=20, value=True)
    with pytest.raises(ValueError, match="unacceptable"):
        WriteHoldingRegisterRequest(register=20, value=False)
    # Plain ints still accepted.
    assert WriteHoldingRegisterRequest(register=20, value=1).value == 1
    assert WriteHoldingRegisterRequest(register=20, value=0).value == 0
