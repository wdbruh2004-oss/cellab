"""Simulation dock: Brownian diffusion of tracer molecules through the crowded cytoplasm."""

from __future__ import annotations

from collections.abc import Callable
from html import escape

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from cellab.model.cell_model import CellModel
from cellab.model.obstacles import ObstacleField
from cellab.render.scene import CellScene
from cellab.science.knowledge import KnowledgeBase
from cellab.sim.diffusion import DiffusionSim, load_tracers

MAX_STEPS_PER_FRAME = 60


class MsdPlot(QtWidgets.QWidget):
    """Mean squared displacement against time, with the free-diffusion line 6·D·t for comparison."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(170)
        self.history: list[tuple[float, float]] = []
        self.D = 0.0

    def set_data(self, history: list[tuple[float, float]], D: float) -> None:
        self.history = list(history)
        self.D = D
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(46, 10, -10, -30)
        p.fillRect(self.rect(), QtGui.QColor("#0b1020"))
        p.setPen(QtGui.QPen(QtGui.QColor("#3b4a72"), 1))
        p.drawRect(r)
        p.setPen(QtGui.QColor("#9fb3d9"))
        p.drawText(QtCore.QRectF(r.left(), r.bottom() + 6, r.width(), 18), QtCore.Qt.AlignmentFlag.AlignCenter,
                   "time (ms)")
        p.save()
        p.translate(12, r.center().y())
        p.rotate(-90)
        p.drawText(QtCore.QRectF(-60, -10, 120, 18), QtCore.Qt.AlignmentFlag.AlignCenter, "MSD (µm²)")
        p.restore()
        if len(self.history) < 2 or self.history[-1][0] <= 0:
            p.drawText(r, QtCore.Qt.AlignmentFlag.AlignCenter, "Release particles to start")
            return
        t_max = self.history[-1][0]
        y_max = max(max(m for _, m in self.history), 6 * self.D * t_max) * 1.05

        def pt(t: float, m: float) -> QtCore.QPointF:
            return QtCore.QPointF(r.left() + r.width() * t / t_max, r.bottom() - r.height() * m / y_max)

        pen = QtGui.QPen(QtGui.QColor("#9aa4b8"), 1.2, QtCore.Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawLine(pt(0, 0), pt(t_max, 6 * self.D * t_max))
        p.setPen(QtGui.QPen(QtGui.QColor("#39ff88"), 2))
        p.drawPolyline(QtGui.QPolygonF([pt(t, m) for t, m in self.history]))
        p.setPen(QtGui.QColor("#9fb3d9"))
        p.drawText(QtCore.QPointF(r.left() + 4, r.top() + 14), f"{y_max:.3g}")
        p.drawText(QtCore.QPointF(r.right() - 48, r.bottom() - 4), f"{1000 * t_max:.3g}")
        p.drawText(QtCore.QPointF(r.left() + 8, r.top() + 32), "— simulated   - - free 6·D·t")


class SimulationPanel(QtWidgets.QWidget):
    def __init__(self, kb: KnowledgeBase, parent=None):
        super().__init__(parent)
        self.kb = kb
        self.tracers = load_tracers()
        self.model: CellModel | None = None
        self.scene: CellScene | None = None
        self._render: Callable[[], None] = lambda: None
        self._selection_point: Callable[[], np.ndarray | None] = lambda: None
        self._field: ObstacleField | None = None
        self.sim: DiffusionSim | None = None

        self.tracer = QtWidgets.QComboBox()
        for t in self.tracers:
            self.tracer.addItem(t.name)
        self.tracer.addItem("Custom diffusion coefficient")
        self.D = QtWidgets.QDoubleSpinBox()
        self.D.setRange(0.1, 1000.0)
        self.D.setDecimals(1)
        self.D.setSuffix(" µm²/s")
        self.n = QtWidgets.QSpinBox()
        self.n.setRange(50, 5000)
        self.n.setSingleStep(100)
        self.n.setValue(800)
        self.speed = QtWidgets.QDoubleSpinBox()
        self.speed.setRange(0.5, 500.0)
        self.speed.setValue(20.0)
        self.speed.setSuffix(" ms per second")
        self.where = QtWidgets.QComboBox()
        self.where.addItems(["Near the nucleus", "At the selected structure"])
        form = QtWidgets.QFormLayout()
        form.addRow("Molecule", self.tracer)
        form.addRow("Diffusion coefficient", self.D)
        form.addRow("Particles", self.n)
        form.addRow("Simulation speed", self.speed)
        form.addRow("Release", self.where)

        self.release_btn = QtWidgets.QPushButton("Release")
        self.pause_btn = QtWidgets.QPushButton("Pause")
        self.clear_btn = QtWidgets.QPushButton("Clear")
        self.pause_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        row = QtWidgets.QHBoxLayout()
        for b in (self.release_btn, self.pause_btn, self.clear_btn):
            row.addWidget(b)
        self.readout = QtWidgets.QLabel()
        self.readout.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.plot = MsdPlot()
        self.source = QtWidgets.QLabel()
        self.source.setWordWrap(True)
        self.source.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.source.setStyleSheet("color: #9aa4b8;")

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        intro = QtWidgets.QLabel("<b>Diffusion in the crowded cytoplasm</b><br><span style='color:#9aa4b8'>"
                                 "Brownian dynamics of tracer molecules among the model's organelles.</span>")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        lay.addLayout(form)
        lay.addLayout(row)
        lay.addWidget(self.readout)
        lay.addWidget(self.plot)
        lay.addWidget(self.source)
        lay.addStretch(1)

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.tick)
        self._clock = QtCore.QElapsedTimer()
        self.tracer.currentIndexChanged.connect(self._on_tracer)
        self.release_btn.clicked.connect(self.release)
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.clear_btn.clicked.connect(self.clear)
        self._on_tracer(0)
        self._update_readout()

    def attach(self, model: CellModel, scene: CellScene, render: Callable[[], None],
               selection_point: Callable[[], np.ndarray | None]) -> None:
        self.model, self.scene, self._render, self._selection_point = model, scene, render, selection_point
        self._field = None

    def _on_tracer(self, index: int) -> None:
        custom = index >= len(self.tracers)
        self.D.setEnabled(custom)
        if custom:
            self.source.setText("Custom value: no literature source.")
            return
        t = self.tracers[index]
        self.D.setValue(t.D)
        refs = "; ".join(self.kb.references[r].short + (f", {at}" if at else "") for r, at in t.refs)
        self.source.setText(f"D = {t.D:g} µm²/s <i>({escape(t.status)})</i> — {escape(refs)}<br>{escape(t.note)}<br>"
                            "Model: point particles, rejected moves at organelle, nuclear and plasma-membrane "
                            "surfaces; no binding, flow or active transport.")

    def release_point(self) -> np.ndarray:
        if self.where.currentIndex() == 1:
            p = self._selection_point()
            if p is not None:
                return np.asarray(p, float)
        m = self.model
        return m.nucleus_center + np.array([-1.0, 0.0, 0.0]) * m.nucleus_axes[0] * 1.45

    def release(self) -> None:
        if self.model is None or self.scene is None:
            return
        if self._field is None:
            self._field = ObstacleField(self.model)
        self.sim = DiffusionSim(D=self.D.value(), start=self.release_point(), n=self.n.value(),
                                obstacles=self._field, seed=7)
        self.scene.set_tracers(self.sim.x)
        self.scene.begin_interaction()
        self._clock.start()
        self.timer.start()
        self.pause_btn.setEnabled(True)
        self.pause_btn.setText("Pause")
        self.clear_btn.setEnabled(True)
        self._update_readout()
        self._render()

    def toggle_pause(self) -> None:
        if self.sim is None:
            return
        if self.timer.isActive():
            self.timer.stop()
            self.pause_btn.setText("Resume")
            self.scene.end_interaction()
            self._render()
        else:
            self._clock.start()
            self.scene.begin_interaction()
            self.timer.start()
            self.pause_btn.setText("Pause")

    def clear(self) -> None:
        self.stop()
        self.sim = None
        if self.scene is not None:
            self.scene.set_tracers(None)
            self._render()
        self.pause_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self._update_readout()

    def stop(self) -> None:
        if self.timer.isActive():
            self.timer.stop()
            if self.scene is not None:
                self.scene.end_interaction()

    def tick(self, real_seconds: float | None = None) -> None:
        if self.sim is None:
            return
        if real_seconds is None:
            real_seconds = max(self._clock.restart() / 1000.0, 1e-3)
        duration = min(self.speed.value() / 1000.0 * real_seconds, MAX_STEPS_PER_FRAME * self.sim.dt)
        self.sim.advance(duration)
        self.scene.set_tracers(self.sim.x)
        self._update_readout()
        self._render()

    def _update_readout(self) -> None:
        s = self.sim
        if s is None:
            self.readout.setText("<span style='color:#9aa4b8'>No particles released.</span>")
            self.plot.set_data([], self.D.value())
            return
        msd = s.msd()
        d_eff = s.effective_D()
        rows = [("Simulated time", f"{1000 * s.time:.2f} ms"),
                ("RMS displacement", f"{msd ** 0.5:.2f} µm"),
                ("Effective D (MSD / 6t)", f"{d_eff:.1f} µm²/s"),
                ("Obstruction (D<sub>eff</sub> / D)", f"{d_eff / s.D:.2f}")]
        self.readout.setText("<table>" + "".join(f"<tr><td style='color:#9aa4b8'>{k}&nbsp;&nbsp;</td>"
                                                 f"<td><b>{v}</b></td></tr>" for k, v in rows) + "</table>")
        self.plot.set_data(s.history, s.D)
