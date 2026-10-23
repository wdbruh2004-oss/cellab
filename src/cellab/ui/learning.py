"""Learning tools: a guided tour through the cell and a quiz built from the knowledge base."""

from __future__ import annotations

from collections.abc import Callable
from html import escape

from PySide6 import QtCore, QtWidgets

from cellab.edu.learning import Question, Tour
from cellab.science.knowledge import KnowledgeBase


class TourPanel(QtWidgets.QWidget):
    """Narrated stops; each stop selects and frames one structure."""

    def __init__(self, kb: KnowledgeBase, tour: Tour, goto: Callable[[str], None], parent=None):
        super().__init__(parent)
        self.kb, self.tour, self.goto = kb, tour, goto
        self.index = -1
        self.title = QtWidgets.QLabel()
        self.text = QtWidgets.QLabel()
        self.text.setWordWrap(True)
        self.prev_btn = QtWidgets.QPushButton("◀ Previous")
        self.next_btn = QtWidgets.QPushButton("Next ▶")
        self.end_btn = QtWidgets.QPushButton("End tour")
        buttons = QtWidgets.QVBoxLayout()
        for b in (self.next_btn, self.prev_btn, self.end_btn):
            buttons.addWidget(b)
        texts = QtWidgets.QVBoxLayout()
        texts.addWidget(self.title)
        texts.addWidget(self.text, 1)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.addLayout(texts, 1)
        lay.addLayout(buttons)
        self.prev_btn.clicked.connect(lambda: self.show_stop(self.index - 1))
        self.next_btn.clicked.connect(lambda: self.show_stop(self.index + 1))

    def show_stop(self, index: int) -> None:
        index = max(0, min(index, len(self.tour.stops) - 1))
        self.index = index
        stop = self.tour.stops[index]
        name = self.kb.get(stop.structure).name
        self.title.setText(f"<b>{escape(self.tour.title)}</b> — stop {index + 1} of {len(self.tour.stops)}: "
                           f"<span style='color:#79c0ff'><b>{escape(name)}</b></span>")
        self.text.setText(escape(stop.text))
        self.prev_btn.setEnabled(index > 0)
        self.next_btn.setEnabled(index < len(self.tour.stops) - 1)
        self.goto(stop.structure)


class QuizDialog(QtWidgets.QDialog):
    """One question at a time with immediate, cited feedback."""

    def __init__(self, make_questions: Callable[[], list[Question]], show: Callable[[str], None], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cell biology quiz")
        self.resize(640, 460)
        self.make_questions, self.show_structure = make_questions, show
        self.progress = QtWidgets.QLabel()
        self.prompt = QtWidgets.QLabel()
        self.prompt.setWordWrap(True)
        self.prompt.setStyleSheet("font-size: 12pt; font-weight: bold;")
        self.box = QtWidgets.QVBoxLayout()
        self.group = QtWidgets.QButtonGroup(self)
        self.feedback = QtWidgets.QLabel()
        self.feedback.setWordWrap(True)
        self.feedback.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.check_btn = QtWidgets.QPushButton("Check answer")
        self.next_btn = QtWidgets.QPushButton("Next question")
        self.show_btn = QtWidgets.QPushButton("Show in 3D")
        close_btn = QtWidgets.QPushButton("Close")
        row = QtWidgets.QHBoxLayout()
        for b in (self.check_btn, self.next_btn, self.show_btn):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(close_btn)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self.progress)
        lay.addWidget(self.prompt)
        lay.addLayout(self.box)
        lay.addWidget(self.feedback, 1)
        lay.addLayout(row)
        self.check_btn.clicked.connect(self.check)
        self.next_btn.clicked.connect(self.next_question)
        self.show_btn.clicked.connect(lambda: self.show_structure(self.current.structure))
        close_btn.clicked.connect(self.accept)
        self.restart()

    @property
    def current(self) -> Question:
        return self.questions[self.index]

    def restart(self) -> None:
        self.questions = self.make_questions()
        self.index, self.score, self.answered = 0, 0, False
        self.next_btn.setText("Next question")
        self._show()

    def _show(self) -> None:
        q = self.current
        self.answered = False
        self.progress.setText(f"Question {self.index + 1} of {len(self.questions)} · score {self.score}")
        self.prompt.setText(q.prompt)
        for b in self.group.buttons():
            self.group.removeButton(b)
            self.box.removeWidget(b)
            b.deleteLater()
        for i, opt in enumerate(q.options):
            rb = QtWidgets.QRadioButton(opt)
            self.group.addButton(rb, i)
            self.box.addWidget(rb)
        self.feedback.setText("")
        self.check_btn.setEnabled(True)
        self.next_btn.setEnabled(False)

    def choose(self, i: int) -> None:
        self.group.button(i).setChecked(True)

    def check(self) -> bool | None:
        chosen = self.group.checkedId()
        if chosen < 0 or self.answered:
            return None
        q = self.current
        self.answered = True
        ok = chosen == q.answer
        self.score += int(ok)
        verdict = ("<span style='color:#3fb950'><b>Correct.</b></span>" if ok else
                   f"<span style='color:#f85149'><b>Not quite</b></span> — the answer is "
                   f"<b>{escape(q.options[q.answer])}</b>.")
        self.feedback.setText(f"{verdict}<br>{escape(q.explanation)}<br>"
                              f"<span style='color:#9aa4b8'>Source: {escape(q.source)}</span>")
        self.progress.setText(f"Question {self.index + 1} of {len(self.questions)} · score {self.score}")
        self.check_btn.setEnabled(False)
        self.next_btn.setEnabled(True)
        if self.index == len(self.questions) - 1:
            self.next_btn.setText("Finish")
        return ok

    def next_question(self) -> None:
        if self.index < len(self.questions) - 1:
            self.index += 1
            self._show()
            return
        QtWidgets.QMessageBox.information(self, "Quiz finished",
                                          f"You scored {self.score} out of {len(self.questions)}.")
        self.restart()
