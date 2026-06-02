"""Register-identification helpers for cross-correlating app display values to addresses.

The GivEnergy Android app's *Read Only* tab shows human-readable telemetry (e.g.
"Grid voltage 242.7 V") but hides register addresses.  These helpers let you figure
out which IR/HR address backs each label by seeding a :class:`MockPlant` with
*sentinel* values — raw register value = register address — then reading the
displayed value off the app and inverting the converter.

Workflow::

    # 1. Build a sentinel-overlaid mock from a real capture
    mock = MockPlant.from_sentinels(
        "path/to/plant.log",
        spec=[(0x31, IR, range(0, 240))],   # seed IR(0-239) with value = address
        offset=0,
    )
    await mock.start("0.0.0.0", 8899)

    # 2. Point the app at the mock, note each displayed value on the Read Only tab.
    #    e.g. app shows "Grid voltage  24.2 V"

    # 3. Identify the address
    candidates = identify(24.2)
    # → [Candidate(address=242, scale=0.1, confidence='single-pass'), ...]

    # 4. Run a second pass (offset=1000) to resolve ambiguity
    mock2 = MockPlant.from_sentinels(..., spec=..., offset=1000)
    # app now shows "Grid voltage 124.2 V"   (= (242+1000)/10)
    candidates = identify(24.2, 124.2, k=1000)
    # → [Candidate(address=242, scale=0.1, confidence='two-pass')]

Two-pass principle
------------------
For any *linear* converter with scale ``s`` (deci: 0.1, centi: 0.01, …):

    d1 = A * s          (offset=0)
    d2 = (A + K) * s    (offset=K)

    s = (d2 - d1) / K
    A = d1 / s

This uniquely recovers both the address and the scale without knowing the converter
up front.  Non-linear registers (uint32 pairs, timeslots, enums, bitfields) are not
auto-identifiable; those need a manual third-pass or direct probing.

Caveats
-------
- Choose K so that ``address + K ≤ 65535`` for all seeded addresses.  K=1000 is safe
  for addresses up to 64535, which covers every known GivEnergy register range.
- SoC-% and other clamped fields may clip implausible sentinel values; handle those
  with a third in-range pass or identify them manually.
- The displayed value may be rounded by the app; use a generous *tolerance*.
"""

from __future__ import annotations

from dataclasses import dataclass

from givenergy_modbus.model.register import Register
from givenergy_modbus.model.register_cache import RegisterCache

# Type alias for the sentinel specification:
# list of (device_address, register_class, address_range)
SentinelSpec = list[tuple[int, type[Register], range]]

# Linear converter scale factors: raw → displayed value.
# Non-linear converters (uint32, timeslot, datetime, string/serial, bitfield, enum)
# are not included — they can't be auto-identified by this method.
CONVERTER_SCALES: dict[str, float] = {
    "uint16": 1.0,
    "int16": 1.0,  # positive values behave identically to uint16
    "deci": 0.1,
    "centi": 0.01,
    "milli": 0.001,
}


@dataclass
class Candidate:
    """A candidate register address inferred from a displayed app value.

    Attributes:
        address: The inferred raw register address (integer, 0–65535).
        scale:   The inferred converter scale (1.0 = uint16, 0.1 = deci, …).
        confidence: ``"two-pass"`` when ``d2`` was provided (unique solution);
                    ``"single-pass"`` when only ``d1`` was given (may have duplicates).
    """

    address: int
    scale: float
    confidence: str  # "two-pass" | "single-pass"


def sentinel_devices(
    base: dict[int, RegisterCache],
    spec: SentinelSpec,
    *,
    offset: int = 0,
) -> dict[int, RegisterCache]:
    """Clone *base* and overlay sentinel values (raw = address + offset).

    Parameters
    ----------
    base:
        Per-device register caches, typically from
        ``plant_from_capture(...).register_caches``.  The returned dict is a
        *deep copy* — the original is not modified.
    spec:
        Sequence of ``(device_address, register_class, address_range)`` triples.
        For each triple, every address in ``address_range`` is written to the
        cache for ``device_address`` as ``register_class(addr): addr + offset``.
        Device addresses not present in *base* are created as empty caches.
    offset:
        Added to every sentinel value.  Pass 1 uses ``offset=0``; pass 2 uses
        ``offset=K`` (e.g. 1000).  Keep K small enough that
        ``max(address_range) + K ≤ 65535``.

    Returns:
    -------
    dict[int, RegisterCache]
        A fresh dict ready to pass to ``MockPlant(devices=...)``.
    """
    devices: dict[int, RegisterCache] = {addr: RegisterCache(dict(cache)) for addr, cache in base.items()}
    for device_address, reg_cls, reg_range in spec:
        if device_address not in devices:
            devices[device_address] = RegisterCache()
        cache = devices[device_address]
        for a in reg_range:
            cache[reg_cls(a)] = a + offset
    return devices


def identify(
    d1: float,
    d2: float | None = None,
    *,
    k: int = 1000,
    reg_range: range | None = None,
    tolerance: float = 1e-3,
) -> list[Candidate]:
    """Infer register address(es) from an app-displayed value.

    Parameters
    ----------
    d1:
        Value the app displayed for pass 1 (sentinel ``offset=0``).
    d2:
        Value the app displayed for pass 2 (sentinel ``offset=k``).
        When provided, the result is a unique two-pass identification.
        When ``None``, all single-pass candidates are returned.
    k:
        The offset used between the two sentinel passes.  Must match the
        ``offset`` argument passed to :func:`sentinel_devices` for pass 2.
    reg_range:
        Optional filter: only return candidates whose address falls in this
        range.  Useful when you know which bank was seeded.
    tolerance:
        Maximum deviation from an integer when checking whether the inferred
        address is a whole number.  Default 0.001 accommodates minor floating-
        point rounding in the app display.

    Returns:
    -------
    list[Candidate]
        For two-pass: at most one entry (empty if the maths doesn't resolve to
        a plausible integer address).
        For single-pass: one entry per scale factor whose inverse is an integer
        address (possibly multiple candidates — use two-pass to disambiguate).
    """
    if d2 is not None:
        return _identify_two_pass(d1, d2, k=k, reg_range=reg_range, tolerance=tolerance)
    return _identify_single_pass(d1, reg_range=reg_range, tolerance=tolerance)


def _identify_two_pass(
    d1: float,
    d2: float,
    *,
    k: int,
    reg_range: range | None,
    tolerance: float,
) -> list[Candidate]:
    diff = d2 - d1
    if abs(diff) < 1e-9:
        return []
    scale = diff / k
    if scale <= 0:
        return []
    address_float = d1 / scale
    address = round(address_float)
    if abs(address_float - address) > tolerance:
        return []
    if not (0 <= address <= 65535):
        return []
    if reg_range is not None and address not in reg_range:
        return []
    return [Candidate(address=address, scale=scale, confidence="two-pass")]


def _identify_single_pass(
    d1: float,
    *,
    reg_range: range | None,
    tolerance: float,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    for scale in CONVERTER_SCALES.values():
        address_float = d1 / scale
        address = round(address_float)
        if abs(address_float - address) > tolerance:
            continue
        if not (0 < address <= 65535):
            continue
        if reg_range is not None and address not in reg_range:
            continue
        # Deduplicate: uint16 and int16 have the same scale (1.0), skip second.
        if any(abs(c.scale - scale) < 1e-9 and c.address == address for c in candidates):
            continue
        candidates.append(Candidate(address=address, scale=scale, confidence="single-pass"))
    return candidates
