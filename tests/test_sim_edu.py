import numpy as np
import pytest

from cellab.edu.learning import generate_quiz, load_tour
from cellab.model.obstacles import ObstacleField
from cellab.sim.diffusion import DiffusionSim, load_tracers


def test_free_diffusion_matches_einstein_relation():
    sim = DiffusionSim(D=27.0, start=np.zeros(3), n=6000, seed=11)
    sim.advance(0.02)
    # MSD = 6 D t; with 6000 particles the relative standard error is about 1.3%
    assert sim.msd() / (6 * 27.0 * sim.time) == pytest.approx(1.0, abs=0.05)
    assert sim.effective_D() == pytest.approx(27.0, rel=0.05)


def test_diffusion_is_deterministic():
    a = DiffusionSim(D=10.0, start=np.zeros(3), n=50, seed=3)
    b = DiffusionSim(D=10.0, start=np.zeros(3), n=50, seed=3)
    a.step(20)
    b.step(20)
    assert np.array_equal(a.x, b.x)


def test_particles_never_enter_organelles(model):
    field = ObstacleField(model)
    start = model.nucleus_center + np.array([-1.0, 0, 0]) * model.nucleus_axes[0] * 1.45
    sim = DiffusionSim(D=27.0, start=start, n=400, obstacles=field, seed=5)
    assert not field.forbidden(sim.origin)[0]
    sim.advance(0.01)
    assert not field.forbidden(sim.x).any()
    assert sim.rejected > 0  # obstacles were actually met


def test_organelles_obstruct_diffusion(model):
    field = ObstacleField(model)
    start = model.nucleus_center + np.array([-1.0, 0, 0]) * model.nucleus_axes[0] * 1.45
    sim = DiffusionSim(D=27.0, start=start, n=600, obstacles=field, seed=9)
    sim.advance(0.05)
    assert sim.effective_D() < 0.95 * 27.0


def test_tracers_are_sourced(kb):
    tracers = load_tracers()
    assert tracers and all(t.D > 0 and t.refs for t in tracers)
    assert all(r in kb.references for t in tracers for r, _ in t.refs)


def test_tour_stops_are_renderable(kb):
    tour = load_tour(kb)
    assert len(tour.stops) >= 10
    assert all(kb.get(s.structure).renderable and s.text for s in tour.stops)


def test_quiz_answers_are_correct(kb, profile):
    qs = generate_quiz(kb, profile, n=200, seed=1)
    assert len(qs) >= 30
    shares = {c.id: c for c in profile.compartments}
    for q in qs:
        assert len(set(q.options)) == len(q.options) >= 3
        assert 0 <= q.answer < len(q.options)
        assert q.structure in kb.structures and q.source
        if q.prompt.startswith("The protein "):
            gene = q.prompt.split()[2]
            owner = next(s for s in kb.structures.values() if any(m.gene == gene for m in s.markers))
            assert q.options[q.answer] == owner.name
        if "share of the cell volume" in q.prompt:
            comp = next(c for c in shares.values() if q.structure in c.structures)
            assert q.options[q.answer] == f"{100 * comp.volume_fraction:g}%"


def test_quiz_is_reproducible(kb, profile):
    a = [q.prompt for q in generate_quiz(kb, profile, n=10, seed=5)]
    b = [q.prompt for q in generate_quiz(kb, profile, n=10, seed=5)]
    assert a == b
