"""Reconcile the v4.1.6 firmware register inventory against the library's decode scales (#385).

Discovery + triage tool, NOT an auto-fixer. Reports where our converter scale diverges from
the doc's declared unit, plus doc-name vs field-name divergences (identity candidates). A
mismatch is a CANDIDATE — the extracted doc has its own errors, so verify each against a
committed fixture before changing decode (the IR23 caution). Sign is handled separately
(tests/model/test_register_conventions.py); this is the scale/identity continuation of #381.

    uv run python scripts/reconcile_v416.py [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# Scale helpers live in the sibling audit tool (scripts/ is sys.path[0] when run directly).
from audit_register_doc import _CONV_SCALE, _code_scale, _doc_scales

from givenergy_modbus.model.battery import BatteryRegisterGetter
from givenergy_modbus.model.hv_bcu import BcuRegisterGetter
from givenergy_modbus.model.inverter import SinglePhaseInverterRegisterGetter
from givenergy_modbus.model.inverter_threephase import ThreePhaseInverterRegisterGetter
from givenergy_modbus.model.lv_bcu import LvBcuRegisterGetter
from givenergy_modbus.model.meter import MeterProductRegisterGetter, MeterRegisterGetter

_INVENTORY = Path(__file__).resolve().parents[1] / "docs" / "reference" / "registers" / "v4.1.6_inventory.json"

# Doc section prefix → (reg_type, [getters]). The section disambiguates device + function code,
# so an address that collides across devices (e.g. IR76 = a cell temp on the battery bus but an
# inverter register at 0x11) matches only within its section's getter(s).
_SECTION_GETTERS: dict[str, tuple[str, list]] = {
    "4.1.1": ("HR", [SinglePhaseInverterRegisterGetter, ThreePhaseInverterRegisterGetter]),
    "4.1.2": ("IR", [SinglePhaseInverterRegisterGetter, ThreePhaseInverterRegisterGetter]),
    "4.2.1": ("IR", [MeterRegisterGetter]),
    "4.2.2": ("HR", [MeterProductRegisterGetter]),
    "4.4.1.1": ("IR", [LvBcuRegisterGetter]),
    "4.4.1.2": ("IR", [BatteryRegisterGetter]),
    "4.4.2.1": ("IR", [BcuRegisterGetter]),
    # 4.3 (AFCI) intentionally unmapped — no dedicated getter; entries report as unmatched.
}


def _conv_name(c) -> str | None:
    if c is None:
        return None
    if isinstance(c, tuple):
        return _conv_name(c[0])
    return getattr(c, "__name__", str(c))


def _iter_doc_entries(node, out: list[dict]) -> None:
    if isinstance(node, dict):
        if node.get("addr") is not None and node.get("section"):
            out.append(node)
        for v in node.values():
            _iter_doc_entries(v, out)
    elif isinstance(node, list):
        for v in node:
            _iter_doc_entries(v, out)


def _code_index() -> dict[tuple[str, str, int], tuple[str, set[str]]]:
    """(getter_name, reg_type, addr) → (field_name, {converter_names})."""
    idx: dict[tuple[str, str, int], tuple[str, set[str]]] = {}
    for getter in {g for _rt, gs in _SECTION_GETTERS.values() for g in gs}:
        for field, defn in getter.REGISTER_LUT.items():
            convs = {_conv_name(defn.pre_conv), _conv_name(defn.post_conv)} - {None}
            for reg in defn.registers:
                idx[(getter.__name__, type(reg).__name__, reg._idx)] = (field, convs)
    return idx


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def reconcile() -> dict[str, list[dict]]:
    """Return scale-mismatch / name-divergence / unmatched lists (doc ↔ code)."""
    doc: list[dict] = []
    _iter_doc_entries(json.load(_INVENTORY.open()), doc)
    code = _code_index()

    scale_mismatch, name_divergence, unmatched = [], [], []
    for e in doc:
        sec_key = e["section"].split()[0]
        mapping = _SECTION_GETTERS.get(sec_key)
        if mapping is None:
            continue  # unmapped section (e.g. AFCI) — not our concern here
        reg_type, getters = mapping
        addr, doc_name, unit = e["addr"], str(e.get("name") or ""), e.get("unit")

        hit = next(
            (
                (g.__name__, *code[(g.__name__, reg_type, addr)])
                for g in getters
                if (g.__name__, reg_type, addr) in code
            ),
            None,
        )
        if hit is None:
            unmatched.append({"section": sec_key, "type": reg_type, "addr": addr, "doc_name": doc_name})
            continue
        gname, field, convs = hit

        doc_scales = _doc_scales(unit or "")
        code_scale = _code_scale(convs)
        if doc_scales and code_scale is not None and code_scale not in doc_scales:
            scale_mismatch.append(
                {
                    "getter": gname,
                    "type": reg_type,
                    "addr": addr,
                    "doc_name": doc_name,
                    "field": field,
                    "doc_unit": unit,
                    "doc_scale": sorted(doc_scales),
                    "code_scale": code_scale,
                    "convs": sorted(convs),
                }
            )
        if doc_name and _norm(doc_name) != _norm(field):
            name_divergence.append(
                {
                    "getter": gname,
                    "type": reg_type,
                    "addr": addr,
                    "doc_name": doc_name,
                    "field": field,
                }
            )
    return {"scale_mismatch": scale_mismatch, "name_divergence": name_divergence, "unmatched": unmatched}


def main() -> None:
    """Run the reconciliation and print the triaged report (optionally dump JSON)."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--show-names", action="store_true", help="also print the (large) name-divergence list")
    args = ap.parse_args()

    result = reconcile()
    print(f"known code converters: {sorted(_CONV_SCALE)}\n")
    print(
        f"=== SCALE MISMATCHES ({len(result['scale_mismatch'])}) — verify each vs a fixture before changing decode ==="
    )
    for r in result["scale_mismatch"]:
        print(
            f"  §{r['type']}({r['addr']:<5}) {r['doc_name'][:22]:22} doc={r['doc_unit']!r}~{r['doc_scale']} "
            f"| {r['field']} code={r['code_scale']} {r['convs']}"
        )
    print(f"\n=== NAME DIVERGENCES ({len(result['name_divergence'])}) — identity candidates ===")
    for r in result["name_divergence"] if args.show_names else result["name_divergence"][:15]:
        print(f"  §{r['type']}({r['addr']:<5}) doc={r['doc_name'][:28]:28} | {r['getter']}.{r['field']}")
    if not args.show_names and len(result["name_divergence"]) > 15:
        print(f"  … {len(result['name_divergence']) - 15} more (use --show-names)")
    print(f"\nunmatched doc entries (no LUT coverage): {len(result['unmatched'])}")

    if args.json:
        args.json.write_text(json.dumps(result, indent=2))
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
