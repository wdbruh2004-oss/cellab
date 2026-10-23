"""Visual style per structure. Colours follow common textbook conventions."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Style:
    color: str
    opacity: float = 1.0
    specular: float = 0.35
    specular_power: float = 30.0
    ambient: float = 0.12
    diffuse: float = 0.85
    point_size: float = 0.0
    line_width: float = 0.0
    tubes: bool = False
    cmap: tuple[str, str] | None = None
    scalars: str | None = None
    parts: dict[str, "Style"] = field(default_factory=dict)


STYLES: dict[str, Style] = {
    "plasma_membrane": Style("#8ab6e8", opacity=0.16, specular=0.6, specular_power=60),
    "nucleus": Style("#7b5cc4", opacity=0.5, specular=0.5, specular_power=50),
    "nucleolus": Style("#3a1f73", specular=0.2),
    "nuclear_pore": Style("#e6dcff", specular=0.2, ambient=0.25),
    "chromatin": Style("#b394f0", opacity=0.55, point_size=2.0),
    "rough_er": Style("#2ec4b6", opacity=0.82, specular=0.45),
    "smooth_er": Style("#86e3d7", opacity=0.9, line_width=2.2, tubes=True),
    "golgi": Style("#f2b62a", specular=0.5, cmap=("#fff1c1", "#c27c00"), scalars="cis_trans"),
    "transport_vesicle": Style("#ffd166", specular=0.5),
    "mitochondrion": Style("#e4572e", specular=0.45, specular_power=40),
    "lysosome": Style("#e0287a", specular=0.5),
    "peroxisome": Style("#7bc950", specular=0.5),
    "endosome": Style("#4ea8de", specular=0.5),
    "ribosome": Style("#f4f1ea", point_size=2.6),
    "centrosome": Style("#ffffff", parts={
        "centrioles": Style("#f8f9ff", specular=0.6, ambient=0.3),
        "pcm": Style("#c9d6ff", opacity=0.22, specular=0.1),
    }),
    "microtubule": Style("#a3e635", opacity=0.9, line_width=1.8, tubes=True),
    "actin_cortex": Style("#ff6b6b", opacity=0.75, line_width=1.3, tubes=True),
    "keratin_if": Style("#f6d55c", opacity=0.75, line_width=1.6, tubes=True),
}

HIGHLIGHT = "#ffe14d"
HIGHLIGHT_ALT = "#4de1ff"
TRACER = "#39ff88"
BACKGROUND_TOP = "#1b2547"
BACKGROUND_BOTTOM = "#06080f"
LABEL_TEXT = "#f2f4f8"
LABEL_BOX = "#101627"


def style_for(structure_id: str, part: str) -> Style:
    st = STYLES[structure_id]
    return st.parts.get(part, st)
