"""Validation report and About/licence dialogs."""

from __future__ import annotations

import platform
from html import escape

from PySide6 import QtCore, QtGui, QtWidgets

import cellab
from cellab.science.knowledge import KnowledgeBase
from cellab.science.validation import ValidationRow, compartment_label


class ValidationDialog(QtWidgets.QDialog):
    def __init__(self, kb: KnowledgeBase, rows: list[ValidationRow], source: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Scientific validation report")
        self.resize(960, 440)
        intro = QtWidgets.QLabel(
            f"Model compartments compared with the reference composition ({escape(source)}). "
            "Geometric compartments must match the reference count exactly and its volume within 0.5%, "
            "and the rendered mesh must stay within 1% of the analytic volume.")
        intro.setWordWrap(True)
        table = QtWidgets.QTableWidget(len(rows), 7)
        table.setHorizontalHeaderLabels(["Compartment", "Reference vol.", "Model vol.", "Rendered mesh",
                                         "Count (ref / model)", "Status", "Note"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        for r, row in enumerate(rows):
            cells = [
                compartment_label(kb, row),
                f"{100 * row.reference_fraction:g}%",
                "—" if row.model_fraction is None else f"{100 * row.model_fraction:.3f}%",
                "—" if row.mesh_fraction is None else f"{100 * row.mesh_fraction:.3f}%",
                "—" if row.model_count is None else f"{row.reference_count:,} / {row.model_count:,}",
                row.status,
                row.note,
            ]
            for c, text in enumerate(cells):
                item = QtWidgets.QTableWidgetItem(text)
                if c == 5:
                    color = {"PASS": "#3fb950", "FAIL": "#f85149"}.get(text, "#d29922")
                    item.setForeground(QtCore.Qt.GlobalColor.white)
                    item.setBackground(QtGui.QColor(color))
                table.setItem(r, c, item)
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(intro)
        lay.addWidget(table)
        lay.addWidget(buttons)
        self.table = table


def about_html(gl_info: str) -> str:
    import numpy
    import pyvista
    import scipy
    from PySide6 import __version__ as pyside_version
    from vtkmodules.vtkCommonCore import vtkVersion
    return f"""
<h2>{cellab.APP_NAME} {cellab.__version__}</h2>
<p>Offline-first 3D cellular laboratory. No network access is needed or used.</p>
<h3>Scientific content</h3>
<p>The curated knowledge base cites its sources for every quantitative statement and labels each value
<i>sourced</i>, <i>textbook</i>, <i>approximate</i>, <i>model</i> or <i>illustrative</i>.
Gene Ontology identifiers (CC BY 4.0) and UniProtKB accessions (CC BY 4.0) are cited as identifiers only;
no database content is redistributed in this version.</p>
<h3>Runtime</h3>
<table>
<tr><td>Python</td><td>{platform.python_version()}</td></tr>
<tr><td>Qt for Python (PySide6, LGPL-3.0)</td><td>{pyside_version}</td></tr>
<tr><td>VTK (BSD-3-Clause)</td><td>{vtkVersion.GetVTKVersion()}</td></tr>
<tr><td>PyVista (MIT)</td><td>{pyvista.__version__}</td></tr>
<tr><td>NumPy (BSD-3-Clause)</td><td>{numpy.__version__}</td></tr>
<tr><td>SciPy (BSD-3-Clause)</td><td>{scipy.__version__}</td></tr>
<tr><td>OpenGL</td><td>{escape(gl_info)}</td></tr>
</table>
<p>Full third-party licence texts are listed in THIRD_PARTY_NOTICES.md next to the executable.</p>
"""


class AboutDialog(QtWidgets.QDialog):
    def __init__(self, gl_info: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"About {cellab.APP_NAME}")
        self.resize(560, 520)
        text = QtWidgets.QTextBrowser()
        text.setHtml(about_html(gl_info))
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(text)
        lay.addWidget(buttons)
