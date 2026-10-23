"""Geometric exclusion field of a built cell: where a small cytoplasmic particle may be."""

from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from cellab.model.cell_model import CellModel
from cellab.model.geom import ellipsoid_norm

DISCRETE = ("mitochondrion", "endosome", "lysosome", "peroxisome")


class ObstacleField:
    """Cytoplasm = inside the plasma membrane, outside the nucleus and outside every discrete organelle.

    Organelle surfaces are found with a KD-tree over points sampled every ``axis_step`` µm along
    each capsule axis (spheres are single points); clearance error is at most ``axis_step / 2``.
    """

    def __init__(self, model: CellModel, axis_step: float = 0.05):
        p0, p1, r = [], [], []
        for sid in DISCRETE:
            pop = model.populations.get(sid)
            if pop is None:
                continue
            a = pop.arrays
            if pop.kind == "capsules":
                p0.append(a["p0"]); p1.append(a["p1"]); r.append(a["radii"])  # noqa: E702
            else:
                p0.append(a["centers"]); p1.append(a["centers"]); r.append(a["radii"])  # noqa: E702
        p0, p1, r = np.vstack(p0), np.vstack(p1), np.concatenate(r)
        length = np.linalg.norm(p1 - p0, axis=1)
        n_samp = np.ceil(length / axis_step).astype(int) + 1
        owner = np.repeat(np.arange(len(r)), n_samp)
        start = np.repeat(np.cumsum(n_samp) - n_samp, n_samp)
        frac = (np.arange(len(owner)) - start) / np.maximum(n_samp[owner] - 1, 1)
        self._tree = cKDTree(p0[owner] + (p1[owner] - p0[owner]) * frac[:, None])
        self._radius = r[owner]
        self.cell_axes = np.asarray(model.cell_axes, float)
        self.nucleus_center = np.asarray(model.nucleus_center, float)
        self.nucleus_axes = np.asarray(model.nucleus_axes, float)

    def organelle_clearance(self, x: np.ndarray) -> np.ndarray:
        d, j = self._tree.query(np.atleast_2d(x), k=6)
        return np.min(d - self._radius[j], axis=1)

    def forbidden(self, x: np.ndarray, radius: float = 0.0) -> np.ndarray:
        x = np.atleast_2d(x)
        bad = ellipsoid_norm(x, 0, self.cell_axes - radius) >= 1.0
        bad |= ellipsoid_norm(x, self.nucleus_center, self.nucleus_axes + radius) <= 1.0
        bad |= self.organelle_clearance(x) <= radius
        return bad

    def nearest_free(self, x: np.ndarray, rng: np.random.Generator, radius: float = 0.0) -> np.ndarray:
        """A free cytoplasm point close to ``x`` (searching outward in growing shells)."""
        x = np.asarray(x, float)
        if not self.forbidden(x, radius)[0]:
            return x
        for scale in (0.1, 0.2, 0.4, 0.8, 1.6, 3.2):
            cand = x + rng.normal(0, scale, (256, 3))
            ok = ~self.forbidden(cand, radius)
            if ok.any():
                c = cand[ok]
                return c[np.argmin(np.linalg.norm(c - x, axis=1))]
        raise ValueError("no free cytoplasm near the requested point")
