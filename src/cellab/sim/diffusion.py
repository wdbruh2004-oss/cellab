"""Brownian dynamics of tracer molecules in the cytoplasm of the model cell.

Each step displaces every particle by a Gaussian increment with per-axis variance 2·D·dt.
Moves that would end inside a forbidden region (an organelle, the nucleus or outside the
plasma membrane) are rejected, i.e. the particle stays put for that step. In free space the
mean squared displacement is exactly 6·D·t, which the test-suite checks.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from dataclasses import field as dc_field

import numpy as np

from cellab.model.obstacles import ObstacleField
from cellab.paths import data_path


@dataclass(frozen=True)
class Tracer:
    id: str
    name: str
    D: float            # µm²/s
    status: str
    refs: tuple[tuple[str, str], ...]
    note: str


def load_tracers() -> list[Tracer]:
    with open(data_path("simulation", "tracers.json"), encoding="utf-8") as fh:
        raw = json.load(fh)["tracers"]
    return [Tracer(t["id"], t["name"], float(t["D_um2_s"]), t["status"],
                   tuple((r["id"], r.get("at", "")) for r in t["refs"]), t.get("note", "")) for t in raw]


@dataclass
class DiffusionSim:
    D: float                          # µm²/s
    start: np.ndarray                 # release point (µm)
    n: int = 800
    obstacles: ObstacleField | None = None
    dt: float = 1e-4                  # s
    seed: int = 1
    time: float = 0.0
    history: list[tuple[float, float]] = dc_field(default_factory=list)

    def __post_init__(self):
        if self.D <= 0 or self.n <= 0 or self.dt <= 0:
            raise ValueError("D, n and dt must be positive")
        self.rng = np.random.default_rng(self.seed)
        start = np.asarray(self.start, float)
        if self.obstacles is not None:
            start = self.obstacles.nearest_free(start, self.rng)
        self.origin = start
        self.x = np.repeat(start[None], self.n, axis=0)
        self.rejected = 0
        self.history = [(0.0, 0.0)]

    @property
    def step_sigma(self) -> float:
        return math.sqrt(2.0 * self.D * self.dt)

    def step(self, steps: int = 1) -> None:
        sigma = self.step_sigma
        for _ in range(steps):
            prop = self.x + self.rng.normal(0.0, sigma, self.x.shape)
            if self.obstacles is not None:
                ok = ~self.obstacles.forbidden(prop)
                self.rejected += int((~ok).sum())
                self.x[ok] = prop[ok]
            else:
                self.x = prop
            self.time += self.dt
        self.history.append((self.time, self.msd()))

    def advance(self, duration: float) -> int:
        steps = max(1, int(round(duration / self.dt)))
        self.step(steps)
        return steps

    def msd(self) -> float:
        d = self.x - self.origin
        return float(np.mean(np.einsum("ij,ij->i", d, d)))

    def effective_D(self) -> float:
        return self.msd() / (6.0 * self.time) if self.time > 0 else float("nan")
