"""Tests for the RS485 battery sub-bus RTU decoder (tests/debug/subbus_rtu.py).

Golden fixture is a serial-redacted slice of a live tap on a two-pack loft install
(subbus_sample_redacted.bin). The real capture is never committed.
"""

from pathlib import Path

from tests.debug import subbus_rtu as sb

FIXTURE = Path(__file__).parent / "fixtures" / "subbus_sample_redacted.bin"


def _stream() -> bytes:
    return FIXTURE.read_bytes()


def test_crc16_known_vector():
    # Canonical CRC-16/MODBUS check value for the ASCII string "123456789".
    assert sb.crc16(b"123456789") == 0x4B37


def test_request_crc_is_big_endian_write_and_read():
    # Requests/writes append CRC big-endian; a read of 60 regs from 0 on addr 2.
    body = bytes.fromhex("02030000003c")
    c = sb.crc16(body)
    frame = body + bytes([c >> 8, c & 0xFF])  # BE
    parsed = sb.parse(frame)
    assert parsed == [sb.Request(addr=2, start=0, count=60)]


def test_response_crc_is_little_endian():
    # Build a minimal response of 2 registers, LE CRC, and round-trip it.
    payload = bytes.fromhex("0001 0002".replace(" ", ""))
    body = bytes([1, 0x03, 0x00, len(payload)]) + payload
    c = sb.crc16(body)
    frame = body + bytes([c & 0xFF, c >> 8])  # LE
    parsed = sb.parse(frame)
    assert parsed == [sb.Response(addr=1, payload=payload)]


def test_fixture_decodes_the_expected_frame_mix():
    frames = sb.parse(_stream())
    kinds = {
        k: sum(isinstance(f, t) for f in frames)
        for k, t in (("resp", sb.Response), ("req", sb.Request), ("write", sb.Write), ("garbage", sb.Garbage))
    }
    # 6 pack responses, requests to addrs 1-5 across cycles, round-robin writes, and one
    # trailing partial frame at the capture boundary (garbage).
    assert kinds["resp"] == 6
    assert kinds["req"] >= 20
    assert kinds["write"] == 5
    assert kinds["garbage"] == 1


def test_only_address_1_responds():
    frames = sb.parse(_stream())
    replied = {f.addr for f in frames if isinstance(f, sb.Response)}
    polled = {f.addr for f in frames if isinstance(f, sb.Request)}
    assert replied == {1}  # only the tapped pack answers
    assert polled == {1, 2, 3, 4, 5}  # master polls the whole downstream slot range


def test_response_decodes_serial_and_cells():
    frames = sb.parse(_stream())
    resp = next(f for f in frames if isinstance(f, sb.Response))
    assert resp.addr == 1
    assert resp.serial == "XX0000A000"  # redacted placeholder
    cells = resp.cell_mv
    assert len(cells) == 16
    assert all(3250 <= mv <= 3350 for mv in cells)  # ~3.31 V LiFePO4, resting


def test_writes_are_reg6_round_robin():
    frames = sb.parse(_stream())
    writes = [f for f in frames if isinstance(f, sb.Write)]
    assert all(w.reg == 6 and w.value == 0x0505 for w in writes)
    # target address marches across the packs, one per cycle.
    assert [w.addr for w in writes] == [5, 1, 2, 3, 4]


def test_redact_leaves_no_real_serial_and_keeps_crc_valid():
    # Redacting an already-redacted stream is idempotent and every frame still CRC-validates.
    red = sb.redact(_stream())
    frames = sb.parse(red)
    assert not any(isinstance(f, sb.Garbage) and len(f.raw) > 8 for f in frames)  # no CRC breakage
    assert all(f.serial == "XX0000A000" for f in frames if isinstance(f, sb.Response))


def test_write_stats_show_a_fixed_keepalive_token():
    frames = sb.parse(_stream())
    stats = sb.write_stats(frames)
    # Every write is reg 6 = 0x0505 — a single (reg, value) key => fixed token, not drifting data.
    assert stats == {(6, 0x0505): 5}
    assert len({v for (_r, v) in stats}) == 1  # no value drift


def test_diagnose_garbage_flags_a_collision():
    # Synthesise a half-duplex collision: a master read-request's bytes land in the middle of an
    # in-flight response's payload. The overlaid region breaks the response CRC (=> Garbage), but
    # the request's fixed tail (03 00 00 00 3c) survives embedded mid-run.
    response_head = bytes([1, 0x03, 0x00, 0x78]) + b"XX0000A000" + bytes(40)
    embedded_request = bytes.fromhex("02030000003ce845")  # a real read-60 request
    collision = response_head + embedded_request + bytes(30)
    d = sb.diagnose_garbage(sb.Garbage(collision))
    assert d.looks_like_response  # starts with a response header shape
    assert d.embedded_master_at is not None  # the request tail is embedded inside
    assert collision[d.embedded_master_at : d.embedded_master_at + 5] == bytes.fromhex("030000003c")


def test_diagnose_garbage_plain_fragment_is_not_a_collision():
    d = sb.diagnose_garbage(sb.Garbage(bytes.fromhex("03030000")))  # the fixture's trailing partial
    assert not d.looks_like_response
    assert d.embedded_master_at is None


def test_cycles_group_polls_replies_writes():
    rounds = sb.cycles(sb.parse(_stream()))
    # Each full cycle polls addr 1 (and gets a reply), sweeps 2-5, and issues one write.
    full = [c for c in rounds if 1 in c.replied]
    assert full, "expected at least one complete cycle"
    c0 = full[0]
    assert 1 in c0.replied and c0.replied[1].serial == "XX0000A000"
    assert set(c0.polled) <= {1, 2, 3, 4, 5}
