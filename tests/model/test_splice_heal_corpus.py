"""Corpus-grounded safety proof for the #299 sustained-step heal.

The #299 heal makes the terminal >=2-physics battery reject recoverable, but ONLY for a bank that
:func:`~givenergy_modbus.model.battery_splice.heal_eligible` passes (every trip a voltage/capacity
surge in absolute range). An ineligible frame never enters the heal streak, so "no corpus corruption
can heal" reduces to "no corpus corruption transition is heal-eligible".

That is the non-vacuous check: simply replaying the corpus and asserting "nothing heals" passes
*vacuously* (the corpus has zero N-poll smooth-reject runs, so no value of N would heal anything).
Instead, this replays every consecutive battery-bank transition in the capture corpus and asserts
that **every** >=2-physics transition — i.e. every corruption event the guard hard-rejects — is
``not heal_eligible``. This pins the class-restriction spine against real wire data, and in
particular catches the IR(103/104) ``t_max``/``t_min`` temp-zero corruption shape that
``is_corruption_cohort`` (IR76-79 only) does not detect: it is ``cell_temp_deci`` class, so it must
be ineligible.
"""

from pathlib import Path

import pytest

from givenergy_modbus.framer import ClientFramer
from givenergy_modbus.model.battery_splice import BANK_BASE, classify_transition, heal_eligible
from givenergy_modbus.pdu import ReadInputRegistersResponse

_CAPTURES = Path(__file__).parents[1] / "fixtures" / "captures"
_BATTERY_DEVICES = range(0x32, 0x38)


def _rx_frames(path: Path) -> list[bytes]:
    frames: list[bytes] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1] == "rx":
            try:
                frames.append(bytes.fromhex(parts[-1]))
            except ValueError:
                continue
    return frames


@pytest.mark.timeout(15)
async def test_no_corpus_corruption_transition_is_heal_eligible():
    """Every >=2-physics corruption transition in the corpus must be ineligible to heal (#299)."""
    framer = ClientFramer()
    prevs: dict[tuple[str, int], list[int]] = {}
    reject_bucket = 0
    for path in sorted(_CAPTURES.glob("*/*.log")):
        for raw in _rx_frames(path):
            async for pdu in framer.decode(raw):
                if (
                    not isinstance(pdu, ReadInputRegistersResponse)
                    or pdu.device_address not in _BATTERY_DEVICES
                    or pdu.base_register != BANK_BASE
                ):
                    continue
                regs = list(pdu.register_values)
                if len(regs) < 60 or all(r == 0 for r in regs):
                    continue  # absent battery slot
                key = (str(path), pdu.device_address)
                prev = prevs.get(key)
                prevs[key] = regs
                if prev is None:
                    continue
                phys, _immut = classify_transition(prev, regs)
                if len(phys) >= 2:
                    reject_bucket += 1
                    assert not heal_eligible(phys), (
                        f"corpus corruption in {path.name} (device 0x{pdu.device_address:02x}) is "
                        f"heal-eligible — class restriction breached: {phys}"
                    )
    # Guard against a silently-empty replay (a moved fixture / decode regression would make the
    # assertion above vacuous). The corpus holds the documented >=2-physics corruption events.
    assert reject_bucket >= 10, f"expected the corpus >=2-physics corruption events, saw {reject_bucket}"
