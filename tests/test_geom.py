import numpy as np
import pytest

from cellab.model.geom import ellipsoid_norm, rotation_from_z, segment_closest_pairs, segment_distances


def _brute(p, q, P, Q, n=400):
    t = np.linspace(0, 1, n)
    a = p + t[:, None] * (q - p)
    b = P + t[:, None] * (Q - P)
    return np.min(np.linalg.norm(a[:, None] - b[None], axis=2))


def test_segment_distance_matches_brute_force():
    rng = np.random.default_rng(1)
    for _ in range(200):
        p, q, P, Q = rng.normal(size=(4, 3))
        if rng.random() < 0.2:
            q = p.copy()
        if rng.random() < 0.2:
            Q = P.copy()
        d = segment_distances(p, q, P[None], Q[None])[0]
        assert d == pytest.approx(_brute(p, q, P, Q), abs=0.02)
        c1, c2 = segment_closest_pairs(p[None], q[None], P[None], Q[None])
        assert np.linalg.norm(c1 - c2) == pytest.approx(d, abs=1e-9)


def test_parallel_and_point_cases():
    p, q = np.array([0., 0, 0]), np.array([1., 0, 0])
    P, Q = np.array([[0., 1, 0]]), np.array([[1., 1, 0]])
    assert segment_distances(p, q, P, Q)[0] == pytest.approx(1.0)
    assert segment_distances(p, p, P, P)[0] == pytest.approx(1.0)


@pytest.mark.parametrize("d", [[0, 0, 1], [0, 0, -1], [1, 0, 0], [0.3, -0.5, 0.8]])
def test_rotation_from_z(d):
    d = np.array(d, float) / np.linalg.norm(d)
    r = rotation_from_z(d[None])[0]
    assert np.allclose(r @ [0, 0, 1], d)
    assert np.allclose(r @ r.T, np.eye(3), atol=1e-12)
    assert np.linalg.det(r) == pytest.approx(1.0)


def test_ellipsoid_norm():
    assert ellipsoid_norm(np.array([[2.0, 0, 0]]), 0, [2, 1, 1])[0] == pytest.approx(1.0)
