"""Audit the GivEnergy MODBUS protocol doc against the library's register map.

One-shot analysis tool (not part of the package). Parses the pandoc-rendered
protocol markdown into a structured register inventory, introspects the
library's REGISTER_LUTs + WRITE_SAFE_REGISTERS, and emits a triaged diff.

Usage:
    uv run python scripts/audit_register_doc.py <protocol.md> [--json out.json]

The doc is a series of pandoc grid tables under "### 4.x" / "## 4.x" headings.
Each register table has columns: Reg.Num | Variable Name | Description | R/W |
Value | Unit | Notes. Section-header rows span all columns (single cell).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

# --- Doc parsing -----------------------------------------------------------

HEADING_RE = re.compile(r"^(#{1,4})\s+(.*?)\s*#*\s*$")
SEP_RE = re.compile(r"^\+[-=:+]+\+?\s*$")


def _is_sep(line: str) -> bool:
    return bool(SEP_RE.match(line.strip()))


def _split_row(line: str) -> list[str]:
    # A grid-table data line: "| c0 | c1 | ... |". Strip the leading/trailing
    # pipe, split on the rest. Cells keep internal spaces; we strip per-cell.
    s = line.strip()
    if not s.startswith("|"):
        return []
    parts = s.split("|")[1:-1]
    return [p.strip() for p in parts]


@dataclass
class DocRegister:
    """One register row parsed from a protocol-doc grid table."""

    section: str
    addr: int | None
    addr_raw: str
    name: str
    description: str
    rw: str
    value: str
    unit: str
    notes: str

    @property
    def writable(self) -> bool:
        """True if the doc marks this register writable (R/W)."""
        return "W" in self.rw.upper()


def _parse_addr(raw: str) -> int | None:
    raw = raw.strip()
    if not raw:
        return None
    # Forms seen: "00", "12", "1143", "0x..", "44~47" (range -> first).
    m = re.match(r"^(0x[0-9a-fA-F]+|\d+)", raw.replace("\\", ""))
    if not m:
        return None
    tok = m.group(1)
    try:
        return int(tok, 16) if tok.lower().startswith("0x") else int(tok)
    except ValueError:
        return None


def _norm_header(cell: str) -> str | None:
    c = cell.replace("*", "").strip().lower().replace(".", "").replace(" ", "")
    if c in {"regnum", "reg"}:
        return "addr"
    if c in {"variablename", "variable", "name"}:
        return "name"
    if c in {"description", "describe"}:
        return "description"
    if c in {"r/w", "rw"}:
        return "rw"
    if c == "value":
        return "value"
    if c == "unit":
        return "unit"
    if c in {"note", "notes"}:
        return "notes"
    return None


def parse_doc(path: Path) -> list[DocRegister]:
    """Parse all register grid tables in the protocol doc into DocRegister rows."""
    lines = path.read_text(encoding="utf-8").splitlines()
    regs: list[DocRegister] = []
    section = "(preamble)"

    # Accumulate multi-line grid rows: between separator lines, a logical row
    # may span several physical lines (pandoc wraps long cells). We merge cells
    # column-wise across the physical lines of one logical row.
    pending: list[list[str]] = []
    in_table = False
    # Column layout of the current table, learned from its header row. Maps a
    # field name -> column index. Tables vary: HR has R/W, IR doesn't, etc.
    header: dict[str, int] = {}

    def flush_row(cols_lines: list[list[str]]):
        nonlocal header
        if not cols_lines:
            return
        width = max(len(c) for c in cols_lines)
        merged = []
        for i in range(width):
            parts = [c[i] for c in cols_lines if i < len(c) and c[i]]
            merged.append(" ".join(parts).strip())
        # Header row: detect by recognised column titles, learn the layout.
        mapped = {}
        for i, cell in enumerate(merged):
            key = _norm_header(cell)
            if key and key not in mapped:
                mapped[key] = i
        if "addr" in mapped and "name" in mapped:
            header = mapped
            return
        # Section-header / banner row: single non-empty cell. Skip.
        nonempty = [m for m in merged if m]
        if len(merged) <= 2 or len(nonempty) <= 1:
            return
        if not header or "addr" not in header:
            return

        def col(field: str) -> str:
            i = header.get(field)
            return merged[i].replace("*", "").strip() if i is not None and i < len(merged) else ""

        addr_raw = col("addr")
        name = col("name")
        if not addr_raw and not name:
            return
        addr = _parse_addr(addr_raw)
        regs.append(
            DocRegister(
                section=section,
                addr=addr,
                addr_raw=addr_raw,
                name=name,
                description=col("description"),
                rw=col("rw") or "R",
                value=col("value"),
                unit=col("unit"),
                notes=col("notes"),
            )
        )

    for line in lines:
        h = HEADING_RE.match(line)
        if h:
            section = h.group(2).replace("*", "").strip()
            in_table = False
            pending = []
            header = {}
            continue
        if _is_sep(line):
            flush_row(pending)
            pending = []
            in_table = True
            continue
        if in_table and line.strip().startswith("|"):
            cols = _split_row(line)
            if cols:
                pending.append(cols)
        elif line.strip() == "":
            continue
        else:
            # Non-table prose ends the current table.
            if in_table and pending:
                flush_row(pending)
            pending = []
            in_table = False
    flush_row(pending)
    return regs


# --- Code introspection ----------------------------------------------------


@dataclass
class CodeRegister:
    """A register address as mapped by the library's REGISTER_LUTs."""

    reg_type: str  # HR / IR / MR
    idx: int
    attrs: list[str] = field(default_factory=list)
    converters: set[str] = field(default_factory=set)
    getters: set[str] = field(default_factory=set)


def introspect_code() -> tuple[dict[tuple[str, int], CodeRegister], set[int], dict[str, dict[int, set[str]]]]:
    """Collect every register the library maps + the WRITE_SAFE address set.

    Also returns a per-getter view (getter name -> register index -> converter
    names) so device sections can be diffed against just their own getter,
    without inverter mappings at the same index muddying the comparison.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from givenergy_modbus.model.battery import BatteryRegisterGetter
    from givenergy_modbus.model.ems import EmsRegisterGetter
    from givenergy_modbus.model.gateway import GatewayV1RegisterGetter, GatewayV2RegisterGetter
    from givenergy_modbus.model.hv_bcu import BcuRegisterGetter
    from givenergy_modbus.model.inverter import SinglePhaseInverterRegisterGetter
    from givenergy_modbus.model.inverter_threephase import ThreePhaseInverterRegisterGetter
    from givenergy_modbus.model.meter import MeterProductRegisterGetter, MeterRegisterGetter
    from givenergy_modbus.pdu.write_registers import WRITE_SAFE_REGISTERS

    getters = {
        "battery": BatteryRegisterGetter,
        "ems": EmsRegisterGetter,
        "gateway_v1": GatewayV1RegisterGetter,
        "gateway_v2": GatewayV2RegisterGetter,
        "hv_bcu": BcuRegisterGetter,
        "inverter_1ph": SinglePhaseInverterRegisterGetter,
        "inverter_3ph": ThreePhaseInverterRegisterGetter,
        "meter": MeterRegisterGetter,
        "meter_product": MeterProductRegisterGetter,
    }

    def conv_name(c) -> str | None:
        if c is None:
            return None
        if isinstance(c, tuple):
            c = c[0]
        return getattr(c, "__name__", str(c))

    out: dict[tuple[str, int], CodeRegister] = {}
    by_getter: dict[str, dict[int, set[str]]] = {gname: {} for gname in getters}
    for gname, g in getters.items():
        for attr, defn in g.REGISTER_LUT.items():
            for reg in defn.registers:
                key = (reg._type, reg._idx)
                cr = out.setdefault(key, CodeRegister(reg._type, reg._idx))
                cr.attrs.append(f"{gname}.{attr}")
                cr.getters.add(gname)
                convs = by_getter[gname].setdefault(reg._idx, set())
                for c in (defn.pre_conv, defn.post_conv):
                    n = conv_name(c)
                    if n:
                        cr.converters.add(n)
                        convs.add(n)
    return out, set(WRITE_SAFE_REGISTERS), by_getter


# --- Diff ------------------------------------------------------------------

# Map doc section prefixes to the register type they describe + the code getter
# bucket they should diff against. The inverter HR/IR sections are diffed
# globally by address; the device sections below are each diffed against just
# their own getter (battery IRs share the IR number space with inverter IRs,
# so a global diff would mask gaps — IR(95) Im_Avg hid this way, see #238).
SECTION_TYPE = {
    "4.1.1": "HR",
    "4.1.2": "IR",
}

# Doc section prefix -> (report label, getter name or None when the library
# has no model for that device at all).
DEVICE_SECTIONS = {
    "4.2.1": ("meter", "meter"),
    "4.2.2": ("meter_product", "meter_product"),
    "4.4.1.1": ("lv_bcu", None),
    "4.4.1.2": ("battery", "battery"),
    "4.4.2.1": ("hv_bcu", "hv_bcu"),
}

# Code converters → the decimal scale they imply (multiplier applied to raw).
_CONV_SCALE = {
    "milli": 0.001,
    "centi": 0.01,
    "deci": 0.1,
    "uint16": 1.0,
    "int16": 1.0,
    "uint32": 1.0,
    "int32": 1.0,
}


def _doc_scale_single(u: str) -> float | None:
    """Scale of one cleaned, lower-cased doc unit token (e.g. '0.1v' -> 0.1)."""
    if not u or u in {"hex", "ascii", "-"}:
        return None
    # Milli-prefixed electrical units (mV/mA/mAh) measure in thousandths of the
    # base unit the code models (V/A/Ah), so fold the prefix into the scale.
    # Deliberately NOT generalised: 'min'/'ms' must keep their existing scale-1
    # reading so the #185 inverter-section baseline is undisturbed.
    m = re.match(r"^(\d*\.?\d+)?\s*(mv|mah|ma)\b", u)
    if m:
        return (float(m.group(1)) if m.group(1) else 1.0) * 0.001
    m = re.match(r"^(\d*\.?\d+)\s*[a-z%]", u)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    # A bare "10w"/"100w" style multiplier.
    m = re.match(r"^(\d+)\s*w", u)
    if m:
        return float(m.group(1))
    if re.match(r"^[a-z%]", u):  # plain unit, scale 1
        return 1.0
    # A bare numeric unit ("0.01" on the meter power-factor rows) is its scale —
    # but only a power of ten reads as one; "101" on HR46 is a version, not a scale.
    if re.match(r"^\d*\.?\d+$", u):
        f = float(u)
        if f > 0 and abs(round(math.log10(f)) - math.log10(f)) < 1e-9:
            return f
    return None


def _doc_scales(unit: str) -> set[float] | None:
    """All plausible scales of a doc unit string.

    Usually a single value, but meter rows give model-dependent alternatives
    ('0.1A/0.01A', '100W/1W') — a slash splits into alternatives only when
    every part is digit-leading, so rate units like '0.1% Pn/min' stay whole.
    """
    u = re.sub(r"[\[\]]|\{\.mark\}|\\", "", unit).strip().lower()
    if "/" in u:
        parts = [p.strip() for p in u.split("/")]
        if all(re.match(r"^\d", p) for p in parts):
            scales = {s for p in parts if (s := _doc_scale_single(p)) is not None}
            return scales or None
    s = _doc_scale_single(u)
    return {s} if s is not None else None


def _code_scale(convs: set[str]) -> float | None:
    """Effective scale of a Def's converters.

    A Def often pairs a width/sign converter (uint32/int16, scale 1) with a
    fractional one (deci/centi/milli). The fractional converter is what scales
    the displayed value, so take the smallest matched scale rather than relying
    on set-iteration order.
    """
    scales = [_CONV_SCALE[c] for c in convs if c in _CONV_SCALE]
    return min(scales) if scales else None


def _ascii(s: str) -> str:
    """Drop non-ASCII (e.g. CJK) so retained fields carry no verbatim doc prose."""
    return re.sub(r"\s+", " ", "".join(c for c in s if ord(c) < 128)).strip()


def _facts_row(r: DocRegister) -> dict:
    """Factual subset of a register row: address/name/unit/RW/range, ASCII-only.

    Drops the doc's `description` and `notes` (the verbatim, partly-Chinese prose) so
    the committed inventory carries reusable register *facts* without redistributing
    GivEnergy's proprietary documentation text.
    """
    return {
        "section": _ascii(r.section),
        "addr": r.addr,
        "addr_raw": _ascii(r.addr_raw),
        "name": _ascii(r.name),
        "rw": _ascii(r.rw),
        "value": _ascii(r.value),
        "unit": _ascii(r.unit),
    }


# --- App-source reconciliation ---------------------------------------------
#
# The GivEnergy mobile app embeds the manufacturer's own writable holding-register
# map; it is extracted (via blutter, from the Dart AOT snapshot) into a committed
# inventory at docs/reference/registers/app_<ver>_inventory.json. This diff
# reconciles that authoritative map against the library's HR definitions so gaps
# and name divergences surface as a repeatable check rather than a one-off script.


def load_app_inventory(path: Path) -> dict[int, dict]:
    """Load an app-derived inventory's holding_registers block as {addr: row}."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return {r["addr"]: r for r in data.get("holding_registers", []) if isinstance(r, dict) and "addr" in r}


def _name_tokens(s: str) -> set[str]:
    """Word tokens of a register name/attr, for low-overlap divergence detection."""
    if not isinstance(s, str):
        return set()
    return set(re.sub(r"[%/&_.]", " ", s.lower()).split())


def diff_app_source(
    app_hr: dict[int, dict],
    code_regs: dict[tuple[str, int], CodeRegister],
    write_safe: set[int],
) -> dict:
    """Reconcile an app-derived HR map against the library's HR definitions.

    Returns matched/gap/code-only counts, the gap list (app-writable HRs with no
    library Def — flagged when already write-safe, i.e. write-only), the set of
    matched HRs whose app label shares no token with any library attr name, and
    write-safety coverage both ways.
    """
    code_hr = {idx: cr for (rtype, idx), cr in code_regs.items() if rtype == "HR"}
    app_set, code_set, ws = set(app_hr), set(code_hr), set(write_safe)
    matched = sorted(app_set & code_set)

    name_divergence = []
    for a in matched:
        lib_tokens: set[str] = set()
        for attr in code_hr[a].attrs:
            lib_tokens |= _name_tokens(attr.split(".", 1)[1])
        if not (_name_tokens(app_hr[a]["name"]) & lib_tokens):
            name_divergence.append({"addr": a, "app_name": app_hr[a]["name"], "code_attrs": sorted(code_hr[a].attrs)})

    return {
        "app_hr_count": len(app_set),
        "code_hr_count": len(code_set),
        "matched_count": len(matched),
        "app_only_count": len(app_set - code_set),
        "app_only": [
            {"addr": a, "name": app_hr[a]["name"], "in_write_safe": a in ws} for a in sorted(app_set - code_set)
        ],
        "code_only": sorted(code_set - app_set),
        "name_divergence": name_divergence,
        "write_safe_coverage": {
            "app_writable_in_write_safe": sorted(app_set & ws),
            "write_safe_not_in_app": sorted(ws - app_set),
        },
    }


def run_app_reconciliation(app_source: Path, json_out: Path | None) -> int:
    """Reconcile the library's HR map against an app-derived inventory; print the diff."""
    code_regs, write_safe, _ = introspect_code()
    report = diff_app_source(load_app_inventory(app_source), code_regs, write_safe)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if json_out:
        json_out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nWrote app-reconciliation report to {json_out}", file=sys.stderr)
    return 0


def main() -> int:
    """Parse the doc, diff against the library, print a JSON report."""
    ap = argparse.ArgumentParser()
    ap.add_argument("doc", type=Path, nargs="?", default=None)
    ap.add_argument(
        "--app-source",
        type=Path,
        default=None,
        help="Reconcile against an app-derived inventory JSON instead of the protocol doc.",
    )
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument(
        "--facts-only",
        action="store_true",
        help="Emit only register facts (addr/name/unit/RW/range), dropping the doc's "
        "verbatim descriptions/notes. Use for a committable inventory.",
    )
    args = ap.parse_args()

    if args.app_source is not None:
        return run_app_reconciliation(args.app_source, args.json)

    if args.doc is None:
        ap.error("a protocol-doc path or --app-source is required")

    return run_doc_audit(args.doc, args.json, args.facts_only)


def run_doc_audit(doc: Path, json_out: Path | None, facts_only: bool) -> int:
    """Diff the protocol doc against the library's register map; print the report."""
    doc_regs = parse_doc(doc)
    code_regs, write_safe, by_getter = introspect_code()

    # Build doc HR/IR address sets from the inverter sections.
    doc_by_type: dict[str, dict[int, DocRegister]] = {"HR": {}, "IR": {}}
    for r in doc_regs:
        for prefix, rtype in SECTION_TYPE.items():
            if r.section.startswith(prefix) and r.addr is not None:
                # First wins (avoids later note-rows clobbering).
                doc_by_type[rtype].setdefault(r.addr, r)

    code_by_type: dict[str, dict[int, CodeRegister]] = {"HR": {}, "IR": {}, "MR": {}}
    for (rtype, idx), cr in code_regs.items():
        code_by_type.setdefault(rtype, {})[idx] = cr

    report: dict[str, object] = {}
    scale_mismatches: list[dict] = []
    for rtype in ("HR", "IR"):
        doc_set = set(doc_by_type[rtype])
        code_set = set(code_by_type[rtype])
        report[rtype] = {
            "doc_count": len(doc_set),
            "code_count": len(code_set),
            "in_doc_not_code": sorted(doc_set - code_set),
            "in_code_not_doc": sorted(code_set - doc_set),
            "in_both": sorted(doc_set & code_set),
        }
        for addr in sorted(doc_set & code_set):
            dr = doc_by_type[rtype][addr]
            cr = code_by_type[rtype][addr]
            ds = _doc_scales(dr.unit)
            cs = _code_scale(cr.converters)
            if ds is not None and cs is not None and all(abs(d - cs) > 1e-9 for d in ds):
                d0 = min(ds)
                scale_mismatches.append(
                    {
                        "reg": f"{rtype}{addr}",
                        "doc_name": dr.name,
                        "doc_unit": dr.unit,
                        "doc_scale": d0 if len(ds) == 1 else sorted(ds),
                        "code_attrs": cr.attrs,
                        "code_convs": sorted(cr.converters),
                        "code_scale": cs,
                        "factor_off": round(cs / d0, 4) if d0 else None,
                    }
                )
    report["scale_mismatches"] = scale_mismatches

    # Device-section diffs: each non-inverter doc section against its own getter.
    device_sections: dict[str, dict] = {}
    for prefix, (label, gname) in DEVICE_SECTIONS.items():
        doc_rows: dict[int, DocRegister] = {}
        for r in doc_regs:
            if r.section.startswith(prefix) and r.addr is not None:
                doc_rows.setdefault(r.addr, r)
        code_addrs = by_getter.get(gname, {}) if gname else {}
        doc_set, code_set = set(doc_rows), set(code_addrs)
        missing = []
        for addr in sorted(doc_set - code_set):
            dr = doc_rows[addr]
            if dr.name.strip().lower() in {"not used", "reserved", ""}:
                continue
            missing.append({"addr": addr, "name": dr.name, "rw": dr.rw, "value": dr.value, "unit": dr.unit})
        sec_mismatches = []
        for addr in sorted(doc_set & code_set):
            dr = doc_rows[addr]
            ds = _doc_scales(dr.unit)
            cs = _code_scale(code_addrs[addr])
            if ds is not None and cs is not None and all(abs(d - cs) > 1e-9 for d in ds):
                sec_mismatches.append(
                    {
                        "addr": addr,
                        "doc_name": dr.name,
                        "doc_unit": dr.unit,
                        "doc_scale": min(ds) if len(ds) == 1 else sorted(ds),
                        "code_convs": sorted(code_addrs[addr]),
                        "code_scale": cs,
                    }
                )
        device_sections[label] = {
            "section_prefix": prefix,
            "getter": gname,
            "doc_count": len(doc_set),
            "code_count": len(code_set),
            "in_doc_not_code": missing,
            "in_code_not_doc": sorted(code_set - doc_set),
            "scale_mismatches": sec_mismatches,
        }
    report["device_sections"] = device_sections

    # Writable-set check: doc-writable HR vs WRITE_SAFE.
    doc_writable_hr = {a for a, r in doc_by_type["HR"].items() if r.writable}
    report["write_safe"] = {
        "write_safe_count": len(write_safe),
        "doc_writable_hr_count": len(doc_writable_hr),
        "in_write_safe_not_doc_writable": sorted(write_safe - doc_writable_hr),
        "doc_writable_not_in_write_safe": sorted(doc_writable_hr - write_safe),
    }

    # Section inventory (counts per parsed section).
    by_section: dict[str, int] = {}
    for r in doc_regs:
        by_section[r.section] = by_section.get(r.section, 0) + 1
    report["sections"] = dict(sorted(by_section.items()))

    print(json.dumps(report, indent=2, ensure_ascii=False))

    if json_out:
        registers = [_facts_row(r) for r in doc_regs] if facts_only else [asdict(r) for r in doc_regs]
        json_out.write_text(
            json.dumps({"doc_registers": registers, "report": report}, indent=2, ensure_ascii=not facts_only),
            encoding="utf-8",
        )
        kind = "facts-only" if facts_only else "full"
        print(f"\nWrote {kind} inventory to {json_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
