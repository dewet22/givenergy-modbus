"""Characterisation harness: pin detect()'s outbound wire sequence frame-for-frame (#268 slice 2).

The bit-identical wire bar: extracting `detect()` into a strategise / probe / validate loop must
not change the request *sequence* it puts on the wire — frame count, HR-vs-IR, device address, base
register, register count, and order. These golden snapshots lock that sequence before the refactor
and assert it is reproduced after.

The recording seam is `send_request_and_await_response`: both `_probe` (probe tier) and the direct
known-tier reads funnel through it, so one tap captures the complete outbound stream in call order.

The goldens are **literal recordings**, never computed from the same rules the production code uses —
a golden test that recomputes the expected sequence can let a bug match a bug. They were captured
from the unchanged `detect()` over each MockPlant fixture.

Coverage — the three identity-complete fixtures that drive a live detect over MockPlant
deterministically (the same set `test_offline_from_caches.py` uses, for the same reason):
  - hybrid_gen1: Step 1 (identity), Step 3 (meter sweep), Step 4 (LV batteries — incl. the cold-start
    re-read at 0x33, #233/#289), Step 4b (LV BCU).
  - aio:         Step 1, Step 2 (BMS@0xA0 + BCU@0x70), Step 2b (AIO modules 0x50–0x53), Step 3.
  - ems:         Step 1, Step 3, Step 5 (EMS rollup IR(2040,55) — a known-tier read).
The non-AIO HV BMU path (Step 2c) has no live-drivable fixture (three_phase_hv_a is a passive refresh
dump with no HR(0,60) identity block at 0x11), so it stays pinned by the unit tests in test_detect.py.
"""

from pathlib import Path

import pytest

from givenergy_modbus.client.client import Client
from givenergy_modbus.pdu import ReadHoldingRegistersRequest, TransparentRequest
from givenergy_modbus.testing import MockPlant

_CAPTURES = Path(__file__).parents[1] / "fixtures" / "captures"

# Fast probe params: absent peripheral addresses time out, so keep them short. Matches the
# integration / offline tests so the recorded sequence is the one those suites already exercise.
_DETECT = dict(timeout=1.0, retries=0, probe_timeout=0.1, probe_retries=0)

# Golden outbound sequences as (reg_type, device_address, base_register, register_count) — literal
# recordings from the unchanged detect(). Order is significant.
_GOLDEN: dict[str, list[tuple[str, int, int, int]]] = {
    # HYBRID_GEN1 — meters (Step 3) precede the LV battery sweep (Step 4); 0x32 is read once via the
    # known-tier preamble, 0x33 twice (the cold-start corroborating re-read), 0x34–0x37 once each
    # (absent → mark_absent), then the LV BCU at 0x31 (Step 4b).
    "hybrid_2_bat_a/hybrid_gen1_arm449_0x11_poll_10min.log": [
        ("HR", 0x11, 0, 60),
        ("IR", 0x01, 60, 30),
        ("IR", 0x02, 60, 30),
        ("IR", 0x03, 60, 30),
        ("IR", 0x04, 60, 30),
        ("IR", 0x05, 60, 30),
        ("IR", 0x06, 60, 30),
        ("IR", 0x07, 60, 30),
        ("IR", 0x08, 60, 30),
        ("IR", 0x32, 60, 60),
        ("IR", 0x33, 60, 60),
        ("IR", 0x33, 60, 60),
        ("IR", 0x34, 60, 60),
        ("IR", 0x35, 60, 60),
        ("IR", 0x36, 60, 60),
        ("IR", 0x37, 60, 60),
        ("IR", 0x31, 60, 60),
    ],
    # ALL_IN_ONE — identity, then BMS@0xA0 (IR 60,5) and the single BCU@0x70, then the four AIO
    # modules 0x50–0x53 (Step 2b), then the meter sweep. HV BMU (Step 2c) and LV (Step 4) are skipped.
    "aio_a/aio_arm612_5min.log": [
        ("HR", 0x11, 0, 60),
        ("IR", 0xA0, 60, 5),
        ("IR", 0x70, 60, 60),
        ("IR", 0x50, 60, 60),
        ("IR", 0x51, 60, 60),
        ("IR", 0x52, 60, 60),
        ("IR", 0x53, 60, 60),
        ("IR", 0x01, 60, 30),
        ("IR", 0x02, 60, 30),
        ("IR", 0x03, 60, 30),
        ("IR", 0x04, 60, 30),
        ("IR", 0x05, 60, 30),
        ("IR", 0x06, 60, 30),
        ("IR", 0x07, 60, 30),
        ("IR", 0x08, 60, 30),
    ],
    # EMS — identity, the meter sweep, then the EMS rollup cross-check IR(2040,55)@0x11 (Step 5,
    # known tier). HV/AIO/LV steps are all skipped.
    "ems_2_inv_3_bat_a/ems_arm1036_60s.log": [
        ("HR", 0x11, 0, 60),
        ("IR", 0x01, 60, 30),
        ("IR", 0x02, 60, 30),
        ("IR", 0x03, 60, 30),
        ("IR", 0x04, 60, 30),
        ("IR", 0x05, 60, 30),
        ("IR", 0x06, 60, 30),
        ("IR", 0x07, 60, 30),
        ("IR", 0x08, 60, 30),
        ("IR", 0x11, 2040, 55),
    ],
}


def _tap_outbound(client: Client) -> list[tuple[str, int, int, int]]:
    """Wrap ``client.send_request_and_await_response`` to record every outbound read, in order.

    Returns the list it appends to (the client is discarded after the run, so no restore needed).
    """
    original = client.send_request_and_await_response
    recorded: list[tuple[str, int, int, int]] = []

    async def _recording(request: TransparentRequest, *args: object, **kwargs: object) -> object:
        reg_type = "HR" if isinstance(request, ReadHoldingRegistersRequest) else "IR"
        recorded.append((reg_type, request.device_address, request.base_register, request.register_count))  # type: ignore[attr-defined]
        return await original(request, *args, **kwargs)  # type: ignore[arg-type]

    client.send_request_and_await_response = _recording  # type: ignore[assignment]
    return recorded


@pytest.mark.parametrize("relpath", list(_GOLDEN))
@pytest.mark.timeout(30)
async def test_detect_wire_sequence_is_bit_identical(relpath: str):
    """detect() over each fixture issues exactly the recorded outbound request sequence."""
    mock = MockPlant.from_capture(_CAPTURES / relpath)
    host, port = await mock.start("127.0.0.1", 0)
    client = Client(host, port, tx_message_wait=0, tx_jitter=0)
    await client.connect()
    recorded = _tap_outbound(client)
    try:
        caps = await client.detect(**_DETECT)  # type: ignore[arg-type]
    finally:
        await client.close()
        await mock.aclose()

    assert caps is not None  # detect completed; the sequence below is a full run, not a partial one
    assert recorded == _GOLDEN[relpath]
