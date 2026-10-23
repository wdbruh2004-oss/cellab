"""Main application window."""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

import cellab
from cellab.model.cell_model import CellModel, build_cell_model
from cellab.render.scene import CellScene, PickResult
from cellab.science.knowledge import KnowledgeBase
from cellab.science.profile import CellProfile
from cellab.science.validation import validate_model
from cellab.ui.dialogs import AboutDialog, ValidationDialog
from cellab.ui.panels import InspectorPanel, StructurePanel
from cellab.ui.viewport import Viewport

SECTION_STEPS = 1000


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, kb: KnowledgeBase, profile: CellProfile, software_gl: bool | None = None,
                 use_settings: bool = True):
        super().__init__()
        self.kb = kb
        self.profile = profile
        self.software_gl_override = software_gl
        self.use_settings = use_settings
        self.model: CellModel | None = None
        self.scene: CellScene | None = None
        self.selection: tuple[str, int | None] | None = None
        self.setWindowTitle(f"{cellab.APP_NAME} — {profile.name}")
        self.setWindowIcon(app_icon())
        self.resize(1500, 920)
        self.setDockOptions(QtWidgets.QMainWindow.DockOption.AnimatedDocks
                            | QtWidgets.QMainWindow.DockOption.AllowTabbedDocks)

        self.viewport = Viewport(self)
        self.setCentralWidget(self.viewport.widget)
        self.structures = StructurePanel(kb)
        self.inspector = InspectorPanel(kb)
        self._dock("Structures", self.structures, QtCore.Qt.DockWidgetArea.LeftDockWidgetArea, 300)
        self._dock("Scientific inspector", self.inspector, QtCore.Qt.DockWidgetArea.RightDockWidgetArea, 420)
        self._build_actions()
        self.status_sel = QtWidgets.QLabel("No selection")
        self.status_gl = QtWidgets.QLabel("")
        self.statusBar().addWidget(self.status_sel, 1)
        self.statusBar().addPermanentWidget(self.status_gl)

        self.viewport.picked.connect(self._on_pick)
        self.viewport.double_clicked.connect(self._on_double_click)
        self.structures.structure_activated.connect(lambda sid: self.select(sid, None))
        self.structures.visibility_changed.connect(self._on_visibility)
        self.inspector.focus_requested.connect(self.focus_selected)
        self.inspector.isolate_requested.connect(self.isolate)
        if use_settings:
            self._restore_settings()

    # --- layout ---------------------------------------------------------------------------------
    def _dock(self, title: str, widget: QtWidgets.QWidget, area, width: int) -> QtWidgets.QDockWidget:
        dock = QtWidgets.QDockWidget(title, self)
        dock.setObjectName(title.replace(" ", "_"))
        dock.setWidget(widget)
        dock.setFeatures(QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable
                         | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.addDockWidget(area, dock)
        self.resizeDocks([dock], [width], QtCore.Qt.Orientation.Horizontal)
        return dock

    def _action(self, text: str, slot, shortcut=None, checkable=False, checked=False, tip="") -> QtGui.QAction:
        a = QtGui.QAction(text, self)
        if shortcut:
            a.setShortcuts([QtGui.QKeySequence(s) for s in (shortcut if isinstance(shortcut, (list, tuple))
                                                             else [shortcut])])
        a.setCheckable(checkable)
        if checkable:
            a.setChecked(checked)
            a.toggled.connect(slot)
        else:
            a.triggered.connect(slot)
        a.setToolTip(tip or text)
        a.setStatusTip(tip or text)
        self.addAction(a)
        return a

    def _build_actions(self) -> None:
        self.act_reset = self._action("Reset view", self.reset_view, ["Home", "R"], tip="Reset camera (Home / R)")
        self.act_section = self._action("Section", self.set_section_enabled, "S", True, True,
                                        tip="Cut the cell open with a horizontal section plane (S)")
        self.act_labels = self._action("Labels", self.set_labels_visible, "L", True, True,
                                       tip="Show structure labels (L)")
        self.act_scale = self._action("Scale bar", self.set_scale_bar_visible, None, True, True)
        self.act_focus = self._action("Focus", self.focus_selected, "F", tip="Fly to the selection (F)")
        self.act_show_all = self._action("Show all", self.show_all, "Ctrl+Shift+A",
                                         tip="Make every structure visible")
        self.act_clear = self._action("Clear selection", self.clear_selection, "Esc")
        self.act_search = self._action("Search", self._focus_search, "Ctrl+F")
        self.act_shot = self._action("Save screenshot…", lambda: self.save_screenshot(None), "Ctrl+Shift+S")
        self.act_validation = self._action("Scientific validation report…", self.show_validation, "Ctrl+Shift+V")
        self.act_about = self._action(f"About {cellab.APP_NAME}…", self.show_about)
        self.act_quit = self._action("Quit", self.close, "Ctrl+Q")

        tb = QtWidgets.QToolBar("View")
        tb.setObjectName("view_toolbar")
        tb.setMovable(False)
        tb.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(tb)
        for a in (self.act_reset, self.act_focus, self.act_show_all):
            tb.addAction(a)
        tb.addSeparator()
        tb.addAction(self.act_section)
        self.section_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.section_slider.setRange(0, SECTION_STEPS)
        self.section_slider.setFixedWidth(220)
        self.section_slider.setToolTip("Section depth")
        self.section_label = QtWidgets.QLabel("  z = 0.0 µm  ")
        tb.addWidget(self.section_slider)
        tb.addWidget(self.section_label)
        tb.addSeparator()
        for a in (self.act_labels, self.act_scale):
            tb.addAction(a)
        tb.addSeparator()
        tb.addAction(self.act_validation)
        self.section_slider.valueChanged.connect(self._on_section_slider)
        self.section_slider.sliderPressed.connect(lambda: self.scene and self.scene.begin_interaction())
        self.section_slider.sliderReleased.connect(self._on_section_released)

        mb = self.menuBar()
        m = mb.addMenu("&File")
        m.addAction(self.act_shot)
        m.addSeparator()
        m.addAction(self.act_quit)
        m = mb.addMenu("&View")
        for a in (self.act_reset, self.act_focus, self.act_show_all, self.act_clear):
            m.addAction(a)
        m.addSeparator()
        for a in (self.act_section, self.act_labels, self.act_scale):
            m.addAction(a)
        m = mb.addMenu("&Science")
        m.addAction(self.act_validation)
        m.addAction(self.act_search)
        m = mb.addMenu("&Help")
        m.addAction(self.act_about)

    # --- initialization --------------------------------------------------------------------------
    def initialize(self) -> None:
        """Build the model and the scene. Call after the window is shown (needs an OpenGL context)."""
        t0 = time.perf_counter()
        self.model = build_cell_model(self.profile)
        t1 = time.perf_counter()
        self.scene = CellScene(self.viewport.plotter, self.model, self.kb,
                               ui_scale=self.viewport.device_pixel_ratio())
        self.scene.build(software_gl=self.software_gl_override)
        self.viewport.attach(self.scene)
        self.structures.set_counts(self.model)
        self.inspector.set_model(self.model)
        lo, hi = self.scene.section_range()
        self.section_slider.blockSignals(True)
        self.section_slider.setValue(int(round((self.scene.section_z - lo) / (hi - lo) * SECTION_STEPS)))
        self.section_slider.blockSignals(False)
        self._update_section_label()
        self.scene.reset_camera(render=False)
        self.viewport.plotter.render()
        self.scene.layout_labels()
        self.viewport.plotter.render()
        t2 = time.perf_counter()
        mode = "software OpenGL — fine structures hide while moving" if self.scene.software_gl else "hardware OpenGL"
        self.status_gl.setText(f"{self.scene.triangle_count():,} triangles · {mode}")
        self.statusBar().showMessage(f"Model built in {t1 - t0:.1f} s, scene in {t2 - t1:.1f} s", 8000)

    # --- selection ---------------------------------------------------------------------------------
    def _on_pick(self, hit: PickResult | None) -> None:
        if hit is None:
            self.clear_selection()
        else:
            self.select(hit.structure_id, hit.instance)

    def _on_double_click(self, hit: PickResult | None) -> None:
        if hit is not None:
            self.select(hit.structure_id, hit.instance)
            self.focus_selected()

    def select(self, sid: str, instance: int | None) -> None:
        self.selection = (sid, instance)
        self.inspector.show_structure(sid, instance)
        self.structures.select(sid)
        if self.scene is not None:
            self.scene.highlight(sid, instance)
            self.viewport.plotter.render()
        name = self.kb.get(sid).name
        self.status_sel.setText(f"Selected: {name}" + (f" #{instance + 1}" if instance is not None else ""))

    def clear_selection(self) -> None:
        self.selection = None
        self.inspector.show_welcome()
        if self.scene is not None:
            self.scene.clear_highlight(render=True)
        self.status_sel.setText("No selection")

    def focus_selected(self) -> None:
        if self.scene is None or self.selection is None:
            return
        sid, inst = self.selection
        if not self.kb.get(sid).renderable:
            return
        if inst is None:
            inst = self._representative_instance(sid)
        self._reveal(sid, inst)
        self.viewport.fly_to(*self.scene.focus_target(sid, inst))

    def _reveal(self, sid: str, inst: int) -> None:
        """Raise the section plane when the focus target lies above it (otherwise it is clipped away)."""
        if not self.act_section.isChecked():
            return
        top = float(self.model.instance_center(sid, inst)[2]) + self.model.instance_extent(sid, inst) / 2
        if top > self.scene.section_z:
            lo, hi = self.scene.section_range()
            z = min(top + 0.25, hi)
            self.section_slider.setValue(int(round((z - lo) / (hi - lo) * SECTION_STEPS)))

    def _representative_instance(self, sid: str) -> int:
        """Instance nearest the camera focal point, so focusing a whole population stays local."""
        pop = self.model.populations[sid]
        if pop.count == 1 or pop.kind in ("ellipsoid", "sheets", "points"):
            return 0
        focal = np.array(self.scene.camera_state()[1])
        n = min(pop.count, 4000)
        centers = np.array([self.model.instance_center(sid, i) for i in range(n)])
        return int(np.argmin(np.linalg.norm(centers - focal, axis=1)))

    # --- visibility --------------------------------------------------------------------------------
    def _on_visibility(self, sid: str, on: bool) -> None:
        if self.scene is not None:
            self.scene.set_visible(sid, on)
            self.viewport.plotter.render()

    def isolate(self, sid: str) -> None:
        for other in self.structures.items:
            if self.kb.get(other).renderable:
                self.structures.set_checked(other, other in (sid, "plasma_membrane"))

    def show_all(self) -> None:
        for sid in self.structures.items:
            if self.kb.get(sid).renderable:
                self.structures.set_checked(sid, True)

    # --- view toggles --------------------------------------------------------------------------------
    def reset_view(self) -> None:
        if self.scene is not None:
            self.viewport.fly_to(*self.scene.home_camera())

    def set_section_enabled(self, on: bool) -> None:
        self.section_slider.setEnabled(on)
        if self.scene is not None:
            self.scene.set_section(on)
            self.viewport.plotter.render()

    def _slider_z(self) -> float:
        lo, hi = self.scene.section_range()
        return lo + (hi - lo) * self.section_slider.value() / SECTION_STEPS

    def _update_section_label(self) -> None:
        if self.scene is not None:
            self.section_label.setText(f"  z = {self._slider_z():+.1f} µm  ")

    def _on_section_slider(self, _value: int) -> None:
        if self.scene is None:
            return
        self._update_section_label()
        self.scene.set_section(self.act_section.isChecked(), self._slider_z(), relayout=False)
        self.viewport.plotter.render()

    def _on_section_released(self) -> None:
        if self.scene is not None:
            self.scene.end_interaction()
            self.scene.layout_labels()
            self.viewport.plotter.render()

    def set_labels_visible(self, on: bool) -> None:
        if self.scene is not None:
            self.scene.set_labels_visible(on)
            self.viewport.plotter.render()

    def set_scale_bar_visible(self, on: bool) -> None:
        if self.scene is not None:
            self.scene.set_scale_bar_visible(on)
            self.viewport.plotter.render()

    def _focus_search(self) -> None:
        self.structures.search.setFocus()
        self.structures.search.selectAll()

    # --- reports & files ---------------------------------------------------------------------------
    def mesh_volumes(self) -> dict[str, float]:
        out = {}
        for sid, parts in self.scene.meshes.items():
            if self.model.populations[sid].volumes is not None and parts[0][0] == "surface":
                out[sid] = float(parts[0][1].volume)
        return out

    def validation_rows(self):
        return validate_model(self.model, self.kb, self.mesh_volumes() if self.scene else None)

    def show_validation(self) -> None:
        if self.model is None:
            return
        src = self.kb.references[self.profile.source_ref].short + ", " + self.profile.source_at
        ValidationDialog(self.kb, self.validation_rows(), src, self).exec()

    def show_about(self) -> None:
        AboutDialog(self.gl_info(), self).exec()

    def gl_info(self) -> str:
        info = self.viewport.plotter.render_window.ReportCapabilities() or ""
        lines = [ln.split(":", 1)[1].strip() for ln in info.splitlines()
                 if ln.startswith(("OpenGL renderer string", "OpenGL version string"))]
        return " · ".join(lines) or "unknown"

    def save_screenshot(self, path: str | None) -> str | None:
        if path is None:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save screenshot", "cell.png", "PNG image (*.png)")
            if not path:
                return None
        self.viewport.plotter.render()
        self.viewport.plotter.screenshot(path)
        self.statusBar().showMessage(f"Saved {path}", 5000)
        return path

    def self_test(self, report_path: str | None = None) -> int:
        """Non-interactive health check used by the packaged build. Returns a process exit code."""
        report: dict = {"version": cellab.__version__}
        try:
            rows = self.validation_rows()
            report["validation"] = {r.compartment: r.status for r in rows}
            ok = all(r.status in ("PASS", "REPRESENTATIONAL", "IMPLICIT") for r in rows)
            w, h = self.scene.renderer.GetSize()
            hit = self.scene.pick(w // 2, h // 2)
            report["center_pick"] = None if hit is None else [hit.structure_id, hit.instance]
            ok &= hit is not None
            if hit is not None:
                self.select(hit.structure_id, hit.instance)  # exercises highlight extraction
                ok &= self.scene.highlight_actor is not None or hit.structure_id == "plasma_membrane"
                self.clear_selection()
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                shot = Path(tmp) / "self_test.png"
                self.save_screenshot(str(shot))
                report["screenshot_bytes"] = shot.stat().st_size
                ok &= report["screenshot_bytes"] > 10_000
            report["gl"] = self.gl_info()
            report["ok"] = bool(ok)
        except Exception as exc:  # noqa: BLE001 - the self-test reports every failure
            report["error"] = repr(exc)
            report["ok"] = False
        text = json.dumps(report, indent=2)
        print(text)
        if report_path:
            Path(report_path).write_text(text, encoding="utf-8")
        return 0 if report["ok"] else 1

    # --- settings ------------------------------------------------------------------------------------
    def _restore_settings(self) -> None:
        s = QtCore.QSettings()
        geo = s.value("window/geometry")
        state = s.value("window/state")
        if geo is not None:
            self.restoreGeometry(geo)
        if state is not None:
            self.restoreState(state)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self.use_settings:
            s = QtCore.QSettings()
            s.setValue("window/geometry", self.saveGeometry())
            s.setValue("window/state", self.saveState())
        self.viewport.close()
        super().closeEvent(event)


def app_icon() -> QtGui.QIcon:
    from cellab.paths import data_path
    path = data_path("icons", "cellab.png")
    if Path(path).exists():
        return QtGui.QIcon(str(path))
    return QtGui.QIcon()
