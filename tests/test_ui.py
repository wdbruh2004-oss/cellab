"""End-to-end tests of the desktop application (needs a display; run under xvfb-run on CI)."""

import socket

import numpy as np
import pytest
from PySide6 import QtCore

from cellab.render.overlays import project_to_display


@pytest.fixture(scope="module")
def no_network():
    real_connect = socket.socket.connect

    def guarded(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError(f"network access attempted: {address!r}")
        return real_connect(self, address)
    socket.socket.connect = guarded
    yield
    socket.socket.connect = real_connect


@pytest.fixture(scope="module")
def win(qapp, kb, profile, no_network):
    from cellab.ui.main_window import MainWindow
    w = MainWindow(kb, profile, use_settings=False)
    w.resize(1400, 900)
    w.show()
    qapp.processEvents()
    w.initialize()
    qapp.processEvents()
    yield w
    w.close()


def _render(win):
    win.viewport.plotter.render()


def _widget_pos(win, world):
    """World point -> Qt widget coordinates (logical pixels, origin top-left)."""
    ren = win.scene.renderer
    x, y, _ = project_to_display(ren, np.asarray(world, float)[None])[0]
    dpr = win.viewport.device_pixel_ratio()
    h = ren.GetSize()[1]
    return QtCore.QPoint(int(round(x / dpr)), int(round((h - y) / dpr)))


def test_window_initializes(win):
    assert win.scene is not None and win.model is not None
    assert "triangles" in win.status_gl.text()
    assert win.structures.items["mitochondrion"].text(1) == "1,700"


def test_tree_lists_every_structure(win, kb):
    assert set(win.structures.items) == set(kb.structures)


def test_tree_selection_updates_inspector(win, qtbot):
    tree = win.structures.tree
    tree.setCurrentItem(win.structures.items["golgi"])
    assert win.inspector.current == ("golgi", None)
    assert "GO:0005794" in win.inspector.browser.toHtml()
    assert win.selection == ("golgi", None)


def test_visibility_toggle_hides_actors(win):
    win.structures.set_checked("mitochondrion", False)
    assert not any(a.GetVisibility() for a in win.scene.actors["mitochondrion"])
    win.structures.set_checked("mitochondrion", True)
    assert all(a.GetVisibility() for a in win.scene.actors["mitochondrion"])


def test_isolate_and_show_all(win):
    win.isolate("peroxisome")
    visible = {sid for sid, on in win.scene.visible.items() if on}
    assert visible == {"peroxisome", "plasma_membrane"}
    win.show_all()
    assert all(win.scene.visible.values())


def test_search_filters_tree(win):
    win.structures.search.setText("LAMP1")
    shown = [sid for sid, it in win.structures.items.items() if not it.isHidden()]
    assert shown == ["lysosome"]
    win.structures.search.clear()
    assert all(not it.isHidden() for it in win.structures.items.values())


def _top_visible_instance(win, sid):
    """Instance just below the section plane: the first thing a ray from above meets."""
    z_cut = win.scene.section_z
    n = win.model.populations[sid].count
    centers = np.array([win.model.instance_center(sid, i) for i in range(n)])
    extent = np.array([win.model.instance_extent(sid, i) for i in range(n)])
    ok = centers[:, 2] + extent / 2 < z_cut - 0.05
    idx = np.nonzero(ok)[0]
    return int(idx[np.argmax(centers[idx, 2])])


def test_mouse_click_selects_instance(win, qtbot):
    win.isolate("lysosome")
    i = _top_visible_instance(win, "lysosome")
    win.scene.set_camera(*win.scene.focus_target("lysosome", i))
    _render(win)
    win.viewport._last_click_t = 0.0
    qtbot.mouseClick(win.viewport.widget, QtCore.Qt.MouseButton.LeftButton,
                     pos=_widget_pos(win, win.model.instance_center("lysosome", i)))
    assert win.selection == ("lysosome", i)
    assert win.scene.highlight_actor is not None
    assert f"Selected instance #{i + 1}" in win.inspector.browser.toHtml()
    win.show_all()
    win.scene.reset_camera()


def test_section_plane_blocks_picking_of_clipped_geometry(win):
    win.isolate("mitochondrion")
    win.scene.reset_camera()
    a = win.model.populations["mitochondrion"].arrays
    mid = 0.5 * (a["p0"] + a["p1"])
    above = np.nonzero(mid[:, 2] - a["radii"] > win.scene.section_z + 1.0)[0]
    _render(win)
    for i in above[:15]:
        x, y, _ = project_to_display(win.scene.renderer, mid[i][None])[0]
        hit = win.scene.pick(x, y)
        assert hit is None or hit.structure_id != "mitochondrion" or hit.instance != i
    win.show_all()


def test_empty_click_clears_selection(win, qtbot):
    win.select("nucleus", 0)
    win.viewport._last_click_t = 0.0
    qtbot.mouseClick(win.viewport.widget, QtCore.Qt.MouseButton.LeftButton, pos=QtCore.QPoint(5, 5))
    assert win.selection is None


def test_vtk_default_keys_are_disabled(win, qtbot):
    for key in (QtCore.Qt.Key.Key_Q, QtCore.Qt.Key.Key_E, QtCore.Qt.Key.Key_W, QtCore.Qt.Key.Key_3):
        qtbot.keyClick(win.viewport.widget, key)
    assert win.isVisible()
    assert win.scene.actors["mitochondrion"][0].GetProperty().GetRepresentation() == 2  # surface


def test_section_toggle_and_slider(win):
    top = float(win.model.cell_axes[2])
    win.act_section.setChecked(False)
    assert win.scene.section_plane.GetOrigin()[2] > top
    win.act_section.setChecked(True)
    win.section_slider.setValue(800)
    assert win.scene.section_plane.GetOrigin()[2] == pytest.approx(win._slider_z())
    assert win._slider_z() > 0
    win.section_slider.setValue(500)


def test_labels_toggle(win):
    win.act_labels.setChecked(False)
    assert not any(it["text"].GetVisibility() for it in win.scene.labels.items)
    win.act_labels.setChecked(True)
    assert any(it["text"].GetVisibility() for it in win.scene.labels.items)


def test_focus_flies_to_selection(win, qtbot):
    win.select("nucleolus", 0)
    win.focus_selected()
    qtbot.waitUntil(lambda: not win.viewport.is_animating(), timeout=10000)
    focal = np.array(win.scene.camera_state()[1])
    assert np.allclose(focal, win.model.instance_center("nucleolus", 0), atol=1e-6)
    win.scene.reset_camera()


def test_validation_dialog(win, kb):
    from cellab.ui.dialogs import ValidationDialog
    rows = win.validation_rows()
    dlg = ValidationDialog(kb, rows, "test", win)
    assert dlg.table.rowCount() == len(win.profile.compartments)
    statuses = {dlg.table.item(r, 5).text() for r in range(dlg.table.rowCount())}
    assert "FAIL" not in statuses and "PASS" in statuses
    dlg.close()


def test_screenshot_has_content(win, tmp_path):
    from PIL import Image
    path = win.save_screenshot(str(tmp_path / "shot.png"))
    img = np.asarray(Image.open(path).convert("RGB"), float)
    assert img.shape[0] > 200 and img.std() > 20


def test_self_test_passes(win):
    assert win.self_test() == 0


def test_focus_raises_section_plane_for_hidden_target(win, qtbot):
    win.section_slider.setValue(500)
    win.select("golgi", 2)
    center = win.model.instance_center("golgi", 2)
    assert center[2] > win.scene.section_z  # the Golgi sits above the default cut
    win.focus_selected()
    qtbot.waitUntil(lambda: not win.viewport.is_animating(), timeout=10000)
    assert win.scene.section_z >= center[2]
    win.section_slider.setValue(500)
    win.scene.reset_camera()


def test_viewport_is_interactive_even_when_pyvista_off_screen(qapp, monkeypatch):
    """Regression: PYVISTA_OFF_SCREEN=true (set by headless CI actions) removed the interactor."""
    import pyvista
    from PySide6 import QtWidgets

    from cellab.ui.viewport import Viewport
    monkeypatch.setattr(pyvista, "OFF_SCREEN", True)
    host = QtWidgets.QWidget()
    vp = Viewport(host)
    try:
        assert vp.plotter.iren is not None
    finally:
        vp.close()
        host.deleteLater()


def test_simulation_panel_runs(win):
    panel = win.simulation
    panel.n.setValue(300)
    panel.release()
    panel.stop()
    for _ in range(3):
        panel.tick(real_seconds=0.05)
    assert panel.sim.time > 0
    assert win.scene.tracer_count() == 300
    assert "Effective D" in panel.readout.text()
    panel.clear()
    assert win.scene.tracer_count() == 0


def test_guided_tour_selects_structures(win, qtbot):
    win.start_tour()
    assert win.tour_dock.isVisible()
    first = win.tour.tour.stops[0].structure
    assert win.selection == (first, None)
    win.tour.next_btn.click()
    assert win.selection == (win.tour.tour.stops[1].structure, None)
    qtbot.waitUntil(lambda: not win.viewport.is_animating(), timeout=10000)
    win.tour.end_btn.click()
    assert not win.tour_dock.isVisible()
    win.section_slider.setValue(500)
    win.scene.reset_camera()


def test_quiz_dialog_scores_answers(win):
    win.show_quiz()
    dlg = win._quiz
    q = dlg.current
    dlg.choose(q.answer)
    assert dlg.check() is True and dlg.score == 1
    dlg.next_question()
    wrong = (dlg.current.answer + 1) % len(dlg.current.options)
    dlg.choose(wrong)
    assert dlg.check() is False and dlg.score == 1
    dlg.close()
