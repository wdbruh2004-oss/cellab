"""Curated, citable knowledge base for cellular structures.

All scientific statements shown in the UI come from the JSON files in
``cellab/data/knowledge``. Each quantity carries a validation status and
references so that the inspector can show the user how trustworthy a value is.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from cellab.paths import data_path

STATUSES = ("sourced", "textbook", "approximate", "model", "illustrative")

GO_ID_RE = re.compile(r"^GO:\d{7}$")
# Official UniProtKB accession pattern (https://www.uniprot.org/help/accession_numbers)
UNIPROT_RE = re.compile(r"^([OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2})$")


class KnowledgeError(ValueError):
    """Raised when the knowledge base violates its schema or integrity rules."""


@dataclass(frozen=True)
class RefCite:
    id: str
    at: str = ""


@dataclass(frozen=True)
class Reference:
    id: str
    short: str
    citation: str
    kind: str
    license: str = ""


@dataclass(frozen=True)
class Quantity:
    label: str
    value: object
    unit: str
    status: str
    refs: tuple[RefCite, ...]
    note: str = ""

    def format_value(self) -> str:
        v = self.value
        if isinstance(v, list):
            return f"{_fmt(v[0])}–{_fmt(v[1])}"
        if isinstance(v, (int, float)):
            return _fmt(v)
        return str(v)


@dataclass(frozen=True)
class Marker:
    gene: str
    protein: str
    uniprot: str
    role: str


@dataclass(frozen=True)
class Structure:
    id: str
    name: str
    category: str
    synonyms: tuple[str, ...]
    go_id: str
    go_label: str
    summary: str
    functions: tuple[str, ...]
    quantities: tuple[Quantity, ...]
    markers: tuple[Marker, ...]
    render_notes: str
    refs: tuple[RefCite, ...]
    renderable: bool = True
    _search_blob: str = field(default="", repr=False, compare=False)


def _fmt(x: float) -> str:
    if isinstance(x, int) or float(x).is_integer():
        x = int(x)
        return f"{x:,}" if abs(x) >= 10000 else str(x)
    if abs(x) >= 1e5:
        return f"{x:.2g}"
    return f"{x:g}"


def _cites(raw) -> tuple[RefCite, ...]:
    return tuple(RefCite(r["id"], r.get("at", "")) for r in raw or [])


class KnowledgeBase:
    def __init__(self, structures: list[Structure], references: dict[str, Reference],
                 status_vocabulary: dict[str, str]):
        self.structures = {s.id: s for s in structures}
        self.order = [s.id for s in structures]
        self.references = references
        self.status_vocabulary = status_vocabulary
        self.validate()

    @classmethod
    def load(cls, directory: Path | None = None) -> "KnowledgeBase":
        directory = directory or data_path("knowledge")
        with open(directory / "references.json", encoding="utf-8") as fh:
            refs_raw = json.load(fh)["references"]
        with open(directory / "structures.json", encoding="utf-8") as fh:
            raw = json.load(fh)
        references = {k: Reference(k, v["short"], v["citation"], v.get("kind", ""), v.get("license", ""))
                      for k, v in refs_raw.items()}
        structures = []
        for s in raw["structures"]:
            st = Structure(
                id=s["id"], name=s["name"], category=s["category"],
                synonyms=tuple(s.get("synonyms", [])),
                go_id=s["go"]["id"], go_label=s["go"]["label"],
                summary=s["summary"], functions=tuple(s.get("functions", [])),
                quantities=tuple(Quantity(q["label"], q["value"], q.get("unit", ""), q["status"],
                                          _cites(q.get("refs")), q.get("note", ""))
                                 for q in s.get("quantities", [])),
                markers=tuple(Marker(m["gene"], m["protein"], m["uniprot"], m.get("role", ""))
                              for m in s.get("markers", [])),
                render_notes=s.get("render_notes", ""),
                refs=_cites(s.get("refs")),
                renderable=s.get("renderable", True),
            )
            blob = " ".join([st.id, st.name, st.category, st.go_id, st.go_label, st.summary,
                             *st.synonyms, *st.functions,
                             *(f"{m.gene} {m.protein} {m.uniprot}" for m in st.markers)]).lower()
            object.__setattr__(st, "_search_blob", blob)
            structures.append(st)
        return cls(structures, references, raw.get("status_vocabulary", {}))

    def validate(self) -> None:
        """Enforce integrity rules. Raises KnowledgeError on the first violation."""
        if set(self.status_vocabulary) != set(STATUSES):
            raise KnowledgeError(f"status vocabulary must define exactly {STATUSES}")
        for s in self.structures.values():
            if not GO_ID_RE.match(s.go_id):
                raise KnowledgeError(f"{s.id}: malformed GO id {s.go_id!r}")
            if not s.refs:
                raise KnowledgeError(f"{s.id}: structure has no references")
            for c in s.refs:
                if c.id not in self.references:
                    raise KnowledgeError(f"{s.id}: unknown reference {c.id!r}")
            for q in s.quantities:
                if q.status not in STATUSES:
                    raise KnowledgeError(f"{s.id}/{q.label}: unknown status {q.status!r}")
                if q.status != "illustrative" and not q.refs:
                    raise KnowledgeError(f"{s.id}/{q.label}: non-illustrative quantity without reference")
                for c in q.refs:
                    if c.id not in self.references:
                        raise KnowledgeError(f"{s.id}/{q.label}: unknown reference {c.id!r}")
                if isinstance(q.value, list) and (len(q.value) != 2 or q.value[0] > q.value[1]):
                    raise KnowledgeError(f"{s.id}/{q.label}: ranges must be [min, max]")
            for m in s.markers:
                if not UNIPROT_RE.match(m.uniprot):
                    raise KnowledgeError(f"{s.id}/{m.gene}: malformed UniProt accession {m.uniprot!r}")

    def get(self, structure_id: str) -> Structure:
        return self.structures[structure_id]

    def search(self, text: str) -> list[str]:
        """Return structure ids matching every whitespace-separated term (case-insensitive).

        Name/synonym hits rank before matches found only in descriptions or markers.
        """
        terms = text.lower().split()
        if not terms:
            return list(self.order)
        hits = [sid for sid in self.order
                if all(t in self.structures[sid]._search_blob for t in terms)]

        def rank(sid: str) -> int:
            s = self.structures[sid]
            names = " ".join([s.name, *s.synonyms, s.id]).lower()
            return 0 if all(t in names for t in terms) else 1
        return sorted(hits, key=rank)
