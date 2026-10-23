"""Random sequential addition of non-overlapping capsules and spheres.

Spheres are capsules with a zero-length axis. A uniform grid keyed on segment
midpoints limits each overlap query to the 27 neighbouring cells.
"""

from __future__ import annotations

import numpy as np

from cellab.model.geom import segment_distances


class CapsulePacker:
    def __init__(self, max_bounding_radius: float, gap: float, capacity: int = 4096):
        self.cell = 2.0 * max_bounding_radius + gap
        self.gap = gap
        self.max_br = max_bounding_radius
        self.p = np.empty((capacity, 3))
        self.q = np.empty((capacity, 3))
        self.r = np.empty(capacity)
        self.n = 0
        self.grid: dict[tuple[int, int, int], list[int]] = {}

    def _key(self, x: np.ndarray) -> tuple[int, int, int]:
        k = np.floor(x / self.cell).astype(int)
        return int(k[0]), int(k[1]), int(k[2])

    def _neighbours(self, mid: np.ndarray) -> np.ndarray:
        kx, ky, kz = self._key(mid)
        idx: list[int] = []
        grid = self.grid
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    bucket = grid.get((kx + dx, ky + dy, kz + dz))
                    if bucket:
                        idx.extend(bucket)
        return np.fromiter(idx, dtype=np.int64, count=len(idx))

    def fits(self, p: np.ndarray, q: np.ndarray, r: float) -> bool:
        br = 0.5 * float(np.linalg.norm(q - p)) + r
        if br > self.max_br + 1e-9:
            raise ValueError("object larger than the packer's max bounding radius")
        idx = self._neighbours(0.5 * (p + q))
        if idx.size == 0:
            return True
        d = segment_distances(p, q, self.p[idx], self.q[idx])
        return bool(np.all(d >= self.r[idx] + r + self.gap))

    def add(self, p: np.ndarray, q: np.ndarray, r: float) -> int:
        if self.n == len(self.r):
            grow = len(self.r)
            self.p = np.vstack([self.p, np.empty((grow, 3))])
            self.q = np.vstack([self.q, np.empty((grow, 3))])
            self.r = np.concatenate([self.r, np.empty(grow)])
        i = self.n
        self.p[i], self.q[i], self.r[i] = p, q, r
        self.grid.setdefault(self._key(0.5 * (p + q)), []).append(i)
        self.n += 1
        return i


def _scatter(idx: np.ndarray, vec: np.ndarray, n: int) -> np.ndarray:
    """Sum rows of ``vec`` into ``n`` bins (much faster than np.add.at)."""
    return np.column_stack([np.bincount(idx, weights=vec[:, k], minlength=n) for k in range(3)])


def relax_pack(centers: np.ndarray, dirs: np.ndarray, half: np.ndarray, radii: np.ndarray, gap: float,
               constrain, rng: np.random.Generator, max_iter: int = 1500, damping: float = 0.9,
               trace: list | None = None):
    """Remove overlaps between capsules by iterative pairwise separation.

    Each capsule is a segment centre +/- dir * half with radius ``radii``. Candidate
    pairs come from a KD-tree over points sampled along each axis; separation uses
    the exact segment-segment closest points, with translation plus a small rigid
    rotation about the centre. ``constrain(C, D, half, radii)`` projects capsules
    back into the allowed region every iteration. Returns (centers, dirs, iterations).
    """
    from scipy.spatial import cKDTree

    from cellab.model.geom import segment_closest_pairs

    C = np.array(centers, float)
    D = np.array(dirs, float)
    n = len(C)
    spacing = float(max(radii.max(), 0.15))
    nseg = np.ceil(2 * half / spacing).astype(int)
    counts = nseg + 1
    owner = np.repeat(np.arange(n), counts)
    start = np.repeat(np.cumsum(counts) - counts, counts)
    k = np.arange(len(owner)) - start
    frac = np.where(nseg[owner] > 0, k / np.maximum(nseg[owner], 1), 0.5)
    offs = (frac - 0.5) * 2 * half[owner]
    skin = 0.3
    cutoff = 2 * float(radii.max()) + gap + spacing + skin
    ref_C = ref_D = None
    pi = pj = None
    for it in range(1, max_iter + 1):
        C = constrain(C, D, half, radii)
        moved = np.inf if ref_C is None else float(np.max(
            np.linalg.norm(C - ref_C, axis=1) + half * np.linalg.norm(D - ref_D, axis=1)))
        if moved > 0.5 * skin:
            # Verlet list: candidate pairs stay valid until something moves by half the skin
            samples = C[owner] + D[owner] * offs[:, None]
            pairs = cKDTree(samples).query_pairs(cutoff, output_type="ndarray")
            oi, oj = owner[pairs[:, 0]], owner[pairs[:, 1]]
            keep = oi != oj
            key = np.unique(np.minimum(oi[keep], oj[keep]) * n + np.maximum(oi[keep], oj[keep]))
            pi, pj = key // n, key % n
            ref_C, ref_D = C.copy(), D.copy()
        bound = half[pi] + half[pj] + radii[pi] + radii[pj] + gap
        close = np.einsum("ij,ij->i", C[pi] - C[pj], C[pi] - C[pj]) < bound * bound
        i, j = pi[close], pj[close]
        hi, hj = half[i, None], half[j, None]
        ci, cj = segment_closest_pairs(C[i] - D[i] * hi, C[i] + D[i] * hi, C[j] - D[j] * hj, C[j] + D[j] * hj)
        diff = ci - cj
        dist = np.linalg.norm(diff, axis=1)
        # push apart to a slightly larger working gap so the tail of tiny overlaps converges fast
        pen = radii[i] + radii[j] + 1.5 * gap - dist
        true_over = pen > 0.5 * gap
        if trace is not None:
            trace.append((int(true_over.sum()), float(pen.max(initial=0.0) - 0.5 * gap)))
        if not true_over.any():
            return C, D, it
        over = pen > 0
        i, j, ci, cj, diff, dist, pen = i[over], j[over], ci[over], cj[over], diff[over], dist[over], pen[over]
        degenerate = dist < 1e-9
        nvec = np.where(degenerate[:, None], rng.normal(size=diff.shape), diff)
        nvec /= np.linalg.norm(nvec, axis=1, keepdims=True)
        step = (0.5 * pen * 1.1 + 1e-3)[:, None] * nvec
        dC = _scatter(i, step, n) - _scatter(j, step, n)
        li, lj = ci - C[i], cj - C[j]
        wi = np.cross(li, step) / (np.einsum("ij,ij->i", li, li) + radii[i] ** 2)[:, None]
        wj = np.cross(lj, -step) / (np.einsum("ij,ij->i", lj, lj) + radii[j] ** 2)[:, None]
        dW = _scatter(i, wi, n) + _scatter(j, wj, n)
        C += damping * dC
        D = D + np.cross(damping * dW, D)
        D /= np.linalg.norm(D, axis=1, keepdims=True)
    raise RuntimeError(f"relaxation did not converge in {max_iter} iterations")
