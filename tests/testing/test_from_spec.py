"""MockPlant.from_spec — declarative synthetic register state (#324).

`from_spec` builds a servable mock from a pure register spec (no base capture), and
with ``verify=True`` round-trips every bank through a scratch ``Plant.update()`` to
prove the synthetic state would survive the client's commit guards — the capgen
lesson from #265: a bank can *serve* fine yet be silently rejected on ingest (splice
guard, cold-start hold, impossible-frame refusal), which reads as "client sees
nothing" when interrogating the app against a mock.
"""

from __future__ import annotations

import pytest

from givenergy_modbus.model.register import HR, IR, MR
from givenergy_modbus.testing import MockPlant


def _healthy_battery_values() -> list[int]:
    """A coherent LV battery IR(60,60) bank that commits through the splice guard."""
    values = [0] * 60
    for i in range(16):  # 16 cells @ 3.300 V
        values[i] = 3300
    for i in range(16, 20):  # IR76-79 cell-mass temps @ 25.0 degC
        values[i] = 250
    values[20] = 52800  # IR80 v_cells_sum
    values[37] = 16  # IR97 num_cells
    values[38] = 3005  # IR98 bms_firmware_version
    values[40] = 55  # IR100 soc
    # valid serial "SA1234A567" at IR(110-114)
    values[50:55] = [0x5341, 0x3132, 0x3334, 0x4135, 0x3637]
    return values


def _impossible_battery_values() -> list[int]:
    """The #350 internally-impossible shape: every cell 0 V while firmware/capacity persist."""
    values = _healthy_battery_values()
    for i in range(16):
        values[i] = 0
    return values


def test_from_spec_builds_caches():
    """Registers land in per-device caches exactly as specced; serials default."""
    mock = MockPlant.from_spec(
        {
            0x11: {(HR, 0): [0x2001, 17], (IR, 0): [1, 2, 3]},
            0x32: {(IR, 60): [3300, 3301]},
        },
        verify=False,
    )
    assert mock.devices[0x11][HR(0)] == 0x2001
    assert mock.devices[0x11][HR(1)] == 17
    assert mock.devices[0x11][IR(2)] == 3
    assert mock.devices[0x32][IR(61)] == 3301
    assert mock.inverter_serial  # falls back to the placeholder serial


def test_from_spec_verify_commits_healthy_banks():
    """verify=True passes when every bank survives Plant.update().

    Covers the cold-start-held battery bank, which needs the corroborating second
    feed (#289). The inverter bank embeds a valid serial at HR(13-17): the commit
    path discards an inverter bank whose serial words don't validate — the exact
    class of silent rejection verify exists to surface.
    """
    inverter_bank = [0x2001] + [0] * 59
    inverter_bank[13:18] = [0x5341, 0x3132, 0x3334, 0x4135, 0x3637]  # "SA1234A567"
    mock = MockPlant.from_spec(
        {
            0x11: {(HR, 0): inverter_bank},
            0x32: {(IR, 60): _healthy_battery_values()},
        },
        verify=True,
    )
    assert mock.devices[0x32][IR(98)] == 3005


def test_from_spec_verify_raises_on_guard_rejected_bank():
    """A guard-refused bank (impossible battery frame, #350) fails verification.

    The error names the device and bank — instead of serving state no client
    will ever ingest.
    """
    with pytest.raises(ValueError, match=r"0x32.*IR.*60"):
        MockPlant.from_spec(
            {0x32: {(IR, 60): _impossible_battery_values()}},
            verify=True,
        )


def test_from_spec_verify_rejects_unsupported_register_class():
    """Only HR/IR banks exist on the read wire; anything else cannot round-trip update()."""
    with pytest.raises(ValueError, match="MR"):
        MockPlant.from_spec({0x01: {(MR, 0): [1, 2]}}, verify=True)


def test_from_spec_unverified_allows_any_register_class():
    """verify=False seeds caches verbatim — MR and friends allowed for direct-cache use."""
    mock = MockPlant.from_spec({0x01: {(MR, 0): [7]}}, verify=False)
    assert mock.devices[0x01][MR(0)] == 7


@pytest.mark.parametrize("bad_value", [70000, -1, 0x10000])
@pytest.mark.parametrize("verify", [True, False])
def test_from_spec_rejects_unencodable_register_words(bad_value: int, verify: bool):
    """Register words outside uint16 can never be encoded onto the wire (Codex, PR #391).

    Plant.update() carries Python ints without range checks, so verification alone
    passed 70000 — and the mock then crashed in struct.pack("H") on the first client
    read of the bank. The range check is unconditional: an unencodable word is invalid
    regardless of verify (verify=False only skips the commit-guard round-trip).
    """
    with pytest.raises(ValueError, match=r"0x11.*HR\(1\)"):
        MockPlant.from_spec({0x11: {(HR, 0): [0x2001, bad_value]}}, verify=verify)
