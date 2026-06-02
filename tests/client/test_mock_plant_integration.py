"""End-to-end integration: drive the real Client against MockPlant.

The golden-master tests (tests/model/test_fixture_golden_master.py) replay recorded
*responses* through decode. These instead exercise the client's own request *generation*
— connect → detect → refresh, over a real socket — against a server that synthesizes
correct-CRC responses from the same captures. That round-trip is what the passive replay
can't cover.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from givenergy_modbus.client.client import Client
from givenergy_modbus.model.inverter import Model
from givenergy_modbus.pdu import ClientIncomingMessage, ReadInputRegistersRequest
from givenergy_modbus.testing import MockPlant

_CAPTURES = Path(__file__).parents[1] / "fixtures" / "captures"


async def _connected_client(mock: MockPlant) -> tuple[Client, str, int]:
    host, port = await mock.start("127.0.0.1", 0)
    client = Client(host, port, tx_message_wait=0, tx_jitter=0)
    await client.connect()
    return client, host, port


async def _client_for(*relpaths: str) -> AsyncIterator[Client]:
    mock = MockPlant.from_capture(*[_CAPTURES / r for r in relpaths])
    client, _, _ = await _connected_client(mock)
    try:
        yield client
    finally:
        await client.close()
        await mock.aclose()


# Fast probe params: absent peripheral addresses time out, so keep them short.
_DETECT = dict(timeout=1.0, retries=0, probe_timeout=0.1, probe_retries=0)


@pytest.mark.timeout(30)
async def test_detect_and_refresh_aio():
    """All-in-One: detect → ALL_IN_ONE @ 0x11 with HV BCU stack; refresh completes."""
    async for client in _client_for("aio_a/aio_arm612_5min.log"):
        caps = await client.detect(**_DETECT)
        assert caps.device_type is Model.ALL_IN_ONE
        assert caps.inverter_address == 0x11
        assert caps.is_hv
        assert caps.bcu_stacks  # the integrated HV stack is detected
        plant = await client.refresh(timeout=1.0, retries=0)
        assert plant.capabilities.device_type is Model.ALL_IN_ONE


@pytest.mark.timeout(30)
async def test_detect_ems():
    """EMS controller: detect → Model.EMS @ 0x11, two managed inverters via the rollup."""
    async for client in _client_for("ems_2_inv_3_bat_a/ems_arm1036_60s.log"):
        caps = await client.detect(**_DETECT)
        assert caps.device_type is Model.EMS
        assert caps.is_ems


@pytest.mark.timeout(30)
async def test_detect_and_refresh_hybrid_gen1():
    """HYBRID_GEN1: detect → Model.HYBRID_GEN1 @ 0x31 (not the 0x11 default); refresh completes."""
    async for client in _client_for("hybrid_2_bat_a/hybrid_gen1_arm449_givbat82_givbat95gen3_60min.log"):
        caps = await client.detect(**_DETECT)
        assert caps.device_type is Model.HYBRID_GEN1
        assert caps.inverter_address == 0x31
        plant = await client.refresh(timeout=1.0, retries=0)
        assert plant.capabilities.device_type is Model.HYBRID_GEN1


@pytest.mark.timeout(30)
async def test_aio_errors_on_absent_three_phase_bank():
    """A direct IR(1000+) read against the AIO mock returns an error response (#105).

    The AIO has no per-phase bank, so this is the faithful reproduction of the #105
    symptom — end-to-end over a real socket through the synthesizing mock.
    """
    mock = MockPlant.from_capture(_CAPTURES / "aio_a/aio_arm612_5min.log")
    client, host, port = await _connected_client(mock)
    try:
        # Bypass detect's gating: ask for the absent bank directly and inspect the reply.
        req = ReadInputRegistersRequest(base_register=1000, register_count=60, device_address=0x11)
        raw = req.encode()
        reader, writer = client.reader, client.writer  # reuse the open connection
        writer.write(raw)
        await writer.drain()
        data = await reader.read(4096)
        pdu = ClientIncomingMessage.decode_bytes(data)
        assert pdu.error is True
    finally:
        await client.close()
        await mock.aclose()
