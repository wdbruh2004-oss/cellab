"""Guided tour and quiz generation. Everything is derived from the curated knowledge base and
the reference profile, so every answer is traceable to a cited source."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass

from cellab.paths import data_path
from cellab.science.knowledge import KnowledgeBase
from cellab.science.profile import CellProfile


@dataclass(frozen=True)
class TourStop:
    structure: str
    text: str


@dataclass(frozen=True)
class Tour:
    title: str
    stops: tuple[TourStop, ...]


def load_tour(kb: KnowledgeBase) -> Tour:
    with open(data_path("edu", "tour.json"), encoding="utf-8") as fh:
        raw = json.load(fh)
    stops = []
    for s in raw["stops"]:
        if s["structure"] not in kb.structures:
            raise ValueError(f"tour stop refers to unknown structure {s['structure']!r}")
        stops.append(TourStop(s["structure"], s.get("text") or kb.get(s["structure"]).summary))
    return Tour(raw["title"], tuple(stops))


@dataclass(frozen=True)
class Question:
    prompt: str
    options: tuple[str, ...]
    answer: int
    explanation: str
    source: str
    structure: str


def _options(rng: random.Random, correct: str, pool: list[str], k: int = 4) -> tuple[tuple[str, ...], int]:
    distractors = [p for p in dict.fromkeys(pool) if p != correct]
    rng.shuffle(distractors)
    opts = [correct, *distractors[:k - 1]]
    rng.shuffle(opts)
    return tuple(opts), opts.index(correct)


def _cite(kb: KnowledgeBase, ref_id: str, at: str) -> str:
    return kb.references[ref_id].short + (f", {at}" if at else "")


def generate_quiz(kb: KnowledgeBase, profile: CellProfile, n: int = 10, seed: int | None = None) -> list[Question]:
    rng = random.Random(seed)
    renderable = [sid for sid in kb.order if kb.get(sid).renderable]
    names = [kb.get(s).name for s in kb.order]
    pool: list[Question] = []

    # Volume shares and counts from the reference table (sourced values)
    geo = [c for c in profile.compartments if len(c.structures) == 1]
    shares = [f"{100 * c.volume_fraction:g}%" for c in profile.compartments]
    counted = [c for c in geo if c.count and c.count > 1]
    for c in geo:
        s = kb.get(c.structures[0])
        plural = c.count is not None and c.count > 1
        label = c.id.replace("_", " ") if plural else s.name.lower()
        opts, ans = _options(rng, f"{100 * c.volume_fraction:g}%", shares)
        pool.append(Question(f"In the reference hepatocyte, what share of the cell volume "
                             f"{'do' if plural else 'does'} the {label} occupy?", opts, ans,
                             f"{s.name}: {100 * c.volume_fraction:g}% of cell volume.",
                             _cite(kb, profile.source_ref, profile.source_at), s.id))
    for c in counted:
        s = kb.get(c.structures[0])
        opts, ans = _options(rng, f"about {c.count:,}", [f"about {x.count:,}" for x in counted])
        pool.append(Question(f"About how many {c.id.replace('_', ' ')} does a hepatocyte contain?", opts, ans,
                             f"The reference table lists about {c.count:,} per cell.",
                             _cite(kb, profile.source_ref, profile.source_at), s.id))

    # Marker proteins -> structure
    for sid in renderable:
        s = kb.get(sid)
        for m in s.markers[:1]:
            opts, ans = _options(rng, s.name, names)
            pool.append(Question(f"The protein {m.gene} ({m.protein}) is a marker of which structure?", opts, ans,
                                 f"{m.gene}: {m.role} — {s.name}.", f"UniProt {m.uniprot}", sid))

    # Functions -> structure
    for sid in renderable:
        s = kb.get(sid)
        if s.functions:
            f = s.functions[0]
            opts, ans = _options(rng, s.name, names)
            ref = s.refs[0]
            pool.append(Question(f"Which structure is responsible for: “{f}”?", opts, ans,
                                 s.summary, _cite(kb, ref.id, ref.at), sid))

    # Sourced/textbook quantities with a single numeric value
    for sid in renderable:
        s = kb.get(sid)
        for q in s.quantities:
            if ("per hepatocyte" in q.label or "Share of" in q.label or q.unit in ("%", "approx.")
                    or q.status not in ("sourced", "textbook") or not isinstance(q.value, (int, float))):
                continue
            if True:
                same_unit = [x.format_value() for t in kb.structures.values() for x in t.quantities
                             if x.unit == q.unit and isinstance(x.value, (int, float))]
                if len(set(same_unit)) < 3:
                    continue
                correct = q.format_value()
                opts, ans = _options(rng, f"{correct} {q.unit}".strip(), [f"{v} {q.unit}".strip() for v in same_unit])
                pool.append(Question(f"{s.name} — {q.label}?", opts, ans, f"{q.label}: {correct} {q.unit}.",
                                     _cite(kb, q.refs[0].id, q.refs[0].at), sid))

    pool = [q for q in pool if len(q.options) >= 3]
    rng.shuffle(pool)
    return pool[:n]
