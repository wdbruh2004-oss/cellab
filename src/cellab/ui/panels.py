"""Dockable side panels: structure browser and scientific inspector."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from cellab.model.cell_model import CellModel
from cellab.render.style import STYLES
from cellab.science.knowledge import KnowledgeBase
from cellab.ui.inspector_html import inspector_html, welcome_html

GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Cell boundary", ("plasma_membrane", "cytosol")),
    ("Nucleus", ("nucleus", "nucleolus", "chromatin", "nuclear_pore")),
    ("Endomembrane system", ("rough_er", "smooth_er", "golgi", "transport_vesicle", "endosome", "lysosome")),
    ("Metabolic organelles", ("mitochondrion", "peroxisome")),
    ("Cytoskeleton", ("centrosome", "microtubule", "actin_cortex", "keratin_if")),
    ("Protein synthesis", ("ribosome",)),
)

SID_ROLE = QtCore.Qt.ItemDataRole.UserRole


def _swatch(color: str) -> QtGui.QIcon:
    pm = QtGui.QPixmap(14, 14)
    pm.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    p.setBrush(QtGui.QColor(color))
    p.setPen(QtGui.QPen(QtGui.QColor("#0b0f1a"), 1))
    p.drawEllipse(1, 1, 12, 12)
    p.end()
    return QtGui.QIcon(pm)


class StructurePanel(QtWidgets.QWidget):
    structure_activated = QtCore.Signal(str)
    visibility_changed = QtCore.Signal(str, bool)

    def __init__(self, kb: KnowledgeBase, parent=None):
        super().__init__(parent)
        self.kb = kb
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Search structures, GO terms, proteins…")
        self.search.setClearButtonEnabled(True)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Structure", "Rendered"])
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(False)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.items: dict[str, QtWidgets.QTreeWidgetItem] = {}
        self.groups: list[QtWidgets.QTreeWidgetItem] = []
        for title, sids in GROUPS:
            g = QtWidgets.QTreeWidgetItem([title])
            f = g.font(0)
            f.setBold(True)
            g.setFont(0, f)
            g.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.tree.addTopLevelItem(g)
            self.groups.append(g)
            for sid in sids:
                s = kb.get(sid)
                it = QtWidgets.QTreeWidgetItem([s.name, ""])
                it.setData(0, SID_ROLE, sid)
                it.setToolTip(0, f"{s.category} · {s.go_id}")
                flags = QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable
                if s.renderable:
                    flags |= QtCore.Qt.ItemFlag.ItemIsUserCheckable
                    it.setCheckState(0, QtCore.Qt.CheckState.Checked)
                    it.setIcon(0, _swatch(STYLES[sid].color if sid in STYLES else "#888888"))
                it.setFlags(flags)
                g.addChild(it)
                self.items[sid] = it
            g.setExpanded(True)
        missing = set(kb.structures) - set(self.items)
        if missing:
            raise RuntimeError(f"structures missing from the browser: {sorted(missing)}")
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addWidget(self.search)
        lay.addWidget(self.tree)
        self.search.textChanged.connect(self.apply_filter)
        self.search.returnPressed.connect(self._activate_first)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.currentItemChanged.connect(self._on_current)

    def set_counts(self, model: CellModel) -> None:
        for sid, it in self.items.items():
            pop = model.populations.get(sid)
            it.setText(1, f"{pop.count:,}" if pop else "—")
            it.setTextAlignment(1, QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)

    def apply_filter(self, text: str) -> list[str]:
        hits = self.kb.search(text)
        allowed = set(hits)
        for g in self.groups:
            any_visible = False
            for i in range(g.childCount()):
                c = g.child(i)
                show = c.data(0, SID_ROLE) in allowed
                c.setHidden(not show)
                any_visible |= show
            g.setHidden(not any_visible)
        return hits

    def _activate_first(self) -> None:
        hits = self.kb.search(self.search.text())
        if hits:
            self.select(hits[0])
            self.structure_activated.emit(hits[0])

    def select(self, sid: str) -> None:
        it = self.items.get(sid)
        if it is not None:
            self.tree.blockSignals(True)
            self.tree.setCurrentItem(it)
            self.tree.scrollToItem(it)
            self.tree.blockSignals(False)

    def set_checked(self, sid: str, on: bool) -> None:
        it = self.items[sid]
        it.setCheckState(0, QtCore.Qt.CheckState.Checked if on else QtCore.Qt.CheckState.Unchecked)

    def _on_item_changed(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        sid = item.data(0, SID_ROLE)
        if sid and column == 0 and item.flags() & QtCore.Qt.ItemFlag.ItemIsUserCheckable:
            self.visibility_changed.emit(sid, item.checkState(0) == QtCore.Qt.CheckState.Checked)

    def _on_current(self, cur, _prev) -> None:
        if cur is not None and cur.data(0, SID_ROLE):
            self.structure_activated.emit(cur.data(0, SID_ROLE))


class InspectorPanel(QtWidgets.QWidget):
    focus_requested = QtCore.Signal()
    isolate_requested = QtCore.Signal(str)

    def __init__(self, kb: KnowledgeBase, parent=None):
        super().__init__(parent)
        self.kb = kb
        self.model: CellModel | None = None
        self.current: tuple[str, int | None] | None = None
        self.browser = QtWidgets.QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(lambda url: QtGui.QDesktopServices.openUrl(url))
        self.focus_btn = QtWidgets.QPushButton("Focus")
        self.focus_btn.setToolTip("Fly the camera to the selection (F)")
        self.isolate_btn = QtWidgets.QPushButton("Isolate")
        self.isolate_btn.setToolTip("Show only this structure (and the membrane outline)")
        self.focus_btn.clicked.connect(self.focus_requested)
        self.isolate_btn.clicked.connect(lambda: self.current and self.isolate_requested.emit(self.current[0]))
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.focus_btn)
        row.addWidget(self.isolate_btn)
        row.addStretch(1)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addLayout(row)
        lay.addWidget(self.browser)
        self.show_welcome()

    def set_model(self, model: CellModel) -> None:
        self.model = model
        if self.current is None:
            self.show_welcome()

    def show_welcome(self) -> None:
        self.current = None
        self.browser.setHtml(welcome_html(self.kb, self.model))
        self.focus_btn.setEnabled(False)
        self.isolate_btn.setEnabled(False)

    def show_structure(self, sid: str, instance: int | None = None) -> None:
        self.current = (sid, instance)
        self.browser.setHtml(inspector_html(self.kb, self.model, sid, instance))
        renderable = self.kb.get(sid).renderable
        self.focus_btn.setEnabled(renderable)
        self.isolate_btn.setEnabled(renderable)
