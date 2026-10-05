"""Answer card for Ask anything (Typeless shows answers in a pop-up card with a Copy button).

Stand-in until the Qt UI (overlay / tray / cards) lands: a tiny Tk window run in a *separate
process*, so it cannot interfere with the hotkey thread or the controller loop.

    python -m local_typeless.card <payload.json>     # {"question": ..., "answer": ...}
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)


def show(question: str, answer: str) -> None:
    """Open the card without blocking the caller."""
    payload = Path(tempfile.mkdtemp(prefix="lt-card-")) / "card.json"
    payload.write_text(json.dumps({"question": question, "answer": answer}, ensure_ascii=False), encoding="utf-8")
    exe = sys.executable
    pythonw = Path(exe).with_name("pythonw.exe")  # no console window flashing up
    if pythonw.exists():
        exe = str(pythonw)
    try:
        subprocess.Popen([exe, "-m", "local_typeless.card", str(payload)], close_fds=True)
    except OSError:
        log.exception("could not open the answer card")


def _run(payload_path: str) -> None:
    import tkinter as tk

    data = json.loads(Path(payload_path).read_text(encoding="utf-8"))
    root = tk.Tk()
    root.title("Ask anything")
    root.attributes("-topmost", True)
    width, height = 520, 360
    x = root.winfo_screenwidth() // 2 - width // 2
    y = root.winfo_screenheight() - height - 120  # above the taskbar, like the Voice bar
    root.geometry(f"{width}x{height}+{x}+{y}")
    font = ("Microsoft YaHei UI", 11)

    tk.Label(root, text=data.get("question", ""), font=(font[0], 10), fg="#666", anchor="w", justify="left",
             wraplength=width - 24).pack(fill="x", padx=12, pady=(10, 4))  # fmt: skip
    text = tk.Text(root, font=font, wrap="word", relief="flat", padx=8, pady=6)
    text.insert("1.0", data.get("answer", ""))
    text.configure(state="disabled")  # read-only but still selectable
    text.pack(fill="both", expand=True, padx=12)

    buttons = tk.Frame(root)
    buttons.pack(fill="x", padx=12, pady=10)

    def copy() -> None:
        root.clipboard_clear()
        root.clipboard_append(data.get("answer", ""))
        copy_btn.configure(text="Copied ✓")

    copy_btn = tk.Button(buttons, text="Copy", width=10, command=copy)
    copy_btn.pack(side="right")
    tk.Button(buttons, text="Close", width=10, command=root.destroy).pack(side="right", padx=8)
    root.bind("<Escape>", lambda _e: root.destroy())
    root.after(100, root.focus_force)
    root.mainloop()
    Path(payload_path).unlink(missing_ok=True)


if __name__ == "__main__":
    _run(sys.argv[1])
