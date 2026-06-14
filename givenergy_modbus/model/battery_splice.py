"""Physics-delta classifier for LV battery banks — the substrate of the #256 splice guard.

BMS sub-bus corruption is re-framed by the dongle with a *valid CRC* (#147), so it passes
the #255 CRC guard and commits valid-looking garbage over good cache. Every spliced value
sits inside its per-register bounds, the bank isn't all-zero (so Pattern B / #206 doesn't
fire) and the serial can stay valid (so ``is_coherent`` passes) — nothing catches it.

What *does* separate corruption from real data is physics: classifying the 1,103
consecutive-frame transitions in the capture corpus by physically-impossible per-register
movement gives perfect separation (1,086 clean / 17 corrupt / zero false trips). Every
corruption event trips >=2 physically-independent registers or changes a normally-constant
one; the only physics-singleton in the corpus (a MOSFET temperature stepping 6.3 degC in
one poll) is genuine.

This module is the single source of truth for those thresholds. ``Plant._commit_bank``
imports it to guard live commits; ``tests/debug/physics_delta_classify.py`` imports it to
re-validate the corpus separation against the very same constants.

Thresholds are in raw register units and set at roughly 10x what the quantity can really do
in a ~30 s poll interval — cell voltages barely move (electrochemical inertia), cell-mass
temperatures drift, the junction-adjacent MOSFET sensor steps (hence its much wider
threshold), capacities move with charge current (~0.5 Ah/poll at LV power). Status/bitfield
words carry no physics and are exempt (IR(91) legitimately toggles 0x0E10 <-> 0x0610 every
few minutes). ``num_cells``, ``bms_firmware_version`` and the serial block are constant —
ANY transient change is corruption on its own.

Indices throughout are **bank-relative** (``i`` == register ``IR(60 + i)``); the trips
returned carry the **absolute** IR number for logging.
"""

from __future__ import annotations

#: Battery banks span IR(60..119); index ``i`` here is register ``IR(BANK_BASE + i)``.
BANK_BASE = 60

# (class name, bank-relative indices, threshold on |delta| in raw units).
SCALAR_RULES: list[tuple[str, list[int], int]] = [
    ("cell_mV", list(range(0, 16)), 100),  # IR(60-75) cells: ~10 mV/poll real max
    ("cell_temp_deci", [16, 17, 18, 19, 43, 44], 50),  # IR(76-79,103,104): thermal mass
    ("mosfet_temp_deci", [21], 200),  # IR(81): junction-adjacent, steps with load
    ("v_cells_sum_mV", [20], 1600),  # IR(80)
    ("soc_pct", [40], 10),  # IR(100)
    ("e_total_deci", [45, 46], 50),  # IR(105/106) lifetime energy
]
# uint32 pairs: (class name, (high index, low index), threshold on the assembled pair value).
PAIR_RULES: list[tuple[str, tuple[int, int], int]] = [
    ("v_out_mV", (22, 23), 2000),  # IR(82-83)
    ("cap_centiAh", (24, 25), 1000),  # IR(84-85) cap_calibrated
    ("cap_centiAh", (26, 27), 1000),  # IR(86-87) cap_design
    ("cap_centiAh", (28, 29), 1000),  # IR(88-89) cap_remaining
    ("cap_centiAh", (41, 42), 1000),  # IR(101-102) cap_design2
]
# num_cells IR(97), bms_firmware_version IR(98), serial block IR(110-114) — ANY change is
# corruption on its own. IR(115) is deliberately NOT here: the corpus treated it as a
# constant canary, but battery.py documents it as a mutable ``usb_device_inserted`` field
# (observed values 0/8/11), so a normal USB insert/remove would false-trip. The temp-zero
# corruption cohort it was meant to catch already trips the >=2-physics rule on the
# temperatures themselves (#256 discussion).
IMMUTABLE: list[int] = [37, 38, *range(50, 55)]
# Exempt (no physics): status/warning words IR(90-94), i_battery IR(95), num_cycles IR(96),
# usb_device_inserted IR(115), unknown/reserved IR(99,107-109,116-119).

#: class name -> threshold, for the escrow guard's value-consistency check on a held trip.
#: Every ``cap_centiAh`` pair shares the same threshold, so the flattening is unambiguous.
THRESHOLD_BY_CLASS: dict[str, int] = {name: thr for name, _, thr in SCALAR_RULES} | {
    name: thr for name, _, thr in PAIR_RULES
}

#: A single trip: (absolute IR number, class name, old comparable value, new comparable value).
#: For pair rules the comparable values are the assembled uint32s, not the high word alone.
Trip = tuple[int, str, int, int]


def classify_transition(
    prev: list[int],
    new: list[int],
    present: set[int] | None = None,
) -> tuple[list[Trip], list[Trip]]:
    """Classify one IR(60,60) battery-bank transition into (physics trips, immutable violations).

    ``prev`` / ``new`` are length-60 lists of **raw** register values, bank-relative
    (``prev[i]`` is the previous raw value of ``IR(BANK_BASE + i)``).

    ``present`` is the set of bank-relative indices whose value is genuinely available in
    *both* banks; a rule is skipped unless all of its registers are present. Pass ``None``
    to evaluate every rule (the offline corpus tool's behaviour, where both frames are
    always full reads). The live guard passes the intersection so a partial bank or a
    never-seen register can't manufacture a spurious delta.

    Each returned trip is ``(absolute_IR_number, class_name, old_comparable, new_comparable)``;
    for pair rules the comparable values are the assembled uint32s.
    """
    phys: list[Trip] = []
    immut: list[Trip] = []
    for name, idxs, thr in SCALAR_RULES:
        for i in idxs:
            if present is not None and i not in present:
                continue
            if abs(new[i] - prev[i]) > thr:
                phys.append((i + BANK_BASE, name, prev[i], new[i]))
    for name, (hi, lo), thr in PAIR_RULES:
        if present is not None and (hi not in present or lo not in present):
            continue
        new_val = (new[hi] << 16) | new[lo]
        old_val = (prev[hi] << 16) | prev[lo]
        if abs(new_val - old_val) > thr:
            phys.append((hi + BANK_BASE, name, old_val, new_val))
    for i in IMMUTABLE:
        if present is not None and i not in present:
            continue
        if new[i] != prev[i]:
            immut.append((i + BANK_BASE, "IMMUTABLE", prev[i], new[i]))
    return phys, immut
