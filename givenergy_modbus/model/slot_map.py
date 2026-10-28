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
    """Register address pairs for charge and discharge time slots.

    ``charge_targets`` / ``discharge_targets`` are the per-slot target SOC registers, index-
    aligned with the slots; empty on maps whose models have no per-slot targets (2-slot models
    use the single charge target, HR 116).
    """

    charge_slots: tuple[tuple[int, int], ...]
    discharge_slots: tuple[tuple[int, int], ...]
    charge_targets: tuple[int, ...] = ()
    discharge_targets: tuple[int, ...] = ()


# Per-slot target SOC registers of the 10-slot block: each slot is a (start, end, target)
# triple from HR 240 (charge) / HR 270 (discharge), so slot n's target is HR 242 + 3(n-1) /
# HR 272 + 3(n-1). The GivEnergy app names them "AC Charge n Upper SOC % Limit" / "DC Discharge
# n Lower SOC % Limit"; the async fork wrote them as CHARGE_/DISCHARGE_TARGET_SOC_n (and the
# same addresses as TPH_* on three-phase).
_TEN_SLOT_CHARGE_TARGETS: tuple[int, ...] = tuple(242 + 3 * k for k in range(10))
_TEN_SLOT_DISCHARGE_TARGETS: tuple[int, ...] = tuple(272 + 3 * k for k in range(10))


SINGLE_PHASE_SLOTS = SlotMap(
    charge_slots=((94, 95), (31, 32)),
    discharge_slots=((56, 57), (44, 45)),
)

# Extended 10-slot map for ALL_IN_ONE, HYBRID_GEN4, HYBRID_HV_GEN3, GATEWAY,
# and HYBRID_GEN3 units with ARM firmware > 302.
#
# Charge slot 2 is HR(243/244) here, next to its target SOC at HR(245), not the legacy
# HR(31/32): a Gen 3 on 10-slot firmware answers writes to HR(31/32) with an error response
# (britkat1980/giv_tcp#619), the async fork wrote slot 2 at 243/244, and on the All-in-One
# captures HR(31/32) reads 1/0 (not a slot) while HR(243/244) holds the real slot. Discharge
# slot 2 stays at HR(44/45): the fork wrote it there and nothing contradicts it.
EXTENDED_SLOTS = SlotMap(
    charge_slots=(
        (94, 95),
        (243, 244),
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
    charge_targets=_TEN_SLOT_CHARGE_TARGETS,
    discharge_targets=_TEN_SLOT_DISCHARGE_TARGETS,
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
    charge_targets=_TEN_SLOT_CHARGE_TARGETS,
    discharge_targets=_TEN_SLOT_DISCHARGE_TARGETS,
)

# EMS plant controllers expose three charge and three discharge time slots in
# their HR(2040+) plant-config block (decoded in model/ems.py): discharge slots
# at 2044-2051 and charge slots at 2053-2060, each a (start, end) HHMM pair with
# its SoC target in the register immediately after. Lets the existing
# set_charge_slot()/set_discharge_slot(idx, ts, slot_map) commands drive an EMS.
EMS_SLOTS = SlotMap(
    charge_slots=(
        (2053, 2054),
        (2056, 2057),
        (2059, 2060),
    ),
    discharge_slots=(
        (2044, 2045),
        (2047, 2048),
        (2050, 2051),
    ),
)
