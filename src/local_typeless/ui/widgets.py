"""Small reusable widgets for the main window."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

from PySide6.QtCore import Property, QEasingCurve, QPoint, QPropertyAnimation, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import icons
from .theme import Palette


def label(text: str, name: str | None = None, *, wrap: bool = False) -> QLabel:
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    return lab


class Card(QFrame):
    def __init__(self, padding: int = 18, spacing: int = 12) -> None:
        super().__init__()
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(padding, padding, padding, padding)
        self.body.setSpacing(spacing)


class KeyCap(QLabel):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setObjectName("KeyCap")


def keycaps(names: list[str]) -> QWidget:
    w = QWidget()
    row = QHBoxLayout(w)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(4)
    for i, name in enumerate(names):
        if i:
            row.addWidget(label("+", "Faint"))
        row.addWidget(KeyCap(name))
    row.addStretch(1)
    return w


class IconButton(QPushButton):
    def __init__(self, icon_name: str, tooltip: str, palette: Palette, on_click: Callable[[], None]) -> None:
        super().__init__()
        self.setObjectName("Ghost")
        self.setIcon(icons.icon(icon_name, palette.muted, 16))
        self.setIconSize(QSize(16, 16))
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(on_click)


class Toggle(QAbstractButton):
    """iOS-style switch with a short slide animation."""

    def __init__(self, palette: Palette, checked: bool = False) -> None:
        super().__init__()
        self.p = palette
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(40, 22)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"pos", self, duration=140, easingCurve=QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)

    def _animate(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def _get_pos(self) -> float:
        return self._pos

    def _set_pos(self, v: float) -> None:
        self._pos = v
        self.update()

    pos = Property(float, _get_pos, _set_pos)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self.p.surface2))
        p.drawRoundedRect(QRectF(0, 0, 40, 22), 11, 11)
        if self._pos > 0:  # the "on" track is the signature gradient, faded in as the knob slides
            g = QLinearGradient(0, 0, 40, 0)
            g.setColorAt(0, QColor(self.p.accent))
            g.setColorAt(1, QColor(self.p.accent2))
            p.setOpacity(self._pos)
            p.setBrush(g)
            p.drawRoundedRect(QRectF(0, 0, 40, 22), 11, 11)
            p.setOpacity(1.0)
        p.setBrush(QColor("#ffffff"))
        x = 3 + self._pos * 18
        p.drawEllipse(QRectF(x, 3, 16, 16))


class Segmented(QFrame):
    """A row of mutually exclusive options (e.g. the history filter)."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], current: str) -> None:
        super().__init__()
        self.setObjectName("SegBox")
        row = QHBoxLayout(self)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)
        self._group = QButtonGroup(self)
        for key, text in options:
            b = QPushButton(text)
            b.setObjectName("Seg")
            b.setCheckable(True)
            b.setChecked(key == current)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
            self._group.addButton(b)
            row.addWidget(b)


class StatCard(Card):
    def __init__(self, palette: Palette, icon_name: str, title: str) -> None:
        super().__init__(padding=16, spacing=6)
        top = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_name, palette.accent, 16))
        top.addWidget(ic)
        top.addWidget(label(title, "StatLabel"))
        top.addStretch(1)
        self.body.addLayout(top)
        self.value = label("—", "StatValue")
        self.note = label("", "Faint")
        self.body.addWidget(self.value)
        self.body.addWidget(self.note)

    def set(self, value: str, note: str = "") -> None:
        self.value.setText(value)
        self.note.setText(note)


class Heatmap(QWidget):
    """Words per day as a GitHub-style grid: columns are weeks, rows Monday..Sunday. Cells grow with the width."""

    WEEKS = 26
    MAX_CELL, GAP = 22, 4

    def __init__(self, palette: Palette) -> None:
        super().__init__()
        self.p = palette
        self.data: dict[date, int] = {}
        self.setMinimumSize(self.WEEKS * 10, 7 * (self.MAX_CELL + self.GAP))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_data(self, data: dict[date, int]) -> None:
        self.data = data
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        today = date.today()
        start = today - timedelta(days=today.weekday() + 7 * (self.WEEKS - 1))
        peak = max(self.data.values(), default=0) or 1
        side = min(self.MAX_CELL + self.GAP, self.width() / self.WEEKS)
        cell = side - self.GAP
        x0 = (self.width() - self.WEEKS * side) / 2
        y0 = (self.height() - 7 * side) / 2
        violet, cyan = QColor(self.p.accent), QColor(self.p.accent2)
        for week in range(self.WEEKS):
            for dow in range(7):
                d = start + timedelta(days=week * 7 + dow)
                if d > today:
                    continue
                n = self.data.get(d, 0)
                if n:  # more words: brighter, and shifting from violet towards cyan
                    k = min(1.0, n / peak)
                    c = QColor(
                        int(violet.red() + (cyan.red() - violet.red()) * k),
                        int(violet.green() + (cyan.green() - violet.green()) * k),
                        int(violet.blue() + (cyan.blue() - violet.blue()) * k),
                    )
                    c.setAlphaF(0.35 + 0.65 * k)
                else:
                    c = QColor(self.p.surface2)
                p.setBrush(c)
                p.drawRoundedRect(QRectF(x0 + week * side, y0 + dow * side, cell, cell), 4, 4)


class FlowLayout(QLayout):
    """Wraps children onto new lines (dictionary chips)."""

    def __init__(self, spacing: int = 8) -> None:
        super().__init__()
        self._items = []
        self._spacing = spacing

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._layout(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._layout(rect, apply=True)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _layout(self, rect: QRect, *, apply: bool) -> int:
        x, y, line = rect.x(), rect.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            if x + hint.width() > rect.right() and line > 0:
                x, y, line = rect.x(), y + line + self._spacing, 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._spacing
            line = max(line, hint.height())
        return y + line - rect.y()


class SettingRow(QWidget):
    """Title (+ optional description) on the left, a control on the right."""

    def __init__(self, title: str, control: QWidget | None = None, description: str = "") -> None:
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 4, 0, 4)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(label(title))
        if description:
            texts.addWidget(label(description, "Faint", wrap=True))
        row.addLayout(texts, 1)
        if control is not None:
            row.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)


def section(title: str) -> tuple[Card, QVBoxLayout]:
    card = Card(padding=18, spacing=6)
    card.body.addWidget(label(title, "SectionTitle"))
    return card, card.body


def divider(palette: Palette) -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {palette.border}; border: none;")
    return line
