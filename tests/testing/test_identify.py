"""Tests for register cross-correlation helpers (identify.py)."""

import pytest

from givenergy_modbus.model.register import HR, IR
from givenergy_modbus.model.register_cache import RegisterCache
from givenergy_modbus.testing.identify import (
    identify,
    sentinel_devices,
)

# ---------------------------------------------------------------------------
# sentinel_devices
# ---------------------------------------------------------------------------


def test_sentinel_devices_overlays_values():
    """Sentinel value at each address equals address + offset."""
    base: dict[int, RegisterCache] = {0x31: RegisterCache()}
    spec = [(0x31, IR, range(10, 15))]
    devices = sentinel_devices(base, spec, offset=0)
    for addr in range(10, 15):
        assert devices[0x31][IR(addr)] == addr


def test_sentinel_devices_offset():
    """offset=K shifts every sentinel value by K."""
    base: dict[int, RegisterCache] = {0x31: RegisterCache()}
    spec = [(0x31, IR, range(50, 55))]
    devices = sentinel_devices(base, spec, offset=1000)
    for addr in range(50, 55):
        assert devices[0x31][IR(addr)] == addr + 1000


def test_sentinel_devices_creates_new_device():
    """A device_address not in base is created automatically."""
    base: dict[int, RegisterCache] = {}
    spec = [(0x11, HR, range(0, 5))]
    devices = sentinel_devices(base, spec)
    assert 0x11 in devices
    assert devices[0x11][HR(3)] == 3


def test_sentinel_devices_does_not_mutate_base():
    """Base caches are not modified."""
    cache = RegisterCache({IR(10): 999})
    base = {0x31: cache}
    sentinel_devices(base, [(0x31, IR, range(10, 12))])
    assert cache[IR(10)] == 999  # original untouched


def test_sentinel_devices_preserves_non_overlaid_registers():
    """Registers outside the spec range keep their base values."""
    base = {0x31: RegisterCache({IR(5): 42})}
    spec = [(0x31, IR, range(10, 15))]
    devices = sentinel_devices(base, spec)
    assert devices[0x31][IR(5)] == 42


# ---------------------------------------------------------------------------
# identify — single-pass
# ---------------------------------------------------------------------------


def test_identify_single_pass_deci():
    """Deci register: displayed = address * 0.1 → candidate address recovered."""
    # Address 2427 at deci scale → displayed 242.7
    candidates = identify(242.7)
    addrs_at_deci = [c.address for c in candidates if abs(c.scale - 0.1) < 1e-9]
    assert 2427 in addrs_at_deci


def test_identify_single_pass_uint16():
    """uint16 register: displayed = address (scale 1.0)."""
    # Address 100 at scale 1.0 → displayed 100.0
    candidates = identify(100.0)
    addrs_at_unit = [c.address for c in candidates if abs(c.scale - 1.0) < 1e-9]
    assert 100 in addrs_at_unit


def test_identify_single_pass_centi():
    """Centi register: displayed = address * 0.01."""
    # Address 4998 at centi scale → displayed 49.98
    candidates = identify(49.98)
    addrs_at_centi = [c.address for c in candidates if abs(c.scale - 0.01) < 1e-9]
    assert 4998 in addrs_at_centi


def test_identify_single_pass_range_filter():
    """reg_range filters candidates to those whose address falls in the range."""
    candidates = identify(242.7, reg_range=range(2400, 2500))
    assert all(2400 <= c.address < 2500 for c in candidates)
    assert any(c.address == 2427 for c in candidates)


def test_identify_single_pass_non_integer_address_excluded():
    """Non-integer inverses at a given scale are excluded; only integer-address scales returned."""
    # 0.37 → uint16: 0.37 (not int, excluded), deci: 3.7 (not int, excluded),
    #         centi: 37.0 (int, included), milli: 370 (int, included)
    candidates = identify(0.37)
    scales = {c.scale for c in candidates}
    assert 0.01 in scales  # centi: 0.37/0.01 = 37 ✓
    assert 1.0 not in scales  # uint16: 0.37 not an integer
    assert 0.1 not in scales  # deci: 3.7 not an integer


def test_identify_single_pass_returns_all_candidates():
    """Single-pass may return multiple candidates (one per matching scale)."""
    # 10.0 → uint16: 10, deci: 100, centi: 1000, milli: 10000 — all valid integers
    candidates = identify(10.0)
    assert len(candidates) >= 2  # at least uint16 + deci match


def test_identify_single_pass_no_duplicates():
    """No duplicate (address, scale) pairs even when multiple scale names match."""
    candidates = identify(100.0)
    seen = [(c.address, c.scale) for c in candidates]
    assert len(seen) == len(set(seen))


# ---------------------------------------------------------------------------
# identify — two-pass
# ---------------------------------------------------------------------------


def test_identify_two_pass_deci():
    """Two-pass uniquely recovers address and scale for a deci register."""
    # Address 2427, deci (0.1): pass1=242.7, pass2=(2427+1000)/10=342.7
    candidates = identify(242.7, 342.7, k=1000)
    assert len(candidates) == 1
    c = candidates[0]
    assert c.address == 2427
    assert abs(c.scale - 0.1) < 1e-9
    assert c.confidence == "two-pass"


def test_identify_two_pass_uint16():
    """Two-pass for a uint16 register (scale=1.0)."""
    # Address 100, scale 1.0: pass1=100, pass2=100+1000=1100
    candidates = identify(100.0, 1100.0, k=1000)
    assert len(candidates) == 1
    assert candidates[0].address == 100
    assert abs(candidates[0].scale - 1.0) < 1e-9


def test_identify_two_pass_centi():
    """Two-pass for a centi register."""
    # Address 4998, centi (0.01): pass1=49.98, pass2=(4998+1000)*0.01=59.98
    candidates = identify(49.98, 59.98, k=1000)
    assert len(candidates) == 1
    assert candidates[0].address == 4998
    assert abs(candidates[0].scale - 0.01) < 1e-9


def test_identify_invalid_k_raises():
    """identify() raises ValueError for non-positive k."""
    with pytest.raises(ValueError, match="k must be a positive integer"):
        identify(100.0, 200.0, k=0)
    with pytest.raises(ValueError, match="k must be a positive integer"):
        identify(100.0, 200.0, k=-1)


def test_identify_two_pass_equal_values_returns_empty():
    """If both passes show the same value (zero diff), return empty."""
    assert identify(100.0, 100.0, k=1000) == []


def test_identify_two_pass_negative_diff_returns_empty():
    """Negative scale is physically meaningless."""
    # d2 < d1 → negative scale
    assert identify(342.7, 242.7, k=1000) == []


def test_identify_two_pass_range_filter():
    """reg_range filter applies to two-pass results."""
    candidates = identify(242.7, 342.7, k=1000, reg_range=range(2000, 2500))
    assert len(candidates) == 1
    assert candidates[0].address == 2427

    # Exclude the address
    candidates_filtered = identify(242.7, 342.7, k=1000, reg_range=range(3000, 4000))
    assert candidates_filtered == []


# ---------------------------------------------------------------------------
# sentinel_devices + identify round-trip
# ---------------------------------------------------------------------------


def test_sentinel_identify_round_trip_deci():
    """End-to-end: seed a deci register, read the forward value, recover address."""
    address = 377  # hypothetical temperature register
    scale = 0.1  # C.deci
    base = {0x31: RegisterCache()}

    # Pass 1: seed value = address
    devices1 = sentinel_devices(base, [(0x31, IR, range(370, 385))], offset=0)
    raw1 = devices1[0x31][IR(address)]
    d1 = raw1 * scale  # simulate app displaying the value

    # Pass 2: seed value = address + K
    k = 1000
    devices2 = sentinel_devices(base, [(0x31, IR, range(370, 385))], offset=k)
    raw2 = devices2[0x31][IR(address)]
    d2 = raw2 * scale

    candidates = identify(d1, d2, k=k)
    assert len(candidates) == 1
    assert candidates[0].address == address
    assert abs(candidates[0].scale - scale) < 1e-9
    assert candidates[0].confidence == "two-pass"


def test_sentinel_identify_round_trip_uint16():
    """uint16 registers round-trip through sentinel_devices + identify."""
    address = 100  # battery SOC
    base = {0x11: RegisterCache()}
    k = 1000

    devices1 = sentinel_devices(base, [(0x11, HR, range(95, 110))], offset=0)
    d1 = float(devices1[0x11][HR(address)])

    devices2 = sentinel_devices(base, [(0x11, HR, range(95, 110))], offset=k)
    d2 = float(devices2[0x11][HR(address)])

    candidates = identify(d1, d2, k=k, reg_range=range(95, 110))
    assert len(candidates) == 1
    assert candidates[0].address == address


# ---------------------------------------------------------------------------
# sentinel_devices — validation
# ---------------------------------------------------------------------------


def test_sentinel_devices_overflow_raises():
    """sentinel_devices raises ValueError when address + offset exceeds uint16 max."""
    base: dict[int, RegisterCache] = {0x31: RegisterCache()}
    spec = [(0x31, IR, range(65530, 65540))]
    with pytest.raises(ValueError, match="is out of the valid 16-bit unsigned integer range"):
        sentinel_devices(base, spec, offset=10)


def test_sentinel_devices_max_valid_address():
    """Address + offset = 65535 is accepted."""
    base: dict[int, RegisterCache] = {0x31: RegisterCache()}
    spec = [(0x31, IR, range(65535, 65536))]
    devices = sentinel_devices(base, spec, offset=0)
    assert devices[0x31][IR(65535)] == 65535


def test_sentinel_devices_address_zero():
    """Register address 0 is valid and correctly seeded."""
    base: dict[int, RegisterCache] = {0x11: RegisterCache()}
    spec = [(0x11, HR, range(0, 3))]
    devices = sentinel_devices(base, spec)
    assert devices[0x11][HR(0)] == 0


# ---------------------------------------------------------------------------
# identify — address 0 and two-pass scale snapping
# ---------------------------------------------------------------------------


def test_identify_single_pass_address_zero():
    """Register 0 at uint16 scale (displayed 0.0) should be a candidate."""
    # Seeded value = 0 → displayed 0.0 at scale 1.0 → address = 0
    candidates = identify(0.0, reg_range=range(0, 5))
    # address=0 at scale=1.0 should be included
    assert any(c.address == 0 and abs(c.scale - 1.0) < 1e-9 for c in candidates)


def test_identify_two_pass_snaps_to_known_scale():
    """Two-pass result uses the snapped known scale even with minor rounding."""
    # Simulate app rounding: true deci scale 0.1, displayed values rounded to 1dp
    # d1 = 24.2 (true: 242 * 0.1), d2 = 124.2 (true: (242+1000) * 0.1)
    # diff / k = 100.0 / 1000 = 0.1 exactly — scale snaps to 0.1
    candidates = identify(24.2, 124.2, k=1000)
    assert len(candidates) == 1
    assert abs(candidates[0].scale - 0.1) < 1e-9
    assert candidates[0].address == 242


def test_identify_two_pass_unknown_scale_returns_empty():
    """Two-pass returns empty if computed scale doesn't match any known converter."""
    # d2 - d1 = 3 with k=1000 → scale = 0.003 — not in CONVERTER_SCALES
    candidates = identify(1.0, 4.0, k=1000)
    assert candidates == []


# ---------------------------------------------------------------------------
# MockPlant.from_sentinels integration
# ---------------------------------------------------------------------------


def test_mock_plant_from_sentinels_overlays_values():
    """from_sentinels seeds sentinel values on top of the base capture."""
    from pathlib import Path

    from givenergy_modbus.testing import MockPlant

    fixture = (
        Path(__file__).parent.parent
        / "fixtures/captures/hybrid_2_bat_a/hybrid_gen1_arm449_givbat82_givbat95gen3_60min.log"
    )
    if not fixture.exists():
        pytest.skip("fixture not available")

    spec = [(0x31, IR, range(100, 105))]
    mock = MockPlant.from_sentinels(fixture, spec=spec, offset=500)
    # Sentinel: IR(100) should be 600 (= 100 + 500)
    assert mock.devices[0x31][IR(100)] == 600
