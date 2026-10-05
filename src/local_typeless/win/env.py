"""User environment variables as currently stored, not as inherited at process start."""

from __future__ import annotations

import winreg


def user_env(name: str) -> str | None:
    r"""HKCU\Environment: a variable set after we started (e.g. while onboarding) is visible here at once,
    while os.environ keeps the snapshot from launch."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _type = winreg.QueryValueEx(key, name)
    except OSError:
        return None
    return str(value).strip() or None
