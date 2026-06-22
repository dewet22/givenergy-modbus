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

Thresholds are in raw register units, set comfortably above what the quantity can really do
in a ~30 s poll interval — cell voltages move little near idle but sag under load, cell-mass
temperatures drift, the junction-adjacent MOSFET sensor steps (hence its much wider
threshold), capacities move with charge current and step on recalibration. Status/bitfield
words carry no physics and are exempt (IR(91) legitimately toggles 0x0E10 <-> 0x0610 every
few minutes). ``num_cells``, ``bms_firmware_version`` and the serial block are constant —
ANY transient change is corruption on its own.

The original Gen1-calibrated corpus separated cleanly, but field reports from higher-power
hardware (hass#186, an AC3 + 2x Giv-Bat 5.2: a ~103 mV cell sag on a load step, a ~10 Ah
capacity recalibration) showed legitimate per-poll deltas just past the ``cell_mV`` (100) and
``cap_centiAh`` (1000) thresholds — caught by the singleton escrow but noisy. Both were widened
(cell_mV->150, cap_centiAh->1500). This is safe because the corpus's *only* corruption signature
is the temperature-zero cohort (>=2 temp registers -> rejected outright): no corruption has ever
presented as a lone ``cell_mV`` or ``cap_centiAh`` delta, so widening exactly these two classes
(temps untouched) cannot weaken detection, and any residual over-threshold singleton still
escrows.

Indices throughout are **bank-relative** (``i`` == register ``IR(60 + i)``); the trips
returned carry the **absolute** IR number for logging.
"""

from __future__ import annotations

#: Battery banks span IR(60..119); index ``i`` here is register ``IR(BANK_BASE + i)``.
BANK_BASE = 60

# (class name, bank-relative indices, threshold on |delta| in raw units).
SCALAR_RULES: list[tuple[str, list[int], int]] = [
    # IR(60-75) cells: ~10 mV/poll at idle, but a higher-power inverter (e.g. AC3) sags a cell
    # ~100+ mV on a charge<->discharge load step (I×R) — see hass#186; 150 clears that with margin.
    ("cell_mV", list(range(0, 16)), 150),
    ("cell_temp_deci", [16, 17, 18, 19, 43, 44], 50),  # IR(76-79,103,104): thermal mass
    ("mosfet_temp_deci", [21], 200),  # IR(81): junction-adjacent, steps with load
    ("v_cells_sum_mV", [20], 1600),  # IR(80)
    ("soc_pct", [40], 10),  # IR(100)
    ("e_total_deci", [45, 46], 50),  # IR(105/106) lifetime energy
]
# uint32 pairs: (class name, (high index, low index), threshold on the assembled pair value).
# cap_centiAh 1500: capacity recalibration (coulomb-count correction) can step ~10 Ah in one poll
# on a larger pack — see hass#186.
PAIR_RULES: list[tuple[str, tuple[int, int], int]] = [
    ("v_out_mV", (22, 23), 2000),  # IR(82-83)
    ("cap_centiAh", (24, 25), 1500),  # IR(84-85) cap_calibrated
    ("cap_centiAh", (26, 27), 1500),  # IR(86-87) cap_design
    ("cap_centiAh", (28, 29), 1500),  # IR(88-89) cap_remaining
    ("cap_centiAh", (41, 42), 1500),  # IR(101-102) cap_design2
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

#: Maximum plausible gap (seconds) between consecutive *observed* battery banks. If the guard
#: sees no full bank for a device for longer than this, the next one arrives after a genuine
#: polling outage (network drop / prolonged refresh failure): the cached baseline is too stale
#: for the per-poll physics thresholds — legitimate SOC/temp/cap drift would exceed them — so the
#: guard resets to cold-start semantics and adopts it.
#: Critically this is measured against the last *observed* bank, NOT the last accepted commit. A
#: sustained corruption run (e.g. a multi-poll temp-zero stream, an observed #256 shape) keeps
#: arriving each poll and is rejected each poll; its last *good commit* ages past this bound, but
#: the observation clock stays ~one poll old, so the bypass never fires and corruption stays
#: rejected for as long as it lasts.
#: Value: 10× the nominal ~30 s poll interval — survives transient hiccups, recovers a real outage
#: on the first post-reconnect poll.
STALE_BYPASS_SECONDS: int = 300

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
