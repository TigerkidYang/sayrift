"""Render the main window with sample data and save a screenshot of every page (both themes).

Uses a throw-away config and history, so the user's real settings are never touched.

Usage: uv run python tools/ui_preview.py [--out DIR] [--lang zh|en]
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import tempfile
import time
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="lt-preview-"))
os.environ["LOCAL_TYPELESS_CONFIG"] = str(TMP / "config.toml")  # must be set before config is used
os.environ["SAYRIFT_CONFIG"] = str(TMP / "config.toml")

from PySide6.QtCore import QPoint, QRectF  # noqa: E402
from PySide6.QtGui import QFontDatabase, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication, QScrollArea, QWidget  # noqa: E402

from local_typeless import config  # noqa: E402
from local_typeless.store import Entry, History, Usage  # noqa: E402
from local_typeless.ui.glass import paint_aurora  # noqa: E402
from local_typeless.ui.main_window import MainWindow  # noqa: E402
from local_typeless.ui.onboarding import Onboarding  # noqa: E402
from local_typeless.ui.pages import Context  # noqa: E402

SAMPLES = [
    ("dictate", "insert", "inserted", "Weixin.exe", "好的，没问题，那我们就周五见吧",
     "好的没问题那我们就周五见吧"),
    ("dictate", "insert", "inserted", "Code.exe", "帮我在 Claude Code 里面跑一下 uv sync，然后用 pytest 测一下 client。",
     "帮我在cloud code里面跑一下uv sync然后用ptest测一下client"),
    ("translate", "insert", "inserted", "OUTLOOK.EXE",
     "We'll have our meeting tomorrow at 4 PM in the third-floor conference room.", "我们明天下午四点在三楼会议室开会"),
    ("ask", "answer", "shown", "chrome.exe", "法国的首都是**巴黎**。", "法国的首都是哪里"),
    ("dictate", "insert", "inserted", "Notion.exe", "这周要做三件事：\n1. 把录音模块写完\n2. 接上 OpenRouter 的接口\n3. 写一个设置界面",
     "这周要做三件事第一把录音模块写完第二接上open router的接口第三写一个设置界面"),
    ("dictate", "insert", "failed", "WINWORD.EXE", "", ""),
]  # fmt: skip


def fill(history: History) -> None:
    now = time.time()
    rnd = random.Random(7)
    for day in range(120, 0, -1):
        if rnd.random() < 0.55:
            for _ in range(rnd.randint(1, 6)):
                t = now - day * 86400 + rnd.randint(0, 36000)
                history.add(Entry("dictate", "insert", "inserted", app="Weixin.exe",
                                  text="示例" * rnd.randint(5, 60), duration_s=rnd.uniform(4, 40), created_at=t))  # fmt: skip
                mode = rnd.choice(["dictate"] * 6 + ["translate", "ask"])
                history.log_usage(Usage(mode, "asr", "openai/gpt-transcribe", cost_usd=rnd.uniform(0.0003, 0.003),
                                        audio_s=rnd.uniform(4, 40), created_at=t))  # fmt: skip
                history.log_usage(Usage(mode, "llm", rnd.choice(["deepseek/deepseek-v4.1-flash"] * 5 + ["qwen/qwen3.8-flash"]),
                                        "DeepInfra", cost_usd=rnd.uniform(0.00005, 0.0004), created_at=t))  # fmt: skip
    for i, (mode, action, status, app, text, raw) in enumerate(SAMPLES):
        e = Entry(mode, action, status, app=app, text=text, raw=raw, duration_s=8, created_at=now - i * 1500)
        if status == "failed":
            e.error = "网络错误——请检查网络或代理"
            e.audio, e.audio_format = b"x", "ogg"
        history.add(e)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=TMP / "shots")
    ap.add_argument("--lang", default="zh")
    ap.add_argument("--pages-only", action="store_true", help="skip onboarding and its microphone checks")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    cfg = config.Config()
    cfg.dictionary = ["Claude Code", "OpenRouter", "Typeless", "pytest", "张伟", "DeepSeek", "Right Alt", "uv sync"]
    cfg.translate.targets = ["English", "Japanese"]
    cfg.app.language = args.lang
    history = History(TMP / "history.sqlite")
    fill(history)

    app = QApplication(sys.argv)
    if os.name == "nt" and os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        # The headless Qt plugin does not enumerate Windows system fonts.
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for filename in ("segoeui.ttf", "segoeuib.ttf", "msyh.ttc"):
            QFontDatabase.addApplicationFont(str(fonts / filename))

    def make_context(palette):
        return Context(cfg=cfg, palette=palette, history=history, retry=lambda _id: None,
                       capture_key=lambda _cb: None, cancel_capture=lambda: None, applied=lambda: None)  # fmt: skip

    win = MainWindow(make_context)
    win.show()
    for theme in ("dark", "light"):
        cfg.app.theme = theme
        win.rebuild()
        for page in ("home", "history", "dictionary", "spend", "settings"):
            win.show_page(page)
            for _ in range(20):
                app.processEvents()
                time.sleep(0.01)
            win.grab().save(str(args.out / f"{theme}_{page}.png"))
            area = win.pages[page].findChild(QScrollArea)
            if area is not None:  # the whole scrollable page over the aurora, not just what fits in the window
                content = area.widget()
                full = QPixmap(content.size())
                painter = QPainter(full)
                paint_aurora(painter, QRectF(full.rect()), win.palette_, 0.0)
                content.render(painter, QPoint(0, 0), renderFlags=QWidget.RenderFlag.DrawChildren)
                painter.end()
                full.save(str(args.out / f"{theme}_{page}_full.png"))
        if args.pages_only:
            continue
        guide = Onboarding(win.ctx, on_done=lambda: None)
        guide.show()
        for step in range(5):
            guide.go(step)
            for _ in range(20):
                app.processEvents()
                time.sleep(0.01)
            guide.grab().save(str(args.out / f"{theme}_guide{step + 1}.png"))
        guide.meter.stop()
        guide.hide()
    print(args.out)
    win.quitting = True
    win.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
