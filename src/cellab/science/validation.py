"""Quantitative comparison of the built model against its reference profile."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cellab.model.cell_model import CellModel
from cellab.science.knowledge import KnowledgeBase

VOLUME_TOLERANCE = 0.005   # relative, model vs reference
MESH_TOLERANCE = 0.01      # relative, rendered mesh vs analytic model volume


@dataclass(frozen=True)
class ValidationRow:
    compartment: str
    structures: tuple[str, ...]
    realization: str
    reference_fraction: float
    model_fraction: float | None
    mesh_fraction: float | None
    reference_count: int | None
    model_count: int | None
    status: str          # PASS / FAIL / REPRESENTATIONAL / IMPLICIT
    note: str


def validate_model(model: CellModel, kb: KnowledgeBase,
                   mesh_volumes: dict[str, float] | None = None) -> list[ValidationRow]:
    prof = model.profile
    V = model.cell_volume
    rows: list[ValidationRow] = []
    for comp in prof.compartments:
        if comp.realization != "geometric":
            note = ("Volume is implicit: the space between rendered structures."
                    if comp.realization == "implicit" else
                    "Geometry is representational; reference volume shown, not geometrically realized.")
            rows.append(ValidationRow(comp.id, comp.structures, comp.realization, comp.volume_fraction,
                                      None, None, comp.count, None, comp.realization.upper()
                                      if comp.realization == "implicit" else "REPRESENTATIONAL", note))
            continue
        model_vol = sum(model.populations[s].total_volume or 0.0 for s in comp.structures)
        count = sum(model.populations[s].count for s in comp.structures)
        mf = model_vol / V
        mesh_f = None
        if mesh_volumes is not None:
            mesh_f = sum(mesh_volumes.get(s, np.nan) for s in comp.structures) / V
        ok = abs(mf - comp.volume_fraction) <= VOLUME_TOLERANCE * comp.volume_fraction
        ok &= comp.count is None or count == comp.count
        if mesh_f is not None:
            ok &= abs(mesh_f - mf) <= MESH_TOLERANCE * mf
        rows.append(ValidationRow(comp.id, comp.structures, comp.realization, comp.volume_fraction, mf, mesh_f,
                                  comp.count, count, "PASS" if ok else "FAIL",
                                  "Count and total volume reproduce the reference."))
    return rows


def compartment_label(kb: KnowledgeBase, row: ValidationRow) -> str:
    return " + ".join(kb.get(s).name for s in row.structures)
