"""Regenerate the documentation screenshots in docs/images (needs a display or xvfb-run)."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np

os.environ.setdefault("QT_API", "pyside6")
from PySide6 import QtWidgets  # noqa: E402

from cellab.science.knowledge import KnowledgeBase  # noqa: E402
from cellab.science.profile import CellProfile  # noqa: E402
from cellab.ui.main_window import MainWindow  # noqa: E402
from cellab.ui.theme import apply_theme  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "docs" / "images"


def settle(app, win, seconds=0.6):
    end = time.monotonic() + seconds
    while time.monotonic() < end or win.viewport.is_animating():
        app.processEvents()
        time.sleep(0.02)
    win.viewport.plotter.render()
    app.processEvents()


def grab(app, win, name):
    settle(app, win)
    path = OUT / name
    win.screen().grabWindow(win.winId()).save(str(path))
    print("wrote", path)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    app = QtWidgets.QApplication(sys.argv[:1])
    apply_theme(app)
    kb, profile = KnowledgeBase.load(), CellProfile.load()
    win = MainWindow(kb, profile, use_settings=False)
    win.resize(1600, 950)
    win.show()
    app.processEvents()
    win.initialize()
    grab(app, win, "overview.png")

    # A mitochondrion exposed by the section plane, selected and framed
    m = win.model
    a = m.populations["mitochondrion"].arrays
    mid = 0.5 * (a["p0"] + a["p1"])
    top = mid[:, 2] + a["radii"]
    ok = np.nonzero((top < win.scene.section_z - 0.05) & (np.abs(mid[:, 0]) < 6))[0]
    i = int(ok[np.argmax(mid[ok, 2])])
    win.select("mitochondrion", i)
    pos, focal, up = win.scene.focus_target("mitochondrion", i)
    pos = np.asarray(focal) + (np.asarray(pos) - np.asarray(focal)) * 2.2
    win.viewport.fly_to(pos, focal, up, duration=0.01)
    grab(app, win, "selection.png")

    win.clear_selection()
    win.isolate("golgi")
    for sid in ("centrosome", "microtubule", "transport_vesicle", "nucleus"):
        win.structures.set_checked(sid, True)
    win.select("golgi", 2)
    win.focus_selected()
    settle(app, win, 1.0)
    pos, focal, up = win.scene.camera_state()
    pos = np.asarray(focal) + (np.asarray(pos) - np.asarray(focal)) * 2.0
    win.viewport.fly_to(pos, focal, up, duration=0.01)
    grab(app, win, "golgi_centrosome.png")
    win.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
