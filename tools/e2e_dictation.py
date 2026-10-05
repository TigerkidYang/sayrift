"""End-to-end check on the real desktop: hotkey -> recording -> OpenRouter -> paste.

What it does:
1. Opens a small Tk window as the paste target and gives it the keyboard focus.
2. Starts the real app (keyboard hook, controller, pipeline, clipboard paste) with audio files
   standing in for the microphone and synthetic key presses accepted.
3. Rounds (Typeless key behaviour):
   - tap Right Alt / tap again           -> cleaned dictation inserted, clipboard restored
   - hold Right Alt / release            -> push-to-talk dictation inserted
   - tap Right Alt / Esc                 -> cancelled, nothing inserted
   - --translate: Right Alt+Right Shift  -> English inserted
   - --ask: text selected + Right Alt+Space "make it more formal" -> selection replaced
            nothing selected + "what is the capital of France"  -> answer card opens

It takes over the keyboard focus for a few seconds and makes billable API calls.
The user's clipboard is backed up first and put back at the end.

Usage: uv run python tools/e2e_dictation.py [--translate] [--ask]
"""

from __future__ import annotations

import argparse
import ctypes
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from local_typeless import config
from local_typeless.app import App
from local_typeless.audio import FileAudio
from local_typeless.keys import VK_ESCAPE, VK_LMENU, VK_RMENU, VK_RSHIFT, VK_SPACE
from local_typeless.win import _api as api
from local_typeless.win import clipboard

AUDIO = Path("evals/asr/audio")
TITLE = "sayrift e2e target"
CARD_TITLE = "Ask anything"
# The target dumps its text to <out> every 100 ms and obeys "prefill:<text>" commands written to
# <out>.cmd (replace the content and select all of it, like a user selecting text before Ask).
TK_TARGET = r"""
import os, sys, tkinter as tk
out = sys.argv[1]; cmd = out + ".cmd"
root = tk.Tk(); root.title(__TITLE__); root.geometry("520x220+200+200"); root.attributes("-topmost", True)
text = tk.Text(root, font=("Microsoft YaHei UI", 12)); text.pack(fill="both", expand=True); text.focus_set()
def tick():
    if os.path.exists(cmd):
        c = open(cmd, encoding="utf-8").read(); os.remove(cmd)
        if c.startswith("prefill:"):
            text.delete("1.0", "end"); text.insert("1.0", c[8:]); text.tag_add("sel", "1.0", "end-1c")
            text.mark_set("insert", "end-1c"); text.focus_force()
    with open(out, "w", encoding="utf-8") as f:
        f.write(text.get("1.0", "end-1c"))
    root.after(100, tick)
root.after(100, tick); root.after(300, text.focus_force)  # focus the Text widget, not the toplevel
root.mainloop()
""".replace("__TITLE__", repr(TITLE))


def key(vk: int, up: bool = False) -> api.INPUT:
    """Synthetic key WITHOUT our inject tag, so the app's hook treats it like a user key press."""
    flags = (api.KEYEVENTF_KEYUP if up else 0) | (api.KEYEVENTF_EXTENDEDKEY if vk in api.EXTENDED_VKS else 0)
    return api.INPUT(type=api.INPUT_KEYBOARD, ki=api.KEYBDINPUT(wVk=vk, dwFlags=flags))


def send(*events: api.INPUT) -> None:
    arr = (api.INPUT * len(events))(*events)
    api.user32.SendInput(len(events), arr, ctypes.sizeof(api.INPUT))


def tap(vk: int) -> None:
    send(key(vk))
    time.sleep(0.08)
    send(key(vk, up=True))


def focus(hwnd: int) -> bool:
    for _ in range(20):
        # An Alt press from us unlocks SetForegroundWindow. A *lone* Alt tap would put the window
        # into menu mode and eat the next key (our Ctrl+V), so mask it with the unassigned VK 0xE8.
        send(key(VK_LMENU), key(0xE8), key(0xE8, up=True), key(VK_LMENU, up=True))
        api.user32.SetForegroundWindow(hwnd)
        time.sleep(0.1)
        if api.user32.GetForegroundWindow() == hwnd:
            return True
    return False


def wait_for(predicate, timeout: float, step: float = 0.1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(step)
    return None


class Target:
    def __init__(self) -> None:
        self.out = Path(tempfile.mkdtemp()) / "target.txt"
        self.out.write_text("", encoding="utf-8")
        self.proc = subprocess.Popen([sys.executable, "-c", TK_TARGET, str(self.out)])
        self.hwnd = wait_for(lambda: api.user32.FindWindowW(None, TITLE), timeout=10) or 0

    def text(self) -> str:
        return self.out.read_text(encoding="utf-8")

    def prefill_selected(self, content: str) -> None:
        Path(str(self.out) + ".cmd").write_text("prefill:" + content, encoding="utf-8")
        wait_for(lambda: self.text() == content, timeout=3)


def session(app: App | None, target: Target, sample: str, *, style: str, chord: int | None = None, timeout=15) -> str:
    """Run one hotkey session with `sample` as the microphone; return what changed in the target.

    `app` is None when the real GUI app runs in a subprocess (its fake microphone is fixed)."""
    if app is not None:
        app.audio.path = AUDIO / f"{sample}.ogg"
    before = target.text()
    if style == "hold":  # push-to-talk: hold the main key while speaking, release to finish
        send(key(VK_RMENU))
        time.sleep(1.2)
        send(key(VK_RMENU, up=True))
    else:
        if chord:  # Right Alt + chord key tapped together -> hands-free session in that mode
            send(key(VK_RMENU))
            time.sleep(0.05)
            tap(chord)
            send(key(VK_RMENU, up=True))
        else:
            tap(VK_RMENU)
        time.sleep(1.2)  # "speaking"
        tap(VK_ESCAPE if style == "cancel" else VK_RMENU)
    got = wait_for(lambda: target.text() != before, timeout=timeout)
    time.sleep(0.3)  # let the Tk dump catch up completely
    now = target.text()
    if not got:
        return ""
    return now[len(before) :] if now.startswith(before) else now


def looks_like_sample(text: str) -> bool:
    return "4点" in text and "会议室" in text and "嗯" not in text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--translate", action="store_true")
    ap.add_argument("--ask", action="store_true")
    ap.add_argument("--gui", action="store_true", help="run the real `sayrift run` (tray + Voice bar) in a subprocess")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if args.gui and args.ask:
        print("--ask needs per-round audio and cannot run with --gui; skipping the Ask rounds")
        args.ask = False

    required = ["zh_disfluent"] + (["zh_ask_formal", "zh_ask_question"] if args.ask else [])
    if any(not (AUDIO / f"{name}.ogg").is_file() for name in required):
        ap.error("Supply your own evaluation recordings first; see evals/README.md. No desktop interaction started.")

    user_clipboard = clipboard.backup()
    sentinel = "E2E original clipboard 原来的剪贴板"
    target = Target()
    gui_proc = None
    if args.gui:
        app = None
        cmd = [sys.executable, "-m", "local_typeless", "--minimized", "run", "--accept-injected"]
        # A copy of the user's config in a temp dir: test sessions land in a throw-away history, not theirs.
        sandbox = Path(tempfile.mkdtemp(prefix="lt-e2e-"))
        if config.config_path().exists():
            shutil.copyfile(config.config_path(), sandbox / "config.toml")
        env = {
            **os.environ,
            "LOCAL_TYPELESS_CONFIG": str(sandbox / "config.toml"),
            "SAYRIFT_CONFIG": str(sandbox / "config.toml"),
        }
        gui_proc = subprocess.Popen([*cmd, "--fake-audio", str(AUDIO / "zh_disfluent.ogg")], env=env)
        runner = None
    else:
        app = App(config.load(), audio=FileAudio(AUDIO / "zh_disfluent.ogg"), accept_injected=True)
        runner = threading.Thread(target=app.run, daemon=True)
    failures: list[str] = []

    def check(ok: bool, message: str) -> None:
        if not ok:
            failures.append(message)

    try:
        if not target.hwnd or not focus(target.hwnd):
            print("FAIL: could not bring the target window to the foreground")
            return 1
        clipboard.set_text(sentinel)
        if runner:
            runner.start()
        time.sleep(4.0 if gui_proc else 0.5)  # hook installed (the GUI app also has to import Qt)
        focus(target.hwnd)

        text = session(app, target, "zh_disfluent", style="tap")
        print(f"tap / tap:        {text!r}")
        check(looks_like_sample(text), f"tap-to-start dictation gave {text!r}")
        restored = wait_for(lambda: clipboard.get_text() == sentinel, timeout=3)
        print(f"clipboard restored: {bool(restored)}")
        check(bool(restored), f"clipboard not restored (now {clipboard.get_text()!r})")

        text = session(app, target, "zh_disfluent", style="hold")
        print(f"hold / release:   {text!r}")
        check(looks_like_sample(text), f"push-to-talk dictation gave {text!r}")

        text = session(app, target, "zh_disfluent", style="cancel", timeout=4)
        print(f"tap / Esc:        {text!r}")
        check(not text, f"Esc should cancel, but {text!r} was inserted")

        if args.translate:
            text = session(app, target, "zh_disfluent", style="tap", chord=VK_RSHIFT)
            print(f"translate:        {text!r}")
            check(bool(text) and not any("一" <= ch <= "鿿" for ch in text), f"translation gave {text!r}")

        if args.ask:
            original = "明天我不来了，身体不太舒服，有事微信找我"
            target.prefill_selected(original)
            text = session(app, target, "zh_ask_formal", style="tap", chord=VK_SPACE)
            print(f"ask (selection):  {text!r}")
            check(bool(text) and text != original and "不来了" not in text, f"selection not rewritten: {text!r}")

            target.prefill_selected("")  # nothing selected
            session(app, target, "zh_ask_question", style="tap", chord=VK_SPACE, timeout=0.5)
            card = wait_for(lambda: api.user32.FindWindowW(None, CARD_TITLE), timeout=15)
            print(f"ask (question):   answer card {'opened' if card else 'did NOT open'}; document {target.text()!r}")
            check(bool(card), "answer card did not open")
            check(target.text() == "", f"a question must not change the document, got {target.text()!r}")
            if card:
                api.user32.PostMessageW(card, 0x0010, 0, 0)  # WM_CLOSE
    finally:
        if app:
            app.stop()
        if runner:
            runner.join(3)
        if gui_proc:
            gui_proc.terminate()
        target.proc.terminate()
        if not user_clipboard.empty:
            clipboard.restore(user_clipboard)

    for f in failures:
        print("FAIL:", f)
    print("PASS" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
