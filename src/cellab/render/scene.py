"""The 3D cell scene: actors, section plane, labels, scale bar, highlight and picking."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pyvista as pv
from vtkmodules.util import numpy_support
from vtkmodules.vtkCommonCore import vtkCommand, vtkFloatArray
from vtkmodules.vtkCommonDataModel import vtkPlane
from vtkmodules.vtkRenderingCore import vtkActor, vtkCellPicker, vtkProperty

from cellab.model.cell_model import CellModel
from cellab.render.geometry import INSTANCE, build_meshes
from cellab.render.overlays import LabelOverlay, ScaleBar, project_to_display
from cellab.render.style import BACKGROUND_BOTTOM, BACKGROUND_TOP, HIGHLIGHT, HIGHLIGHT_ALT, style_for
from cellab.science.knowledge import KnowledgeBase

LABELED = ("plasma_membrane", "nucleus", "nucleolus", "nuclear_pore", "chromatin", "rough_er", "smooth_er",
           "golgi", "mitochondrion", "lysosome", "peroxisome", "endosome", "ribosome", "centrosome",
           "microtubule", "actin_cortex", "keratin_if")


@dataclass(frozen=True)
class PickResult:
    structure_id: str
    instance: int
    world: tuple[float, float, float]


def detect_software_gl(render_window) -> bool:
    """True when OpenGL is provided by a CPU rasterizer (Mesa llvmpipe, WARP, SwiftShader)."""
    try:
        info = render_window.ReportCapabilities() or ""
        if "renderer string" not in info:
            render_window.Render()
            info = render_window.ReportCapabilities() or ""
    except Exception:  # noqa: BLE001 - capability probing must never break startup
        return False
    return any(k in info for k in ("llvmpipe", "softpipe", "SwiftShader", "Microsoft Basic Render", "GDI Generic"))


def highlight_color(base: str) -> str:
    """Yellow highlight, or cyan when the structure itself is yellow/orange-gold (low contrast)."""
    import colorsys
    r, g, b = _hex_rgb(base) / 255
    hue = colorsys.rgb_to_hsv(r, g, b)[0] * 360
    return HIGHLIGHT_ALT if 30 <= hue <= 70 else HIGHLIGHT


def _hex_rgb(c: str) -> np.ndarray:
    c = c.lstrip("#")
    return np.array([int(c[i:i + 2], 16) for i in (0, 2, 4)], float)


class CellScene:
    def __init__(self, plotter: pv.Plotter, model: CellModel, kb: KnowledgeBase, ui_scale: float = 1.0):
        self.plotter = plotter
        self.renderer = plotter.renderer
        self.model = model
        self.kb = kb
        self.ui_scale = ui_scale
        self.meshes = build_meshes(model)
        self.actors: dict[str, list[vtkActor]] = {}
        self._owner: dict[int, str] = {}
        self._actor_mesh: dict[int, pv.PolyData] = {}
        self.visible: dict[str, bool] = {sid: True for sid in self.meshes}
        self.section_plane = vtkPlane()
        self.section_plane.SetNormal(0, 0, -1)
        self.section_enabled = True
        self.section_z = float(model.nucleus_center[2])
        self.labels_visible = True
        self.highlight_actor = None
        self.selection: tuple[str, int] | None = None
        self.picker = vtkCellPicker()
        self.picker.SetTolerance(0.004)
        self.picker.PickFromListOn()
        self.labels = LabelOverlay(self.renderer, ui_scale)
        self.scale_bar = ScaleBar(self.renderer, ui_scale)
        self.software_gl = False
        self.interaction_lod = False
        self._lod_hidden: list[vtkActor] = []

    # --- construction ------------------------------------------------------------------------
    def build(self, software_gl: bool | None = None) -> None:
        p = self.plotter
        self.software_gl = detect_software_gl(p.render_window) if software_gl is None else software_gl
        self.interaction_lod = self.software_gl
        p.set_background(BACKGROUND_BOTTOM, top=BACKGROUND_TOP)
        if not self.software_gl:
            # Correct ordering of translucent membranes; too slow for software rasterizers
            p.enable_depth_peeling(number_of_peels=6, occlusion_ratio=0.0)
            p.enable_anti_aliasing("fxaa")
        for sid, parts in self.meshes.items():
            self.actors[sid] = []
            for part, mesh in parts:
                actor = self._add(sid, part, mesh)
                self.actors[sid].append(actor)
                self._owner[id(actor)] = sid
                self._actor_mesh[id(actor)] = mesh
                self.picker.AddPickList(actor)
        self.renderer.AddObserver(vtkCommand.StartEvent, self._on_render_start)
        self.reset_camera(render=False)
        self.set_section(True, self.section_z, relayout=False)

    def _add(self, sid: str, part: str, mesh: pv.PolyData):
        st = style_for(sid, part)
        kw = dict(opacity=st.opacity, pickable=True, show_scalar_bar=False, reset_camera=False,
                  name=f"{sid}:{part}")
        if st.scalars:
            lo, hi = _hex_rgb(st.cmap[0]), _hex_rgb(st.cmap[1])
            t = np.asarray(mesh.cell_data[st.scalars])[:, None]
            mesh.cell_data["rgb"] = ((1 - t) * lo + t * hi).astype(np.uint8)
            kw.update(scalars="rgb", rgb=True, preference="cell")
        else:
            kw["color"] = st.color
        if st.point_size:
            actor = self.plotter.add_mesh(mesh, style="points", point_size=st.point_size * self.ui_scale,
                                          render_points_as_spheres=True, **kw)
        elif st.line_width:
            actor = self.plotter.add_mesh(mesh, line_width=st.line_width * self.ui_scale,
                                          render_lines_as_tubes=st.tubes, **kw)
        else:
            actor = self.plotter.add_mesh(mesh, specular=st.specular, specular_power=st.specular_power,
                                          ambient=st.ambient, diffuse=st.diffuse, **kw)
            actor.prop.interpolation = "phong"
            if st.opacity >= 0.99 and not st.scalars:
                # Inner faces exposed by the section plane read as a solid, darker cut surface
                back = vtkProperty()
                back.SetColor(*(_hex_rgb(st.color) / 255 * 0.55))
                back.SetAmbient(0.55)
                back.SetDiffuse(0.4)
                back.SetSpecular(0.0)
                actor.SetBackfaceProperty(back)
        actor.GetMapper().AddClippingPlane(self.section_plane)
        return actor

    # --- state --------------------------------------------------------------------------------
    def set_visible(self, sid: str, on: bool) -> None:
        self.visible[sid] = on
        for a in self.actors.get(sid, []):
            a.SetVisibility(on)
            a.SetPickable(on)
        self.labels.apply_visibility({s for s, v in self.visible.items() if not v})
        if self.selection and self.selection[0] == sid and not on:
            self.clear_highlight()

    def set_opacity(self, sid: str, opacity: float) -> None:
        for a in self.actors.get(sid, []):
            a.GetProperty().SetOpacity(opacity)

    def set_section(self, enabled: bool, z: float | None = None, relayout: bool = True) -> None:
        self.section_enabled = enabled
        if z is not None:
            self.section_z = float(z)
        top = float(self.model.cell_axes[2])
        self.section_plane.SetOrigin(0, 0, self.section_z if enabled else top + 10.0)
        if relayout:
            self.layout_labels()

    def section_range(self) -> tuple[float, float]:
        top = float(self.model.cell_axes[2])
        return -top, top

    def set_labels_visible(self, on: bool) -> None:
        self.labels_visible = on
        self.labels.visible = on
        self.labels.apply_visibility()

    def set_scale_bar_visible(self, on: bool) -> None:
        self.scale_bar.set_visible(on)

    def triangle_count(self) -> int:
        return int(sum(m.n_cells for parts in self.meshes.values() for _, m in parts))

    # --- camera -----------------------------------------------------------------------------------
    def home_camera(self, fill: float = 0.62) -> tuple[tuple, tuple, tuple]:
        """Oblique top view; the cell spans ``fill`` of the narrower viewport dimension."""
        A = self.model.cell_axes
        d = np.array([0.32, -0.78, 1.0])
        d /= np.linalg.norm(d)
        w, h = self.renderer.GetSize()
        aspect = w / h if w > 0 and h > 0 else 1.0
        dist = float(A.max()) / (fill * math.tan(math.radians(15)) * min(1.0, aspect))
        return tuple(d * dist), (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)

    def reset_camera(self, render: bool = True) -> None:
        self.set_camera(*self.home_camera())
        self.layout_labels()
        if render:
            self.plotter.render()

    def set_camera(self, position, focal, up) -> None:
        cam = self.renderer.GetActiveCamera()
        cam.SetPosition(*position)
        cam.SetFocalPoint(*focal)
        cam.SetViewUp(*up)
        cam.SetViewAngle(30)
        cam.OrthogonalizeViewUp()
        self.renderer.ResetCameraClippingRange()
        self.plotter.camera_set = True  # stop PyVista from resetting the view on its first render

    def camera_state(self) -> tuple[tuple, tuple, tuple]:
        cam = self.renderer.GetActiveCamera()
        return cam.GetPosition(), cam.GetFocalPoint(), cam.GetViewUp()

    def focus_target(self, sid: str, instance: int) -> tuple[tuple, tuple, tuple]:
        center = self.model.instance_center(sid, instance)
        extent = self.model.instance_extent(sid, instance)
        pos, focal, up = self.camera_state()
        direction = np.asarray(pos) - np.asarray(focal)
        direction /= np.linalg.norm(direction)
        dist = max(extent * 3.5, 2.5)
        return tuple(center + direction * dist), tuple(center), up

    # --- labels ------------------------------------------------------------------------------------
    def _eye_depth_buffer(self) -> np.ndarray | None:
        """Eye-space depth (µm) of the last rendered frame, shape (h, w); None if unavailable."""
        ren = self.renderer
        w, h = ren.GetSize()
        cam = ren.GetActiveCamera()
        if cam.GetParallelProjection():
            return None
        state = (cam.GetPosition(), cam.GetFocalPoint(), cam.GetViewUp(), (w, h))
        if state != getattr(self, "_last_frame_state", None):
            self.plotter.render_window.Render()  # depth buffer must match the current camera
        arr = vtkFloatArray()
        if not self.plotter.render_window.GetZbufferData(0, 0, w - 1, h - 1, arr):
            return None
        zwin = numpy_support.vtk_to_numpy(arr).reshape(h, w)
        near, far = cam.GetClippingRange()
        ndc = 2.0 * zwin - 1.0
        return 2.0 * near * far / (far + near - ndc * (far - near))

    def layout_labels(self) -> None:
        """Place one label per visible structure on a ring around the cell (or the viewport when
        zoomed in). Anchors are chosen among points that are actually visible in the last frame."""
        ren = self.renderer
        w, h = ren.GetSize()
        if w < 50 or h < 50:
            self.labels.clear()
            return
        A = self.model.cell_axes
        z_cut = self.section_z if self.section_enabled else float(A[2]) + 1.0
        outline = A * np.array([[math.cos(t), math.sin(t), 0.0] for t in np.linspace(0, 2 * math.pi, 48)])
        ring = project_to_display(ren, outline)[:, :2]
        cx, cy = ring.mean(axis=0)
        rx = max(np.ptp(ring[:, 0]) / 2, 60)
        ry = max(np.ptp(ring[:, 1]) / 2, 60)
        zoomed = rx > 0.42 * w or ry > 0.42 * h
        if zoomed:
            cx, cy, rx, ry = w / 2, h / 2, 0.36 * w, 0.36 * h
        depth = self._eye_depth_buffer()
        cands: dict[str, np.ndarray] = {}
        disp: dict[str, np.ndarray] = {}
        rng = np.random.default_rng(7)
        margin = 0.06
        for sid in LABELED:
            if sid not in self.meshes or not self.visible.get(sid, False):
                continue
            pts = np.vstack([m.points for _, m in self.meshes[sid]])
            if len(pts) > 6000:
                pts = pts[rng.choice(len(pts), 6000, replace=False)]
            pts = pts[pts[:, 2] <= z_cut - 0.02]
            if len(pts) == 0:
                continue
            d = project_to_display(ren, pts)
            inside = ((d[:, 2] > 0) & (d[:, 0] >= margin * w) & (d[:, 0] < (1 - margin) * w)
                      & (d[:, 1] >= margin * h) & (d[:, 1] < (1 - margin) * h))
            opaque = all(a.GetProperty().GetOpacity() >= 0.99 for a in self.actors[sid])
            if depth is not None and opaque:
                xi = np.clip(d[:, 0].astype(int), 0, w - 1)
                yi = np.clip(d[:, 1].astype(int), 0, h - 1)
                inside &= d[:, 2] <= depth[yi, xi] + 0.08
            if not inside.any():
                continue
            cands[sid] = pts[inside]
            disp[sid] = d[inside, :2]
        if not cands:
            self.labels.clear()
            return
        natural = {sid: math.atan2(np.mean(d[:, 1]) - cy, np.mean(d[:, 0]) - cx) for sid, d in disp.items()}
        order = sorted(natural, key=natural.get)
        n = len(order)
        step = 2 * math.pi / n
        best, best_cost = 0.0, float("inf")
        for k in range(72):
            start = -math.pi + k * (2 * math.pi / 72)
            cost = sum(1 - math.cos(start + i * step - natural[s]) for i, s in enumerate(order))
            if cost < best_cost:
                best, best_cost = start, cost
        lrx = min(rx * 1.08 + 26 * self.ui_scale, 0.47 * w)
        lry = min(ry * 1.08 + 18 * self.ui_scale, 0.46 * h)
        labels = []
        for i, sid in enumerate(order):
            theta = best + i * step
            d = disp[sid]
            ang = np.arctan2(d[:, 1] - cy, d[:, 0] - cx)
            rad = np.hypot((d[:, 0] - cx) / rx, (d[:, 1] - cy) / ry)
            score = np.cos(ang - theta) + 0.25 * np.clip(rad, 0, 1.2)
            j = int(np.argmax(score))
            lx, ly = cx + math.cos(theta) * lrx, cy + math.sin(theta) * lry
            labels.append((sid, self.kb.get(sid).name, cands[sid][j], np.array([lx - d[j, 0], ly - d[j, 1]])))
        self.labels.set_labels(labels)

    def _on_render_start(self, *_):
        self.labels.update()
        self.scale_bar.update()
        cam = self.renderer.GetActiveCamera()
        self._last_frame_state = (cam.GetPosition(), cam.GetFocalPoint(), cam.GetViewUp(),
                                  tuple(self.renderer.GetSize()))

    # Fine, numerous structures are hidden while the camera moves when interaction LOD is on
    LOD_STRUCTURES = ("nuclear_pore", "ribosome", "chromatin", "actin_cortex", "smooth_er", "transport_vesicle")

    def begin_interaction(self) -> None:
        if not self.interaction_lod or self._lod_hidden:
            return
        for sid in self.LOD_STRUCTURES:
            for a in self.actors.get(sid, []):
                if a.GetVisibility():
                    a.SetVisibility(False)
                    self._lod_hidden.append(a)

    def end_interaction(self) -> None:
        for a in self._lod_hidden:
            a.SetVisibility(True)
        self._lod_hidden = []

    # --- selection ---------------------------------------------------------------------------------
    def pick(self, x: float, y: float) -> PickResult | None:
        """Pick at display coordinates. Translucent outer membranes are picked last."""
        deferred = [a for a in self.actors.get("plasma_membrane", []) if a.GetPickable()]
        for a in deferred:
            a.SetPickable(False)
        try:
            hit = self._pick_once(x, y)
        finally:
            for a in deferred:
                a.SetPickable(self.visible["plasma_membrane"])
        return hit or self._pick_once(x, y)

    def _pick_once(self, x: float, y: float) -> PickResult | None:
        if not self.picker.Pick(x, y, 0, self.renderer):
            return None
        actor = self.picker.GetActor()
        cell = self.picker.GetCellId()
        if actor is None or cell < 0 or id(actor) not in self._owner:
            return None
        mesh = self._actor_mesh[id(actor)]
        inst = int(mesh.cell_data[INSTANCE][cell])
        return PickResult(self._owner[id(actor)], inst, tuple(self.picker.GetPickPosition()))

    def highlight(self, sid: str, instance: int | None) -> None:
        self.clear_highlight(render=False)
        self.selection = (sid, instance if instance is not None else -1)
        if instance is None or sid not in self.meshes or sid in ("plasma_membrane",):
            return
        parts = []
        for _, mesh in self.meshes[sid]:
            ids = np.nonzero(np.asarray(mesh.cell_data[INSTANCE]) == instance)[0]
            if len(ids):
                parts.append(mesh.extract_cells(ids).extract_surface(algorithm=None))
        if not parts:
            return
        sel = parts[0] if len(parts) == 1 else parts[0].merge(parts[1:])
        st = style_for(sid, self.meshes[sid][0][0])
        color = highlight_color(st.color)
        if st.point_size:
            actor = self.plotter.add_mesh(sel, color=color, style="points", render_points_as_spheres=True,
                                          point_size=st.point_size * 3.2 * self.ui_scale, pickable=False,
                                          reset_camera=False, name="__highlight__")
        elif st.line_width:
            actor = self.plotter.add_mesh(sel, color=color, line_width=st.line_width * 2.6 * self.ui_scale,
                                          render_lines_as_tubes=True, pickable=False, reset_camera=False,
                                          name="__highlight__")
        else:
            c = np.asarray(sel.center)
            grown = sel.copy()
            grown.points = c + (grown.points - c) * 1.06
            actor = self.plotter.add_mesh(grown, color=color, opacity=0.45, ambient=0.6,
                                          pickable=False, reset_camera=False, name="__highlight__")
        actor.GetMapper().AddClippingPlane(self.section_plane)
        self.highlight_actor = actor

    def clear_highlight(self, render: bool = False) -> None:
        if self.highlight_actor is not None:
            self.plotter.remove_actor(self.highlight_actor, render=False)
            self.highlight_actor = None
        self.selection = None
        if render:
            self.plotter.render()
