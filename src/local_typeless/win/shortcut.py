"""Start menu / desktop shortcuts and the taskbar identity."""

from __future__ import annotations

import ctypes
import os
import subprocess
from pathlib import Path

from ..brand import APP_NAME, LEGACY_SLUG
from .autostart import launcher

APP_ID = "local-typeless.app"  # AppUserModelID: taskbar groups our windows under our icon, not pythonw's
NAME = APP_NAME
ICON = Path(__file__).resolve().parents[1] / "assets" / "app.ico"


def set_app_id() -> None:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(ctypes.c_wchar_p(APP_ID))


def _folder(csidl: int) -> Path:
    # Ask the shell: the desktop is often redirected (OneDrive), so %USERPROFILE%\Desktop can be wrong.
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf)
    return Path(buf.value)


def locations(name: str = NAME) -> list[Path]:
    CSIDL_PROGRAMS, CSIDL_DESKTOPDIRECTORY = 0x02, 0x10
    return [_folder(CSIDL_PROGRAMS) / f"{name}.lnk", _folder(CSIDL_DESKTOPDIRECTORY) / f"{name}.lnk"]


def remove_legacy() -> None:
    """Remove the old generated shortcuts only after the replacement shortcuts exist."""
    for path in locations(LEGACY_SLUG):
        path.unlink(missing_ok=True)


def create(paths: list[Path] | None = None, *, target: Path | None = None, icon: Path | None = None) -> list[Path]:
    """Write .lnk files pointing at the app (default: the running app or this checkout's windowless launcher).
    IShellLink via ctypes COM is ~150 lines of vtable plumbing; WScript.Shell through PowerShell is one call."""
    target = target or launcher()
    icon = icon or ICON
    if not target.exists():
        raise FileNotFoundError(f"{target} is missing; run `uv sync` first")
    made = []
    for path in paths or locations():
        path.parent.mkdir(parents=True, exist_ok=True)
        script = (
            "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:LT_LNK); "
            "$s.TargetPath = $env:LT_TARGET; $s.IconLocation = $env:LT_ICON + ',0'; "
            "$s.WorkingDirectory = $env:USERPROFILE; $s.Description = 'Voice dictation'; $s.Save()"
        )
        env = {**os.environ, "LT_LNK": str(path), "LT_TARGET": str(target), "LT_ICON": str(icon)}
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            env=env,
            check=True,
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        made.append(path)
    return made
