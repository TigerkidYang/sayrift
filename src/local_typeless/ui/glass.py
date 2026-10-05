"""The signature pieces of the Glass language: the drifting aurora, the orb, and the pill navigation."""

from __future__ import annotations

import math
import time
from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QRadialGradient
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QPushButton, QSizePolicy, QWidget

from .theme import Palette


def mix(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
        int(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


class Aurora(QWidget):
    """Window background: three soft light blobs drifting on slow, independent orbits.

    Repaints at ~15 fps only while visible; the motion is slow enough that this reads as smooth, and it costs
    a few radial-gradient fills per frame.
    """

    # (centre x, centre y, radius) as fractions of the widget, orbit radius, orbit speed, phase
    BLOBS = (
        (0.15, 0.18, 0.62, 0.06, 0.07, 0.0),
        (0.88, 0.78, 0.70, 0.07, 0.05, 2.1),
        (0.62, 0.05, 0.48, 0.05, 0.09, 4.2),
    )

    def __init__(self, palette: Palette, *, animate: bool = True) -> None:
        super().__init__()
        self.p = palette
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self._t0 = time.monotonic()
        self._timer = QTimer(self, interval=66, timeout=self.update)
        self._animate = animate

    def showEvent(self, event) -> None:
        if self._animate:
            self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def paintEvent(self, _event) -> None:
        paint_aurora(QPainter(self), QRectF(self.rect()), self.p, time.monotonic() - self._t0)


def paint_aurora(p: QPainter, rect: QRectF, palette: Palette, t: float) -> None:
    p.fillRect(rect, QColor(palette.base))
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    w, h = rect.width(), rect.height()
    size = max(w, h)
    strength = 0.55 if palette.dark else 0.75
    for (cx, cy, r, orbit, speed, phase), color in zip(Aurora.BLOBS, palette.aurora, strict=True):
        x = rect.left() + (cx + orbit * math.cos(t * speed + phase)) * w
        y = rect.top() + (cy + orbit * math.sin(t * speed * 1.3 + phase)) * h
        radius = r * size
        g = QRadialGradient(QPointF(x, y), radius)
        c = QColor(color)
        c.setAlphaF(strength)
        g.setColorAt(0.0, c)
        c.setAlphaF(strength * 0.45)
        g.setColorAt(0.45, c)
        c.setAlphaF(0.0)
        g.setColorAt(1.0, c)
        p.setBrush(g)
        p.drawEllipse(QPointF(x, y), radius, radius)


class Orb(QWidget):
    """A luminous sphere that breathes when idle, swells with your voice, and shimmers while processing."""

    def __init__(self, palette: Palette, diameter: int = 132) -> None:
        super().__init__()
        self.p = palette
        self.d = diameter
        self.state = "ready"
        self.level = 0.0  # 0..1, smoothed
        self._target = 0.0
        pad = int(diameter * 0.45)  # room for the glow
        self.setFixedSize(diameter + 2 * pad, diameter + 2 * pad)
        self._t0 = time.monotonic()
        self._timer = QTimer(self, interval=33, timeout=self._tick)

    def set_state(self, state: str) -> None:
        self.state = state
        if state != "listening":
            self._target = 0.0

    def set_level(self, level: float) -> None:
        self._target = max(0.0, min(1.0, level))

    def showEvent(self, event) -> None:
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def _tick(self) -> None:
        self.level += (self._target - self.level) * 0.25
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        t = time.monotonic() - self._t0
        breathe = math.sin(t * (2 * math.pi / 4.0))  # one breath every 4 s
        if self.state == "listening":
            scale = 1.0 + 0.04 * breathe + 0.14 * self.level
            glow = 0.55 + 0.4 * self.level
        elif self.state == "processing":
            scale = 1.0 + 0.02 * math.sin(t * 6)
            glow = 0.5 + 0.15 * math.sin(t * 6)
        else:
            scale = 1.0 + 0.025 * breathe
            glow = 0.38 + 0.08 * breathe
        c = QPointF(self.width() / 2, self.height() / 2)
        r = self.d / 2 * scale
        violet, cyan = QColor(self.p.accent), QColor(self.p.accent2)

        halo = QRadialGradient(c, r * 1.9)
        for stop, color, alpha in ((0.35, violet, glow), (0.6, cyan, glow * 0.35), (1.0, cyan, 0.0)):
            col = QColor(color)
            col.setAlphaF(max(0.0, min(1.0, alpha)))
            halo.setColorAt(stop, col)
        p.setBrush(halo)
        p.drawEllipse(c, r * 1.9, r * 1.9)

        # The sphere: a highlight that slowly circles the top-left while processing, else sits still.
        angle = t * 2.2 if self.state == "processing" else 0.0
        hx = c.x() - r * (0.32 * math.cos(angle) + 0.0 * math.sin(angle))
        hy = c.y() - r * (0.40 - 0.1 * math.sin(angle))
        sphere = QRadialGradient(QPointF(hx, hy), r * 1.55)
        sphere.setColorAt(0.0, QColor("#ffffff"))
        sphere.setColorAt(0.12, mix(QColor("#ffffff"), violet, 0.55))
        sphere.setColorAt(0.42, violet)
        sphere.setColorAt(0.78, cyan)
        sphere.setColorAt(1.0, QColor("#0b3b52") if self.p.dark else mix(cyan, QColor("#0b3b52"), 0.5))
        p.setBrush(sphere)
        p.drawEllipse(c, r, r)


class NavPill(QFrame):
    """Centered pill of page buttons; the current page is a solid pill."""

    changed = Signal(str)

    def __init__(self, items: list[tuple[str, str]], on_change: Callable[[str], None] | None = None) -> None:
        super().__init__()
        self.setObjectName("NavPill")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        row = QHBoxLayout(self)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)
        self._group = QButtonGroup(self)
        self.buttons: dict[str, QPushButton] = {}
        for key, text in items:
            b = QPushButton(text)
            b.setObjectName("NavItem")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
            self._group.addButton(b)
            row.addWidget(b)
            self.buttons[key] = b
        if on_change:
            self.changed.connect(on_change)

    def select(self, key: str) -> None:
        self.buttons[key].setChecked(True)


def glass_rect(p: QPainter, rect: QRectF, palette: Palette, radius: float) -> None:
    """Paint a frosted panel (fill + hairline) — for custom-painted widgets outside the stylesheet."""
    p.setPen(QColor(palette.border))
    p.setBrush(QColor(palette.surface))
    p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
