"""Quantitative cell profiles: compartment volume fractions and counts with provenance."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from cellab.paths import data_path

REALIZATIONS = ("geometric", "representational", "implicit")


class ProfileError(ValueError):
    pass


@dataclass(frozen=True)
class Compartment:
    id: str
    structures: tuple[str, ...]
    volume_fraction: float
    count: int | None
    realization: str


@dataclass(frozen=True)
class CellProfile:
    id: str
    name: str
    description: str
    seed: int
    source_ref: str
    source_at: str
    semi_axes: tuple[float, float, float]
    cell_note: str
    compartments: tuple[Compartment, ...]
    params: dict

    @property
    def cell_volume(self) -> float:
        a, b, c = self.semi_axes
        return 4.0 / 3.0 * math.pi * a * b * c

    def compartment_for(self, structure_id: str) -> Compartment | None:
        for c in self.compartments:
            if structure_id in c.structures:
                return c
        return None

    def compartment(self, compartment_id: str) -> Compartment:
        for c in self.compartments:
            if c.id == compartment_id:
                return c
        raise KeyError(compartment_id)

    def target_volume(self, compartment_id: str) -> float:
        return self.compartment(compartment_id).volume_fraction * self.cell_volume

    @classmethod
    def load(cls, path: Path | str | None = None) -> "CellProfile":
        path = Path(path) if path else data_path("profiles", "hepatocyte_reference.json")
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        prof = cls(
            id=raw["id"], name=raw["name"], description=raw["description"], seed=int(raw["seed"]),
            source_ref=raw["composition_source"]["id"], source_at=raw["composition_source"]["at"],
            semi_axes=tuple(float(x) for x in raw["cell"]["semi_axes_um"]),
            cell_note=raw["cell"].get("note", ""),
            compartments=tuple(Compartment(c["id"], tuple(c["structures"]), float(c["volume_fraction"]),
                                           c["count"], c["realization"]) for c in raw["compartments"]),
            params=raw["parameters"],
        )
        prof.validate()
        return prof

    def validate(self, known_structures: set[str] | None = None) -> None:
        total = sum(c.volume_fraction for c in self.compartments)
        if abs(total - 1.0) > 1e-6:
            raise ProfileError(f"volume fractions sum to {total:.4f}, expected 1.0")
        seen: set[str] = set()
        for c in self.compartments:
            if c.realization not in REALIZATIONS:
                raise ProfileError(f"{c.id}: unknown realization {c.realization!r}")
            if not 0 < c.volume_fraction < 1:
                raise ProfileError(f"{c.id}: volume fraction out of (0, 1)")
            if c.realization == "geometric" and not c.count:
                raise ProfileError(f"{c.id}: geometric compartments need a count")
            for s in c.structures:
                if s in seen:
                    raise ProfileError(f"structure {s} assigned to more than one compartment")
                seen.add(s)
                if known_structures is not None and s not in known_structures:
                    raise ProfileError(f"{c.id}: unknown structure {s!r}")
        if any(x <= 0 for x in self.semi_axes):
            raise ProfileError("cell semi-axes must be positive")
