"""Screen-space overlays: leader-line labels and a physical scale bar.

Both are updated at the start of every render, so they follow the camera
without extra render passes.
"""

from __future__ import annotations

import math

import numpy as np
import vtkmodules.vtkRenderingFreeType  # noqa: F401 - registers the text renderer used by vtkTextActor
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
from vtkmodules.vtkRenderingCore import vtkActor2D, vtkPolyDataMapper2D, vtkRenderer, vtkTextActor

from cellab.render.style import LABEL_BOX, LABEL_TEXT


def project_to_display(renderer: vtkRenderer, pts: np.ndarray) -> np.ndarray:
    """Vectorized world -> display (pixel) projection for an (n, 3) array."""
    w, h = renderer.GetSize()
    ox, oy = renderer.GetOrigin()
    cam = renderer.GetActiveCamera()
    m = cam.GetCompositeProjectionTransformMatrix(w / max(h, 1), -1, 1)
    M = np.array([[m.GetElement(i, j) for j in range(4)] for i in range(4)])
    hom = np.c_[pts, np.ones(len(pts))] @ M.T
    ndc = hom[:, :3] / hom[:, 3:4]
    return np.column_stack([(ndc[:, 0] + 1) * 0.5 * w + ox, (ndc[:, 1] + 1) * 0.5 * h + oy, hom[:, 3]])


def _hex(c: str) -> tuple[float, float, float]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))


class LabelOverlay:
    def __init__(self, renderer: vtkRenderer, ui_scale: float = 1.0):
        self.renderer = renderer
        self.ui_scale = ui_scale
        self.items: list[dict] = []
        self.visible = True
        self._pd = vtkPolyData()
        mapper = vtkPolyDataMapper2D()
        mapper.SetInputData(self._pd)
        self._lines = vtkActor2D()
        self._lines.SetMapper(mapper)
        prop = self._lines.GetProperty()
        prop.SetColor(*_hex(LABEL_TEXT))
        prop.SetOpacity(0.8)
        prop.SetLineWidth(1.2 * ui_scale)
        prop.SetPointSize(5 * ui_scale)
        renderer.AddViewProp(self._lines)

    def clear(self) -> None:
        for it in self.items:
            self.renderer.RemoveViewProp(it["text"])
        self.items = []
        self._pd.Initialize()

    def set_labels(self, labels: list[tuple[str, str, np.ndarray, np.ndarray]]) -> None:
        """labels: (structure_id, text, world anchor, pixel offset of the text from the anchor)."""
        self.clear()
        for sid, text, anchor, offset in labels:
            ta = vtkTextActor()
            ta.SetInput(text)
            tp = ta.GetTextProperty()
            tp.SetFontSize(int(round(13 * self.ui_scale)))
            tp.SetColor(*_hex(LABEL_TEXT))
            tp.SetBackgroundColor(*_hex(LABEL_BOX))
            tp.SetBackgroundOpacity(0.78)
            tp.SetFrame(True)
            tp.SetFrameColor(*_hex("#3b4a72"))
            tp.SetVerticalJustificationToCentered()
            if offset[0] < 0:
                tp.SetJustificationToRight()
            ta.SetPickable(False)
            self.renderer.AddViewProp(ta)
            self.items.append({"sid": sid, "text": ta, "anchor": np.asarray(anchor, float),
                               "offset": np.asarray(offset, float)})
        self.apply_visibility()

    def apply_visibility(self, hidden: set[str] | None = None) -> None:
        if hidden is not None:
            self._hidden = hidden
        hidden = getattr(self, "_hidden", set())
        for it in self.items:
            it["text"].SetVisibility(self.visible and it["sid"] not in hidden)
        self._lines.SetVisibility(self.visible)

    def update(self) -> None:
        shown = [it for it in self.items if it["text"].GetVisibility()]
        if not shown:
            self._pd.Initialize()
            return
        disp = project_to_display(self.renderer, np.array([it["anchor"] for it in shown]))
        w, h = self.renderer.GetSize()
        margin = 6 * self.ui_scale
        bbox = [0.0] * 4
        pts = vtkPoints()
        lines = vtkCellArray()
        verts = vtkCellArray()
        boxes = []
        for it, (x, y, _) in zip(shown, disp, strict=True):
            tx, ty = x + it["offset"][0], y + it["offset"][1]
            it["text"].GetBoundingBox(self.renderer, bbox)
            tw, th = bbox[1] - bbox[0], bbox[3] - bbox[2]
            right = it["offset"][0] < 0
            # keep the text box inside the viewport; the leader line follows
            tx = min(max(tx, tw + margin), w - margin) if right else max(min(tx, w - tw - margin), margin)
            ty = min(max(ty, th / 2 + margin), h - th / 2 - margin)
            boxes.append([x, y, tx, ty, tw, th, right])
        _separate(boxes, gap=3 * self.ui_scale, h=h, margin=margin)
        for it, (x, y, tx, ty, _tw, _th, right) in zip(shown, boxes, strict=True):
            it["text"].SetPosition(tx + (-4 if right else 4) * self.ui_scale, ty)
            a = pts.InsertNextPoint(x, y, 0)
            b = pts.InsertNextPoint(tx, ty, 0)
            lines.InsertNextCell(2, (a, b))
            verts.InsertNextCell(1, (a,))
        self._pd.SetPoints(pts)
        self._pd.SetLines(lines)
        self._pd.SetVerts(verts)
        self._pd.Modified()


def _separate(boxes: list[list], gap: float, h: float, margin: float, iterations: int = 12) -> None:
    """Push vertically overlapping label boxes apart (in place). Box: [ax, ay, tx, ty, tw, th, right]."""
    def x_range(b):
        return (b[2] - b[4], b[2]) if b[6] else (b[2], b[2] + b[4])
    for _ in range(iterations):
        moved = False
        order = sorted(range(len(boxes)), key=lambda i: boxes[i][3])
        for a_i, b_i in zip(order, order[1:], strict=False):
            a, b = boxes[a_i], boxes[b_i]
            (a0, a1), (b0, b1) = x_range(a), x_range(b)
            if a1 < b0 or b1 < a0:
                continue
            need = (a[5] + b[5]) / 2 + gap - (b[3] - a[3])
            if need > 0:
                a[3] -= need / 2
                b[3] += need / 2
                moved = True
        for b in boxes:
            b[3] = min(max(b[3], b[5] / 2 + margin), h - b[5] / 2 - margin)
        if not moved:
            break


NICE_LENGTHS_UM = (0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20)


def choose_scale_length(um_per_px: float, min_px: float, max_px: float) -> float:
    for length in NICE_LENGTHS_UM:
        if min_px <= length / um_per_px <= max_px:
            return length
    return NICE_LENGTHS_UM[0] if NICE_LENGTHS_UM[0] / um_per_px > max_px else NICE_LENGTHS_UM[-1]


class ScaleBar:
    """Scale bar valid at the camera focal point (perspective projection)."""

    def __init__(self, renderer: vtkRenderer, ui_scale: float = 1.0):
        self.renderer = renderer
        self.ui_scale = ui_scale
        self._pd = vtkPolyData()
        mapper = vtkPolyDataMapper2D()
        mapper.SetInputData(self._pd)
        self.bar = vtkActor2D()
        self.bar.SetMapper(mapper)
        self.bar.GetProperty().SetColor(1, 1, 1)
        self.bar.GetProperty().SetLineWidth(2.5 * ui_scale)
        self.text = vtkTextActor()
        tp = self.text.GetTextProperty()
        tp.SetFontSize(int(round(13 * ui_scale)))
        tp.SetColor(1, 1, 1)
        tp.SetJustificationToCentered()
        tp.SetBold(True)
        renderer.AddViewProp(self.bar)
        renderer.AddViewProp(self.text)
        self.length_um = None

    def set_visible(self, on: bool) -> None:
        self.bar.SetVisibility(on)
        self.text.SetVisibility(on)

    def um_per_pixel(self) -> float:
        cam = self.renderer.GetActiveCamera()
        h = max(self.renderer.GetSize()[1], 1)
        if cam.GetParallelProjection():
            return 2 * cam.GetParallelScale() / h
        return 2 * cam.GetDistance() * math.tan(math.radians(cam.GetViewAngle()) / 2) / h

    def update(self) -> None:
        upp = self.um_per_pixel()
        length = choose_scale_length(upp, 70 * self.ui_scale, 190 * self.ui_scale)
        px = length / upp
        x0, y0 = 24 * self.ui_scale, 26 * self.ui_scale
        tick = 6 * self.ui_scale
        pts = vtkPoints()
        for p in ((x0, y0), (x0 + px, y0), (x0, y0 - tick), (x0, y0 + tick),
                  (x0 + px, y0 - tick), (x0 + px, y0 + tick)):
            pts.InsertNextPoint(p[0], p[1], 0)
        lines = vtkCellArray()
        for a, b in ((0, 1), (2, 3), (4, 5)):
            lines.InsertNextCell(2, (a, b))
        self._pd.SetPoints(pts)
        self._pd.SetLines(lines)
        self._pd.Modified()
        label = f"{length * 1000:.0f} nm" if length < 1 else f"{length:g} µm"
        self.text.SetInput(label)
        self.text.SetPosition(x0 + px / 2, y0 + 8 * self.ui_scale)
        self.length_um = length
