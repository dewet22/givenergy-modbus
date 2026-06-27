"""Guard the app-vs-library register reconciliation.

The GivEnergy app's authoritative writable-register map lives at
docs/reference/registers/app_4.0.7_inventory.json; the diff against the library's
HR definitions is committed alongside it as app_4.0.7_reconciliation.json. This
test recomputes the diff from the live code and asserts it still equals the
committed report, so adding/removing a register Def can't silently shift the
reconciliation — an intentional change regenerates the report, an accidental one
fails here.

Regenerate after an intended change:
    uv run python scripts/audit_register_doc.py \
        --app-source docs/reference/registers/app_4.0.7_inventory.json \
        --json docs/reference/registers/app_4.0.7_reconciliation.json
"""

import json
import sys
from pathlib import Path

import pytest

# scripts/ isn't a package; make audit_register_doc.py importable by filename.
_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _REPO / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import audit_register_doc as audit  # noqa: E402, I001

_REGISTERS = _REPO / "docs" / "reference" / "registers"
_INVENTORY = _REGISTERS / "app_4.0.7_inventory.json"
_BASELINE = _REGISTERS / "app_4.0.7_reconciliation.json"


@pytest.fixture(scope="module")
def live_report() -> dict:
    code_regs, write_safe, _, installer_write = audit.introspect_code()
    app_hr = audit.load_app_inventory(_INVENTORY)
    return audit.diff_app_source(app_hr, code_regs, write_safe, installer_write)


def test_reconciliation_matches_committed_baseline(live_report):
    """The live app-vs-code diff equals the committed reconciliation report."""
    assert live_report == json.loads(_BASELINE.read_text(encoding="utf-8"))


def test_library_not_over_permissive(live_report):
    """Every write-safe HR is in the app's writable surface (no over-permission).

    This is an invariant, not a baseline number: nothing should be writable in
    the library that the manufacturer's app does not also expose as writable.
    """
    assert live_report["write_safe_coverage"]["write_safe_not_in_app"] == []


def test_installer_writes_not_over_permissive(live_report):
    """Every installer-write HR is in the app's writable surface (no over-permission).

    Same invariant as the standard write-safe set, applied to the installer tier:
    nothing should be installer-writable that the app's surface doesn't expose.
    """
    assert live_report["installer_write_coverage"]["installer_write_not_in_app"] == []
