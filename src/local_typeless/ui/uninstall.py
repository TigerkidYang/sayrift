"""`Sayrift uninstall` (Apps & features > Uninstall): confirm, stop the app, remove it."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QCheckBox, QMessageBox

from .. import config
from ..win import install
from .i18n import language, set_language
from .single_instance import quit_running

_ZH = {
    "title": "卸载 Sayrift",
    "confirm": "确定要从这台电脑上卸载 Sayrift 吗？",
    "data": "同时删除历史记录、词典和设置",
    "busy": "Sayrift 还在运行，而且没有响应退出请求。请从托盘菜单退出后再试。",
    "done": "Sayrift 已卸载。",
}
_EN = {
    "title": "Uninstall Sayrift",
    "confirm": "Remove Sayrift from this computer?",
    "data": "Also delete history, dictionary and settings",
    "busy": "Sayrift is still running and did not quit. Quit it from the tray menu and try again.",
    "done": "Sayrift has been removed.",
}


def run(quiet: bool = False) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    set_language("auto")
    t = _ZH if language() == "zh" else _EN
    delete_data = False
    if not quiet:
        box = QMessageBox(QMessageBox.Icon.Question, t["title"], t["confirm"])
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        check = QCheckBox(t["data"])
        box.setCheckBox(check)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return 1
        delete_data = check.isChecked()
    if not quit_running():
        if not quiet:
            QMessageBox.warning(None, t["title"], t["busy"])
        return 1
    # Capture the custom/legacy install location before unregister removes it.
    installed = install.installed_dir()
    if getattr(sys, "frozen", False):
        installed = install.validate_install_dir(installed or Path(sys.executable).parent)
        if installed != Path(sys.executable).resolve().parent:
            raise ValueError("The running application does not match the registered installation")
    install.unregister()
    if delete_data:
        shutil.rmtree(config.config_dir(), ignore_errors=True)
    if not quiet:
        QMessageBox.information(None, t["title"], t["done"])
    if getattr(sys, "frozen", False):  # only an installed copy deletes its own folder
        install.remove_dir_after_exit(installed or install.default_dir())
    del app
    return 0
