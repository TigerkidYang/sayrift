"""Cards: Ask anything answers, and dictations that could not be inserted.

Typeless shows answers in a pop-up card and offers the result when no text field has focus.
Cards are shown without activation (you keep typing where you were); click Copy or Close.
Look: the Glass language, like the Voice bar — a dark frosted panel with a soft shadow.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QCursor,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from .i18n import tr
from .theme import DARK

WIDTH = 480
SHADOW = 18
RADIUS = 18
FONT = '"Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI"'
STYLE = f"""
QLabel#title {{ color: {DARK.muted}; font: 600 9pt {FONT}; }}
QLabel#question {{ color: {DARK.text}; font: 600 11pt {FONT}; }}
QTextBrowser {{ background: transparent; border: none; color: {DARK.text}; font: 10.5pt {FONT};
               selection-background-color: {DARK.accent}; }}
QPushButton {{ background: #1cffffff; color: {DARK.text}; border: 1px solid #24ffffff; border-radius: 10px;
              padding: 6px 16px; font: 9.5pt {FONT}; }}
QPushButton:hover {{ background: #30ffffff; }}
QPushButton#primary {{ background: {DARK.pill}; color: {DARK.on_pill}; border: none; font-weight: 600; }}
QPushButton#primary:hover {{ background: #ffffff; }}
"""
# Markdown answers: calmer lists and code than QTextBrowser's defaults.
DOC_CSS = f"""
p, li {{ line-height: 150%; }}
ul, ol {{ margin-left: 0px; -qt-list-indent: 1; }}
code {{ font-family: "Cascadia Mono", Consolas; background-color: #22ffffff; color: {DARK.accent2}; }}
pre {{ font-family: "Cascadia Mono", Consolas; background-color: #16ffffff; }}
a {{ color: {DARK.accent2}; }}
"""


def _polish_markdown(text: QTextBrowser) -> None:
    """Qt's Markdown import ignores the default stylesheet for code and uses wide list indents: fix both."""
    doc = text.document()
    doc.setIndentWidth(16)
    cursor = QTextCursor(doc)
    block = doc.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and frag.charFormat().fontFixedPitch():
                fmt = QTextCharFormat()
                fmt.setFontFamilies(["Cascadia Mono", "Consolas"])
                fmt.setForeground(QColor(DARK.accent2))
                cursor.setPosition(frag.position())
                cursor.setPosition(frag.position() + frag.length(), QTextCursor.MoveMode.KeepAnchor)
                cursor.mergeCharFormat(fmt)
            it += 1
        block = block.next()


class Card(QWidget):
    def __init__(self, title: str, question: str, body: str, *, markdown: bool = False) -> None:
        """`markdown`: render the body as Markdown (Ask answers, like Typeless); else plain text."""
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        super().__init__(None, flags | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet(STYLE)
        self.body = body

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SHADOW + 20, SHADOW + 16, SHADOW + 20, SHADOW + 16)
        layout.setSpacing(8)
        head = QHBoxLayout()
        head.setSpacing(8)
        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {DARK.accent}, stop:1 {DARK.accent2});"
            " border-radius: 4px;"
        )
        head.addWidget(dot)
        head.addWidget(QLabel(title, objectName="title"))
        head.addStretch(1)
        layout.addLayout(head)
        if question:
            q = QLabel(question, objectName="question")
            q.setWordWrap(True)
            layout.addWidget(q)
        text = QTextBrowser()
        text.document().setDefaultStyleSheet(DOC_CSS)
        if markdown:
            text.setMarkdown(body)
            _polish_markdown(text)
        else:
            text.setPlainText(body)
        text.setOpenExternalLinks(True)
        # Measure at the final width (card width - margins - document margins), else the height is wrong.
        inner = WIDTH - 2 * SHADOW - 40
        text.document().setTextWidth(inner - 2 * text.document().documentMargin())
        doc_height = int(text.document().size().height()) + 6
        text.setFixedHeight(max(40, min(380, doc_height)))
        layout.addWidget(text)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton(tr("card.close"), clicked=self.close)
        self.copy_button = QPushButton(tr("card.copy"), clicked=self.copy, objectName="primary")
        for b in (close, self.copy_button):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            buttons.addWidget(b)
        layout.addLayout(buttons)
        self.setFixedWidth(WIDTH)
        self.adjustSize()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        panel = QRectF(SHADOW, SHADOW, self.width() - 2 * SHADOW, self.height() - 2 * SHADOW)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(SHADOW, 0, -2):
            p.setBrush(QColor(0, 0, 0, int(40 * (1 - i / SHADOW) ** 2)))
            p.drawRoundedRect(panel.adjusted(-i, -i + 6, i, i + 6), RADIUS + i, RADIUS + i)
        path = QPainterPath()
        path.addRoundedRect(panel, RADIUS, RADIUS)
        p.fillPath(path, QColor("#101119"))  # opaque: text over desktop icons would be hard to read
        # a faint aurora tint in the top corner ties the card to the app's look
        glow = QLinearGradient(QPointF(panel.left(), panel.top()), QPointF(panel.center().x(), panel.center().y()))
        tint = QColor(DARK.accent)
        tint.setAlpha(34)
        glow.setColorAt(0, tint)
        tint.setAlpha(0)
        glow.setColorAt(1, tint)
        p.fillPath(path, glow)
        edge = QLinearGradient(0, panel.top(), 0, panel.bottom())
        edge.setColorAt(0, QColor("#40ffffff"))
        edge.setColorAt(1, QColor("#12ffffff"))
        p.setPen(QPen(edge, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(panel.adjusted(0.5, 0.5, -0.5, -0.5), RADIUS, RADIUS)

    def copy(self) -> None:
        QGuiApplication.clipboard().setText(self.body)  # the user's own copy: normal clipboard history applies
        self.copy_button.setText(tr("card.copied"))
        QTimer.singleShot(1500, lambda: self.copy_button.setText(tr("card.copy")))

    def show_near_bottom(self) -> None:
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        self.move(QPoint(area.center().x() - self.width() // 2, area.bottom() - 120 - self.height() + SHADOW))
        self.show()
        if sys.platform == "win32":
            from ..win._api import make_window_non_activating

            make_window_non_activating(int(self.winId()), click_through=False)
