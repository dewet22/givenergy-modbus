"""Declarative capability manifest — model(+firmware) → register semantics (#293, Slice A).

One place answering "what does this register/field mean on this model". Grown in
slices: A (this file's initial content) covers register SEMANTICS — value-source
routing and per-model field identity. Slices B-D will add the capability fact
tables, the polling ranges, and the write surface.

Keys are the RESOLVED specific ``Model`` (from ``resolve_model``), never the coarse
family. Every accessor takes ``arm_fw`` so a firmware column exists in the contract
from day one; no Slice A row uses it (future users: slot_map's ``HYBRID_GEN3 and
arm_fw > 302`` extended-slot wrinkle, the Gateway V1/V2 layout variant — Slice B+).
"""

from givenergy_modbus.model.inverter import Model

# Per-(specific-model, metric) authoritative battery-energy source (#184; relocated
# verbatim from inverter._BATTERY_ENERGY_SOURCE in Slice A). Declared only where a
# wire capture positively confirms it; an absent model or metric routes to None
# (honest "no evidence yet" + a forcing function for which captures to chase).
# "today"/"total" each map to an altN whose register name is built as
# e_battery_{charge,discharge}_{metric}_{altN} (see SinglePhaseInverter._battery_energy).
#
#   alt1 = IR(36/37) daily, IR(180/181) total   alt2 = IR(182/183) daily, HR total (dead)
#   alt3 = HR(4113/4114) daily (dead, never polled — see #48)
#
# Evidence (tests/fixtures/captures/): GEN1 populates the alt2 daily registers as
# authoritative and IR alt1 totals; AC/AIO populate alt1 daily, totals unknown → None.
VALUE_SOURCES: dict[str, dict[Model, str]] = {
    "battery_energy_today": {
        Model.HYBRID_GEN1: "alt2",
        Model.AC: "alt1",
        Model.ALL_IN_ONE: "alt1",
    },
    "battery_energy_total": {
        Model.HYBRID_GEN1: "alt1",
    },
}


def battery_energy_source(model: Model, metric: str, arm_fw: int | None = None) -> str | None:
    """Return the authoritative altN source tag for a battery-energy metric, or None.

    ``arm_fw`` is accepted for forward-compatibility with firmware-gated rows (none
    exist in Slice A).
    """
    return VALUE_SOURCES.get(f"battery_energy_{metric}", {}).get(model)
