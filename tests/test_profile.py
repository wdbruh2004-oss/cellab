import json

import pytest

from cellab.paths import data_path
from cellab.science.profile import CellProfile, ProfileError

# Alberts et al., Molecular Biology of the Cell, 6th ed., Table 12-2 (hepatocyte):
# compartment -> (percent of total cell volume, approximate number per cell)
TABLE_12_2 = {
    "cytosol": (54, 1), "mitochondria": (22, 1700), "rough_er": (9, 1), "smooth_er_golgi": (6, None),
    "nucleus": (6, 1), "peroxisomes": (1, 400), "lysosomes": (1, 300), "endosomes": (1, 200),
}


def test_profile_reproduces_reference_table(profile):
    got = {c.id: (round(c.volume_fraction * 100, 6), c.count) for c in profile.compartments}
    assert got == TABLE_12_2
    assert profile.source_ref == "alberts6" and "12-2" in profile.source_at


def test_profile_structures_exist(profile, kb):
    profile.validate(set(kb.structures))


def test_cell_size_in_hepatocyte_range(profile):
    # equivalent-sphere diameter must lie in the textbook 20-30 µm hepatocyte range
    d = (6 * profile.cell_volume / 3.141592653589793) ** (1 / 3)
    assert 20 <= d <= 30


def _write(tmp_path, mutate):
    raw = json.loads(data_path("profiles", "hepatocyte_reference.json").read_text(encoding="utf-8"))
    mutate(raw)
    p = tmp_path / "p.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    return p


@pytest.mark.parametrize("mutate,msg", [
    (lambda r: r["compartments"][1].update(volume_fraction=0.30), "sum to"),
    (lambda r: r["compartments"][1].update(realization="magic"), "unknown realization"),
    (lambda r: r["compartments"][2].update(structures=["mitochondrion"]), "more than one compartment"),
])
def test_invalid_profiles_rejected(tmp_path, mutate, msg):
    with pytest.raises(ProfileError, match=msg):
        CellProfile.load(_write(tmp_path, mutate))
