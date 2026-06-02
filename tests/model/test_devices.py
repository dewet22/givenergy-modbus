"""Tests for the unified Inverter facade and InverterSummary.

Phase 1 of the Plant refactor — see ``docs/v2.1-roadmap.md`` for the
wider design these tests verify.
"""

from givenergy_modbus.model.devices import Inverter, InverterSummary
from givenergy_modbus.model.ems import Ems
from givenergy_modbus.model.inverter import Model, Status
from givenergy_modbus.model.plant import Plant, PlantCapabilities
from givenergy_modbus.model.register import IR
from givenergy_modbus.model.register_cache import RegisterCache

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _encode_serial(serial: str) -> dict[int, int]:
    """Encode a 10-char serial as the five raw IR values the EMS rollup expects.

    Slot 1 uses IR(2066..2070); callers shift the keys for other slots.
    Returns ``{0: reg_value_0, 1: reg_value_1, ...}`` keyed by offset so
    the caller can compose into the right slot.
    """
    assert len(serial) == 10, f"serial must be 10 chars, got {len(serial)}"
    out = {}
    for i in range(5):
        hi = ord(serial[i * 2])
        lo = ord(serial[i * 2 + 1])
        out[i] = (hi << 8) | lo
    return out


def _add_rollup_slot(values: dict, slot: int, *, serial: str, **fields) -> dict:
    """Add one managed-inverter slot's register values into ``values`` in place.

    ``slot`` is 1-based. Optional kwargs populate the per-slot fields:
    ``status``, ``power``, ``soc``, ``temp_deci`` (raw deci-scaled).

    Mutates and returns ``values`` so callers can chain. The shared
    bitfield register IR(2045) (which packs status for all 4 slots into
    one word) is OR-merged with whatever is already there — necessary
    when multiple slots are added sequentially, otherwise slot 2's
    status would overwrite slot 1's.
    """
    serial_offset = 2066 + (slot - 1) * 5
    for i, v in _encode_serial(serial).items():
        values[IR(serial_offset + i)] = v
    if "power" in fields:
        # IR(2054..2057) holds inverter_N_power, slot 1 = 2054
        values[IR(2053 + slot)] = fields["power"] & 0xFFFF
    if "soc" in fields:
        # IR(2058..2061) holds inverter_N_soc, slot 1 = 2058
        values[IR(2057 + slot)] = fields["soc"]
    if "temp_deci" in fields:
        # IR(2062..2065) holds inverter_N_temp at C.deci scaling
        values[IR(2061 + slot)] = fields["temp_deci"]
    if "status" in fields:
        # IR(2045) packs 4 inverter statuses as 3-bit fields, LSB-first:
        # slot N occupies bits [(3N-3):(3N-1)] from the LSB, so shifts are 0, 3, 6, 9.
        shift = (slot - 1) * 3
        values[IR(2045)] = values.get(IR(2045), 0) | ((fields["status"] & 0x7) << shift)
    return values


# ---------------------------------------------------------------------------
# InverterSummary
# ---------------------------------------------------------------------------


def test_inverter_summary_construction():
    """Dataclass holds the five summary fields plus optional defaults."""
    s = InverterSummary(serial_number="XX1234A567")
    assert s.serial_number == "XX1234A567"
    assert s.status is None
    assert s.p_inverter_out is None
    assert s.battery_soc is None
    assert s.t_inverter_heatsink is None

    s2 = InverterSummary(
        serial_number="XX1234A567",
        status=Status.NORMAL,
        p_inverter_out=2500,
        battery_soc=72,
        t_inverter_heatsink=35.0,
    )
    assert s2.p_inverter_out == 2500
    assert s2.battery_soc == 72


# ---------------------------------------------------------------------------
# Unified Inverter facade
# ---------------------------------------------------------------------------


def test_unified_inverter_from_summary_is_blinded():
    """from_summary() produces a blinded inverter; fields resolve from the summary."""
    s = InverterSummary(
        serial_number="XX1234A567",
        status=Status.NORMAL,
        p_inverter_out=1800,
        battery_soc=65,
        t_inverter_heatsink=28.5,
    )
    inv = Inverter.from_summary(s)

    assert inv.data_source == "ems_rollup"
    assert inv.is_blinded is True
    assert inv.serial_number == "XX1234A567"
    assert inv.status == Status.NORMAL
    assert inv.p_inverter_out == 1800
    assert inv.battery_soc == 65
    assert inv.t_inverter_heatsink == 28.5

    # Blinded inverters honestly report no batteries — see plan, not stubs.
    assert inv.batteries == []
    assert inv.direct is None
    assert inv.summary is s


def test_unified_inverter_from_direct_not_blinded():
    """from_direct() produces a not-blinded inverter that reads through to the source."""

    class FakeDirect:
        serial_number = "ZZ9876B543"
        status = Status.NORMAL
        battery_soc = 88
        t_inverter_heatsink = 31.2
        # p_inverter_out intentionally absent — single-phase direct sources don't expose it.

    inv = Inverter.from_direct(FakeDirect())

    assert inv.data_source == "direct"
    assert inv.is_blinded is False
    assert inv.serial_number == "ZZ9876B543"
    assert inv.battery_soc == 88
    assert inv.t_inverter_heatsink == 31.2
    # p_inverter_out not exposed on single-phase direct → resolves to None
    assert inv.p_inverter_out is None
    assert inv.summary is None


def test_unified_inverter_merge_prefers_direct_then_summary():
    """merge() prefers the direct source per-field; the summary fills only what's missing."""

    class FakeDirect:
        serial_number = "ZZ9876B543"
        status = Status.NORMAL
        battery_soc = 90
        t_inverter_heatsink = 30.0
        # p_inverter_out missing on direct — summary should fill it.

    summary = InverterSummary(
        serial_number="ZZ9876B543",
        status=Status.WAITING,  # superseded by direct
        p_inverter_out=2200,  # only source — fills the gap
        battery_soc=65,  # superseded by direct
        t_inverter_heatsink=27.0,  # superseded by direct
    )

    inv = Inverter.merge(FakeDirect(), summary)

    assert inv.data_source == "merged"
    assert inv.is_blinded is False  # direct present
    # Direct preferred where present:
    assert inv.status == Status.NORMAL
    assert inv.battery_soc == 90
    assert inv.t_inverter_heatsink == 30.0
    # Summary fills the gap direct can't:
    assert inv.p_inverter_out == 2200


def test_blinded_inverter_reports_empty_batteries():
    """Regression-style: a blinded inverter must return an empty battery list, not stubs.

    The EMS rollup doesn't expose per-battery serials/SoC/cell voltages,
    so honestly answering "we cannot see batteries from here" is the
    contract. Consumers iterating ``inverter.batteries`` see an empty
    iterable rather than fake ``is_valid=False`` placeholders.
    """
    inv = Inverter.from_summary(InverterSummary(serial_number="XX1234A567"))
    assert inv.batteries == []


# ---------------------------------------------------------------------------
# Ems.managed_inverters
# ---------------------------------------------------------------------------


def test_ems_managed_inverters_constructs_summaries_per_populated_slot():
    """Ems.managed_inverters yields one InverterSummary per non-empty slot."""
    values: dict = {IR(2044): 2}  # inverter_count = 2
    _add_rollup_slot(
        values,
        1,
        serial="XX1234A567",
        power=1800,
        soc=65,
        temp_deci=285,  # 28.5 °C (deci scaling)
        status=2,  # per-slot EMS status code (2 = present/idle, the verified value)
    )
    _add_rollup_slot(
        values,
        2,
        serial="ZZ9876B543",
        power=2200,
        soc=78,
        temp_deci=312,
        status=2,
    )
    ems = Ems.from_register_cache(RegisterCache(values))

    managed = ems.managed_inverters
    assert len(managed) == 2
    assert managed[0].serial_number == "XX1234A567"
    # Asserting on status as well as the simpler fields guards the bitfield
    # encode/decode contract — the bit positions for the per-slot status
    # fields are MSB-first (see ``Converter.bitfield``), so a regression in
    # the encoder shift direction or in the decoder slice would surface here.
    # The per-slot status is an uninterpreted hex code (#108), so code 2 → "2".
    assert managed[0].status == "2"
    assert managed[0].p_inverter_out == 1800
    assert managed[0].battery_soc == 65
    assert managed[0].t_inverter_heatsink == 28.5
    assert managed[1].serial_number == "ZZ9876B543"
    assert managed[1].status == "2"
    assert managed[1].p_inverter_out == 2200


def test_ems_managed_inverters_strips_serial_padding():
    """Serial numbers with trailing null / space padding must be stripped before storage.

    The EMS pads short or empty serials with null bytes. The stored
    ``InverterSummary.serial_number`` is used later for reconciliation
    against directly-reported inverter serials, which arrive without
    that padding — comparison would silently fail if we stored the
    raw padded form.
    """
    # Build slot 1 with a 9-char serial "XX1234A56" plus a trailing space byte in the
    # last register. The raw decoded form is "XX1234A56 " (10 chars, trailing space),
    # which is what ``Converter.string`` returns; the strip path must trim it back to
    # "XX1234A56". Earlier revisions of this test used a 10-char serial that exactly
    # filled the register block, leaving no padding to trim — the test passed even
    # without the strip call. Use a partial-padding case so the strip codepath is
    # genuinely exercised.
    values = {
        IR(2044): 1,
        IR(2066): (ord("X") << 8) | ord("X"),
        IR(2067): (ord("1") << 8) | ord("2"),
        IR(2068): (ord("3") << 8) | ord("4"),
        IR(2069): (ord("A") << 8) | ord("5"),
        IR(2070): (ord("6") << 8) | ord(" "),
    }
    ems = Ems.from_register_cache(RegisterCache(values))

    managed = ems.managed_inverters
    assert len(managed) == 1
    # Trailing space stripped — stored serial is the 9-char unpadded form.
    assert managed[0].serial_number == "XX1234A56"


def test_ems_managed_inverters_skips_whitespace_only_serials():
    """A slot whose serial is purely whitespace / null bytes is treated as empty.

    Mirrors the strip-then-validate path that pairs with
    test_ems_managed_inverters_strips_serial_padding — establishes that
    the validity check operates on the same form as the stored value.
    """
    values = {
        IR(2044): 1,
        # All bytes 0x20 (space) — decodes to "          " which strips to "".
        IR(2066): 0x2020,
        IR(2067): 0x2020,
        IR(2068): 0x2020,
        IR(2069): 0x2020,
        IR(2070): 0x2020,
    }
    ems = Ems.from_register_cache(RegisterCache(values))
    assert ems.managed_inverters == []


def test_unified_inverter_falls_through_when_direct_has_no_serial():
    """A merged/direct facade with a missing or empty direct serial falls through to the summary.

    Defensive path: protects against a partially-populated direct
    source where the serial cache hasn't yet been read but the summary
    has. Keeps the facade honest rather than returning an empty string.
    """

    class FakeDirect:
        serial_number = ""  # falsy — should fall through to summary
        status = Status.NORMAL

    summary = InverterSummary(serial_number="XX1234A567", status=Status.NORMAL)
    inv = Inverter.merge(FakeDirect(), summary)

    assert inv.serial_number == "XX1234A567"


def test_ems_managed_inverters_skips_empty_slots():
    """Slots with empty / whitespace / null serial are filtered out.

    Mirrors the Meter.is_valid() pattern: signal of "nothing wired here"
    is a missing identity, not a separate flag.
    """
    values: dict = {IR(2044): 1}
    _add_rollup_slot(values, 1, serial="XX1234A567")
    # Slot 2 and beyond: deliberately leave serial registers unpopulated.
    ems = Ems.from_register_cache(RegisterCache(values))

    managed = ems.managed_inverters
    assert len(managed) == 1
    assert managed[0].serial_number == "XX1234A567"


# ---------------------------------------------------------------------------
# Plant.inverters
# ---------------------------------------------------------------------------


def test_plant_inverters_ems_returns_blinded_per_managed_slot():
    """For an EMS plant: one blinded Inverter per managed-inverter slot.

    The headline Phase 1 use case (Nick's installation): an EMS dongle
    with two managed inverters should surface as two ``Inverter``
    instances, each ``data_source="ems_rollup"`` and ``is_blinded=True``.
    """
    values: dict = {IR(2040): 1, IR(2044): 2}  # ems_status set, inverter_count = 2
    _add_rollup_slot(values, 1, serial="XX1234A567", power=1800, soc=65)
    _add_rollup_slot(values, 2, serial="ZZ9876B543", power=2200, soc=78)

    plant = Plant()
    plant.capabilities = PlantCapabilities(device_type=Model.EMS, inverter_address=0x32)
    plant.register_caches[0x32] = RegisterCache(values)

    inverters = plant.inverters
    assert len(inverters) == 2
    assert all(inv.is_blinded for inv in inverters)
    assert all(inv.data_source == "ems_rollup" for inv in inverters)
    serials = {inv.serial_number for inv in inverters}
    assert serials == {"XX1234A567", "ZZ9876B543"}


def test_plant_inverters_non_ems_returns_single_direct_inverter():
    """For a non-EMS plant: one Inverter wrapping the directly-decoded inverter.

    Back-compat shape: existing single-inverter consumers continue to
    work via ``plant.inverter`` (singular); the new ``plant.inverters``
    (plural) surface returns the same data wrapped in a ``data_source="direct"`` facade.
    """
    plant = Plant()
    plant.capabilities = PlantCapabilities(device_type=Model.HYBRID_GEN3, inverter_address=0x32)

    inverters = plant.inverters
    assert len(inverters) == 1
    assert inverters[0].data_source == "direct"
    assert inverters[0].is_blinded is False
    # The wrapped direct source is the same instance Plant.inverter returns.
    assert inverters[0].direct is not None
