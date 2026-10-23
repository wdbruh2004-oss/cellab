import math

import numpy as np
import pytest
from scipy.spatial import cKDTree

from cellab.model.cell_model import build_cell_model
from cellab.model.geom import ellipsoid_norm, segment_closest_pairs


def _capsules(model):
    """All discrete organelles as (p0, p1, r) arrays."""
    p0, p1, r = [], [], []
    m = model.populations["mitochondrion"].arrays
    p0.append(m["p0"]); p1.append(m["p1"]); r.append(m["radii"])
    for sid in ("endosome", "lysosome", "peroxisome"):
        a = model.populations[sid].arrays
        p0.append(a["centers"]); p1.append(a["centers"]); r.append(a["radii"])
    return np.vstack(p0), np.vstack(p1), np.concatenate(r)


def test_deterministic(profile, model):
    again = build_cell_model(profile)
    for sid, pop in model.populations.items():
        for k, v in pop.arrays.items():
            if isinstance(v, np.ndarray):
                assert np.array_equal(v, again.populations[sid].arrays[k]), (sid, k)


def test_counts_match_reference(profile, model):
    for comp in profile.compartments:
        if comp.realization == "geometric":
            assert sum(model.populations[s].count for s in comp.structures) == comp.count


def test_volume_fractions_match_reference(profile, model):
    for comp in profile.compartments:
        if comp.realization == "geometric":
            vol = sum(model.populations[s].total_volume for s in comp.structures)
            assert vol / model.cell_volume == pytest.approx(comp.volume_fraction, rel=1e-9)


def test_no_overlaps_between_discrete_organelles(profile, model):
    p0, p1, r = _capsules(model)
    gap = profile.params["organelle_gap_um"]
    mid = 0.5 * (p0 + p1)
    reach = 0.5 * np.linalg.norm(p1 - p0, axis=1) + r
    pairs = cKDTree(mid).query_pairs(2 * reach.max() + gap, output_type="ndarray")
    i, j = pairs[:, 0], pairs[:, 1]
    c1, c2 = segment_closest_pairs(p0[i], p1[i], p0[j], p1[j])
    clearance = np.linalg.norm(c1 - c2, axis=1) - r[i] - r[j]
    assert clearance.min() >= gap * 0.999, f"min clearance {clearance.min():.4f} µm"


def test_organelles_respect_boundaries(profile, model):
    p0, p1, r = _capsules(model)
    margin = profile.params["cortex_margin_um"]
    for e in (p0, p1):
        assert np.all(ellipsoid_norm(e, 0, model.cell_axes[None] - margin - r[:, None]) < 1.0)
    for t in np.linspace(0, 1, 9):
        x = p0 + t * (p1 - p0)
        rho = ellipsoid_norm(x, model.nucleus_center, model.nucleus_axes)
        assert np.all(rho > 1.0), "organelle intersects the nucleus"


def test_mitochondrial_diameters_in_textbook_range(model, kb):
    q = next(q for q in kb.get("mitochondrion").quantities if q.label == "Typical diameter")
    d = 2 * model.populations["mitochondrion"].arrays["radii"]
    assert d.min() >= q.value[0] and d.max() <= q.value[1]


def test_nuclear_pore_count_in_textbook_range(model, kb):
    q = next(q for q in kb.get("nuclear_pore").quantities if "per nucleus" in q.label)
    assert q.value[0] <= model.populations["nuclear_pore"].count <= q.value[1]


def test_nuclear_pores_lie_on_envelope(model):
    c = model.populations["nuclear_pore"].arrays["centers"]
    rho = ellipsoid_norm(c, model.nucleus_center, model.nucleus_axes)
    assert np.allclose(rho, 1.0, atol=1e-9)


def test_golgi_stack_size_in_textbook_range(model, kb):
    q = next(q for q in kb.get("golgi").quantities if "Cisternae" in q.label)
    assert q.value[0] <= model.populations["golgi"].meta["per_stack"] <= q.value[1]


def test_centriole_dimensions(model, kb):
    a = model.populations["centrosome"].arrays
    qs = {q.label: q.value for q in kb.get("centrosome").quantities}
    assert qs["Centriole diameter"][0] <= 2 * a["radius"][0] <= qs["Centriole diameter"][1]
    assert qs["Centriole length"][0] <= a["length"][0] <= qs["Centriole length"][1]
    assert len(a["centers"]) == qs["Centrioles per G1 centrosome"]
    u, v = a["axes"]
    assert abs(u @ v) < 1e-9, "centrioles must be orthogonal"


def test_nucleoli_inside_nucleus(model):
    a = model.populations["nucleolus"].arrays
    rho = ellipsoid_norm(a["centers"], model.nucleus_center, model.nucleus_axes - a["radii"].max())
    assert np.all(rho < 1)


def test_chromatin_inside_nucleus(model):
    pts = model.populations["chromatin"].arrays["points"]
    assert np.all(ellipsoid_norm(pts, model.nucleus_center, model.nucleus_axes) < 1)


def test_instance_descriptions(model):
    rows = dict(model.describe_instance("mitochondrion", 0))
    r = model.populations["mitochondrion"].arrays["radii"][0]
    assert rows["Diameter"] == f"{2 * r:.2f} µm"
    rows = dict(model.describe_instance("nucleus", 0))
    assert "6.0% of cell" in rows["Volume"]
    rows = dict(model.describe_instance("golgi", 0))
    assert "(cis)" in rows["Cisterna"]
    assert dict(model.describe_instance("ribosome", 0))["Type"] == "ER-bound ribosome"


def test_build_is_fast_enough(model):
    assert model.stats["build_seconds"] < 15
    assert math.isfinite(model.stats["relaxation_iterations"])
