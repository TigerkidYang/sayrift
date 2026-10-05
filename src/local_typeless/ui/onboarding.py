"""First-run guide: API key and connection, microphone, shortcuts, try all three modes, launch at login.

Shown on the first launch (until finished or skipped) and from Settings > About.
"""

from __future__ import annotations

import contextlib
import subprocess
import sys
import threading
from collections.abc import Callable

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import config, keys
from . import icons
from .glass import Aurora, Orb
from .i18n import tr
from .main_window import dark_title_bar
from .pages import Context
from .settings_page import HotkeyField, MicTest, _autostart_enabled, _set_autostart, combo, lang_label, mic_options
from .theme import stylesheet
from .widgets import Card, Segmented, SettingRow, Toggle, divider, keycaps, label

STEPS = 5


class Dots(QWidget):
    """Step indicator: the current step is a wide pill, the others small dots."""

    def __init__(self, ctx: Context) -> None:
        super().__init__()
        self.p = ctx.palette
        self.current = 0
        self.setFixedSize(STEPS * 14 + 16, 8)

    def set(self, i: int) -> None:
        self.current = i
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        x = 0.0
        for i in range(STEPS):
            w = 24.0 if i == self.current else 8.0
            p.setBrush(QColor(self.p.accent if i <= self.current else self.p.border))
            p.drawRoundedRect(QRectF(x, 0, w, 8), 4, 4)
            x += w + 6


class _Result(QObject):
    got = Signal(bool, str)


def _status_line(ctx: Context) -> tuple[QWidget, Callable[[str, str], None]]:
    """An icon + text row; returns (widget, set(kind, text)) with kind in ok / bad / wait."""
    w = QWidget()
    row = QHBoxLayout(w)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)
    ic = QLabel()
    text = label("")
    text.setWordWrap(True)
    row.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
    row.addWidget(text, 1)
    colors = {"ok": ctx.palette.success, "bad": ctx.palette.danger, "wait": ctx.palette.muted}
    names = {"ok": "check", "bad": "info", "wait": "timer"}

    def set_(kind: str, message: str) -> None:
        ic.setPixmap(icons.pixmap(names[kind], colors[kind], 18))
        text.setText(message)

    return w, set_


class Onboarding(QWidget):
    def __init__(self, ctx: Context, on_done: Callable[[], None]) -> None:
        super().__init__()
        self.ctx, self._on_done = ctx, on_done
        self._finished = False
        self.setWindowTitle(tr("onb.title"))
        self.setWindowIcon(QIcon(str(icons.APP_ICON)))
        self.setObjectName("Content")
        self.setStyleSheet(stylesheet(ctx.palette))
        self.resize(760, 600)
        self.setMinimumSize(680, 560)

        canvas = Aurora(ctx.palette)  # the same drifting aurora as the main window
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(canvas)
        root = QVBoxLayout(canvas)
        root.setContentsMargins(44, 32, 44, 28)
        root.setSpacing(20)
        top = QHBoxLayout()
        self.dots = Dots(ctx)
        top.addWidget(self.dots, 0, Qt.AlignmentFlag.AlignVCenter)
        top.addStretch(1)
        self.step_label = label("", "Faint")
        top.addWidget(self.step_label)
        root.addLayout(top)

        self.stack = QStackedWidget()
        for build in (self._welcome, self._mic, self._keys, self._try, self._done):
            self.stack.addWidget(build())
        root.addWidget(self.stack, 1)

        bottom = QHBoxLayout()
        self.skip = QPushButton(tr("onb.skip"))
        self.skip.setObjectName("Ghost")
        self.skip.clicked.connect(self.finish)
        bottom.addWidget(self.skip)
        bottom.addStretch(1)
        self.back = QPushButton(tr("onb.back"))
        self.back.clicked.connect(lambda: self.go(self.stack.currentIndex() - 1))
        self.next = QPushButton(tr("onb.next"))
        self.next.setObjectName("Primary")
        self.next.setDefault(True)
        self.next.clicked.connect(self._next)
        for b in (self.skip, self.back, self.next):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        bottom.addWidget(self.back)
        bottom.addWidget(self.next)
        root.addLayout(bottom)
        self.go(0)

    # --- navigation ---------------------------------------------------------------------------

    def go(self, i: int) -> None:
        i = max(0, min(STEPS - 1, i))
        self.stack.setCurrentIndex(i)
        self.dots.set(i)
        self.step_label.setText(tr("onb.step", i=i + 1, n=STEPS))
        self.back.setVisible(i > 0)
        self.skip.setVisible(i < STEPS - 1)
        self.next.setText(tr("onb.finish") if i == STEPS - 1 else tr("onb.next"))
        if i == 1:
            self.meter.start()
        else:
            self.meter.stop()
        if i == 3:
            self._try_mode(self._try_current)
        if i == STEPS - 1:
            self._fill_done()

    def _next(self) -> None:
        if self.stack.currentIndex() == STEPS - 1:
            if self.autostart.isChecked() != _autostart_enabled():
                with contextlib.suppress(OSError):
                    _set_autostart(self.autostart.isChecked())
            self.finish()
        else:
            self.go(self.stack.currentIndex() + 1)

    def finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        self.meter.stop()
        self.ctx.cancel_capture()
        self.ctx.cfg.app.onboarded = True
        self.ctx.save()
        self.hide()
        self._on_done()

    def closeEvent(self, event) -> None:  # closing the guide counts as skipping it
        self.finish()
        event.accept()

    def showEvent(self, event) -> None:
        dark_title_bar(self, self.ctx.palette.dark)
        if sys.platform == "win32":
            from ..win.dwm import caption_colors

            p = self.ctx.palette
            caption_colors(int(self.winId()), p.base, p.text, p.base)
        super().showEvent(event)

    # --- pages --------------------------------------------------------------------------------

    @staticmethod
    def _page(title: str, sub: str) -> tuple[QWidget, QVBoxLayout]:
        w = QWidget()
        col = QVBoxLayout(w)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(14)
        col.addWidget(label(title, "HeroTitle"))
        w.sub = label(sub, "PageSub", wrap=True)
        col.addWidget(w.sub)
        col.addSpacing(6)
        return w, col

    def _welcome(self) -> QWidget:
        w = QWidget()
        col = QVBoxLayout(w)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(14)
        col.addWidget(Orb(self.ctx.palette, 72), 0, Qt.AlignmentFlag.AlignLeft)
        col.addSpacing(-20)
        col.addWidget(label(tr("onb.title"), "HeroTitle"))
        col.addWidget(label(tr("onb.welcome.sub"), "PageSub", wrap=True))
        col.addSpacing(8)

        card = Card(padding=18, spacing=10)
        key_line, self._set_key = _status_line(self.ctx)
        self.net_line, self._set_net = _status_line(self.ctx)
        card.body.addWidget(key_line)
        card.body.addWidget(self.net_line)
        self.key_help = label(tr("onb.key.missing.desc"), "Faint", wrap=True)
        card.body.addWidget(self.key_help)
        self.key_buttons = QWidget()
        row = QHBoxLayout(self.key_buttons)
        row.setContentsMargins(0, 0, 0, 0)
        edit = QPushButton(tr("onb.key.edit"))
        edit.clicked.connect(lambda: subprocess.Popen(["rundll32.exe", "sysdm.cpl,EditEnvironmentVariables"]))
        recheck = QPushButton(tr("onb.key.recheck"))
        recheck.clicked.connect(self._check_key)
        row.addWidget(edit)
        row.addWidget(recheck)
        row.addStretch(1)
        card.body.addWidget(self.key_buttons)
        col.addWidget(card)
        col.addStretch(1)
        self._net = _Result()
        self._net.got.connect(self._net_result)
        QTimer.singleShot(0, self._check_key)
        return w

    def _check_key(self) -> None:
        key = config.api_key()
        found = bool(key)
        self._set_key("ok" if found else "bad", tr("onb.key.ok") if found else tr("onb.key.missing"))
        self.key_help.setVisible(not found)
        self.key_buttons.setVisible(not found)
        self._set_net("wait", tr("onb.net.checking"))
        self.net_line.setVisible(found)
        if not found:
            return
        proxy = self.ctx.cfg.openrouter.proxy

        def work() -> None:
            from ..openrouter import OpenRouterClient, OpenRouterError

            try:
                with OpenRouterClient(api_key=key, proxy=proxy) as client:
                    client.check()
                self._net.got.emit(True, "")
            except OpenRouterError as e:
                self._net.got.emit(False, str(e)[:120])

        threading.Thread(target=work, name="key-check", daemon=True).start()

    def _net_result(self, ok: bool, why: str) -> None:
        if ok:
            self._set_net("ok", tr("onb.net.ok"))
        else:
            reason = "API key" if "401" in why or "403" in why else why
            self._set_net("bad", tr("onb.net.bad", why=reason))
            self.key_buttons.setVisible(True)

    def _mic(self) -> QWidget:
        w, col = self._page(tr("onb.mic.title"), tr("onb.mic.sub"))
        card = Card(padding=18, spacing=12)
        cfg = self.ctx.cfg

        def pick(device: str) -> None:
            cfg.audio.device = device
            self.ctx.save()
            self.meter.start()

        card.body.addWidget(SettingRow(tr("set.mic"), combo(mic_options(), cfg.audio.device, pick)))
        self.meter = MicTest(self.ctx, seconds=None)
        self.meter.button.hide()
        card.body.addWidget(self.meter)
        heard_line, set_heard = _status_line(self.ctx)
        card.body.addWidget(heard_line)
        col.addWidget(card)
        col.addStretch(1)

        def poll() -> None:
            heard = self.meter.peak > 0.25
            set_heard("ok" if heard else "wait", tr("onb.mic.heard") if heard else tr("onb.mic.silent"))

        self._heard_timer = QTimer(self, interval=200, timeout=poll)
        self._heard_timer.start()
        poll()
        return w

    def _keys(self) -> QWidget:
        w, col = self._page(tr("onb.keys.title"), tr("onb.keys.sub"))
        card = Card(padding=18, spacing=6)
        p = self.ctx.palette
        card.body.addWidget(SettingRow(tr("set.shortcut.main"), HotkeyField(self.ctx, "main")))
        card.body.addWidget(divider(p))
        card.body.addWidget(
            SettingRow(
                tr("set.shortcut.translate"), HotkeyField(self.ctx, "translate"), tr("set.shortcut.translate.desc")
            )
        )
        card.body.addWidget(divider(p))
        card.body.addWidget(
            SettingRow(tr("set.shortcut.ask"), HotkeyField(self.ctx, "ask"), tr("set.shortcut.ask.desc"))
        )
        col.addWidget(card)
        col.addWidget(label(tr("onb.keys.tip"), "Muted", wrap=True))
        col.addStretch(1)
        return w

    def _try(self) -> QWidget:
        w, col = self._page(tr("onb.try.title"), tr("onb.try.sub"))
        modes = [("dictate", tr("mode.dictate")), ("translate", tr("mode.translate")), ("ask", tr("mode.ask"))]
        seg = Segmented(modes, "dictate")
        col.addWidget(seg, 0, Qt.AlignmentFlag.AlignLeft)
        card = Card(padding=18, spacing=12)
        self.try_hint = label("", wrap=True)
        card.body.addWidget(self.try_hint)
        self.try_box = QPlainTextEdit()
        self.try_box.setMinimumHeight(120)
        card.body.addWidget(self.try_box)
        done_line, self._set_try = _status_line(self.ctx)
        self._try_line = done_line
        card.body.addWidget(done_line)
        col.addWidget(card)
        col.addStretch(1)
        self.try_box.textChanged.connect(self._try_changed)
        seg.changed.connect(self._try_mode)
        self._try_mode("dictate")
        return w

    def _try_mode(self, mode: str) -> None:
        self._try_current = mode
        h = self.ctx.cfg.hotkeys
        k, t, a = keys.display(h.main), keys.display(h.translate), keys.display(h.ask)
        target = lang_label(self.ctx.cfg.translate.targets[0]) if self.ctx.cfg.translate.targets else ""
        hints = {
            "dictate": tr("onb.try.dictate", k=k),
            "translate": tr("onb.try.translate", k=k, k2=t, target=target),
            "ask": tr("onb.try.ask", k=k, k2=a),
        }
        self.try_hint.setText(hints[mode])
        self._try_initial = tr("onb.try.ask.sample") if mode == "ask" else ""
        self.try_box.blockSignals(True)
        self.try_box.setPlainText(self._try_initial)
        self.try_box.blockSignals(False)
        self.try_box.setPlaceholderText(tr("onb.try.placeholder"))
        self._try_line.hide()
        self.try_box.setFocus()
        if mode == "ask":
            self.try_box.selectAll()

    def _try_changed(self) -> None:
        text = self.try_box.toPlainText().strip()
        if text and text != self._try_initial:
            self._set_try("ok", tr("onb.try.done"))
            self._try_line.show()

    def _done(self) -> QWidget:
        w, col = self._page(tr("onb.done.title"), "")
        self.done_sub = w.sub
        self.cheat = Card(padding=18, spacing=6)
        col.addWidget(self.cheat)
        card = Card(padding=18, spacing=6)
        # Typeless launches at login by default, so the guide offers it switched on.
        self.autostart = Toggle(self.ctx.palette, True)
        card.body.addWidget(SettingRow(tr("onb.done.autostart"), self.autostart))
        col.addWidget(card)
        col.addStretch(1)
        return w

    def _fill_done(self) -> None:
        """Shortcuts may have changed on step 3, so the summary is built when the last step opens."""
        h = self.ctx.cfg.hotkeys
        self.done_sub.setText(tr("onb.done.sub", k=keys.display(h.main)))
        body = self.cheat.body
        while body.count():
            item = body.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
                item.widget().deleteLater()
        rows = [
            (tr("mode.dictate"), [h.main]),
            (tr("mode.translate"), [h.main, h.translate]),
            (tr("mode.ask"), [h.main, h.ask]),
        ]
        for i, (name, combo_keys) in enumerate(rows):
            if i:
                body.addWidget(divider(self.ctx.palette))
            body.addWidget(SettingRow(name, keycaps([keys.display(k) for k in combo_keys])))
