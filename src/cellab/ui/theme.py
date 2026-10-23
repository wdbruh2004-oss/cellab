"""Dark application theme (Fusion style + palette + small stylesheet)."""

from __future__ import annotations

from PySide6 import QtGui, QtWidgets

STYLESHEET = """
QMainWindow, QDialog { background: #0e1424; }
QDockWidget { color: #dfe6f3; font-weight: bold; }
QDockWidget::title { background: #141c31; padding: 6px; }
QTreeWidget, QTextBrowser, QTableWidget, QLineEdit {
    background: #0b1020; color: #e6e9ef; border: 1px solid #222c47; border-radius: 4px;
    selection-background-color: #2f4a86; }
QLineEdit { padding: 5px; }
QToolBar { background: #121a2e; border: none; spacing: 4px; padding: 3px; }
QToolButton { color: #dfe6f3; padding: 4px 8px; border-radius: 4px; }
QToolButton:checked { background: #2f4a86; }
QToolButton:hover { background: #22325a; }
QPushButton { background: #1d2a4a; color: #e6e9ef; border: 1px solid #2f3d63; border-radius: 4px; padding: 5px 12px; }
QPushButton:hover { background: #26375f; }
QPushButton:disabled { color: #6b7590; }
QStatusBar { background: #0b1020; color: #9aa4b8; }
QHeaderView::section { background: #141c31; color: #9fb3d9; border: none; padding: 4px; }
QSlider::groove:horizontal { height: 4px; background: #2a3350; border-radius: 2px; }
QSlider::handle:horizontal { background: #79c0ff; width: 14px; margin: -6px 0; border-radius: 7px; }
"""


def apply_theme(app: QtWidgets.QApplication) -> None:
    app.setStyle("Fusion")
    pal = QtGui.QPalette()
    c = QtGui.QColor
    role = QtGui.QPalette.ColorRole
    pal.setColor(role.Window, c("#0e1424"))
    pal.setColor(role.WindowText, c("#e6e9ef"))
    pal.setColor(role.Base, c("#0b1020"))
    pal.setColor(role.AlternateBase, c("#121a2e"))
    pal.setColor(role.Text, c("#e6e9ef"))
    pal.setColor(role.Button, c("#1d2a4a"))
    pal.setColor(role.ButtonText, c("#e6e9ef"))
    pal.setColor(role.Highlight, c("#2f4a86"))
    pal.setColor(role.HighlightedText, c("#ffffff"))
    pal.setColor(role.ToolTipBase, c("#141c31"))
    pal.setColor(role.ToolTipText, c("#e6e9ef"))
    pal.setColor(role.Link, c("#79c0ff"))
    app.setPalette(pal)
    app.setStyleSheet(STYLESHEET)
