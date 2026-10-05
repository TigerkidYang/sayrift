"""Per-user install bookkeeping shared by the setup program and `sayrift uninstall`.

No admin rights: files go to %LOCALAPPDATA%\\Programs, registration to HKCU.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
import winreg
import zipfile
from collections.abc import Callable
from pathlib import Path

from ..brand import APP_NAME
from . import autostart, shortcut

EXE_NAME = "sayrift.exe"
LEGACY_EXE_NAME = "local-typeless.exe"
# Keep this key so Setup discovers and upgrades the original installation in place.
_UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\local-typeless"


def default_dir() -> Path:
    return Path(os.environ["LOCALAPPDATA"]) / "Programs" / APP_NAME


def installed_dir() -> Path | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _UNINSTALL_KEY) as key:
            return Path(winreg.QueryValueEx(key, "InstallLocation")[0])
    except OSError:
        return None


def validate_install_dir(path: Path) -> Path:
    """Only app-specific directories are eligible for recursive cleanup."""
    absolute = path.absolute()
    resolved = path.resolve()
    if absolute != resolved or resolved.name.casefold() not in {"sayrift", "local-typeless"}:
        raise ValueError("Expected a Sayrift installation directory, without directory links")
    return resolved


def replace_payload(target: Path, payload: Path, progress: Callable[[int], None]) -> None:
    """Extract and validate before replacing files; restore the old payload if a move fails."""
    target = validate_install_dir(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    owned = (EXE_NAME, "_internal", "licenses", LEGACY_EXE_NAME)
    has_app = any((target / name).is_file() for name in (EXE_NAME, LEGACY_EXE_NAME))
    if not has_app and any((target / name).exists() for name in owned):
        raise ValueError("Install location contains files that do not belong to this installation")
    for name in owned:
        entry = target / name
        if entry.is_symlink() or entry.is_junction():
            raise ValueError("Refusing to replace a linked application payload")
    stage = Path(tempfile.mkdtemp(prefix=".sayrift-setup-", dir=target.parent)).resolve()
    preserve_backup = False
    try:
        fresh, backup = stage / "new", stage / "previous"
        fresh.mkdir()
        backup.mkdir()
        with zipfile.ZipFile(payload) as archive:
            members = archive.infolist()
            for i, member in enumerate(members):
                destination = (fresh / member.filename).resolve()
                relative = destination.relative_to(fresh)
                if not relative.parts or relative.parts[0] not in owned[:3]:
                    raise ValueError("Unexpected file in the installer payload")
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Linked files are not allowed in the installer payload")
                archive.extract(member, fresh)
                progress(2 + int(88 * (i + 1) / len(members)))
        if not (fresh / EXE_NAME).is_file() or not (fresh / "_internal").is_dir():
            raise ValueError("Installer payload is incomplete")
        target.mkdir(exist_ok=True)
        saved, placed = [], []
        try:
            for name in owned:
                if (target / name).exists():
                    (target / name).replace(backup / name)
                    saved.append(name)
            for name in owned[:3]:
                if (fresh / name).exists():
                    (fresh / name).replace(target / name)
                    placed.append(name)
        except OSError:
            try:
                for name in reversed(placed):
                    (target / name).replace(fresh / name)
                for name in reversed(saved):
                    (backup / name).replace(target / name)
            except OSError:
                preserve_backup = True
                raise RuntimeError(f"Could not restore the previous app; its files are preserved at {backup}") from None
            raise
        progress(95)
    finally:
        if not preserve_backup:
            shutil.rmtree(stage)


def register(install_dir: Path, version: str, *, desktop: bool) -> None:
    """Shortcuts + the Apps & features entry. Re-running (an upgrade) overwrites both."""
    exe = install_dir / EXE_NAME
    paths = shortcut.locations()
    shortcut.create(paths if desktop else paths[:1], target=exe, icon=exe)
    shortcut.remove_legacy()
    size_kb = sum(f.stat().st_size for f in install_dir.rglob("*") if f.is_file()) // 1024
    values = {
        "DisplayName": (APP_NAME, winreg.REG_SZ),
        "DisplayVersion": (version, winreg.REG_SZ),
        "Publisher": (APP_NAME, winreg.REG_SZ),
        "DisplayIcon": (str(exe), winreg.REG_SZ),
        "InstallLocation": (str(install_dir), winreg.REG_SZ),
        "UninstallString": (f'"{exe}" uninstall', winreg.REG_SZ),
        "QuietUninstallString": (f'"{exe}" uninstall --quiet', winreg.REG_SZ),
        "EstimatedSize": (size_kb, winreg.REG_DWORD),
        "NoModify": (1, winreg.REG_DWORD),
        "NoRepair": (1, winreg.REG_DWORD),
    }
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _UNINSTALL_KEY) as key:
        for name, (value, kind) in values.items():
            winreg.SetValueEx(key, name, 0, kind, value)
    if autostart.enabled():  # keep the user's choice, but point it at the installed exe
        autostart.set_enabled(True, target=exe)


def unregister() -> None:
    for path in shortcut.locations():
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
    shortcut.remove_legacy()
    with contextlib.suppress(OSError):
        autostart.set_enabled(False)
    with contextlib.suppress(OSError):
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, _UNINSTALL_KEY)


def remove_dir_after_exit(path: Path) -> None:
    """Wait for this process, then remove the verified installation using a literal path."""
    path = validate_install_dir(path)
    if Path(sys.executable).resolve().parent != path:
        raise ValueError("Refusing to remove a directory other than the running installation")
    script = (
        "Wait-Process -Id $env:SAYRIFT_UNINSTALL_PID -ErrorAction SilentlyContinue; "
        "Start-Sleep -Seconds 1; "
        "Remove-Item -LiteralPath $env:SAYRIFT_UNINSTALL_DIR -Recurse -Force"
    )
    subprocess.Popen(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        env={**os.environ, "SAYRIFT_UNINSTALL_DIR": str(path), "SAYRIFT_UNINSTALL_PID": str(os.getpid())},
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
        close_fds=True,
    )
