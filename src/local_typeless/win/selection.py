"""Read the text currently selected in the focused app (Ask anything; docs/architecture.md §5.4).

Clipboard round-trip (the UI Automation path is a later improvement):
1. back up the clipboard and put a unique marker on it;
2. send Ctrl+Insert (copy that does not interrupt console programs, unlike Ctrl+C);
3. poll the clipboard sequence number for up to ~1.2 s;
4. restore the clipboard.

"No selection" is detected when nothing new lands on the clipboard, or when an editor that copies
the whole current line without a selection (VS Code, JetBrains, Notepad++, ...) hands back
exactly one line with its line break.
"""

from __future__ import annotations

import logging
import time
import uuid

from ..keys import VK_LCONTROL
from . import _api as api
from . import clipboard, inject
from .foreground import WindowInfo

log = logging.getLogger(__name__)

# Editors that copy the entire current line when nothing is selected.
LINE_COPY_EXES = frozenset({
    "code.exe", "cursor.exe", "windsurf.exe", "code - insiders.exe", "devenv.exe", "notepad++.exe",
    "sublime_text.exe", "idea64.exe", "pycharm64.exe", "webstorm64.exe", "clion64.exe", "goland64.exe",
    "rider64.exe", "phpstorm64.exe", "rubymine64.exe", "datagrip64.exe", "studio64.exe",
})  # fmt: skip


def looks_like_whole_line_copy(target: WindowInfo, text: str) -> bool:
    if target.exe_lower not in LINE_COPY_EXES:
        return False
    return text.endswith("\n") and text.count("\n") == 1


def capture(target: WindowInfo, *, timeout_s: float = 1.2) -> str | None:
    """Return the selected text, or None when nothing is selected (or it cannot be read)."""
    try:
        original = clipboard.backup()
    except OSError:
        log.warning("cannot read the selection: clipboard unavailable", exc_info=True)
        return None
    marker = f"local-typeless-selection-probe-{uuid.uuid4()}"
    text: str | None = None
    try:
        seq = clipboard.set_text(marker)
        held = inject.held_modifiers()
        inject.send_chord(VK_LCONTROL, api.VK_INSERT, release_first=held)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            time.sleep(0.02)
            if clipboard.sequence() != seq:
                time.sleep(0.03)  # let the owner finish rendering every format
                text = clipboard.get_text()
                break
    except OSError:
        log.warning("reading the selection failed", exc_info=True)
    finally:
        try:
            clipboard.restore(original)
        except OSError:
            log.warning("could not restore the clipboard after reading the selection", exc_info=True)
    if not text or text == marker or looks_like_whole_line_copy(target, text):
        return None
    return text
