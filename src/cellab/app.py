"""Application entry point."""

from __future__ import annotations

import argparse
import os
import sys

os.environ.setdefault("QT_API", "pyside6")


def _parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="cellab", description="CellLab: offline 3D cellular laboratory")
    p.add_argument("--screenshot", metavar="PNG", help="render the default view to PNG and exit")
    p.add_argument("--window-screenshot", metavar="PNG", help="capture the whole window to PNG and exit")
    p.add_argument("--select", metavar="STRUCTURE[:N]", help="select a structure (and instance) at startup")
    p.add_argument("--self-test", action="store_true", help="run a non-interactive health check and exit")
    p.add_argument("--report", metavar="JSON", help="with --self-test: also write the report to this file")
    p.add_argument("--software-gl", action="store_true", help="force the software-rendering performance mode")
    p.add_argument("--size", default=None, help="window size WIDTHxHEIGHT")
    p.add_argument("--no-settings", action="store_true", help="ignore saved window layout")
    return p.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    args = _parse(sys.argv[1:] if argv is None else argv)
    from PySide6 import QtCore, QtGui, QtWidgets

    import cellab
    from cellab.science.knowledge import KnowledgeBase
    from cellab.science.profile import CellProfile
    from cellab.ui.main_window import MainWindow, app_icon
    from cellab.ui.theme import apply_theme

    QtCore.QCoreApplication.setOrganizationName(cellab.APP_NAME)
    QtCore.QCoreApplication.setApplicationName(cellab.APP_NAME)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
    apply_theme(app)
    app.setWindowIcon(app_icon())

    splash = QtWidgets.QSplashScreen(_splash_pixmap(cellab.APP_NAME, cellab.__version__))
    splash.show()
    splash.showMessage("Loading knowledge base…", QtCore.Qt.AlignmentFlag.AlignBottom
                       | QtCore.Qt.AlignmentFlag.AlignHCenter, QtGui.QColor("#9fb3d9"))
    app.processEvents()
    kb = KnowledgeBase.load()
    profile = CellProfile.load()
    profile.validate(set(kb.structures))

    use_settings = not (args.no_settings or args.screenshot or args.window_screenshot or args.self_test)
    win = MainWindow(kb, profile, software_gl=True if args.software_gl else None, use_settings=use_settings)
    if args.size:
        w, h = (int(v) for v in args.size.lower().split("x"))
        win.resize(w, h)
    win.show()
    splash.showMessage("Building the cell model…", QtCore.Qt.AlignmentFlag.AlignBottom
                       | QtCore.Qt.AlignmentFlag.AlignHCenter, QtGui.QColor("#9fb3d9"))
    app.processEvents()
    win.initialize()
    splash.finish(win)

    if args.select:
        sid, _, inst = args.select.partition(":")
        win.select(sid, int(inst) - 1 if inst else None)
    if args.screenshot:
        QtCore.QTimer.singleShot(400, lambda: (win.save_screenshot(args.screenshot), win.close(), app.quit()))
    elif args.window_screenshot:
        def _grab():
            win.viewport.plotter.render()
            app.processEvents()
            win.screen().grabWindow(win.winId()).save(args.window_screenshot)
            win.close()
            app.quit()
        QtCore.QTimer.singleShot(600, _grab)
    elif args.self_test:
        def _test():
            code = win.self_test(args.report)
            win.close()
            app.exit(code)
        QtCore.QTimer.singleShot(400, _test)
    return app.exec()


def _splash_pixmap(name: str, version: str):
    from PySide6 import QtCore, QtGui
    pm = QtGui.QPixmap(520, 300)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    g = QtGui.QLinearGradient(0, 0, 0, 300)
    g.setColorAt(0, QtGui.QColor("#1b2547"))
    g.setColorAt(1, QtGui.QColor("#06080f"))
    p.fillRect(pm.rect(), g)
    p.setPen(QtCore.Qt.PenStyle.NoPen)
    p.setBrush(QtGui.QColor(138, 182, 232, 60))
    p.drawEllipse(QtCore.QPointF(110, 150), 80, 66)
    p.setBrush(QtGui.QColor("#7b5cc4"))
    p.drawEllipse(QtCore.QPointF(104, 152), 30, 26)
    p.setBrush(QtGui.QColor("#e4572e"))
    for x, y in ((60, 120), (150, 115), (160, 185), (70, 190), (125, 205)):
        p.drawRoundedRect(QtCore.QRectF(x - 12, y - 5, 24, 10), 5, 5)
    p.setPen(QtGui.QColor("#ffffff"))
    f = QtGui.QFont()
    f.setPointSize(26)
    f.setBold(True)
    p.setFont(f)
    p.drawText(QtCore.QRectF(210, 100, 300, 50), name)
    f.setPointSize(11)
    f.setBold(False)
    p.setFont(f)
    p.setPen(QtGui.QColor("#9fb3d9"))
    p.drawText(QtCore.QRectF(212, 150, 300, 60), f"Offline 3D cellular laboratory\nversion {version}")
    p.end()
    return pm
