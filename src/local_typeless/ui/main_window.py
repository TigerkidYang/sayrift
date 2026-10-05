"""The main window: an aurora canvas with a pill navigation on top and the pages below."""

from __future__ import annotations

import sys

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QColor, QIcon, QPainter
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import icons
from .glass import Aurora, NavPill
from .i18n import set_language, tr
from .pages import Context, DictionaryPage, HistoryPage, HomePage
from .settings_page import SettingsPage
from .spend_page import SpendPage
from .theme import APP_NAME, palette_for, stylesheet

NAV = [("home", "nav.home"), ("history", "nav.history"), ("dictionary", "nav.dictionary"), ("spend", "nav.spend"),
       ("settings", "nav.settings")]  # fmt: skip


class StatusDot(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(8, 8)
        self.color = QColor("#4ee3b0")

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.color)
        p.drawEllipse(0, 0, 8, 8)


class MainWindow(QMainWindow):
    def __init__(self, make_context) -> None:
        """`make_context(palette)` returns a pages.Context; called again when theme / language change."""
        super().__init__()
        self._make_context = make_context
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(icons.APP_ICON)))
        self.resize(1120, 760)
        self.setMinimumSize(920, 640)
        self.quitting = False
        self._current = "home"
        self._status = ("status.ready", "#4ee3b0", "ready")
        self.build()

    # --- construction -------------------------------------------------------------------------

    def build(self) -> None:
        ctx0 = self._make_context(None)
        set_language(ctx0.cfg.app.language)
        self.palette_ = palette_for(ctx0.cfg.app.theme)
        self.ctx: Context = self._make_context(self.palette_)
        self.setStyleSheet(stylesheet(self.palette_))
        self._title_bar()

        root = Aurora(self.palette_)
        col = QVBoxLayout(root)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(self._top_bar())
        self.stack = QStackedWidget()
        self.stack.setObjectName("Content")
        self.pages = {
            "home": HomePage(self.ctx, open_history=lambda: self.show_page("history")),
            "history": HistoryPage(self.ctx),
            "dictionary": DictionaryPage(self.ctx),
            "spend": SpendPage(self.ctx),
            "settings": SettingsPage(self.ctx, on_theme_or_language=lambda _v: self.rebuild()),
        }
        for page in self.pages.values():
            page.setObjectName("Page")
            self.stack.addWidget(page)
        col.addWidget(self.stack, 1)
        old = self.centralWidget()
        self.setCentralWidget(root)
        if old is not None:
            old.deleteLater()
        self.show_page(self._current, animate=False)
        self.set_status(*self._status)

    def rebuild(self) -> None:
        """Theme or language changed: rebuild every widget with the new palette and strings."""
        self.build()

    def _top_bar(self) -> QWidget:
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(24, 16, 24, 6)

        left = QWidget()
        brand = QHBoxLayout(left)
        brand.setContentsMargins(0, 0, 0, 0)
        brand.setSpacing(9)
        logo = QLabel()
        logo.setPixmap(QIcon(str(icons.APP_ICON)).pixmap(22, 22))
        brand.addWidget(logo)
        name = QLabel(APP_NAME)
        name.setObjectName("Brand")
        brand.addWidget(name)
        brand.addStretch(1)

        self.nav = NavPill([(k, tr(t)) for k, t in NAV], on_change=self.show_page)

        right = QWidget()
        status = QHBoxLayout(right)
        status.setContentsMargins(0, 0, 0, 0)
        status.setSpacing(8)
        status.addStretch(1)
        self.dot = StatusDot()
        status.addWidget(self.dot)
        self.status_label = QLabel()
        self.status_label.setObjectName("Status")
        status.addWidget(self.status_label)

        # Equal side columns keep the pill exactly centred whatever the brand / status widths are.
        row.addWidget(left, 1)
        row.addWidget(self.nav, 0, Qt.AlignmentFlag.AlignCenter)
        row.addWidget(right, 1)
        return bar

    def _title_bar(self) -> None:
        if sys.platform != "win32":
            return
        from ..win.dwm import caption_colors
        from ..win.dwm import dark_title_bar as set_dark

        hwnd = int(self.winId())
        set_dark(hwnd, self.palette_.dark)
        caption_colors(hwnd, self.palette_.base, self.palette_.text, self.palette_.base)

    # --- behaviour ----------------------------------------------------------------------------

    def show_page(self, key: str, animate: bool = True) -> None:
        self._current = key
        self.nav.select(key)
        page = self.pages[key]
        self.stack.setCurrentWidget(page)
        if hasattr(page, "refresh"):
            page.refresh()
        if animate:  # a short fade: the page settles in rather than snapping
            effect = QGraphicsOpacityEffect(page)
            page.setGraphicsEffect(effect)
            anim = QPropertyAnimation(effect, b"opacity", page)
            anim.setDuration(160)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.finished.connect(lambda: page.setGraphicsEffect(None))
            anim.start()

    def refresh_current(self) -> None:
        if self.isVisible() and self._current in ("home", "history", "spend"):
            self.pages[self._current].refresh()

    def set_status(self, key: str, color: str, state: str = "") -> None:
        self._status = (key, color, state)
        self.status_label.setText(tr(key))
        self.dot.color = QColor(color)
        self.dot.update()
        home = self.pages.get("home")
        if home is not None and state and hasattr(home, "set_state"):
            home.set_state(state)

    def set_level(self, level: float) -> None:
        home = self.pages.get("home")
        if home is not None and self.isVisible() and hasattr(home, "set_level"):
            home.set_level(level)

    def open(self) -> None:
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()
        self.show_page(self._current, animate=False)

    def closeEvent(self, event) -> None:
        if self.quitting:
            event.accept()
        else:  # closing the window keeps the app running in the tray
            event.ignore()
            self.hide()


def dark_title_bar(widget: QWidget, dark: bool) -> None:
    if sys.platform == "win32":
        from ..win.dwm import dark_title_bar as set_dark

        set_dark(int(widget.winId()), dark)
