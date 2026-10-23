"""Vectorized geometric helpers (units: micrometres)."""

from __future__ import annotations

import numpy as np

EPS = 1e-12


def random_unit_vectors(rng: np.random.Generator, n: int) -> np.ndarray:
    v = rng.normal(size=(n, 3))
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def ellipsoid_norm(points: np.ndarray, center, axes) -> np.ndarray:
    """Normalized ellipsoidal radius: 1.0 on the surface, <1 inside."""
    d = (np.asarray(points, float) - np.asarray(center, float)) / np.asarray(axes, float)
    return np.sqrt(np.sum(d * d, axis=-1))


def ellipsoid_ray_scale(directions: np.ndarray, axes) -> np.ndarray:
    """Distance along unit directions (from the centre) to the unit-scale ellipsoid surface."""
    d = np.atleast_2d(directions) / np.asarray(axes, float)
    return 1.0 / np.sqrt(np.sum(d * d, axis=1))


def ellipsoid_normals(points: np.ndarray, center, axes) -> np.ndarray:
    g = (np.asarray(points, float) - np.asarray(center, float)) / np.asarray(axes, float) ** 2
    return g / np.linalg.norm(g, axis=-1, keepdims=True)


def fibonacci_sphere(n: int) -> np.ndarray:
    i = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * i / n)
    theta = np.pi * (1 + 5 ** 0.5) * i
    return np.column_stack([np.cos(theta) * np.sin(phi), np.sin(theta) * np.sin(phi), np.cos(phi)])


def rotation_from_z(directions: np.ndarray) -> np.ndarray:
    """Rotation matrices (n, 3, 3) mapping +z onto each unit direction (Rodrigues)."""
    d = np.atleast_2d(np.asarray(directions, float))
    d = d / np.linalg.norm(d, axis=1, keepdims=True)
    z = np.array([0.0, 0.0, 1.0])
    v = np.cross(z, d)
    s = np.linalg.norm(v, axis=1)
    c = d[:, 2]
    n = len(d)
    k = np.zeros((n, 3, 3))
    k[:, 0, 1], k[:, 0, 2] = -v[:, 2], v[:, 1]
    k[:, 1, 0], k[:, 1, 2] = v[:, 2], -v[:, 0]
    k[:, 2, 0], k[:, 2, 1] = -v[:, 1], v[:, 0]
    factor = np.where(s > 1e-9, (1 - c) / np.maximum(s * s, EPS), 0.0)
    r = np.eye(3)[None] + k + k @ k * factor[:, None, None]
    flip = (s <= 1e-9) & (c < 0)
    r[flip] = np.diag([1.0, -1.0, -1.0])
    return r


def orthonormal_frame(u: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    u = np.asarray(u, float)
    u = u / np.linalg.norm(u)
    helper = np.array([0.0, 0.0, 1.0]) if abs(u[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    v = np.cross(u, helper)
    v /= np.linalg.norm(v)
    w = np.cross(u, v)
    return u, v, w


def segment_distances(p: np.ndarray, q: np.ndarray, P: np.ndarray, Q: np.ndarray) -> np.ndarray:
    """Minimum distances between segment [p, q] and each segment [P_i, Q_i].

    Degenerate segments (points) are supported, so spheres and capsules share one
    test. Algorithm: Ericson, Real-Time Collision Detection (2005), section 5.1.9.
    """
    d1 = q - p
    d2 = Q - P
    r = p - P
    a = float(d1 @ d1)
    e = np.einsum("ij,ij->i", d2, d2)
    f = np.einsum("ij,ij->i", d2, r)
    e_ok = e > EPS
    e_safe = np.where(e_ok, e, 1.0)
    if a <= EPS:
        s = np.zeros(len(P))
        t = np.where(e_ok, np.clip(f / e_safe, 0.0, 1.0), 0.0)
    else:
        c = r @ d1
        b = d2 @ d1
        denom = a * e - b * b
        d_ok = denom > EPS
        s = np.where(d_ok, np.clip((b * f - c * e) / np.where(d_ok, denom, 1.0), 0.0, 1.0), 0.0)
        t = np.where(e_ok, (b * s + f) / e_safe, 0.0)
        s = np.where(~e_ok, np.clip(-c / a, 0.0, 1.0), s)
        s = np.where(t < 0.0, np.clip(-c / a, 0.0, 1.0), s)
        s = np.where(t > 1.0, np.clip((b - c) / a, 0.0, 1.0), s)
        t = np.clip(t, 0.0, 1.0)
    diff = (p + s[:, None] * d1) - (P + t[:, None] * d2)
    return np.sqrt(np.einsum("ij,ij->i", diff, diff))


def point_segment_distance(x: np.ndarray, p: np.ndarray, q: np.ndarray) -> float:
    d = q - p
    dd = float(d @ d)
    t = 0.0 if dd <= EPS else float(np.clip((x - p) @ d / dd, 0.0, 1.0))
    return float(np.linalg.norm(p + t * d - x))


def segment_closest_pairs(P1: np.ndarray, Q1: np.ndarray, P2: np.ndarray, Q2: np.ndarray):
    """Closest points between paired segments [P1_i, Q1_i] and [P2_i, Q2_i] (all arrays (m, 3))."""
    d1 = Q1 - P1
    d2 = Q2 - P2
    r = P1 - P2
    a = np.einsum("ij,ij->i", d1, d1)
    e = np.einsum("ij,ij->i", d2, d2)
    f = np.einsum("ij,ij->i", d2, r)
    c = np.einsum("ij,ij->i", d1, r)
    b = np.einsum("ij,ij->i", d1, d2)
    a_ok, e_ok = a > EPS, e > EPS
    a_s, e_s = np.where(a_ok, a, 1.0), np.where(e_ok, e, 1.0)
    denom = a * e - b * b
    d_ok = denom > EPS
    s = np.where(d_ok, np.clip((b * f - c * e) / np.where(d_ok, denom, 1.0), 0.0, 1.0), 0.0)
    t = (b * s + f) / e_s
    s = np.where(t < 0.0, np.clip(-c / a_s, 0.0, 1.0), np.where(t > 1.0, np.clip((b - c) / a_s, 0.0, 1.0), s))
    t = np.clip(t, 0.0, 1.0)
    s = np.where(~a_ok, 0.0, s)
    t = np.where(~a_ok, np.clip(f / e_s, 0.0, 1.0), t)
    t = np.where(~e_ok, 0.0, t)
    s = np.where(~e_ok & a_ok, np.clip(-c / a_s, 0.0, 1.0), s)
    return P1 + s[:, None] * d1, P2 + t[:, None] * d2
