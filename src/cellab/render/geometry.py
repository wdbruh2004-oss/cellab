"""Convert model populations into merged, pickable PyVista meshes.

Every instance of a population is merged into one mesh (few draw calls). The
``instance_id`` cell array maps any picked cell back to the instance it came from.
"""

from __future__ import annotations

import math

import numpy as np
import pyvista as pv

from cellab.model.cell_model import CellModel, Population
from cellab.model.geom import orthonormal_frame, rotation_from_z

INSTANCE = "instance_id"


# --- templates ------------------------------------------------------------------------------

def _latlong(n_lat: int, n_lon: int, split_equator: bool):
    """Unit sphere as lat/long rings (poles excluded) plus two pole vertices.

    With ``split_equator`` the equator ring is duplicated, giving top/bottom halves
    that can be pulled apart to form a capsule. Returns verts, normals, half flag, triangles.
    """
    if split_equator:
        half_n = n_lat // 2
        lat_top = np.linspace(0, math.pi / 2, half_n + 1)[1:]
        lat_bot = np.linspace(math.pi / 2, math.pi, half_n + 1)[:-1]
        lats = np.concatenate([lat_top, lat_bot])
        flags = np.concatenate([np.ones(half_n), -np.ones(half_n)])
    else:
        lats = np.linspace(0, math.pi, n_lat + 1)[1:-1]
        flags = np.sign(np.cos(lats))
    lons = np.linspace(0, 2 * math.pi, n_lon, endpoint=False)
    T, L = np.meshgrid(lats, lons, indexing="ij")
    ring = np.stack([np.sin(T) * np.cos(L), np.sin(T) * np.sin(L), np.cos(T)], axis=-1).reshape(-1, 3)
    half = np.repeat(flags, n_lon)
    verts = np.vstack([[0, 0, 1], ring, [0, 0, -1]])
    half = np.concatenate([[1.0], half, [-1.0]])
    n_r = len(lats)
    tris = []
    top, bottom = 0, len(verts) - 1
    idx = lambda r, c: 1 + r * n_lon + (c % n_lon)  # noqa: E731
    for c in range(n_lon):
        tris.append((top, idx(0, c), idx(0, c + 1)))
        tris.append((bottom, idx(n_r - 1, c + 1), idx(n_r - 1, c)))
    for r in range(n_r - 1):
        for c in range(n_lon):
            a, b, d, e = idx(r, c), idx(r, c + 1), idx(r + 1, c), idx(r + 1, c + 1)
            tris.append((a, d, b))
            tris.append((b, d, e))
    return verts, verts.copy(), half, np.array(tris, dtype=np.int64)


def _torus_template(n_u: int, n_v: int, minor_ratio: float):
    u = np.linspace(0, 2 * math.pi, n_u, endpoint=False)
    v = np.linspace(0, 2 * math.pi, n_v, endpoint=False)
    U, Vv = np.meshgrid(u, v, indexing="ij")
    center = np.stack([np.cos(U), np.sin(U), np.zeros_like(U)], axis=-1)
    normal = np.stack([np.cos(Vv) * np.cos(U), np.cos(Vv) * np.sin(U), np.sin(Vv)], axis=-1)
    verts = (center + minor_ratio * normal).reshape(-1, 3)
    tris = []
    for i in range(n_u):
        for j in range(n_v):
            a, b = i * n_v + j, ((i + 1) % n_u) * n_v + j
            c, d = i * n_v + (j + 1) % n_v, ((i + 1) % n_u) * n_v + (j + 1) % n_v
            tris += [(a, b, c), (c, b, d)]
    return verts, normal.reshape(-1, 3), np.array(tris, dtype=np.int64)


def _tube_template(n_sides: int):
    ang = np.linspace(0, 2 * math.pi, n_sides, endpoint=False)
    ring = np.column_stack([np.cos(ang), np.sin(ang)])
    verts = np.vstack([np.column_stack([ring, np.full(n_sides, -0.5)]),
                       np.column_stack([ring, np.full(n_sides, 0.5)])])
    normals = np.column_stack([np.vstack([ring, ring]), np.zeros(2 * n_sides)])
    tris = []
    for i in range(n_sides):
        a, b, c, d = i, (i + 1) % n_sides, i + n_sides, (i + 1) % n_sides + n_sides
        tris += [(a, b, c), (c, b, d)]
    return verts, normals, np.array(tris, dtype=np.int64)


def _volume_compensated(template, n_lon: int):
    """Scale a lat/long template radially so the faceted mesh encloses the analytic volume.

    Inscribed facets lose volume; for capsules the cylinder dominates, so the radial
    factor is set from the polygon-to-circle area ratio, for spheres from the mesh volume.
    """
    verts, normals, half, tris = template
    mesh = pv.PolyData.from_regular_faces(verts, tris)
    k = (4 / 3 * math.pi / mesh.volume) ** (1 / 3)
    return verts * k, normals, half, tris


def _capsule_compensated(template, n_lon: int):
    verts, normals, half, tris = template
    area_ratio = n_lon / (2 * math.pi) * math.sin(2 * math.pi / n_lon)
    return verts / math.sqrt(area_ratio), normals, half, tris


_SPHERE_HI = _volume_compensated(_latlong(14, 24, False), 24)
_SPHERE_MID = _volume_compensated(_latlong(9, 14, False), 14)
_SPHERE_LO = _volume_compensated(_latlong(6, 10, False), 10)
_CAPSULE = _capsule_compensated(_latlong(10, 14, True), 14)
_TORUS = _torus_template(8, 4, 1 / 3)
_TUBE = _tube_template(6)


def _merge(verts: np.ndarray, normals: np.ndarray, tris: np.ndarray, n_inst: int,
           instance_ids: np.ndarray | None = None) -> pv.PolyData:
    """verts/normals: (n_inst, nv, 3) already transformed; tris: template triangles."""
    nv = verts.shape[1]
    faces = (tris[None] + (np.arange(n_inst) * nv)[:, None, None]).reshape(-1, 3)
    mesh = pv.PolyData.from_regular_faces(verts.reshape(-1, 3), faces)
    mesh.point_data["Normals"] = normals.reshape(-1, 3)
    mesh.point_data.active_normals_name = "Normals"
    ids = np.arange(n_inst) if instance_ids is None else instance_ids
    mesh.cell_data[INSTANCE] = np.repeat(ids, len(tris)).astype(np.int32)
    return mesh


def spheres_mesh(centers: np.ndarray, radii: np.ndarray, detail: str = "mid") -> pv.PolyData:
    verts, normals, _, tris = {"hi": _SPHERE_HI, "mid": _SPHERE_MID, "lo": _SPHERE_LO}[detail]
    v = centers[:, None, :] + radii[:, None, None] * verts[None]
    n = np.broadcast_to(normals[None], v.shape)
    return _merge(v, n, tris, len(centers))


def capsules_mesh(p0: np.ndarray, p1: np.ndarray, radii: np.ndarray) -> pv.PolyData:
    verts, normals, half, tris = _CAPSULE
    axis = p1 - p0
    length = np.linalg.norm(axis, axis=1)
    rot = rotation_from_z(axis / np.maximum(length, 1e-9)[:, None])
    local = radii[:, None, None] * verts[None] + np.zeros((len(p0), 1, 3))
    local[..., 2] += half[None] * (length[:, None] / 2)
    v = np.einsum("nij,nkj->nki", rot, local) + (0.5 * (p0 + p1))[:, None, :]
    n = np.einsum("nij,kj->nki", rot, normals)
    return _merge(v, n, tris, len(p0))


def tori_mesh(centers, normals_, major, minor) -> pv.PolyData:
    verts, nrm, tris = _TORUS
    rot = rotation_from_z(normals_)
    local = major[:, None, None] * verts[None]
    v = np.einsum("nij,nkj->nki", rot, local) + centers[:, None, :]
    n = np.einsum("nij,kj->nki", rot, nrm)
    return _merge(v, n, tris, len(centers))


def tubes_mesh(centers, axes, radius: float, length: float, ids: np.ndarray) -> pv.PolyData:
    verts, nrm, tris = _TUBE
    rot = rotation_from_z(axes)
    local = verts * np.array([radius, radius, length])
    v = np.einsum("nij,kj->nki", rot, local) + centers[:, None, :]
    n = np.einsum("nij,kj->nki", rot, nrm)
    return _merge(v, n, tris, len(centers), instance_ids=ids)


def ellipsoid_mesh(center, axes, res: int = 96) -> pv.PolyData:
    verts, normals, _, tris = _latlong(res // 2, res, False)
    v = (np.asarray(center) + verts * np.asarray(axes))[None]
    n = normals / np.asarray(axes)
    n = (n / np.linalg.norm(n, axis=1, keepdims=True))[None]
    return _merge(v, n, tris, 1)


def cisternae_mesh(pop: Population) -> pv.PolyData:
    a = pop.arrays
    verts, _, _, tris = _latlong(10, 32, False)
    out = []
    for i in range(pop.count):
        u, v, w = orthonormal_frame(a["axes"][i])
        local = verts * np.array([a["radii"][i], a["radii"][i], a["thickness"][i]])
        rho2 = local[:, 0] ** 2 + local[:, 1] ** 2
        local[:, 2] += a["curvature"][i] * rho2  # rims bend toward the trans face
        world = a["centers"][i] + local[:, 0:1] * v + local[:, 1:2] * w + local[:, 2:3] * u
        out.append(world)
    mesh = pv.PolyData.from_regular_faces(
        np.vstack(out), (tris[None] + (np.arange(pop.count) * len(verts))[:, None, None]).reshape(-1, 3))
    mesh.cell_data[INSTANCE] = np.repeat(np.arange(pop.count), len(tris)).astype(np.int32)
    mesh.cell_data["cis_trans"] = np.repeat(a["frac"], len(tris))
    return mesh.compute_normals(cell_normals=False, split_vertices=False, auto_orient_normals=False)


def sheets_mesh(pop: Population) -> pv.PolyData:
    pts, mask = pop.arrays["points"], pop.arrays["mask"]
    L, nt, npp, _ = pts.shape
    out_v, out_f, out_layer = [], [], []
    offset = 0
    for li in range(L):
        ti, pi = np.nonzero(mask[li])
        a = ti * npp + pi
        b = ti * npp + pi + 1
        c = (ti + 1) * npp + pi
        d = (ti + 1) * npp + pi + 1
        faces = np.vstack([np.column_stack([a, c, b]), np.column_stack([b, c, d])]) + offset
        out_v.append(pts[li].reshape(-1, 3))
        out_f.append(faces)
        out_layer.append(np.full(len(faces), li))
        offset += nt * npp
    mesh = pv.PolyData.from_regular_faces(np.vstack(out_v), np.vstack(out_f))
    mesh.cell_data["layer"] = np.concatenate(out_layer).astype(np.int32)
    mesh = mesh.clean()
    # Each connected sheet patch becomes one pickable instance
    labelled = mesh.connectivity(extraction_mode="all")
    labelled.cell_data[INSTANCE] = labelled.cell_data["RegionId"].astype(np.int32)
    return labelled.compute_normals(cell_normals=False, split_vertices=False, auto_orient_normals=False)


def polylines_mesh(pop: Population) -> pv.PolyData:
    pts, off = pop.arrays["points"], pop.arrays["offsets"]
    counts = np.diff(off)
    lines = np.concatenate([np.concatenate([[c], np.arange(s, s + c)]) for s, c in zip(off[:-1], counts, strict=True)])
    mesh = pv.PolyData(pts, lines=lines)
    mesh.cell_data[INSTANCE] = np.arange(pop.count, dtype=np.int32)
    return mesh


def points_mesh(pop: Population) -> pv.PolyData:
    mesh = pv.PolyData(pop.arrays["points"])
    mesh.cell_data[INSTANCE] = pop.arrays["instance"].astype(np.int32)
    return mesh


def centrosome_meshes(pop: Population) -> tuple[pv.PolyData, pv.PolyData]:
    """Two centrioles of nine microtubule triplets each, plus the pericentriolar material."""
    a = pop.arrays
    R, Lc = float(a["radius"][0]), float(a["length"][0])
    mt_r = 0.0125
    centers, axes, ids = [], [], []
    for ci, (c, ax) in enumerate(zip(a["centers"], a["axes"], strict=True)):
        u, v, w = orthonormal_frame(ax)
        for k in range(9):
            phi = 2 * math.pi * k / 9
            radial = math.cos(phi) * v + math.sin(phi) * w
            tangent = -math.sin(phi) * v + math.cos(phi) * w
            blade = math.cos(math.radians(50)) * radial + math.sin(math.radians(50)) * tangent
            for m in (-1, 0, 1):  # A, B, C tubules along the tilted blade
                centers.append(c + (R - 0.025) * radial + m * 0.022 * blade)
                axes.append(u)
                ids.append(ci)
    tubes = tubes_mesh(np.array(centers), np.array(axes), mt_r, Lc, np.array(ids))
    pcm = spheres_mesh(a["pcm_center"][None], a["pcm_radius"], "hi")
    pcm.cell_data[INSTANCE] = np.full(pcm.n_cells, 2, dtype=np.int32)
    return tubes, pcm


def build_meshes(model: CellModel) -> dict[str, list[tuple[str, pv.PolyData]]]:
    """Return {structure_id: [(part_name, mesh), ...]}."""
    out: dict[str, list[tuple[str, pv.PolyData]]] = {}
    for sid, pop in model.populations.items():
        a = pop.arrays
        k = pop.kind
        if k == "ellipsoid":
            out[sid] = [("surface", ellipsoid_mesh(a["center"][0], a["axes"][0]))]
        elif k == "spheres":
            detail = "hi" if pop.count < 10 else ("lo" if a["radii"].max() < 0.1 else "mid")
            out[sid] = [("surface", spheres_mesh(a["centers"], a["radii"], detail))]
        elif k == "capsules":
            out[sid] = [("surface", capsules_mesh(a["p0"], a["p1"], a["radii"]))]
        elif k == "tori":
            out[sid] = [("surface", tori_mesh(a["centers"], a["normals"], a["major"], a["minor"]))]
        elif k == "cisternae":
            out[sid] = [("surface", cisternae_mesh(pop))]
        elif k == "sheets":
            out[sid] = [("surface", sheets_mesh(pop))]
        elif k == "polylines":
            out[sid] = [("lines", polylines_mesh(pop))]
        elif k == "points":
            out[sid] = [("points", points_mesh(pop))]
        elif k == "centrosome":
            tubes, pcm = centrosome_meshes(pop)
            out[sid] = [("centrioles", tubes), ("pcm", pcm)]
        else:
            raise ValueError(f"unknown population kind {k!r}")
    return out
