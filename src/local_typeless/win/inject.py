"""Insert text into the focused control of another app via the clipboard (docs/architecture.md §5.3).

Lessons from similar projects (docs/references.md §3.2) that shape this module:
- Send the whole Ctrl+V as ONE SendInput call so no other input can interleave. Separate
  calls are the likely cause of the "only a 'v' appears with a Chinese IME" bug.
- Wait until the user has physically released the hotkey's modifiers; release any that are
  still down inside the same SendInput batch, or the app sees Ctrl+Alt+V.
- UIPI silently drops injected input into elevated windows (SendInput still reports
  success), so check elevation up front.
- Terminals want Ctrl+Shift+V; classic consoles take their own Paste system command.
- Restore the user's clipboard only if it is still ours, and after rapid back-to-back
  dictations restore the *original* content, not the previous dictation.
"""

from __future__ import annotations

import ctypes
import logging
import threading
import time
from dataclasses import dataclass

from ..keys import VK_LCONTROL, VK_LSHIFT
from . import _api as api
from . import clipboard
from .foreground import WindowInfo, we_are_elevated

log = logging.getLogger(__name__)

TERMINAL_EXES = frozenset({
    "windowsterminal.exe", "wt.exe", "mintty.exe", "alacritty.exe", "wezterm-gui.exe",
    "kitty.exe", "tabby.exe", "hyper.exe", "warp.exe", "conemu64.exe", "conemu.exe",
})  # fmt: skip
_CONSOLE_CLASS = "ConsoleWindowClass"
_CONSOLE_PASTE_COMMAND = 0xFFF1  # the console's own Edit > Paste
_EDIT_CLASSES = frozenset({"Edit"})  # classic Win32 edit controls accept WM_PASTE directly


@dataclass(frozen=True, slots=True)
class PasteResult:
    ok: bool
    method: str
    detail: str = ""


def _key(vk: int, up: bool = False) -> api.INPUT:
    flags = api.KEYEVENTF_KEYUP if up else 0
    if vk in api.EXTENDED_VKS:
        flags |= api.KEYEVENTF_EXTENDEDKEY
    scan = api.user32.MapVirtualKeyW(vk, api.MAPVK_VK_TO_VSC)
    return api.INPUT(
        type=api.INPUT_KEYBOARD,
        ki=api.KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=api.INJECT_TAG),
    )


def send(events: list[api.INPUT]) -> bool:
    arr = (api.INPUT * len(events))(*events)
    sent = api.user32.SendInput(len(events), arr, ctypes.sizeof(api.INPUT))
    return sent == len(events)


def held_modifiers() -> list[int]:
    return [vk for vk in api.MODIFIER_VKS if api.key_is_down(vk)]


def wait_modifiers_released(timeout_s: float = 0.5) -> list[int]:
    """Poll until no modifier is physically down; return those still down at the timeout."""
    deadline = time.monotonic() + timeout_s
    held = held_modifiers()
    while held and time.monotonic() < deadline:
        time.sleep(0.01)
        held = held_modifiers()
    return held


def send_chord(*vks: int, release_first: list[int] | None = None) -> bool:
    events = [_key(vk, up=True) for vk in (release_first or [])]
    events += [_key(vk) for vk in vks] + [_key(vk, up=True) for vk in reversed(vks)]
    return send(events)


def press(vk: int) -> bool:
    """Key-down only (used to hand a swallowed hotkey back to the system)."""
    return send([_key(vk)])


def paste_method(target: WindowInfo) -> str:
    if target.class_name == _CONSOLE_CLASS:
        return "console-command"
    if target.exe_lower in TERMINAL_EXES:
        return "ctrl+shift+v"
    if target.focus_class in _EDIT_CLASSES and target.focus_hwnd:
        return "wm_paste"
    return "ctrl+v"


class Paster:
    """Owns the clipboard round-trip; one instance per app."""

    def __init__(self, *, restore_delay_s: float = 0.8, modifier_timeout_s: float = 0.5) -> None:
        self.restore_delay_s = restore_delay_s
        self.modifier_timeout_s = modifier_timeout_s
        self._lock = threading.Lock()
        self._pending: tuple[clipboard.Snapshot, int, threading.Timer] | None = None

    def paste(self, text: str, target: WindowInfo) -> PasteResult:
        if not text:
            return PasteResult(True, "none", "empty text")
        if target.elevated and not we_are_elevated():
            clipboard.set_text(text)
            return PasteResult(False, "clipboard", "target runs as administrator; text left on the clipboard")

        original = self._take_original()
        seq = clipboard.set_text(text)
        still_held = wait_modifiers_released(self.modifier_timeout_s)

        if api.user32.GetForegroundWindow() != target.hwnd:
            api.user32.SetForegroundWindow(target.hwnd)
            time.sleep(0.05)
            if api.user32.GetForegroundWindow() != target.hwnd:
                # Keep the dictation on the clipboard: it is what the user needs right now.
                return PasteResult(False, "clipboard", "focus moved to another window; text left on the clipboard")

        method = paste_method(target)
        if method == "console-command":
            ok = bool(api.user32.PostMessageW(target.hwnd, api.WM_SYSCOMMAND, _CONSOLE_PASTE_COMMAND, 0))
        elif method == "wm_paste":
            api.user32.SendMessageW(target.focus_hwnd, api.WM_PASTE, 0, 0)
            ok = True
        elif method == "ctrl+shift+v":
            ok = send_chord(VK_LCONTROL, VK_LSHIFT, api.VK_V, release_first=still_held)
        else:
            ok = send_chord(VK_LCONTROL, api.VK_V, release_first=still_held)

        self._schedule_restore(original, seq)
        return PasteResult(ok, method, "" if ok else "SendInput was rejected")

    # --- clipboard restore -----------------------------------------------------------------------

    def _take_original(self) -> clipboard.Snapshot:
        with self._lock:
            pending, self._pending = self._pending, None
        if pending:  # a previous dictation has not been restored yet: its snapshot is the original
            pending[2].cancel()
            return pending[0]
        try:
            return clipboard.backup()
        except OSError:
            log.warning("could not back up the clipboard; it will not be restored", exc_info=True)
            return clipboard.Snapshot()

    def _schedule_restore(self, original: clipboard.Snapshot, seq: int) -> None:
        timer = threading.Timer(self.restore_delay_s, self._restore, args=(original, seq))
        timer.daemon = True
        with self._lock:
            self._pending = (original, seq, timer)
        timer.start()

    def _restore(self, original: clipboard.Snapshot, seq: int) -> None:
        with self._lock:
            if not self._pending or self._pending[1] != seq:
                return
            self._pending = None
        if clipboard.sequence() != seq:
            log.debug("clipboard changed since the paste; not restoring")
            return
        if original.empty:
            return
        try:
            clipboard.restore(original)
        except OSError:
            log.warning("clipboard restore failed", exc_info=True)

    def flush(self) -> None:
        """Restore now if a restore is pending (used on shutdown and in tests)."""
        with self._lock:
            pending = self._pending
        if pending:
            pending[2].cancel()
            self._restore(pending[0], pending[1])
