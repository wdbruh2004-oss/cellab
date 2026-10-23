"""Generate THIRD_PARTY_NOTICES.md from the installed runtime dependency closure.

Walks the requirement graph of the ``cellab`` distribution (runtime only), then
writes each package's name, version, declared licence and bundled licence texts.
Run from the project root:  uv run python scripts/gen_notices.py
"""

from __future__ import annotations

import re
from importlib import metadata
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
LICENSE_FILE_RE = re.compile(r"(LICEN[CS]E|COPYING|NOTICE|AUTHORS)", re.I)


def runtime_closure(root: str) -> list[metadata.Distribution]:
    env = default_environment()
    seen: dict[str, metadata.Distribution] = {}
    stack = [root]
    while stack:
        name = stack.pop()
        key = name.lower().replace("_", "-")
        if key in seen:
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        seen[key] = dist
        for raw in dist.requires or []:
            req = Requirement(raw)
            if req.marker is not None and not req.marker.evaluate({**env, "extra": ""}):
                continue
            stack.append(req.name)
    seen.pop(root, None)
    return sorted(seen.values(), key=lambda d: d.metadata["Name"].lower())


def licence_of(dist: metadata.Distribution) -> str:
    md = dist.metadata
    expr = md.get("License-Expression")
    if expr:
        return expr
    lic = (md.get("License") or "").strip()
    if lic and len(lic) < 80 and "\n" not in lic:
        return lic
    classifiers = [c.split("::")[-1].strip() for c in md.get_all("Classifier") or [] if c.startswith("License ::")]
    return ", ".join(classifiers) or "see licence text"


def licence_texts(dist: metadata.Distribution) -> list[tuple[str, str]]:
    out = []
    for f in dist.files or []:
        if ".dist-info" in str(f) and LICENSE_FILE_RE.search(Path(str(f)).name):
            try:
                out.append((Path(str(f)).name, Path(f.locate()).read_text(encoding="utf-8", errors="replace")))
            except OSError:
                pass
    return out


def main() -> None:
    dists = runtime_closure("cellab")
    lines = ["# Third-party notices", "",
             "CellLab bundles the following open-source components. Each is used under its own licence, "
             "reproduced below. PySide6/Qt are used under the LGPL-3.0: the one-folder distribution keeps the "
             "Qt libraries as separate, replaceable files.", "",
             "| Package | Version | Licence |", "|---|---|---|"]
    for d in dists:
        lines.append(f"| {d.metadata['Name']} | {d.version} | {licence_of(d)} |")
    lines.append("")
    for d in dists:
        lines += [f"## {d.metadata['Name']} {d.version}", "", f"Licence: {licence_of(d)}", ""]
        home = d.metadata.get("Home-page") or next(
            (u.split(",", 1)[1].strip() for u in d.metadata.get_all("Project-URL") or []), "")
        if home:
            lines += [f"Project: {home}", ""]
        for name, text in licence_texts(d):
            lines += [f"<details><summary>{name}</summary>", "", "```text", text.strip(), "```", "", "</details>", ""]
    out = ROOT / "THIRD_PARTY_NOTICES.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(dists)} packages)")


if __name__ == "__main__":
    main()
