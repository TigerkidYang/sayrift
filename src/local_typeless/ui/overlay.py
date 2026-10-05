"""Voice bar: the pill shown while listening / processing (behaviour per Typeless, docs/typeless-features.md §1-2).

Official layout: × (cancel) · waveform · timer · ✓ (finish). In the last 60 s before the 9-minute cap the timer
turns into a red countdown. Our look is the Glass language: a dark frosted pill with a soft glow, a mode chip, a
violet-to-cyan waveform, and a round white finish button. It fades and rises in, and fades out when done.

It must never take the keyboard focus (the text goes into the window that had it): it is a frameless,
always-on-top tool window shown without activation, with WS_EX_NOACTIVATE on top of Qt's flags. Clicking its
buttons therefore works without stealing the focus.
"""

from __future__ import annotations

import math
import sys
import time
from collections import deque

from PySide6.QtCore import QPoint, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QWidget

from .i18n import tr
from .theme import DARK

BARS = 22
HEIGHT = 46
GLOW = 16  # transparent margin around the pill for its glow
BUTTON = 30
PAD = 8
BOTTOM_MARGIN = 64  # above the taskbar

FILL = QColor("#e6101119")
EDGE = QColor("#30ffffff")
FG = QColor(DARK.text)
MUTED = QColor(DARK.muted)
CHIP = QColor("#1cffffff")
GHOST = QColor("#16ffffff")
GHOST_HOVER = QColor("#30ffffff")
FINISH = QColor("#f3f4f8")
FINISH_HOVER = QColor("#ffffff")
VIOLET, CYAN = QColor(DARK.accent), QColor(DARK.accent2)
ERROR = QColor(DARK.danger)


def level_to_height(rms: float) -> float:
    """RMS (int16 scale) -> 0..1 bar height. Room noise (~100) stays flat; speech (~1000-5000) fills."""
    return max(0.0, min(1.0, (rms - 150.0) / 2500.0)) ** 0.6


def clock_text(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def mode_text(label: str) -> str:
    """The controller's mode label (dictate / ask / translate:<target>) -> the chip text."""
    if label.startswith("translate:"):
        from .settings_page import lang_label

        return f"{tr('mode.translate')} · {lang_label(label.split(':', 1)[1])}"
    if label == "ask":
        return tr("bar.ask")
    if label in ("", "dictate"):
        return tr("mode.dictate")
    return label


def _font(size: float, weight: QFont.Weight = QFont.Weight.Medium) -> QFont:
    f = QFont()
    f.setFamilies(["Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI"])
    f.setPointSizeF(size)
    f.setWeight(weight)
    return f


class VoiceBar(QWidget):
    cancel_clicked = Signal()
    finish_clicked = Signal()

    def __init__(self) -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.state = "hidden"
        self.label = ""
        self.message = ""
        self._levels: deque[float] = deque([0.0] * BARS, maxlen=BARS)
        self._shown: list[float] = [0.0] * BARS  # eased copy of _levels, so bars glide instead of jump
        self._started = 0.0
        self._max_seconds = 540.0
        self._hover: str | None = None
        self._styled = False
        self._font = _font(9.5)
        self._mono = _font(9.5)
        self._anim = QTimer(self, interval=16, timeout=self._tick)
        self._hide_timer = QTimer(self, singleShot=True, timeout=self._fade_out)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.finished.connect(self._faded)
        self._rise = 0.0  # 0..1 entrance progress, drives a small upward slide
        self._base_y = 0

    # --- state changes (GUI thread) ------------------------------------------------------------

    def listening(self, label: str, max_seconds: float) -> None:
        if self.state != "listening":  # a mode switch mid-session keeps the timer running
            self._levels.extend([0.0] * BARS)
            self._started = time.monotonic()
        self.state, self.label, self.message = "listening", label, ""
        self._max_seconds = max_seconds
        self._show()

    def push_level(self, rms: float) -> None:
        if self.state == "listening":
            self._levels.append(level_to_height(rms))

    def processing(self) -> None:
        if self.state != "hidden":
            self.state = "processing"
            self._show()

    def done(self) -> None:
        if self.state != "hidden":
            self.state = "done"
            self._hide_timer.start(260)

    def cancelled(self) -> None:
        self._fade_out()

    def error(self, message: str) -> None:
        self.state, self.message = "error", tr(message)
        self._show()
        self._hide_timer.start(3200)

    # --- geometry ------------------------------------------------------------------------------

    def _pill(self) -> QRectF:
        return QRectF(GLOW, GLOW, self.width() - 2 * GLOW, HEIGHT)

    def _cancel_rect(self) -> QRectF:
        r = self._pill()
        return QRectF(r.left() + PAD, r.top() + (HEIGHT - BUTTON) / 2, BUTTON, BUTTON)

    def _finish_rect(self) -> QRectF:
        r = self._pill()
        return QRectF(r.right() - PAD - BUTTON, r.top() + (HEIGHT - BUTTON) / 2, BUTTON, BUTTON)

    def _buttons(self) -> dict[str, QRectF]:
        if self.state == "listening":
            return {"cancel": self._cancel_rect(), "finish": self._finish_rect()}
        if self.state == "processing":
            return {"cancel": self._cancel_rect()}
        return {}

    def _chip_width(self) -> float:
        return QFontMetrics(self._font).horizontalAdvance(mode_text(self.label)) + 32

    def _pill_width(self) -> int:
        metrics = QFontMetrics(self._font)
        if self.state == "error":
            return max(240, metrics.horizontalAdvance(self.message) + 64)
        wave = BARS * 5
        timer = QFontMetrics(self._mono).horizontalAdvance("0:00")
        return int(PAD + BUTTON + 10 + self._chip_width() + 14 + wave + 14 + timer + 12 + BUTTON + PAD)

    # --- window plumbing -----------------------------------------------------------------------

    def _show(self) -> None:
        self._hide_timer.stop()
        was_visible = self.isVisible() and self._fade.endValue() != 0.0
        self.resize(self._pill_width() + 2 * GLOW, HEIGHT + 2 * GLOW)
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        self._base_y = area.bottom() - BOTTOM_MARGIN - HEIGHT - GLOW
        self.move(QPoint(area.center().x() - self.width() // 2, self._base_y))
        if not was_visible:
            self._rise = 0.0
            self.setWindowOpacity(0.0)
            self._fade.stop()
            self._fade.setDuration(140)
            self._fade.setStartValue(0.0)
            self._fade.setEndValue(1.0)
            self._fade.start()
        if not self.isVisible():
            self.show()
            if sys.platform == "win32" and not self._styled:
                from ..win._api import make_window_non_activating

                make_window_non_activating(int(self.winId()), click_through=False)
                self._styled = True
        self._anim.start()
        self.update()

    def _fade_out(self) -> None:
        if not self.isVisible():
            self._faded_now()
            return
        self._fade.stop()
        self._fade.setDuration(180)
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _faded(self) -> None:
        if self._fade.endValue() == 0.0:
            self._faded_now()

    def _faded_now(self) -> None:
        self.state = "hidden"
        self._hover = None
        self._anim.stop()
        self.hide()

    # kept for callers / tests that hide immediately
    def _hide(self) -> None:
        self._faded_now()

    def _tick(self) -> None:
        if self._rise < 1.0:  # rise 6 px while fading in
            self._rise = min(1.0, self._rise + 0.12)
            self.move(self.x(), int(self._base_y + 6 * (1 - self._rise) ** 2))
        for i, target in enumerate(self._levels):
            self._shown[i] += (target - self._shown[i]) * 0.35
        self.update()

    # --- mouse ---------------------------------------------------------------------------------

    def _hit(self, pos: QPointF) -> str | None:
        return next((name for name, rect in self._buttons().items() if rect.contains(pos)), None)

    def mouseMoveEvent(self, event) -> None:
        hover = self._hit(event.position())
        if hover != self._hover:
            self._hover = hover
            self.setCursor(Qt.CursorShape.PointingHandCursor if hover else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, _event) -> None:
        self._hover = None
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        hit = self._hit(event.position())
        if hit == "cancel":
            self.cancel_clicked.emit()
        elif hit == "finish":
            self.finish_clicked.emit()

    # --- painting ------------------------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pill = self._pill()
        self._paint_shell(p, pill)
        p.setFont(self._font)

        if self.state == "error":
            self._paint_error(p, pill)
            return

        buttons = self._buttons()
        left = pill.left() + PAD + BUTTON + 10 if "cancel" in buttons else pill.left() + 16
        right = pill.right() - (PAD + BUTTON + 12 if "finish" in buttons else 16)
        if "cancel" in buttons:
            self._paint_cancel(p, buttons["cancel"])
        if "finish" in buttons:
            self._paint_finish(p, buttons["finish"])
        if self.state == "done":
            self._paint_done(p, pill)
            return

        # mode chip
        chip = QRectF(left, pill.center().y() - 12, self._chip_width(), 24)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(CHIP)
        p.drawRoundedRect(chip, 12, 12)
        dot = QLinearGradient(chip.left() + 9, 0, chip.left() + 15, 0)
        dot.setColorAt(0, VIOLET)
        dot.setColorAt(1, CYAN)
        p.setBrush(dot)
        p.drawEllipse(QPointF(chip.left() + 12, chip.center().y()), 3, 3)
        p.setPen(FG)
        p.drawText(chip.adjusted(20, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, mode_text(self.label))
        left = chip.right() + 14

        if self.state == "listening":
            elapsed = time.monotonic() - self._started
            remaining = self._max_seconds - elapsed
            countdown = remaining <= 60  # Typeless: 60-second countdown before the 9-minute cap
            p.setFont(self._mono)
            tw = QFontMetrics(self._mono).horizontalAdvance("0:00") + 2
            p.setPen(ERROR if countdown else MUTED)
            p.drawText(QRectF(right - tw, pill.top(), tw, HEIGHT),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                       clock_text(remaining if countdown else elapsed))  # fmt: skip
            right -= tw + 14
            self._paint_bars(p, QRectF(left, pill.top() + 10, right - left, HEIGHT - 20))
        elif self.state == "processing":
            self._paint_flow(p, QRectF(left, pill.top() + 10, right - left, HEIGHT - 20))

    def _paint_shell(self, p: QPainter, pill: QRectF) -> None:
        for i in range(GLOW, 0, -2):  # soft shadow: stacked, fading rounded rects
            shadow = QColor(0, 0, 0, int(34 * (1 - i / GLOW) ** 2))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(shadow)
            p.drawRoundedRect(pill.adjusted(-i, -i + 4, i, i + 4), HEIGHT / 2 + i, HEIGHT / 2 + i)
        path = QPainterPath()
        path.addRoundedRect(pill, HEIGHT / 2, HEIGHT / 2)
        p.fillPath(path, FILL)
        edge = QLinearGradient(0, pill.top(), 0, pill.bottom())  # brighter along the top: light from above
        edge.setColorAt(0, QColor("#4affffff"))
        edge.setColorAt(1, QColor("#14ffffff"))
        p.setPen(QPen(edge, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(pill.adjusted(0.5, 0.5, -0.5, -0.5), HEIGHT / 2, HEIGHT / 2)

    def _paint_cancel(self, p: QPainter, r: QRectF) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(GHOST_HOVER if self._hover == "cancel" else GHOST)
        p.drawEllipse(r)
        pen = QPen(FG if self._hover == "cancel" else MUTED, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        c, d = r.center(), BUTTON * 0.15
        p.drawLine(QPointF(c.x() - d, c.y() - d), QPointF(c.x() + d, c.y() + d))
        p.drawLine(QPointF(c.x() - d, c.y() + d), QPointF(c.x() + d, c.y() - d))

    def _check(self, p: QPainter, c: QPointF, color: QColor, s: float) -> None:
        pen = QPen(color, 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPolyline([QPointF(c.x() - 5 * s, c.y() + 0.2 * s), QPointF(c.x() - 1.6 * s, c.y() + 3.6 * s),
                        QPointF(c.x() + 5 * s, c.y() - 3.8 * s)])  # fmt: skip

    def _paint_finish(self, p: QPainter, r: QRectF) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(FINISH_HOVER if self._hover == "finish" else FINISH)
        p.drawEllipse(r)
        self._check(p, r.center(), QColor("#0b0c12"), BUTTON / 26)

    def _paint_done(self, p: QPainter, pill: QRectF) -> None:
        c = pill.center()
        g = QLinearGradient(c.x() - 14, 0, c.x() + 14, 0)
        g.setColorAt(0, VIOLET)
        g.setColorAt(1, CYAN)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(c, 14, 14)
        self._check(p, c, QColor("#ffffff"), 1.1)

    def _paint_error(self, p: QPainter, pill: QRectF) -> None:
        c = QPointF(pill.left() + 24, pill.center().y())
        p.setPen(QPen(ERROR, 1.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, 8, 8)
        p.drawLine(QPointF(c.x(), c.y() - 4), QPointF(c.x(), c.y() + 1))
        p.drawPoint(QPointF(c.x(), c.y() + 4))
        p.setPen(FG)
        p.drawText(pill.adjusted(42, 0, -18, 0), Qt.AlignmentFlag.AlignVCenter, self.message)

    def _bar_brush(self, area: QRectF) -> QLinearGradient:
        g = QLinearGradient(area.left(), 0, area.right(), 0)
        g.setColorAt(0, VIOLET)
        g.setColorAt(1, CYAN)
        return g

    def _paint_bars(self, p: QPainter, area: QRectF) -> None:
        step = area.width() / BARS
        bar_w = max(2.5, step * 0.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._bar_brush(area))
        for i, v in enumerate(self._shown):
            h = max(3.0, v * area.height())
            cx = area.left() + step * (i + 0.5)
            p.drawRoundedRect(QRectF(cx - bar_w / 2, area.center().y() - h / 2, bar_w, h), bar_w / 2, bar_w / 2)

    def _paint_flow(self, p: QPainter, area: QRectF) -> None:
        """Processing: a travelling wave across the bars, so the pill visibly works without a spinner."""
        t = time.monotonic()
        step = area.width() / BARS
        bar_w = max(2.5, step * 0.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._bar_brush(area))
        for i in range(BARS):
            v = 0.18 + 0.5 * max(0.0, math.sin(t * 5.0 - i * 0.45)) ** 2
            h = max(3.0, v * area.height())
            cx = area.left() + step * (i + 0.5)
            p.drawRoundedRect(QRectF(cx - bar_w / 2, area.center().y() - h / 2, bar_w, h), bar_w / 2, bar_w / 2)
