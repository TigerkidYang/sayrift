"""Qt front-end: owns the GUI thread and runs the controller on a worker thread.

`QtUi` implements the `Ui` protocol by emitting signals; Qt queues them onto the GUI thread,
so the controller, audio and hook threads never touch widgets.
"""

from __future__ import annotations

import logging
import signal
import sys
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import single_instance
from .cards import Card
from .i18n import tr
from .icons import APP_ICON
from .main_window import MainWindow
from .onboarding import Onboarding
from .overlay import VoiceBar
from .pages import Context
from .theme import palette_for
from .tray import Tray

if TYPE_CHECKING:
    from ..app import App
    from ..config import Config
    from ..store import History

log = logging.getLogger(__name__)

STATUS_COLORS = {"ready": "#4ee3b0", "listening": "#ff7a8a", "processing": "#ffc46b"}


class QtUi(QObject):
    _listening = Signal(str, float)
    _level = Signal(float)
    _processing = Signal()
    _done = Signal(str)
    _cancelled = Signal()
    _error = Signal(str)
    _answer = Signal(str, str)
    _result = Signal(str, str)
    _history_changed = Signal()

    def __init__(self, bar: VoiceBar, tray: Tray) -> None:
        super().__init__()
        self.bar, self.tray = bar, tray
        self.window: MainWindow | None = None
        self.server = None  # single-instance endpoint, kept alive here
        self._cards: list[Card] = []
        self._request_cancel: Callable[[], None] = lambda: None
        self._request_finish: Callable[[], None] = lambda: None
        bar.cancel_clicked.connect(lambda: self._request_cancel())
        bar.finish_clicked.connect(lambda: self._request_finish())
        self._listening.connect(self._on_listening)
        self._level.connect(bar.push_level)
        self._level.connect(self._on_level)
        self._processing.connect(self._on_processing)
        self._done.connect(self._on_done)
        self._cancelled.connect(self._on_cancelled)
        self._error.connect(self._on_error)
        self._answer.connect(self._on_answer)
        self._result.connect(self._on_result)
        self._history_changed.connect(self._on_history_changed)

    def bind(self, controller: App) -> None:
        """Route the Voice bar's × / ✓ buttons to the controller."""
        self._request_cancel = controller.request_cancel
        self._request_finish = controller.request_finish

    # --- Ui protocol (any thread) ---------------------------------------------------------------

    def listening(self, label: str, max_seconds: float) -> None:
        self._listening.emit(label, max_seconds)

    def level(self, rms: float) -> None:
        self._level.emit(rms)

    def processing(self) -> None:
        self._processing.emit()

    def done(self, text: str) -> None:
        self._done.emit(text)

    def cancelled(self) -> None:
        self._cancelled.emit()

    def error(self, message: str) -> None:
        self._error.emit(message)

    def answer(self, question: str, answer: str) -> None:
        self._answer.emit(question, answer)

    def result(self, text: str, reason: str) -> None:
        self._result.emit(text, reason)

    def history_changed(self) -> None:
        self._history_changed.emit()

    # --- GUI thread ------------------------------------------------------------------------------

    def _on_level(self, rms: float) -> None:
        if self.window is not None:
            from .overlay import level_to_height

            self.window.set_level(level_to_height(rms))

    def _status(self, key: str) -> None:
        if self.window is not None:
            self.window.set_status(f"status.{key}", STATUS_COLORS[key], key)

    def _on_listening(self, label: str, max_seconds: float) -> None:
        self.bar.listening(label, max_seconds)
        self.tray.set_state("listening")
        self._status("listening")

    def _on_processing(self) -> None:
        self.bar.processing()
        self.tray.set_state("processing")
        self._status("processing")

    def _on_done(self, text: str) -> None:
        self.bar.done()
        self.tray.set_state("idle")
        self.tray.add_recent(text)
        self._status("ready")

    def _on_cancelled(self) -> None:
        self.bar.cancelled()
        self.tray.set_state("idle")
        self._status("ready")

    def _on_error(self, message: str) -> None:
        self.bar.error(message)
        self.tray.set_state("error", message)
        self._status("ready")

    def _on_history_changed(self) -> None:
        if self.window is not None:
            self.window.refresh_current()

    def _show_card(self, card: Card) -> None:
        self._cards = [c for c in self._cards if c.isVisible()] + [card]
        card.show_near_bottom()

    def _on_answer(self, question: str, answer: str) -> None:
        self._show_card(Card(tr("card.answer"), question, answer, markdown=True))
        self.tray.add_recent(answer)

    def _on_result(self, text: str, reason: str) -> None:
        log.info("result card instead of pasting: %s", reason)  # technical detail stays in the log
        self._show_card(Card(tr("card.result"), "", text))
        self.tray.add_recent(text)


def run(
    cfg: Config, make_app: Callable[[QtUi], App], *, history: History | None = None, minimized: bool = False
) -> int:
    """Start the GUI; `make_app(ui)` builds the controller wired to that UI.

    The main window opens at launch unless `minimized` (launch at login starts quietly in the tray)."""
    if sys.platform == "win32":
        from ..win import shortcut

        shortcut.set_app_id()  # before any window exists, or the taskbar shows pythonw's icon
    qapp = QApplication.instance() or QApplication(sys.argv)
    if not minimized and sys.platform == "win32":
        from ..win.foreground import allow_any_foreground

        allow_any_foreground()
    if single_instance.notify_running(b"quiet" if minimized else b"open"):
        log.info("already running: asked that instance to show its window")
        return 0
    qapp.setQuitOnLastWindowClosed(False)  # closing the window or a card must not quit the tray app
    qapp.setWindowIcon(QIcon(str(APP_ICON)))
    bar = VoiceBar()
    controller: App | None = None
    window: MainWindow | None = None

    def quit_app() -> None:
        if controller:
            controller.stop()
        if window is not None:
            window.quitting = True
            window.close()
        qapp.quit()

    def open_window() -> None:
        if window is not None:
            window.open()

    tray = Tray(cfg, on_quit=quit_app, on_open=open_window)
    ui = QtUi(bar, tray)
    controller = make_app(ui)
    ui.bind(controller)

    def applied() -> None:
        controller.apply_settings()
        tray.settings_changed()

    def make_context(palette) -> Context:
        return Context(
            cfg=cfg,
            palette=palette,
            history=history,
            retry=controller.retry,
            capture_key=controller.capture_next_key,
            cancel_capture=controller.cancel_capture,
            applied=applied,
            run_onboarding=show_onboarding,
        )

    guide: Onboarding | None = None

    def show_onboarding() -> None:
        nonlocal guide
        if guide is None or not guide.isVisible():
            guide = Onboarding(make_context(palette_for(cfg.app.theme)), on_done=open_window)
            if window is not None:
                window.hide()
        guide.show()
        guide.raise_()
        guide.activateWindow()

    window = MainWindow(make_context)
    ui.window = window
    ui.server = single_instance.listen(
        lambda msg: open_window() if msg == b"open" else quit_app() if msg == b"quit" else None
    )
    worker = threading.Thread(target=controller.run, name="controller", daemon=True)
    worker.start()
    if not minimized:
        window.open() if cfg.app.onboarded else show_onboarding()

    signal.signal(signal.SIGINT, lambda *_: quit_app())  # Ctrl+C in the console
    heartbeat = QTimer(interval=250, timeout=lambda: None)  # let Python handle signals during exec()
    heartbeat.start()
    code = qapp.exec()
    controller.stop()
    worker.join(3)
    return code
