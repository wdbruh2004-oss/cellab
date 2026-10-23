import dataclasses

import numpy as np
import pytest

from cellab.render.geometry import INSTANCE, build_meshes
from cellab.science.validation import validate_model
from cellab.ui.inspector_html import inspector_html, welcome_html


@pytest.fixture(scope="module")
def meshes(model):
    return build_meshes(model)


def test_every_population_has_meshes(model, meshes):
    assert set(meshes) == set(model.populations)


def test_instance_ids_cover_population(model, meshes):
    for sid, parts in meshes.items():
        if sid == "rough_er":
            continue  # instances are connected sheet patches, counted after meshing
        ids = np.unique(np.concatenate([np.asarray(m.cell_data[INSTANCE]) for _, m in parts]))
        assert ids.min() == 0 and ids.max() == model.populations[sid].count - 1, sid


def test_meshes_are_finite(meshes):
    for parts in meshes.values():
        for _, m in parts:
            assert np.all(np.isfinite(m.points))


def test_rendered_volumes_match_model(model, meshes):
    for sid in ("mitochondrion", "lysosome", "peroxisome", "endosome", "nucleus"):
        mesh = meshes[sid][0][1]
        assert mesh.volume == pytest.approx(model.populations[sid].total_volume, rel=0.01), sid


def test_validation_passes(model, kb, meshes):
    vols = {sid: float(parts[0][1].volume) for sid, parts in meshes.items()
            if model.populations[sid].volumes is not None and parts[0][0] == "surface"}
    rows = validate_model(model, kb, vols)
    status = {r.compartment: r.status for r in rows}
    assert status["mitochondria"] == "PASS"
    assert status["nucleus"] == "PASS"
    assert status["rough_er"] == "REPRESENTATIONAL"
    assert status["cytosol"] == "IMPLICIT"
    assert all(s in ("PASS", "REPRESENTATIONAL", "IMPLICIT") for s in status.values())


def test_validation_detects_wrong_volume(model, kb):
    pops = dict(model.populations)
    mito = pops["mitochondrion"]
    pops["mitochondrion"] = dataclasses.replace(mito, volumes=mito.volumes * 1.05)
    broken = dataclasses.replace(model, populations=pops)
    status = {r.compartment: r.status for r in validate_model(broken, kb)}
    assert status["mitochondria"] == "FAIL"


def test_inspector_html(kb, model):
    html = inspector_html(kb, model, "lysosome", 3)
    assert "GO:0005764" in html and "LAMP1" in html and "P11279" in html
    assert "Selected instance #4" in html
    assert "Table 12-2" in html and "sourced" in html
    assert "Alberts B, Johnson A" in html  # full citation in the reference list
    for sid in kb.structures:
        assert kb.get(sid).name in inspector_html(kb, model, sid)
    assert "Navigation" in welcome_html(kb, model)
