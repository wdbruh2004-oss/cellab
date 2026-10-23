"""3D viewport: embeds the VTK render window in Qt and turns mouse input into
navigation, selection and level-of-detail switching."""

from __future__ import annotations

import time

import numpy as np
from PySide6 import QtCore, QtWidgets
from pyvistaqt import QtInteractor

from cellab.render.scene import CellScene, PickResult

CLICK_SLOP_PX = 4


class Viewport(QtCore.QObject):
    picked = QtCore.Signal(object)          # PickResult or None
    double_clicked = QtCore.Signal(object)  # PickResult or None

    def __init__(self, parent: QtWidgets.QWidget):
        super().__init__(parent)
        # Always interactive: PYVISTA_OFF_SCREEN (set by some CI/headless setups) would otherwise
        # create the widget without a render-window interactor.
        self.plotter = QtInteractor(parent, auto_update=False, off_screen=False)
        if self.plotter.iren is None:
            raise RuntimeError("the 3D view has no interactor (off-screen rendering is forced)")
        self.widget: QtWidgets.QWidget = self.plotter.interactor
        self.widget.setMinimumSize(320, 240)
        self.scene: CellScene | None = None
        self._press: tuple[int, int] | None = None
        self._dragging = False
        self._last_click_t = 0.0
        self._anim_timer = QtCore.QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._animate_step)
        self._anim = None
        self._wheel_timer = QtCore.QTimer(self)
        self._wheel_timer.setSingleShot(True)
        self._wheel_timer.setInterval(280)
        self._wheel_timer.timeout.connect(self._end_interaction)
        self._disable_vtk_keys()
        # Mouse input is observed at the Qt level: PyVista's interactor style consumes VTK's
        # button-release events, so VTK observers cannot reliably detect clicks.
        self.widget.installEventFilter(self)

    def _disable_vtk_keys(self) -> None:
        """VTK/PyVista bind keys such as 'q' (quit), 'w' (wireframe) and 'e' (exit).
        All keyboard handling goes through Qt shortcuts instead."""
        iren = self.plotter.iren
        iren.clear_key_event_callbacks()
        vtk_iren = iren.interactor
        self._swallowers = []
        for evt in ("CharEvent", "KeyPressEvent", "KeyReleaseEvent"):
            holder: dict[str, int] = {}

            def swallow(_obj, _evt, holder=holder):
                cmd = vtk_iren.GetCommand(holder["tag"])
                if cmd is not None:
                    cmd.SetAbortFlag(1)
            holder["tag"] = vtk_iren.AddObserver(evt, swallow, 100.0)
            self._swallowers.append(swallow)

    def attach(self, scene: CellScene) -> None:
        self.scene = scene

    def device_pixel_ratio(self) -> float:
        return float(self.widget.devicePixelRatioF())

    # --- mouse handling ---------------------------------------------------------------------------
    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt API
        t = event.type()
        E = QtCore.QEvent.Type
        if t in (E.MouseButtonPress, E.MouseButtonDblClick):
            self._stop_animation()
            if event.button() == QtCore.Qt.MouseButton.LeftButton:
                self._press = (event.position().x(), event.position().y())
                self._dragging = False
            else:
                self._press = None
                self._dragging = True
                self._begin_interaction()
        elif t == E.MouseMove and event.buttons() != QtCore.Qt.MouseButton.NoButton:
            if self._press is not None and not self._dragging:
                dx = event.position().x() - self._press[0]
                dy = event.position().y() - self._press[1]
                if abs(dx) > CLICK_SLOP_PX or abs(dy) > CLICK_SLOP_PX:
                    self._dragging = True
                    self._begin_interaction()
        elif t == E.MouseButtonRelease:
            if self._dragging:
                self._dragging = False
                self._press = None
                self._end_interaction()
            elif self._press is not None and event.button() == QtCore.Qt.MouseButton.LeftButton:
                pos = self._press
                self._press = None
                self._click(*pos)
        elif t == E.Wheel:
            self._stop_animation()
            self._begin_interaction()
            self._wheel_timer.start()
        return False

    def to_display(self, x: float, y: float) -> tuple[int, int]:
        """Qt logical widget coordinates -> VTK display pixels (origin bottom-left)."""
        dpr = self.device_pixel_ratio()
        h = self.plotter.render_window.GetSize()[1]
        return int(round(x * dpr)), int(round(h - y * dpr - 1))

    def _click(self, x: float, y: float) -> None:
        if self.scene is None:
            return
        hit = self.scene.pick(*self.to_display(x, y))
        now = time.monotonic()
        double = now - self._last_click_t < 0.35
        self._last_click_t = now
        (self.double_clicked if double else self.picked).emit(hit)

    def _begin_interaction(self) -> None:
        if self.scene is not None:
            self.scene.begin_interaction()

    def _end_interaction(self) -> None:
        if self.scene is not None:
            self.scene.end_interaction()
            self.scene.layout_labels()
            self.plotter.render()

    # --- camera animation ---------------------------------------------------------------------------
    def fly_to(self, position, focal, up, duration: float = 0.45) -> None:
        if self.scene is None:
            return
        start = self.scene.camera_state()
        self._anim = {"t0": time.monotonic(), "dur": max(duration, 1e-3),
                      "p0": np.array(start[0]), "f0": np.array(start[1]), "u0": np.array(start[2]),
                      "p1": np.array(position), "f1": np.array(focal), "u1": np.array(up)}
        self.scene.begin_interaction()
        self._anim_timer.start()

    def _animate_step(self) -> None:
        a = self._anim
        if a is None:
            self._anim_timer.stop()
            return
        t = min((time.monotonic() - a["t0"]) / a["dur"], 1.0)
        s = t * t * (3 - 2 * t)  # smoothstep
        up = a["u0"] + (a["u1"] - a["u0"]) * s
        self.scene.set_camera(a["p0"] + (a["p1"] - a["p0"]) * s, a["f0"] + (a["f1"] - a["f0"]) * s,
                              up / max(np.linalg.norm(up), 1e-9))
        if t >= 1.0:
            self._anim = None
            self._anim_timer.stop()
            self._end_interaction()
        else:
            self.plotter.render()

    def _stop_animation(self) -> None:
        if self._anim is not None:
            self._anim = None
            self._anim_timer.stop()
            if self.scene is not None:
                self.scene.end_interaction()

    def is_animating(self) -> bool:
        return self._anim is not None

    def close(self) -> None:
        self._anim_timer.stop()
        self._wheel_timer.stop()
        self.plotter.close()


__all__ = ["Viewport", "PickResult"]
