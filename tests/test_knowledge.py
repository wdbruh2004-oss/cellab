import dataclasses
import json
import shutil

import pytest

from cellab.paths import data_path
from cellab.render.style import STYLES
from cellab.science.knowledge import STATUSES, KnowledgeBase, KnowledgeError


def test_loads_and_validates(kb):
    assert len(kb.structures) >= 19
    assert set(kb.status_vocabulary) == set(STATUSES)


def test_every_quantity_is_traceable(kb):
    for s in kb.structures.values():
        assert s.refs, s.id
        for q in s.quantities:
            assert q.status in STATUSES
            if q.status != "illustrative":
                assert q.refs, f"{s.id}/{q.label} has no source"


def test_every_renderable_structure_has_a_style(kb):
    for s in kb.structures.values():
        if s.renderable:
            assert s.id in STYLES, s.id


@pytest.mark.parametrize("query,expected", [
    ("LAMP1", "lysosome"), ("mito", "mitochondrion"), ("GO:0005794", "golgi"),
    ("keratin", "keratin_if"), ("P60709", "actin_cortex"), ("rough er", "rough_er"), ("NPC", "nuclear_pore"),
])
def test_search_finds_expected_structure_first(kb, query, expected):
    assert kb.search(query)[0] == expected


def test_empty_search_returns_everything(kb):
    assert kb.search("   ") == kb.order


def test_search_requires_all_terms(kb):
    assert kb.search("lysosome zzzz-not-a-term") == []


def _corrupt(tmp_path, mutate):
    src = data_path("knowledge")
    dst = tmp_path / "knowledge"
    shutil.copytree(src, dst)
    data = json.loads((dst / "structures.json").read_text(encoding="utf-8"))
    mutate(data)
    (dst / "structures.json").write_text(json.dumps(data), encoding="utf-8")
    return dst


@pytest.mark.parametrize("mutate,message", [
    (lambda d: d["structures"][0]["quantities"][0].update(status="guess"), "unknown status"),
    (lambda d: d["structures"][0]["quantities"][0].update(refs=[]), "without reference"),
    (lambda d: d["structures"][0]["quantities"][0].update(refs=[{"id": "nope"}]), "unknown reference"),
    (lambda d: d["structures"][0]["go"].update(id="GO:123"), "malformed GO"),
    (lambda d: d["structures"][0]["markers"][0].update(uniprot="XYZ"), "malformed UniProt"),
    (lambda d: d["structures"][0].update(refs=[]), "no references"),
    (lambda d: d["structures"][0]["quantities"][1].update(value=[30, 20]), "ranges must be"),
])
def test_integrity_rules_reject_bad_data(tmp_path, mutate, message):
    with pytest.raises(KnowledgeError, match=message):
        KnowledgeBase.load(_corrupt(tmp_path, mutate))


def test_quantity_formatting(kb):
    q = next(q for q in kb.get("mitochondrion").quantities if q.label == "Typical diameter")
    assert q.format_value() == "0.5–1"
    q2 = dataclasses.replace(q, value=16569)
    assert q2.format_value() == "16,569"
