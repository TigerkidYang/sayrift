"""Sayrift Setup: a per-user installer (no admin) for the app folder bundled into this exe as payload.zip.

Installs to %LOCALAPPDATA%\\Programs\\Sayrift, adds Start menu (and optionally desktop) shortcuts and an
Apps & features entry whose Uninstall runs `sayrift.exe uninstall`. Re-running it upgrades in place.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from local_typeless import __version__
from local_typeless.ui import icons
from local_typeless.ui.glass import Aurora
from local_typeless.ui.i18n import language, set_language
from local_typeless.ui.single_instance import quit_running
from local_typeless.ui.theme import palette_for, stylesheet
from local_typeless.ui.widgets import Card, SettingRow, Toggle, divider, label
from local_typeless.win import install
from local_typeless.win.dwm import caption_colors, dark_title_bar

_ZH = {
    "window": "Sayrift 安装程序",
    "title": "安装 Sayrift",
    "sub": "在任何应用里，用说话代替打字。安装只需要几秒钟，不需要管理员权限。",
    "upgrade": "将把已安装的版本更新到 {v}，你的历史记录、词典和设置都会保留。",
    "where": "安装位置",
    "change": "更改",
    "desktop": "创建桌面快捷方式",
    "cancel": "取消",
    "install": "安装",
    "installing": "正在安装…",
    "stopping": "正在关闭正在运行的 Sayrift…",
    "copying": "正在复制文件…",
    "done.title": "安装完成",
    "done.sub": "可以在开始菜单里找到 Sayrift。以后要卸载，在“设置 → 应用”里找到它即可。",
    "launch": "立即启动 Sayrift",
    "finish": "完成",
    "failed": "安装失败：{e}",
    "busy": "Sayrift 正在运行，而且没有响应退出请求。请从托盘菜单退出后再安装。",
}
_EN = {
    "window": "Sayrift Setup",
    "title": "Install Sayrift",
    "sub": "Speak instead of typing, in any app. Installing takes a few seconds and needs no admin rights.",
    "upgrade": "The installed copy will be updated to {v}. Your history, dictionary and settings are kept.",
    "where": "Install location",
    "change": "Change",
    "desktop": "Create a desktop shortcut",
    "cancel": "Cancel",
    "install": "Install",
    "installing": "Installing…",
    "stopping": "Closing the running Sayrift…",
    "copying": "Copying files…",
    "done.title": "Installed",
    "done.sub": "You'll find Sayrift in the Start menu. To remove it later, use Settings → Apps.",
    "launch": "Launch Sayrift now",
    "finish": "Finish",
    "failed": "Installation failed: {e}",
    "busy": "Sayrift is running and did not quit. Quit it from the tray menu, then run Setup again.",
}


def payload() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1] / "build")) / "payload.zip"


class Worker(QObject):
    progress = Signal(int, str)
    finished = Signal(str)  # "" on success, else an error message

    def __init__(self, target: Path, desktop: bool, t: dict[str, str]) -> None:
        super().__init__()
        self.target, self.desktop, self.t = target, desktop, t

    def run(self) -> None:
        try:
            self.target = install.validate_install_dir(self.target)
            self.progress.emit(0, self.t["stopping"])
            if not quit_running():
                self.finished.emit(self.t["busy"])
                return
            self.progress.emit(2, self.t["copying"])
            install.replace_payload(self.target, payload(), lambda value: self.progress.emit(value, self.t["copying"]))
            install.register(self.target, __version__, desktop=self.desktop)
            self.progress.emit(100, "")
            self.finished.emit("")
        except Exception as e:  # show anything to the user rather than dying silently
            self.finished.emit(self.t["failed"].format(e=e))


class Setup(QWidget):
    def __init__(self) -> None:
        super().__init__()
        set_language("auto")
        self.t = _ZH if language() == "zh" else _EN
        self.p = palette_for("system")
        self.setWindowTitle(self.t["window"])
        self.setWindowIcon(QIcon(str(icons.APP_ICON)))
        self.setObjectName("Content")
        self.setStyleSheet(stylesheet(self.p))
        self.setFixedSize(620, 460)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        self.target = install.installed_dir() or install.default_dir()

        canvas = Aurora(self.p)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(canvas)
        root = QVBoxLayout(canvas)
        root.setContentsMargins(40, 32, 40, 28)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.stack.addWidget(self._welcome())
        self.stack.addWidget(self._progress())
        self.stack.addWidget(self._done())

    def showEvent(self, event) -> None:
        dark_title_bar(int(self.winId()), self.p.dark)
        caption_colors(int(self.winId()), self.p.base, self.p.text, self.p.base)
        super().showEvent(event)

    def _head(self, col: QVBoxLayout, title: str, sub: str) -> None:
        logo = QLabel()
        logo.setPixmap(QIcon(str(icons.APP_ICON)).pixmap(56, 56))
        col.addWidget(logo)
        col.addSpacing(6)
        col.addWidget(label(title, "HeroTitle"))
        col.addWidget(label(sub, "PageSub", wrap=True))
        col.addSpacing(10)

    def _buttons(self, col: QVBoxLayout, *buttons: QPushButton) -> None:
        col.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        for b in buttons:
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            row.addWidget(b)
        col.addLayout(row)

    def _welcome(self) -> QWidget:
        w = QWidget()
        col = QVBoxLayout(w)
        col.setContentsMargins(0, 0, 0, 0)
        upgrading = install.installed_dir() is not None
        sub = self.t["upgrade"].format(v=__version__) if upgrading else self.t["sub"]
        self._head(col, f"{self.t['title']} {__version__}", sub)
        card = Card(padding=16, spacing=6)
        where = QWidget()
        row = QHBoxLayout(where)
        row.setContentsMargins(0, 0, 0, 0)
        self.path_label = label(str(self.target), "Muted")
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(self.path_label, 1)
        change = QPushButton(self.t["change"])
        change.clicked.connect(self._pick_dir)
        change.setEnabled(not upgrading)  # an upgrade stays where the app already is
        row.addWidget(change)
        card.body.addWidget(label(self.t["where"]))
        card.body.addWidget(where)
        card.body.addWidget(divider(self.p))
        self.desktop = Toggle(self.p, True)
        card.body.addWidget(SettingRow(self.t["desktop"], self.desktop))
        col.addWidget(card)
        cancel = QPushButton(self.t["cancel"])
        cancel.clicked.connect(self.close)
        go = QPushButton(self.t["install"])
        go.setObjectName("Primary")
        go.setDefault(True)
        go.clicked.connect(self._install)
        self._buttons(col, cancel, go)
        return w

    def _progress(self) -> QWidget:
        w = QWidget()
        col = QVBoxLayout(w)
        col.setContentsMargins(0, 0, 0, 0)
        self._head(col, self.t["installing"], "")
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.bar.setStyleSheet(
            f"QProgressBar {{ background: {self.p.surface2}; border: none; border-radius: 4px; }}"
            f"QProgressBar::chunk {{ background: {self.p.accent}; border-radius: 4px; }}"
        )
        col.addWidget(self.bar)
        self.step = label("", "Faint")
        col.addWidget(self.step)
        col.addStretch(1)
        return w

    def _done(self) -> QWidget:
        w = QWidget()
        col = QVBoxLayout(w)
        col.setContentsMargins(0, 0, 0, 0)
        self._head(col, self.t["done.title"], self.t["done.sub"])
        card = Card(padding=16, spacing=6)
        self.launch = Toggle(self.p, True)
        card.body.addWidget(SettingRow(self.t["launch"], self.launch))
        col.addWidget(card)
        finish = QPushButton(self.t["finish"])
        finish.setObjectName("Primary")
        finish.setDefault(True)
        finish.clicked.connect(self._finish)
        self._buttons(col, finish)
        return w

    def _pick_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, self.t["where"], str(self.target.parent))
        if chosen:
            self.target = Path(chosen) / "Sayrift"
            self.path_label.setText(str(self.target))

    def _install(self) -> None:
        self.stack.setCurrentIndex(1)
        self.thread = QThread()
        self.worker = Worker(self.target, self.desktop.isChecked(), self.t)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.finished.connect(self.thread.quit)
        self.thread.start()

    def _on_progress(self, value: int, text: str) -> None:
        self.bar.setValue(value)
        if text:
            self.step.setText(text)

    def _on_finished(self, error: str) -> None:
        if error:
            QMessageBox.critical(self, self.t["window"], error)
            self.stack.setCurrentIndex(0)
            return
        self.stack.setCurrentIndex(2)

    def _finish(self) -> None:
        if self.launch.isChecked():
            subprocess.Popen([str(self.target / install.EXE_NAME)], cwd=self.target, close_fds=True)
        self.close()


def silent() -> int:
    """`Setup.exe --silent`: default location, desktop shortcut, no UI, no launch; exit code 0 on success."""
    app = QApplication(sys.argv)
    set_language("auto")
    worker = Worker(install.installed_dir() or install.default_dir(), True, _ZH if language() == "zh" else _EN)
    errors: list[str] = []
    worker.finished.connect(errors.append)
    worker.run()
    del app
    return 1 if errors and errors[0] else 0


def main() -> int:
    if "--silent" in sys.argv:
        return silent()
    app = QApplication(sys.argv)
    win = Setup()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
