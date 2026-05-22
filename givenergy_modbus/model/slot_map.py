"""Charge/discharge slot register address layouts.

Carved out from `model/inverter.py` so that `client/commands.py` and the
inverter mixin (also in `client/commands.py`) can both reference these without
introducing a circular import between `client/*` and `model/inverter.py`.

`model/inverter.py` and `model/inverter_threephase.py` re-export from here for
backward compatibility — existing imports like
`from givenergy_modbus.model.inverter import SINGLE_PHASE_SLOTS` continue to
work.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SlotMap:
    """Register address pairs for charge and discharge time slots."""

    charge_slots: tuple[tuple[int, int], ...]
    discharge_slots: tuple[tuple[int, int], ...]


SINGLE_PHASE_SLOTS = SlotMap(
    charge_slots=((94, 95), (31, 32)),
    discharge_slots=((56, 57), (44, 45)),
)

# Extended 10-slot map for ALL_IN_ONE, HYBRID_GEN4, HYBRID_HV_GEN3,
# and HYBRID_GEN3 units with ARM firmware > 302.
EXTENDED_SLOTS = SlotMap(
    charge_slots=(
        (94, 95),
        (31, 32),
        (246, 247),
        (249, 250),
        (252, 253),
        (255, 256),
        (258, 259),
        (261, 262),
        (264, 265),
        (267, 268),
    ),
    discharge_slots=(
        (56, 57),
        (44, 45),
        (276, 277),
        (279, 280),
        (282, 283),
        (285, 286),
        (288, 289),
        (291, 292),
        (294, 295),
        (297, 298),
    ),
)

# Three-phase inverters have their first two charge/discharge slot pairs at
# the higher-numbered HR(1113-1121) range; slots 3-10 reuse the EXTENDED_SLOTS
# addresses.
THREE_PHASE_SLOTS = SlotMap(
    charge_slots=(
        (1113, 1114),
        (1115, 1116),
        (246, 247),
        (249, 250),
        (252, 253),
        (255, 256),
        (258, 259),
        (261, 262),
        (264, 265),
        (267, 268),
    ),
    discharge_slots=(
        (1118, 1119),
        (1120, 1121),
        (276, 277),
        (279, 280),
        (282, 283),
        (285, 286),
        (288, 289),
        (291, 292),
        (294, 295),
        (297, 298),
    ),
)
