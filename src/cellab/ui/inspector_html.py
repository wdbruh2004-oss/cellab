"""HTML for the scientific inspector (pure functions, testable without Qt)."""

from __future__ import annotations

from html import escape

from cellab.model.cell_model import CellModel
from cellab.science.knowledge import KnowledgeBase, Structure

STATUS_COLORS = {
    "sourced": "#3fb950",
    "textbook": "#58a6ff",
    "approximate": "#d29922",
    "model": "#bc8cff",
    "illustrative": "#f0883e",
}

CSS = """
<style>
body { color: #e6e9ef; font-size: 10pt; }
h2 { color: #ffffff; margin: 0 0 2px 0; }
h3 { color: #9fb3d9; margin: 14px 0 4px 0; font-size: 10pt; text-transform: uppercase; }
.sub { color: #9aa4b8; }
.badge { color: #0d1117; font-weight: bold; }
table { border-collapse: collapse; }
td, th { padding: 3px 6px; border-bottom: 1px solid #2a3350; vertical-align: top; }
th { color: #9fb3d9; text-align: left; font-weight: normal; }
.k { color: #9aa4b8; }
.note { color: #c9b07a; }
a { color: #79c0ff; }
.sel { background-color: #2b2410; }
</style>
"""


def _badge(status: str) -> str:
    c = STATUS_COLORS.get(status, "#888")
    return f'<span style="background-color:{c}; color:#0d1117;">&nbsp;{escape(status)}&nbsp;</span>'


def _cite(kb: KnowledgeBase, cites) -> str:
    parts = []
    for c in cites:
        short = kb.references[c.id].short
        parts.append(escape(short + (f", {c.at}" if c.at else "")))
    return "; ".join(parts)


def _model_block(kb: KnowledgeBase, model: CellModel, s: Structure) -> str:
    pop = model.populations.get(s.id)
    comp = model.profile.compartment_for(s.id)
    rows = []
    if pop is not None:
        rows.append(("Rendered instances", f"{pop.count:,}"))
        if pop.total_volume is not None and s.id != "plasma_membrane":
            rows.append(("Model volume", f"{pop.total_volume:,.2f} µm³ "
                                         f"({100 * pop.total_volume / model.cell_volume:.2f}% of cell)"))
    if comp is not None:
        where = f"{model.profile.source_at}"
        joint = "" if len(comp.structures) == 1 else " (combined: " + ", ".join(
            kb.get(x).name for x in comp.structures) + ")"
        rows.append(("Reference volume share", f"{100 * comp.volume_fraction:g}%{escape(joint)} — {escape(where)}"))
        rows.append(("Realization", {
            "geometric": "Geometric: count and total volume reproduce the reference",
            "representational": "Representational: arrangement only, volume not realized",
            "implicit": "Implicit: space between structures"}[comp.realization]))
    if not rows:
        return ""
    body = "".join(f"<tr><td class='k'>{escape(k)}</td><td>{v}</td></tr>" for k, v in rows)
    return f"<h3>In this model</h3><table width='100%'>{body}</table>"


def inspector_html(kb: KnowledgeBase, model: CellModel | None, structure_id: str,
                   instance: int | None = None) -> str:
    s = kb.get(structure_id)
    out = [CSS, f"<h2>{escape(s.name)}</h2>",
           f"<div class='sub'>{escape(s.category)} · Gene Ontology "
           f"<a href='https://www.ebi.ac.uk/QuickGO/term/{s.go_id}'>{s.go_id}</a> ({escape(s.go_label)})</div>"]
    if model is not None and instance is not None and instance >= 0 and structure_id in model.populations:
        facts = model.describe_instance(structure_id, instance)
        body = "".join(f"<tr><td class='k'>{escape(k)}</td><td>{escape(v)}</td></tr>" for k, v in facts)
        out.append(f"<h3>Selected instance #{instance + 1}</h3><table width='100%' class='sel'>{body}</table>")
    if model is not None:
        out.append(_model_block(kb, model, s))
    out.append(f"<h3>Overview</h3><p>{escape(s.summary)}</p>")
    if s.functions:
        out.append("<h3>Functions</h3><ul>" + "".join(f"<li>{escape(f)}</li>" for f in s.functions) + "</ul>")
    if s.quantities:
        rows = "".join(
            f"<tr><td>{escape(q.label)}</td><td><b>{escape(q.format_value())}</b> {escape(q.unit)}"
            + (f"<br><span class='note'>{escape(q.note)}</span>" if q.note else "")
            + f"</td><td>{_badge(q.status)}</td><td class='k'>{_cite(kb, q.refs)}</td></tr>"
            for q in s.quantities)
        out.append("<h3>Quantitative data</h3><table width='100%'><tr><th>Quantity</th><th>Value</th>"
                   f"<th>Status</th><th>Source</th></tr>{rows}</table>")
    if s.markers:
        rows = "".join(
            f"<tr><td><b>{escape(m.gene)}</b></td>"
            f"<td>{escape(m.protein)}<br><span class='k'>{escape(m.role)}</span></td>"
            f"<td><a href='https://www.uniprot.org/uniprotkb/{m.uniprot}'>{m.uniprot}</a></td></tr>"
            for m in s.markers)
        out.append("<h3>Marker proteins (human)</h3><table width='100%'><tr><th>Gene</th><th>Protein / role</th>"
                   f"<th>UniProt</th></tr>{rows}</table>")
    if s.render_notes:
        out.append(f"<h3>Representation</h3><p class='note'>{escape(s.render_notes)}</p>")
    refs = []
    seen = set()
    for c in list(s.refs) + [c for q in s.quantities for c in q.refs]:
        if c.id in seen:
            continue
        seen.add(c.id)
        r = kb.references[c.id]
        lic = f" <span class='k'>[{escape(r.license)}]</span>" if r.license else ""
        refs.append(f"<li>{escape(r.citation)}{lic}</li>")
    out.append("<h3>References</h3><ol>" + "".join(refs) + "</ol>")
    legend = " ".join(f"{_badge(k)}" for k in STATUS_COLORS)
    out.append(f"<p class='k'>Status legend: {legend}</p>")
    return "".join(out)


def welcome_html(kb: KnowledgeBase, model: CellModel | None) -> str:
    n = ""
    if model is not None:
        total = sum(p.count for p in model.populations.values())
        n = (f"<p>{escape(model.profile.name)}: {total:,} rendered instances across "
             f"{len(model.populations)} structure types.</p>")
    return (CSS + "<h2>Scientific inspector</h2>"
            "<p class='sub'>Click any structure in the 3D view, or choose one from the Structures panel.</p>"
            + n +
            "<h3>Navigation</h3><table>"
            "<tr><td class='k'>Rotate</td><td>Left-drag</td></tr>"
            "<tr><td class='k'>Pan</td><td>Middle-drag or Shift + left-drag</td></tr>"
            "<tr><td class='k'>Zoom</td><td>Mouse wheel or right-drag</td></tr>"
            "<tr><td class='k'>Select</td><td>Left-click</td></tr>"
            "<tr><td class='k'>Focus selection</td><td>F or double-click</td></tr>"
            "<tr><td class='k'>Reset view</td><td>Home / R</td></tr>"
            "<tr><td class='k'>Section view</td><td>S, depth slider in the toolbar</td></tr>"
            "<tr><td class='k'>Labels</td><td>L</td></tr>"
            "<tr><td class='k'>Search</td><td>Ctrl+F</td></tr></table>")
