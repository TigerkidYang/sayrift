"""Who has the keyboard focus: foreground window, owning process, focused control, elevation."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes as w
from dataclasses import dataclass
from functools import cache

from . import _api as api


@dataclass(frozen=True, slots=True)
class WindowInfo:
    hwnd: int
    pid: int
    exe: str  # basename, e.g. "Weixin.exe"; "" if the process could not be queried
    title: str
    class_name: str
    focus_hwnd: int  # focused control inside the window (0 if unknown)
    focus_class: str
    elevated: bool | None  # None when we are not allowed to ask

    @property
    def exe_lower(self) -> str:
        return self.exe.lower()


def _window_text(hwnd: int) -> str:
    n = api.user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    api.user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _class_name(hwnd: int) -> str:
    if not hwnd:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    api.user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _process_exe(pid: int) -> str:
    h = api.kernel32.OpenProcess(api.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        size = w.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if api.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
        return ""
    finally:
        api.kernel32.CloseHandle(h)


def _token_elevated(process_handle: int) -> bool | None:
    token = w.HANDLE()
    if not api.advapi32.OpenProcessToken(process_handle, api.TOKEN_QUERY, ctypes.byref(token)):
        return None
    try:
        elevation = api.TOKEN_ELEVATION()
        size = w.DWORD()
        ok = api.advapi32.GetTokenInformation(
            token, api.TokenElevation, ctypes.byref(elevation), ctypes.sizeof(elevation), ctypes.byref(size)
        )
        return bool(elevation.TokenIsElevated) if ok else None
    finally:
        api.kernel32.CloseHandle(token)


def process_elevated(pid: int) -> bool | None:
    h = api.kernel32.OpenProcess(api.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        # A non-elevated process cannot open most elevated ones for token queries; treat
        # "access denied" as a strong hint rather than a fact.
        return None
    try:
        return _token_elevated(h)
    finally:
        api.kernel32.CloseHandle(h)


@cache
def we_are_elevated() -> bool:
    return bool(_token_elevated(api.kernel32.GetCurrentProcess()))


def foreground() -> WindowInfo:
    hwnd = api.user32.GetForegroundWindow() or 0
    pid = w.DWORD()
    thread_id = api.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)) if hwnd else 0
    focus = 0
    if thread_id:
        info = api.GUITHREADINFO(cbSize=ctypes.sizeof(api.GUITHREADINFO))
        if api.user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
            focus = info.hwndFocus or 0
    return WindowInfo(
        hwnd=hwnd,
        pid=pid.value,
        exe=_process_exe(pid.value) if pid.value else "",
        title=_window_text(hwnd) if hwnd else "",
        class_name=_class_name(hwnd),
        focus_hwnd=focus,
        focus_class=_class_name(focus),
        elevated=process_elevated(pid.value) if pid.value else None,
    )


def allow_any_foreground() -> None:
    """Let another process (the running instance) take the foreground: only the process the user just
    launched holds that right, so the second instance hands it over before asking the first to show itself."""
    ASFW_ANY = 0xFFFFFFFF
    ctypes.windll.user32.AllowSetForegroundWindow(ASFW_ANY)
