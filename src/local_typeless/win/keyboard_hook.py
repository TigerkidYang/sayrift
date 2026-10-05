"""Global low-level keyboard hook (WH_KEYBOARD_LL) on a dedicated thread.

Why a low-level hook instead of RegisterHotKey: we need key-*up* events (push-to-talk),
modifier-only hotkeys (Right Alt alone) and the ability to swallow keys.

Rules the callback lives by (see docs/architecture.md §5.1):
- Return within microseconds. Windows silently removes a hook whose callback exceeds
  LowLevelHooksTimeout, so we also re-install the hook periodically while idle.
- Ignore input we injected ourselves (tagged with INJECT_TAG); optionally ignore all
  injected input (default) so other automation tools cannot trigger dictation.
"""

from __future__ import annotations

import ctypes
import logging
import threading
from collections.abc import Callable
from ctypes import wintypes as w
from dataclasses import dataclass

from . import _api as api

log = logging.getLogger(__name__)

_WM_REINSTALL = api.WM_APP + 1
_REINSTALL_EVERY_MS = 60_000


@dataclass(frozen=True, slots=True)
class KeyEvent:
    vk: int
    down: bool
    injected: bool
    time_ms: int


class KeyboardHook:
    def __init__(
        self,
        handler: Callable[[KeyEvent], bool],
        *,
        accept_injected: bool = False,
        can_reinstall: Callable[[], bool] = lambda: True,
    ) -> None:
        """`handler` returns True to swallow the event. `can_reinstall` gates the periodic
        re-install (only do it while no hotkey is held)."""
        self._handler = handler
        self._accept_injected = accept_injected
        self._can_reinstall = can_reinstall
        self._proc = api.HOOKPROC(self._callback)  # keep a reference: ctypes must not free it
        self._hook = None
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._error: str | None = None
        self._last_event: tuple[int, int, int] | None = None

    # --- lifecycle -----------------------------------------------------------------------------

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="keyboard-hook", daemon=True)
        self._thread.start()
        self._ready.wait(5)
        if self._error:
            raise OSError(self._error)

    def stop(self) -> None:
        if self._thread and self._thread.is_alive():
            api.user32.PostThreadMessageW(self._thread_id, api.WM_QUIT, 0, 0)
            self._thread.join(2)

    def request_reinstall(self) -> None:
        """Ask the hook thread to re-install (e.g. after resume from sleep)."""
        if self._thread_id:
            api.user32.PostThreadMessageW(self._thread_id, _WM_REINSTALL, 0, 0)

    # --- hook thread ---------------------------------------------------------------------------

    def _install(self) -> None:
        new = api.user32.SetWindowsHookExW(api.WH_KEYBOARD_LL, self._proc, api.kernel32.GetModuleHandleW(None), 0)
        if not new:
            raise OSError(f"SetWindowsHookExW failed: {ctypes.get_last_error()}")
        old, self._hook = self._hook, new
        if old:
            api.user32.UnhookWindowsHookEx(old)

    def _run(self) -> None:
        self._thread_id = api.kernel32.GetCurrentThreadId()
        try:
            self._install()
        except OSError as e:
            self._error = str(e)
            self._ready.set()
            return
        timer = api.user32.SetTimer(None, 0, _REINSTALL_EVERY_MS, None)
        self._ready.set()
        msg = w.MSG()
        while api.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == _WM_REINSTALL or (msg.message == api.WM_TIMER and self._can_reinstall()):
                try:
                    self._install()
                    log.debug("keyboard hook re-installed")
                except OSError:
                    log.exception("keyboard hook re-install failed")
                continue
            api.user32.TranslateMessage(ctypes.byref(msg))
            api.user32.DispatchMessageW(ctypes.byref(msg))
        api.user32.KillTimer(None, timer)
        if self._hook:
            api.user32.UnhookWindowsHookEx(self._hook)
            self._hook = None

    def _callback(self, n_code: int, w_param: int, l_param: int) -> int:
        if n_code == api.HC_ACTION:
            kb = api.KBDLLHOOKSTRUCT.from_address(l_param)
            injected = bool(kb.flags & api.LLKHF_INJECTED)
            ours = kb.dwExtraInfo == api.INJECT_TAG
            # During a periodic re-install two hooks exist for a moment; skip the duplicate.
            key = (kb.vkCode, w_param, kb.time)
            duplicate = key == self._last_event
            self._last_event = key
            if not ours and not duplicate and (self._accept_injected or not injected):
                down = w_param in (api.WM_KEYDOWN, api.WM_SYSKEYDOWN)
                try:
                    if self._handler(KeyEvent(kb.vkCode, down, injected, kb.time)):
                        return 1
                except Exception:  # never let an exception escape into Windows' input path
                    log.exception("hotkey handler failed")
        return api.user32.CallNextHookEx(None, n_code, w_param, l_param)
