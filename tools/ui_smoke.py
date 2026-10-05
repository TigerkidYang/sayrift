"""UI smoke test: Voice bar states and cards render, and none of them steals the keyboard focus.

Opens the e2e Tk window as the focused app, shows each UI state, checks GetForegroundWindow()
is unchanged after every step, and saves screenshots for eyeballing.

Usage: uv run python tools/ui_smoke.py [--out DIR]
"""

from __future__ import annotations

import argparse
import ctypes
import random
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).parent))
from e2e_dictation import Target, focus

from local_typeless.ui.cards import Card
from local_typeless.ui.overlay import VoiceBar
from local_typeless.win import _api as api

user32 = ctypes.WinDLL("user32")
POINT = wintypes.POINT
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004


def pump(app: QApplication, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def grab(app: QApplication, widget, path: Path) -> None:
    screen = app.primaryScreen()
    g = widget.frameGeometry()
    screen.grabWindow(0, g.x() - 12, g.y() - 12, g.width() + 24, g.height() + 24).save(str(path))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path(tempfile.mkdtemp(prefix="lt-ui-")))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    sys.stdout.reconfigure(encoding="utf-8")

    target = Target()
    app = QApplication(sys.argv)
    failures = []
    try:
        if not target.hwnd or not focus(target.hwnd):
            print("FAIL: could not focus the target window")
            return 1

        def still_focused(step: str) -> None:
            fg = api.user32.GetForegroundWindow()
            ok = fg == target.hwnd
            print(f"{step:28} focus kept: {ok}")
            if not ok:
                failures.append(step)

        bar = VoiceBar()
        levels = QTimer(interval=50, timeout=lambda: bar.push_level(random.uniform(200, 4000)))
        levels.start()
        bar.listening("dictate", 540)
        pump(app, 1.0)
        still_focused("listening")
        grab(app, bar, args.out / "1_listening.png")

        bar.listening("translate:English", 540)
        pump(app, 0.6)
        still_focused("listening (translate)")
        grab(app, bar, args.out / "2_translate.png")

        bar.listening("dictate", 50)  # inside the last minute: countdown
        pump(app, 0.6)
        grab(app, bar, args.out / "3_countdown.png")

        # A real mouse click on ✓ must fire the button without activating the Voice bar.
        clicks: list[str] = []
        bar.finish_clicked.connect(lambda: clicks.append("finish"))
        center = bar.mapToGlobal(bar._finish_rect().center().toPoint())
        ratio = bar.devicePixelRatioF()  # Qt works in logical pixels, SetCursorPos in physical ones
        saved = POINT()
        user32.GetCursorPos(ctypes.byref(saved))
        user32.SetCursorPos(int(center.x() * ratio), int(center.y() * ratio))
        pump(app, 0.2)
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        pump(app, 0.3)
        user32.SetCursorPos(saved.x, saved.y)
        print(f"{'click ✓ on the Voice bar':28} signal fired: {clicks == ['finish']}")
        if clicks != ["finish"]:
            failures.append("click ✓ (no signal)")
        still_focused("after clicking ✓")

        levels.stop()
        bar.processing()
        pump(app, 0.6)
        still_focused("processing")
        grab(app, bar, args.out / "4_processing.png")

        bar.error("err.mic")
        pump(app, 0.5)
        still_focused("error")
        grab(app, bar, args.out / "5_error.png")

        answer = "法国的首都是**巴黎**（Paris）。\n\n- 人口约 210 万\n- 位于塞纳河畔，代码示例：`print('bonjour')`"
        card = Card("Ask anything", "法国的首都是哪里？", answer, markdown=True)
        card.show_near_bottom()
        pump(app, 0.8)
        still_focused("answer card")
        grab(app, card, args.out / "6_card.png")
        card.close()
    finally:
        target.proc.terminate()

    print("screenshots:", args.out)
    print("PASS" if not failures else f"FAIL: focus stolen at {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
