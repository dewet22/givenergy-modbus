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


# IR(44)/IR(45-46) identity overrides (#293): on these models the registers carry the
# inverter's battery-discharge AC OUTPUT, not PV generation — delta-evidenced against
# HV-stack counters (AberDino's 2×AIO, 2026-07-02: IR44 = 0.90× stack discharge,
# accumulates pre-dawn, flat through an 11.5 kWh PV midday) and the ems_2_inv_3_bat_a
# fixture's Model.AC units (IR44 == battery discharge). Unlisted models keep the
# status quo (e_pv_generation_* live — the #174 hybrid verdict); adding a row here is
# the entire upgrade path when new evidence lands. AIO_COMMERCIAL/ALL_IN_ONE_HYBRID
# are ThreePhase-decoded and never reach the SinglePhaseInverter validator.
FIELD_IDENTITY: dict[str, frozenset[Model]] = {
    "ir44_inverter_out": frozenset({Model.AC, Model.ALL_IN_ONE}),
}


def ir44_is_inverter_output(model: Model, arm_fw: int | None = None) -> bool:
    """True when IR44/IR45-46 carry inverter output (not PV) on this model (#293)."""
    return model in FIELD_IDENTITY["ir44_inverter_out"]
