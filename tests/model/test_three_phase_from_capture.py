"""Wire-level regression test for the three-phase decode, replayed from a real capture.

The first real three-phase dataset — a GIV-3HY-11 HV hybrid from givenergy-hass#174 —
fed through the framer into a bare ``Plant``, asserting the decoded battery values. Every
other three-phase test primes synthetic registers; this is the only one that proves the
real wire→model path, and it locks in the fixes these frames drove:

- ``i_battery`` is centi, not deci (#264);
- ``p_battery`` / ``e_battery_throughput`` are derived from the native three-phase
  registers (#262);
- the HV BCU cluster block decodes (the path consumers read per-stack SOC from).

See ``tests/fixtures/captures/three_phase_hv_a/README.md`` for provenance.
"""

from pathlib import Path

import pytest

from givenergy_modbus.framer import ClientFramer
from givenergy_modbus.model.hv_bcu import Bcu
from givenergy_modbus.model.inverter_threephase import ThreePhaseInverter
from givenergy_modbus.model.plant import Plant
from givenergy_modbus.pdu.transparent import TransparentResponse

_CAPTURE = Path(__file__).parents[1] / "fixtures" / "captures" / "three_phase_hv_a" / "giv3hy11_hass174_180s.txt"


def _frames() -> list[bytes]:
    """Read frames from the integration's ``tx:/rx: <hex>`` capture format."""
    frames: list[bytes] = []
    for line in _CAPTURE.read_text(encoding="utf-8").splitlines():
        for prefix in ("rx: ", "tx: "):
            if line.startswith(prefix):
                try:
                    frames.append(bytes.fromhex(line[len(prefix) :]))
                except ValueError:
                    pass
    return frames


async def _replay() -> Plant:
    """Decode the capture into a bare (no-capabilities) Plant — raw caches keyed by wire address."""
    framer = ClientFramer()
    plant = Plant()
    for raw in _frames():
        async for pdu in framer.decode(raw):
            if isinstance(pdu, TransparentResponse) and not pdu.error:
                plant.update(pdu)
    return plant


@pytest.mark.timeout(15)
async def test_three_phase_inverter_battery_decode_from_capture():
    """Inverter-level battery fields decode correctly on a real three-phase HV unit (0x11)."""
    inv = ThreePhaseInverter.from_register_cache((await _replay()).register_caches[0x11])
    assert inv.battery_soc == 71  # type: ignore[attr-defined]
    # #264: i_battery is centi, not deci — the final frame's raw -1 decodes to -0.01 A (was -0.1).
    assert inv.i_battery == pytest.approx(-0.01)  # type: ignore[attr-defined]
    assert inv.p_battery_charge == pytest.approx(8.1)  # type: ignore[attr-defined]
    assert inv.p_battery_discharge == pytest.approx(0.0)  # type: ignore[attr-defined]
    # #262: derived p_battery = discharge − charge (negative = charging), single-phase sign convention.
    assert inv.p_battery == pytest.approx(-8.1)  # type: ignore[attr-defined]
    # #262: derived e_battery_throughput = charge_total + discharge_total.
    assert inv.e_battery_throughput == pytest.approx(11840.2 + 10753.6)  # type: ignore[attr-defined]
    assert inv.v_battery_bms == pytest.approx(470.3)  # type: ignore[attr-defined]


@pytest.mark.timeout(15)
async def test_three_phase_hv_bcu_decode_from_capture():
    """BCU cluster-level data decodes (the path consumers read per-stack SOC/temp from)."""
    bcu = Bcu.from_register_cache((await _replay()).register_caches[0x70])
    assert bcu.number_of_modules == 6  # type: ignore[attr-defined]
    assert bcu.battery_soc_max == 71  # type: ignore[attr-defined]
    assert bcu.battery_soc_min == 68  # type: ignore[attr-defined]
    assert bcu.battery_voltage == pytest.approx(470.3)  # type: ignore[attr-defined]
    assert bcu.battery_soh == 95  # type: ignore[attr-defined]
