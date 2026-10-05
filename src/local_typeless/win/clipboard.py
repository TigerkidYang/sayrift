"""Clipboard backup / set / restore for paste-based insertion (docs/architecture.md §5.3).

- Opening the clipboard needs an owner window: with a NULL owner, SetClipboardData fails
  after EmptyClipboard. We use a throw-away STATIC window per operation (as pyperclip does),
  so no long-lived owner has to pump WM_DESTROYCLIPBOARD for other processes.
- OpenClipboard fails while another process (clipboard history, a manager) holds it: retry.
- Everything we put on the clipboard is flagged so it stays out of Win+V history and the
  cloud clipboard; that includes re-putting the user's own content on restore, which
  would otherwise show up in the history a second time.
"""

from __future__ import annotations

import ctypes
import logging
import struct
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from . import _api as api

log = logging.getLogger(__name__)

# Formats whose clipboard handle is not an HGLOBAL (GDI objects, metafiles, owner-display,
# private ranges): their bytes cannot be copied and restored safely, so they are skipped.
_NOT_HGLOBAL = {2, 3, 9, 14, 0x80, 0x82, 0x83, 0x8E}
_MAX_BACKUP_BYTES = 64 * 1024 * 1024
_MAX_BACKUP_SECONDS = 0.3  # delayed-render owners (e.g. Excel) can take long per format


def _skip(fmt: int) -> bool:
    return fmt in _NOT_HGLOBAL or 0x200 <= fmt <= 0x3FF


class ClipboardBusy(OSError):
    pass


@dataclass
class Snapshot:
    items: list[tuple[int, bytes]] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.items


def sequence() -> int:
    return api.user32.GetClipboardSequenceNumber()


@contextmanager
def _opened(retries: int = 25, delay: float = 0.02) -> Iterator[None]:
    hwnd = api.user32.CreateWindowExW(0, "STATIC", None, 0, 0, 0, 0, 0, None, None, None, None)
    try:
        for _ in range(retries):
            if api.user32.OpenClipboard(hwnd):
                break
            time.sleep(delay)
        else:
            raise ClipboardBusy(f"OpenClipboard failed (error {ctypes.get_last_error()})")
        try:
            yield
        finally:
            api.user32.CloseClipboard()
    finally:
        if hwnd:
            api.user32.DestroyWindow(hwnd)


def _read(fmt: int) -> bytes | None:
    h = api.user32.GetClipboardData(fmt)
    if not h:
        return None
    size = api.kernel32.GlobalSize(h)
    ptr = api.kernel32.GlobalLock(h)
    if not ptr:
        return None
    try:
        return ctypes.string_at(ptr, size)
    finally:
        api.kernel32.GlobalUnlock(h)


def _write(fmt: int, data: bytes) -> None:
    h = api.kernel32.GlobalAlloc(api.GMEM_MOVEABLE, max(len(data), 1))
    if not h:
        raise MemoryError("GlobalAlloc failed")
    ptr = api.kernel32.GlobalLock(h)
    ctypes.memmove(ptr, data, len(data))
    api.kernel32.GlobalUnlock(h)
    if not api.user32.SetClipboardData(fmt, h):  # on success the system owns h
        api.kernel32.GlobalFree(h)
        raise OSError(f"SetClipboardData({fmt}) failed (error {ctypes.get_last_error()})")


def _write_history_opt_out() -> None:
    zero = struct.pack("<I", 0)
    for name in (
        "ExcludeClipboardContentFromMonitorProcessing",
        "CanIncludeInClipboardHistory",
        "CanUploadToCloudClipboard",
    ):
        _write(api.user32.RegisterClipboardFormatW(name), zero)


def backup() -> Snapshot:
    """Copy every restorable format currently on the clipboard (text first)."""
    snap = Snapshot()
    deadline = time.monotonic() + _MAX_BACKUP_SECONDS
    total = 0
    with _opened():
        formats = []
        fmt = api.user32.EnumClipboardFormats(0)
        while fmt:
            formats.append(fmt)
            fmt = api.user32.EnumClipboardFormats(fmt)
        formats.sort(key=lambda f: f != api.CF_UNICODETEXT)
        for fmt in formats:
            if _skip(fmt):
                continue
            if time.monotonic() > deadline:
                log.info("clipboard backup truncated after %d formats (time limit)", len(snap.items))
                break
            data = _read(fmt)
            if data is None:
                continue
            total += len(data)
            if total > _MAX_BACKUP_BYTES:
                log.info("clipboard backup truncated (size limit)")
                break
            snap.items.append((fmt, data))
    return snap


def restore(snap: Snapshot) -> None:
    with _opened():
        api.user32.EmptyClipboard()
        for fmt, data in snap.items:
            try:
                _write(fmt, data)
            except OSError:
                log.debug("could not restore clipboard format %d", fmt, exc_info=True)
        if snap.items:
            _write_history_opt_out()


def set_text(text: str) -> int:
    """Put `text` on the clipboard (kept out of clipboard history); return the new sequence number."""
    with _opened():
        api.user32.EmptyClipboard()
        _write(api.CF_UNICODETEXT, (text + "\0").encode("utf-16-le"))
        _write_history_opt_out()
    return sequence()


def get_text() -> str | None:
    with _opened():
        data = _read(api.CF_UNICODETEXT)
    if data is None:
        return None
    return data.decode("utf-16-le", errors="replace").split("\0", 1)[0]
