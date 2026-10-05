"""System tray icon and menu; double-click (or "Open") shows the main window.

The icon is the Glass orb: plain when ready, ringed while listening, dimmed while processing.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QAction, QActionGroup, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .. import config, keys
from .i18n import set_language, tr
from .icons import paint_orb
from .theme import palette_for, stylesheet

RECENT = 5


def orb_icon(state: str) -> QIcon:
    icon = QIcon()
    for size in (16, 20, 24, 32, 48, 64):
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(size / 2, size / 2)
        if state == "listening":
            paint_orb(p, c, size * 0.3, glow=False, ring=True)
        else:
            paint_orb(p, c, size * 0.44, glow=False, dim=0.45 if state == "processing" else 1.0)
        p.end()
        icon.addPixmap(pm)
    return icon


class Tray:
    def __init__(self, cfg: config.Config, *, on_quit: Callable[[], None], on_open: Callable[[], None]) -> None:
        self.cfg = cfg
        self._on_quit, self._on_open = on_quit, on_open
        self._icons = {state: orb_icon(state) for state in ("idle", "listening", "processing")}
        self.icon = QSystemTrayIcon(self._icons["idle"])
        self.icon.activated.connect(
            lambda reason: on_open() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None
        )
        self._recent: list[str] = []
        self._state, self._message = "idle", ""
        self._menu: QMenu | None = None
        self._build_menu()
        self.icon.show()

    def _build_menu(self) -> None:
        set_language(self.cfg.app.language)
        menu = QMenu()
        menu.setStyleSheet(stylesheet(palette_for(self.cfg.app.theme)))
        menu.setDefaultAction(menu.addAction(tr("tray.open"), self._on_open))
        self._status = menu.addAction("")
        self._status.setEnabled(False)
        menu.addSeparator()
        self._translate_menu = menu.addMenu(tr("tray.translate_to"))
        self._rebuild_targets()
        self._recent_menu = menu.addMenu(tr("tray.recent"))
        self._rebuild_recent()
        menu.addSeparator()
        self._autostart = menu.addAction(tr("tray.autostart"), self._toggle_autostart)
        self._autostart.setCheckable(True)
        self._autostart.setChecked(self._autostart_enabled())
        menu.addAction(tr("tray.logs"), lambda: os.startfile(config.config_dir() / "logs"))
        menu.addSeparator()
        menu.addAction(tr("tray.quit"), self._on_quit)
        self._menu = menu  # keep a reference: the tray does not own it
        self.icon.setContextMenu(menu)
        self._show_status()

    def set_state(self, state: str, message: str = "") -> None:
        """state: idle / listening / processing / error (message = an err.* key)."""
        self._state, self._message = state, message
        self.icon.setIcon(self._icons.get(state, self._icons["idle"]))
        self._show_status()

    def _show_status(self) -> None:
        k = keys.display(self.cfg.hotkeys.main)
        if self._state == "error":
            text = tr("tray.status.error", m=tr(self._message))
        else:
            text = tr({"listening": "tray.status.listening", "processing": "tray.status.processing"}.get(
                self._state, "tray.status.ready"), k=k)  # fmt: skip
        self._status.setText(text)
        self.icon.setToolTip(f"Sayrift — {text}")

    def add_recent(self, text: str) -> None:
        if text:
            self._recent = [text, *[t for t in self._recent if t != text]][:RECENT]
            self._rebuild_recent()

    def settings_changed(self) -> None:
        """Settings were saved (possibly language or theme): rebuild the menu."""
        self._build_menu()

    # --- menus ---------------------------------------------------------------------------------

    def _rebuild_targets(self) -> None:
        from .settings_page import lang_label

        self._translate_menu.clear()
        group = QActionGroup(self._translate_menu)
        for lang in self.cfg.translate.targets:
            action = QAction(lang_label(lang), self._translate_menu, checkable=True)
            action.setChecked(lang == self.cfg.translate.targets[0])
            action.triggered.connect(lambda _checked=False, lang=lang: self._pick_target(lang))
            group.addAction(action)
            self._translate_menu.addAction(action)

    def _pick_target(self, lang: str) -> None:
        # Typeless lets you pick the current target from an ordered list; the pick moves to the front.
        targets = self.cfg.translate.targets
        self.cfg.translate.targets = [lang, *[t for t in targets if t != lang]]
        config.save(self.cfg)
        self._rebuild_targets()

    def _rebuild_recent(self) -> None:
        self._recent_menu.clear()
        if not self._recent:
            empty = self._recent_menu.addAction(tr("tray.recent.empty"))
            empty.setEnabled(False)
        for text in self._recent:
            label = text.replace("\n", " ")
            label = label[:40] + "…" if len(label) > 40 else label
            self._recent_menu.addAction(label, lambda text=text: QGuiApplication.clipboard().setText(text))

    @staticmethod
    def _autostart_enabled() -> bool:
        try:
            from ..win import autostart

            return autostart.enabled()
        except OSError:
            return False

    def _toggle_autostart(self, checked: bool) -> None:
        from ..win import autostart

        if checked and not autostart.launcher().exists():
            self._autostart.setChecked(False)
            return
        autostart.set_enabled(checked)
