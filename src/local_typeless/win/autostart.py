"""Launch at login (a Typeless setting): a per-user Run entry pointing at the windowless launcher."""

from __future__ import annotations

import contextlib
import sys
import winreg
from pathlib import Path

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE = "local-typeless"


def launcher() -> Path:
    """The installed app's own exe; in a dev checkout, `sayrift-gui.exe` next to the interpreter
    (uv puts it in .venv\\Scripts)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable)
    return Path(sys.executable).with_name("sayrift-gui.exe")


def enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _VALUE)
            return True
    except OSError:
        return False


def set_enabled(on: bool, target: Path | None = None) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if on:
            winreg.SetValueEx(key, _VALUE, 0, winreg.REG_SZ, f'"{target or launcher()}" --minimized')
        else:
            with contextlib.suppress(FileNotFoundError):
                winreg.DeleteValue(key, _VALUE)
