"""Procedural, deterministic construction of a quantitative cell model.

Units are micrometres throughout. Discrete compartments realized geometrically
(nucleus, mitochondria, peroxisomes, lysosomes, endosomes) reproduce the volume
fractions and counts of the profile exactly; everything else is representational
and flagged as such in the knowledge base.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np
from scipy.spatial import cKDTree

from cellab.model.geom import (
    ellipsoid_norm,
    ellipsoid_normals,
    ellipsoid_ray_scale,
    fibonacci_sphere,
    orthonormal_frame,
    random_unit_vectors,
)
from cellab.model.packing import relax_pack
from cellab.science.profile import CellProfile


class LayoutError(RuntimeError):
    pass


@dataclass
class Population:
    structure_id: str
    kind: str
    count: int
    arrays: dict[str, np.ndarray]
    volumes: np.ndarray | None = None
    meta: dict = field(default_factory=dict)

    @property
    def total_volume(self) -> float | None:
        return None if self.volumes is None else float(np.sum(self.volumes))


@dataclass
class CellModel:
    profile: CellProfile
    cell_axes: np.ndarray
    nucleus_center: np.ndarray
    nucleus_axes: np.ndarray
    centrosome_center: np.ndarray
    golgi_zone: tuple[np.ndarray, float]
    populations: dict[str, Population]
    stats: dict

    @property
    def cell_volume(self) -> float:
        return self.profile.cell_volume

    def instance_center(self, structure_id: str, idx: int) -> np.ndarray:
        pop = self.populations[structure_id]
        a = pop.arrays
        k = pop.kind
        if k == "ellipsoid":
            return a["center"][0]
        if k in ("spheres", "tori", "cisternae"):
            return a["centers"][idx]
        if k == "capsules":
            return 0.5 * (a["p0"][idx] + a["p1"][idx])
        if k == "polylines":
            o = a["offsets"]
            return a["points"][o[idx]:o[idx + 1]].mean(axis=0)
        if k == "points":
            return a["points"][a["instance"] == idx].mean(axis=0)
        if k == "centrosome":
            return a["centers"][min(idx, len(a["centers"]) - 1)] if idx < 2 else a["pcm_center"]
        if k == "sheets":
            return self.nucleus_center
        raise KeyError(k)

    def instance_extent(self, structure_id: str, idx: int) -> float:
        """Approximate size (µm) of one instance, used for camera framing."""
        pop = self.populations[structure_id]
        a = pop.arrays
        k = pop.kind
        if k == "ellipsoid":
            return float(2 * a["axes"][0].max())
        if k == "spheres":
            return float(2 * a["radii"][idx])
        if k == "capsules":
            return float(np.linalg.norm(a["p1"][idx] - a["p0"][idx]) + 2 * a["radii"][idx])
        if k == "tori":
            return float(2 * (a["major"][idx] + a["minor"][idx]))
        if k == "cisternae":
            return float(2 * a["radii"][idx])
        if k == "polylines":
            o = a["offsets"]
            pts = a["points"][o[idx]:o[idx + 1]]
            return float(np.ptp(pts, axis=0).max())
        if k == "points":
            pts = a["points"][a["instance"] == idx]
            return float(max(np.ptp(pts, axis=0).max(), 0.1))
        if k == "centrosome":
            return 1.2
        return float(2 * self.nucleus_axes.max() * 1.3)

    def describe_instance(self, structure_id: str, idx: int) -> list[tuple[str, str]]:
        """Human-readable, model-derived facts about one rendered instance."""
        pop = self.populations[structure_id]
        a = pop.arrays
        k = pop.kind
        rows: list[tuple[str, str]] = []
        c = self.instance_center(structure_id, idx)
        if k == "ellipsoid":
            ax = a["axes"][0]
            vol = 4 / 3 * math.pi * float(np.prod(ax))
            rows += [("Dimensions", " × ".join(f"{2 * x:.1f}" for x in ax) + " µm"),
                     ("Volume", f"{vol:,.0f} µm³ ({100 * vol / self.cell_volume:.1f}% of cell)")]
            if structure_id == "plasma_membrane":
                p = 1.6075
                area = 4 * math.pi * ((ax[0] ** p * ax[1] ** p + ax[0] ** p * ax[2] ** p
                                       + ax[1] ** p * ax[2] ** p) / 3) ** (1 / p)
                rows.append(("Surface area", f"≈ {area:,.0f} µm² (Knud Thomsen approx.)"))
        elif k == "capsules":
            r = float(a["radii"][idx])
            length = float(np.linalg.norm(a["p1"][idx] - a["p0"][idx])) + 2 * r
            rows += [("Length", f"{length:.2f} µm"), ("Diameter", f"{2 * r:.2f} µm"),
                     ("Volume", f"{pop.volumes[idx]:.3f} µm³")]
        elif k == "spheres":
            r = float(a["radii"][idx])
            rows += [("Diameter", f"{2 * r * 1000:.0f} nm" if r < 0.25 else f"{2 * r:.2f} µm"),
                     ("Volume", f"{4 / 3 * math.pi * r ** 3:.4f} µm³")]
        elif k == "tori":
            rows += [("Outer diameter", f"{2 * (a['major'][idx] + a['minor'][idx]) * 1000:.0f} nm")]
        elif k == "cisternae":
            frac = float(a["frac"][idx])
            face = "cis" if frac < 0.34 else ("trans" if frac > 0.66 else "medial")
            rows += [("Stack", f"{int(a['stack'][idx]) + 1} of {pop.meta['stacks']}"),
                     ("Cisterna", f"{int(a['level'][idx]) + 1} of {pop.meta['per_stack']} ({face})"),
                     ("Diameter", f"{2 * a['radii'][idx]:.2f} µm (illustrative)")]
        elif k == "polylines":
            o = a["offsets"]
            pts = a["points"][o[idx]:o[idx + 1]]
            length = float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))
            rows.append(("Path length", f"{length:.2f} µm"))
        elif k == "points":
            n = int(np.sum(a["instance"] == idx))
            kinds = pop.meta.get("instance_kinds")
            if kinds is not None:
                rows.append(("Type", kinds(idx)))
            rows.append(("Rendered points", str(n)))
        elif k == "centrosome":
            rows.append(("Part", ("Mother centriole", "Daughter centriole", "Pericentriolar material")[min(idx, 2)]))
        rho = float(ellipsoid_norm(c, self.nucleus_center, self.nucleus_axes))
        rows.append(("Centre (x, y, z)", ", ".join(f"{v:.2f}" for v in c) + " µm"))
        if structure_id not in ("plasma_membrane", "nucleus", "nucleolus", "chromatin", "nuclear_pore"):
            rows.append(("Normalized nuclear radius", f"{rho:.2f} (1.0 = envelope)"))
        return rows


def _truncated_normal(rng, mean, sd, lo, hi, n):
    out = rng.normal(mean, sd, n)
    bad = (out < lo) | (out > hi)
    while bad.any():
        out[bad] = rng.normal(mean, sd, bad.sum())
        bad = (out < lo) | (out > hi)
    return out


def build_cell_model(profile: CellProfile) -> CellModel:
    t0 = time.perf_counter()
    rng = np.random.default_rng(profile.seed)
    P = profile.params
    A = np.array(profile.semi_axes, float)
    V = profile.cell_volume
    gap = float(P["organelle_gap_um"])
    margin = float(P["cortex_margin_um"])
    excl = float(P["perinuclear_exclusion_scale"])
    pops: dict[str, Population] = {}

    # Plasma membrane / cell boundary
    pops["plasma_membrane"] = Population("plasma_membrane", "ellipsoid", 1,
                                         {"center": np.zeros((1, 3)), "axes": A[None]},
                                         volumes=np.array([V]))

    # Nucleus: volume fixed by the profile, shape by the axis ratio
    ratio = np.array(P["nucleus_axis_ratio"], float)
    vn = profile.target_volume("nucleus")
    k = (3 * vn / (4 * math.pi * np.prod(ratio))) ** (1 / 3)
    N = k * ratio
    nc = np.array(P["nucleus_center_um"], float)
    probe = nc + N * excl * np.vstack([np.eye(3), -np.eye(3)])
    if np.any(ellipsoid_norm(probe, 0, A - margin) >= 1):
        raise LayoutError("nucleus plus perinuclear zone does not fit inside the cell")
    pops["nucleus"] = Population("nucleus", "ellipsoid", 1, {"center": nc[None], "axes": N[None]},
                                 volumes=np.array([4 / 3 * math.pi * np.prod(N)]))

    # Centrosome and Golgi ribbon, placed on the side of the nucleus given by golgi_direction
    u, v, w = orthonormal_frame(np.array(P["golgi_direction"], float))
    surf = float(ellipsoid_ray_scale(u, N)[0])
    base = nc + u * surf * excl
    centro = base + u * 0.55
    n_stacks, per_stack = int(P["golgi_stacks"]), int(P["golgi_cisternae_per_stack"])
    R_c = float(P["golgi_cisterna_radius_um"])
    phis = np.linspace(-np.radians(110), np.radians(110), n_stacks)
    cis_centers, cis_axes, cis_radii, cis_level, cis_stack, cis_frac = [], [], [], [], [], []
    for si, phi in enumerate(phis):
        s_pos = centro + u * 0.25 + 1.35 * (math.cos(phi) * v + math.sin(phi) * w)
        axis = s_pos - nc
        axis /= np.linalg.norm(axis)
        for j in range(per_stack):
            cis_centers.append(s_pos + axis * (j - (per_stack - 1) / 2) * 0.11)
            cis_axes.append(axis)
            cis_radii.append(R_c * (1 - 0.07 * abs(j - (per_stack - 1) / 2)) * rng.uniform(0.92, 1.08))
            cis_level.append(j)
            cis_stack.append(si)
            cis_frac.append(j / max(per_stack - 1, 1))
    cis_centers = np.array(cis_centers)
    cis_radii = np.array(cis_radii)
    zone_c = centro + u * 0.25
    zone_r = float(np.max(np.linalg.norm(cis_centers - zone_c, axis=1) + cis_radii)) + 0.25
    pops["golgi"] = Population("golgi", "cisternae", len(cis_centers), {
        "centers": cis_centers, "axes": np.array(cis_axes), "radii": cis_radii,
        "thickness": np.full(len(cis_centers), 0.035), "curvature": np.full(len(cis_centers), 0.28),
        "level": np.array(cis_level), "stack": np.array(cis_stack), "frac": np.array(cis_frac)},
        meta={"stacks": n_stacks, "per_stack": per_stack})

    # Centrosome: two orthogonal centrioles (diameter 0.22 µm, length 0.45 µm) and a PCM cloud
    pops["centrosome"] = Population("centrosome", "centrosome", 3, {
        "centers": np.array([centro, centro + 0.16 * w + 0.12 * v]),
        "axes": np.array([v, w]), "radius": np.array([0.11]), "length": np.array([0.45]),
        "pcm_center": centro + 0.06 * w, "pcm_radius": np.array([0.42])})

    # --- Discrete organelles ------------------------------------------------------------------
    lo_box = -(A - margin)
    hi_box = A - margin

    def sample_points(n: int) -> np.ndarray:
        """Uniform points in the cytoplasm outside the perinuclear zone."""
        out: list[np.ndarray] = []
        got = 0
        while got < n:
            x = rng.uniform(lo_box, hi_box, (max(2 * (n - got), 64), 3))
            x = x[(ellipsoid_norm(x, 0, A - margin) < 1.0) & (ellipsoid_norm(x, nc, N * excl) >= 1.0)]
            out.append(x)
            got += len(x)
        return np.vstack(out)[:n]

    # Mitochondria: count and total volume from the profile; radii and length variation are model choices
    mp = P["mitochondrion_radius_um"]
    n_m = int(profile.compartment("mitochondria").count)
    vm = profile.target_volume("mitochondria")
    radii = _truncated_normal(rng, mp["mean"], mp["sd"], mp["min"], mp["max"], n_m)
    cv = float(P["mitochondrion_length_cv"])
    sigma = math.sqrt(math.log(1 + cv * cv))
    raw_len = rng.lognormal(-sigma * sigma / 2, sigma, n_m)
    cap_vol = 4 / 3 * math.pi * radii ** 3
    scale = (vm - cap_vol.sum()) / np.sum(math.pi * radii ** 2 * raw_len)
    if scale <= 0:
        raise LayoutError("mitochondrial radii too large for the target volume")
    lengths = raw_len * scale

    sphere_specs = []
    for comp_id, sid in (("endosomes", "endosome"), ("lysosomes", "lysosome"), ("peroxisomes", "peroxisome")):
        comp = profile.compartment(comp_id)
        n = int(comp.count)
        rr = rng.normal(1.0, float(P["spherical_organelle_radius_cv"]), n).clip(0.6, 1.5)
        target = profile.target_volume(comp_id)
        rr *= (target / np.sum(4 / 3 * math.pi * rr ** 3)) ** (1 / 3)
        sphere_specs.append((sid, rr))

    # All discrete organelles are packed together: random start, then overlap relaxation
    all_r = np.concatenate([radii, *(rr for _, rr in sphere_specs)])
    all_h = np.concatenate([lengths / 2, *(np.zeros(len(rr)) for _, rr in sphere_specs)])
    n_all = len(all_r)
    start_c = sample_points(n_all)
    start_d = random_unit_vectors(rng, n_all)
    shell_all = (A - margin)[None] - all_r[:, None]
    excl_all = N[None] * excl + all_r[:, None]

    def violations(C, D, h, r, idx):
        """Boolean mask over ``idx``: capsule leaves the cell, enters the perinuclear zone or the Golgi zone."""
        shell, excl_axes = shell_all[idx], excl_all[idx]
        bad = np.zeros(len(C), bool)
        for sgn in (-1.0, 1.0):
            bad |= ellipsoid_norm(C + sgn * D * h[:, None], 0, shell) >= 1.0
        for t in (-1.0, -0.5, 0.0, 0.5, 1.0):
            bad |= ellipsoid_norm(C + D * (t * h)[:, None], nc, excl_axes) < 1.0
        p0, d = C - D * h[:, None], 2 * D * h[:, None]
        s = np.clip(np.einsum("ij,ij->i", zone_c - p0, d) / np.maximum(np.einsum("ij,ij->i", d, d), 1e-12), 0, 1)
        bad |= np.linalg.norm(p0 + s[:, None] * d - zone_c, axis=1) <= zone_r + r
        return bad

    def project(C, D, h, r, idx):
        shell, excl_axes = shell_all[idx], excl_all[idx]
        for sgn in (-1.0, 1.0):
            e = C + sgn * D * h[:, None]
            rho = ellipsoid_norm(e, 0, shell)
            out = rho > 1.0
            C[out] -= e[out] - e[out] / rho[out, None] * (1.0 - 1e-4)
        for t in (-1.0, -0.5, 0.0, 0.5, 1.0):
            x = C + D * (t * h)[:, None]
            rho = ellipsoid_norm(x, nc, excl_axes)
            ins = rho < 1.0
            C[ins] += (x[ins] - nc) * (1.0 / rho[ins, None] - 1.0) * 1.001
        p0, d = C - D * h[:, None], 2 * D * h[:, None]
        s = np.clip(np.einsum("ij,ij->i", zone_c - p0, d) / np.maximum(np.einsum("ij,ij->i", d, d), 1e-12), 0, 1)
        off = p0 + s[:, None] * d - zone_c
        dist = np.linalg.norm(off, axis=1)
        deficit = zone_r + r - dist
        bad = deficit > 0
        C[bad] += off[bad] / np.maximum(dist[bad, None], 1e-9) * (deficit[bad, None] * 1.001)
        return C

    def constrain(C, D, h, r):
        C = C.copy()
        idx = np.arange(len(C))
        for _ in range(60):
            idx = idx[violations(C[idx], D[idx], h[idx], r[idx], idx)]
            if idx.size == 0:
                break
            C[idx] = project(C[idx], D[idx], h[idx], r[idx], idx)
        return C

    try:
        C, D, iterations = relax_pack(start_c, start_d, all_h, all_r, gap, constrain, rng)
    except RuntimeError as exc:
        raise LayoutError(str(exc)) from exc
    if violations(C, D, all_h, all_r, np.arange(n_all)).any():
        raise LayoutError("relaxed layout violates the cell/nucleus/Golgi constraints")

    # KD-tree over points along every organelle axis, used to keep later point clouds out of organelles
    axis_step = 0.05
    n_samp = np.ceil(2 * all_h / axis_step).astype(int) + 1
    owner = np.repeat(np.arange(n_all), n_samp)
    frac = (np.arange(len(owner)) - np.repeat(np.cumsum(n_samp) - n_samp, n_samp)) / np.maximum(n_samp[owner] - 1, 1)
    axis_pts = C[owner] + D[owner] * ((frac - 0.5) * 2 * all_h[owner])[:, None]
    axis_tree = cKDTree(axis_pts)

    def clearance(x: np.ndarray) -> np.ndarray:
        """Approximate distance from points to the nearest discrete-organelle surface (µm)."""
        d, j = axis_tree.query(x, k=6)
        return np.min(d - all_r[owner[j]], axis=1)

    m_p0 = C[:n_m] - D[:n_m] * all_h[:n_m, None]
    m_p1 = C[:n_m] + D[:n_m] * all_h[:n_m, None]
    m_vol = math.pi * radii ** 2 * lengths + cap_vol
    pops["mitochondrion"] = Population("mitochondrion", "capsules", n_m,
                                       {"p0": m_p0, "p1": m_p1, "radii": radii}, volumes=m_vol)
    k0 = n_m
    for sid, rr in sphere_specs:
        pops[sid] = Population(sid, "spheres", len(rr), {"centers": C[k0:k0 + len(rr)].copy(), "radii": rr},
                               volumes=4 / 3 * math.pi * rr ** 3)
        k0 += len(rr)

    # --- Nuclear contents -------------------------------------------------------------------
    nl_r = np.array(P["nucleolus_radii_um"], float)
    nl_c: list[np.ndarray] = []
    for r in nl_r:
        for _ in range(1000):
            x = nc + rng.uniform(-1, 1, 3) * N * 0.5
            if ellipsoid_norm(x, nc, N - r - 0.4) < 1 and all(np.linalg.norm(x - y) > r + q + 0.3
                                                                 for y, q in zip(nl_c, nl_r[:len(nl_c)], strict=True)):
                nl_c.append(x)
                break
        else:
            raise LayoutError("could not place nucleolus")
    nl_c = np.array(nl_c)
    pops["nucleolus"] = Population("nucleolus", "spheres", len(nl_r), {"centers": nl_c, "radii": nl_r},
                                   volumes=4 / 3 * math.pi * nl_r ** 3)

    n_pore = int(P["nuclear_pore_count"])
    dirs = fibonacci_sphere(n_pore) + rng.normal(0, 0.35 / math.sqrt(n_pore), (n_pore, 3))
    dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
    pore_c = nc + dirs * N
    pops["nuclear_pore"] = Population("nuclear_pore", "tori", n_pore, {
        "centers": pore_c, "normals": ellipsoid_normals(pore_c, nc, N),
        "major": np.full(n_pore, 0.045), "minor": np.full(n_pore, 0.015)})

    n_chr = int(P["chromatin_points"])
    chrom = []
    while len(chrom) < n_chr:
        x = nc + rng.uniform(-1, 1, (4096, 3)) * N
        rho = ellipsoid_norm(x, nc, N)
        dn = np.min(np.linalg.norm(x[:, None] - nl_c[None], axis=2) - nl_r[None], axis=1)
        # heterochromatin enriched at the periphery and around nucleoli; sparse elsewhere
        keep_p = np.where((rho > 0.84) & (rho < 0.98), 0.9, 0.0)
        keep_p = np.maximum(keep_p, np.where((dn > 0.02) & (dn < 0.3), 0.8, 0.0))
        keep_p = np.where((rho < 0.84) & (dn >= 0.3), 0.07, keep_p)
        keep_p = np.where((rho >= 0.98) | (dn <= 0.02), 0.0, keep_p)
        chrom.extend(x[rng.random(len(x)) < keep_p])
    chrom = np.array(chrom[:n_chr])
    pops["chromatin"] = Population("chromatin", "points", 1,
                                   {"points": chrom, "instance": np.zeros(len(chrom), int)})

    # --- Rough ER: fenestrated perinuclear sheets ---------------------------------------
    n_t, n_p = 64, 128
    th = np.linspace(0.04 * math.pi, 0.96 * math.pi, n_t)
    ph = np.linspace(0, 2 * math.pi, n_p)
    TT, PP = np.meshgrid(th, ph, indexing="ij")
    unit = np.stack([np.sin(TT) * np.cos(PP), np.sin(TT) * np.sin(PP), np.cos(TT)], axis=-1)
    gap_cos = math.cos(math.radians(32))
    sheet_pts, sheet_mask = [], []
    for s in P["rough_er_sheet_scales"]:
        pts = nc + unit * N * float(s)
        mid = 0.25 * (unit[:-1, :-1] + unit[1:, :-1] + unit[:-1, 1:] + unit[1:, 1:])
        mid /= np.linalg.norm(mid, axis=-1, keepdims=True)
        kvec = random_unit_vectors(rng, 6) * rng.uniform(2.2, 3.6, (6, 1))
        phase = rng.uniform(0, 2 * math.pi, 6)
        field_ = np.mean(np.sin(mid @ kvec.T + phase), axis=-1)
        kf = random_unit_vectors(rng, 5) * rng.uniform(13, 17, (5, 1))
        holes = np.mean(np.sin(mid @ kf.T + rng.uniform(0, 2 * math.pi, 5)), axis=-1)
        dir_mid = mid * N
        dir_mid /= np.linalg.norm(dir_mid, axis=-1, keepdims=True)
        mask = (field_ > -0.08) & (holes < 0.55) & (dir_mid @ u < gap_cos)
        sheet_pts.append(pts)
        sheet_mask.append(mask)
    sheet_pts = np.array(sheet_pts)
    sheet_mask = np.array(sheet_mask)
    pops["rough_er"] = Population("rough_er", "sheets", len(sheet_pts),
                                  {"points": sheet_pts, "mask": sheet_mask},
                                  meta={"scales": list(P["rough_er_sheet_scales"])})

    # Ribosomes: ER-bound (on sheet faces) and free polysomes
    n_bound = int(P["ribosomes_bound_rendered"])
    li, ti, pi_ = np.nonzero(sheet_mask)
    a0 = sheet_pts[li, ti, pi_]
    e1 = sheet_pts[li, ti + 1, pi_] - a0
    e2 = sheet_pts[li, ti, pi_ + 1] - a0
    area = np.linalg.norm(np.cross(e1, e2), axis=1)
    pick = rng.choice(len(area), n_bound, p=area / area.sum())
    s_, t_ = rng.random((2, n_bound))
    bound = a0[pick] + s_[:, None] * e1[pick] + t_[:, None] * e2[pick]
    bnorm = ellipsoid_normals(bound, nc, N)
    bound += bnorm * np.where(rng.random(n_bound) < 0.5, 0.03, -0.03)[:, None]

    n_poly = int(P["ribosomes_free_polysomes_rendered"])
    free_pts, free_inst = [], []
    seeds = sample_points(4 * n_poly)
    seeds = seeds[clearance(seeds) > 0.12][:n_poly]
    if len(seeds) < n_poly:
        raise LayoutError("not enough free cytosol for polysomes")
    for made, x in enumerate(seeds):
        m = int(rng.integers(5, 9))
        axis = random_unit_vectors(rng, 1)[0]
        _, pv_, pw_ = orthonormal_frame(axis)
        tt = np.arange(m) * 0.6
        pts = (x + np.outer(np.arange(m) * 0.03, axis) + 0.03 * (np.outer(np.cos(tt), pv_)
                                                                  + np.outer(np.sin(tt), pw_)))
        free_pts.append(pts)
        free_inst.append(np.full(m, n_bound + made))
    rib_pts = np.vstack([bound, *free_pts])
    rib_inst = np.concatenate([np.arange(n_bound), *free_inst])

    def rib_kind(i: int, _nb=n_bound) -> str:
        return "ER-bound ribosome" if i < _nb else "Free polysome (cytosolic)"
    pops["ribosome"] = Population("ribosome", "points", n_bound + n_poly,
                                  {"points": rib_pts, "instance": rib_inst},
                                  meta={"instance_kinds": rib_kind, "bound": n_bound, "polysomes": n_poly})

    # Transport vesicles budding near Golgi rims
    n_ves = int(P["transport_vesicle_count"])
    ves_c, ves_r = [], []
    cax = pops["golgi"].arrays["axes"]
    while len(ves_c) < n_ves:
        i = int(rng.integers(len(cis_centers)))
        _, gv, gw = orthonormal_frame(cax[i])
        ang = rng.uniform(0, 2 * math.pi)
        rad = cis_radii[i] * rng.uniform(1.08, 1.45)
        ves_c.append(cis_centers[i] + rad * (math.cos(ang) * gv + math.sin(ang) * gw)
                     + cax[i] * (rng.uniform(-0.1, 0.1) + 0.28 * rad * rad))
        ves_r.append(rng.uniform(0.03, 0.045))
    ves_r = np.array(ves_r)
    pops["transport_vesicle"] = Population("transport_vesicle", "spheres", n_ves,
                                           {"centers": np.array(ves_c), "radii": ves_r},
                                           volumes=4 / 3 * math.pi * ves_r ** 3)

    # --- Cytoskeleton ------------------------------------------------------------------------
    def push_out(pts: np.ndarray, scale: float) -> np.ndarray:
        rho = ellipsoid_norm(pts, nc, N * scale)
        inside = rho < 1.0
        pts = pts.copy()
        pts[inside] = nc + (pts[inside] - nc) / rho[inside, None]
        rc = ellipsoid_norm(pts, 0, A * 0.975)
        out = rc > 1.0
        pts[out] = pts[out] / rc[out, None]
        return pts

    def polyline_population(sid: str, paths: list[np.ndarray]) -> Population:
        offsets = np.concatenate([[0], np.cumsum([len(p) for p in paths])])
        return Population(sid, "polylines", len(paths), {"points": np.vstack(paths), "offsets": offsets})

    mt_paths = []
    for _ in range(int(P["microtubule_count"])):
        d = random_unit_vectors(rng, 1)[0]
        reach = rng.uniform(0.6, 0.97) if rng.random() < 0.3 else rng.uniform(0.92, 0.97)
        end = d * float(ellipsoid_ray_scale(d, A)[0]) * reach
        mid = 0.5 * (centro + end)
        ctrl = mid + random_unit_vectors(rng, 1)[0] * 0.18 * np.linalg.norm(end - centro)
        t = np.linspace(0, 1, 56)[:, None]
        pts = (1 - t) ** 2 * centro + 2 * (1 - t) * t * ctrl + t ** 2 * end
        for _ in range(3):
            pts = push_out(pts, 1.29)
            pts[1:-1] = (pts[:-2] + pts[1:-1] + pts[2:]) / 3
        mt_paths.append(push_out(pts, 1.29))
    pops["microtubule"] = polyline_population("microtubule", mt_paths)

    if_paths = []
    for _ in range(int(P["keratin_filament_count"])):
        d0 = random_unit_vectors(rng, 1)[0]
        start = nc + d0 * N * 1.03
        d1 = d0 + 0.5 * random_unit_vectors(rng, 1)[0]
        d1 /= np.linalg.norm(d1)
        end = d1 * float(ellipsoid_ray_scale(d1, A)[0]) * 0.955
        t = np.linspace(0, 1, 64)[:, None]
        base_ = (1 - t) * start + t * end
        _, pv_, pw_ = orthonormal_frame(end - start)
        waves = rng.uniform(2.5, 5.0)
        phase = rng.uniform(0, 2 * math.pi)
        wob = 0.28 * np.sin(2 * math.pi * waves * t + phase) * pv_ + 0.18 * np.cos(2 * math.pi * waves * 0.7 * t) * pw_
        if_paths.append(push_out(base_ + wob * np.sin(math.pi * t), 1.02))
    pops["keratin_if"] = polyline_population("keratin_if", if_paths)

    n_act = int(P["actin_segment_count"])
    dirs = random_unit_vectors(rng, n_act)
    cpts = dirs * ellipsoid_ray_scale(dirs, A)[:, None] * 0.975
    nrm = ellipsoid_normals(cpts, 0, A)
    tang = random_unit_vectors(rng, n_act)
    tang -= nrm * np.sum(tang * nrm, axis=1, keepdims=True)
    tang /= np.linalg.norm(tang, axis=1, keepdims=True)
    half = rng.uniform(0.3, 0.65, n_act)[:, None]
    seg = np.stack([cpts - tang * half, cpts + tang * half], axis=1)
    seg /= ellipsoid_norm(seg, 0, A * 0.975)[..., None]
    pops["actin_cortex"] = polyline_population("actin_cortex", list(seg))

    # Smooth ER: tubular network with mostly three-way junctions
    n_nodes = int(P["smooth_er_nodes"])
    cand = sample_points(6 * n_nodes)
    cand = cand[(ellipsoid_norm(cand, nc, N) > 1.5) & (ellipsoid_norm(cand, 0, A) > 0.45)
                & (np.linalg.norm(cand - zone_c, axis=1) > zone_r)]
    if len(cand) < n_nodes:
        raise LayoutError("not enough cytoplasm for the smooth-ER network")
    nodes = cand[:n_nodes]
    dmat = np.linalg.norm(nodes[:, None] - nodes[None], axis=2)
    np.fill_diagonal(dmat, np.inf)
    edges = set()
    for i in range(n_nodes):
        for j in np.argsort(dmat[i])[:3]:
            if dmat[i, j] < 2.4:
                edges.add((min(i, int(j)), max(i, int(j))))
    edges = sorted(edges)
    ser_paths = []
    for i, j in edges:
        t = np.linspace(0, 1, 6)[:, None]
        bend = random_unit_vectors(rng, 1)[0] * 0.12 * dmat[i, j]
        ser_paths.append((1 - t) * nodes[i] + t * nodes[j] + np.sin(math.pi * t) * bend)
    pops["smooth_er"] = polyline_population("smooth_er", ser_paths)

    stats = {
        "build_seconds": time.perf_counter() - t0,
        "relaxation_iterations": iterations,
        "discrete_organelles": int(n_m + sum(len(r) for _, r in sphere_specs)),
    }
    return CellModel(profile, A, nc, N, centro, (zone_c, zone_r), pops, stats)
