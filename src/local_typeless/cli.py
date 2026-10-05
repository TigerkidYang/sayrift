"""Command-line entry point.

`sayrift` (or `sayrift run`) starts the dictation app. `file` and `polish` are
developer commands that exercise the pipeline without hotkeys or a microphone.
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import logging.handlers
import os
import sys
from pathlib import Path

from . import __version__, config, pipeline, prompts
from .openrouter import OpenRouterClient, OpenRouterError

AUDIO_FORMATS = {
    ".ogg": "ogg",
    ".opus": "ogg",
    ".mp3": "mp3",
    ".wav": "wav",
    ".flac": "flac",
    ".m4a": "m4a",
    ".webm": "webm",
}


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="sayrift", description="Sayrift voice dictation for Windows")
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    ap.add_argument("--minimized", action="store_true", help="start in the tray without opening the main window")
    sub = ap.add_subparsers(dest="cmd")

    r = sub.add_parser("run", help="start the dictation app (default)")
    r.add_argument("--no-ui", action="store_true", help="console only: no tray icon or Voice bar")
    r.add_argument("--fake-audio", type=Path, help="use this audio file instead of the microphone (testing)")
    r.add_argument("--accept-injected", action="store_true", help="react to synthetic key presses (testing)")

    f = sub.add_parser("file", help="dictate from an audio file (ASR + cleanup)")
    f.add_argument("path", type=Path)
    f.add_argument("--raw", action="store_true", help="skip the LLM cleanup stage")
    f.add_argument("--translate", action="store_true", help="Translate mode instead of dictation")

    p = sub.add_parser("polish", help="run only the cleanup stage on a transcript")
    p.add_argument("text")

    sub.add_parser("shortcuts", help="create Start menu and desktop shortcuts to the windowless app")
    u = sub.add_parser("uninstall", help="remove the installed app (used by Apps & features)")
    u.add_argument("--quiet", action="store_true", help="no questions; keep user data")

    a = sub.add_parser("ask", help="run Ask anything on a spoken instruction (as text)")
    a.add_argument("text", help="what the user said")
    a.add_argument("--selection", help="text that was selected in the app")

    for sp in (f, p, a):
        sp.add_argument("--app", help="pretend the text goes into this app, e.g. Weixin.exe")
        sp.add_argument("--title", help="pretend window title")
    return ap


def _setup_logging(verbose: bool, *, to_file: bool) -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO if to_file else logging.WARNING)
    if sys.stderr is not None:  # the windowless launcher (pythonw) has no console streams
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))
        root.addHandler(console)
    if to_file:
        log_dir = config.config_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            log_dir / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        fh.setFormatter(logging.Formatter("%(asctime)s %(threadName)s %(name)s %(levelname)s %(message)s"))
        root.addHandler(fh)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")  # pipes on Windows default to the ANSI code page
    if sys.stderr is None:  # windowless launcher: keep print(..., file=sys.stderr) harmless
        sys.stderr = sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    args = _build_parser().parse_args(argv)
    cmd = args.cmd or "run"
    _setup_logging(args.verbose, to_file=cmd == "run")
    if cmd == "uninstall":  # before loading the config: a broken config must not block removal
        from .ui.uninstall import run as uninstall

        return uninstall(quiet=args.quiet)

    try:
        cfg = config.load()
    except (ValueError, OSError) as e:
        print(f"error: bad config file {config.config_path()}: {e}", file=sys.stderr)
        return 2

    if cmd == "run":
        return _run_app(cfg, args)
    if cmd == "shortcuts":
        from .win import shortcut

        for path in shortcut.create():
            print(path)
        return 0

    ctx = prompts.Context(app=args.app, window_title=args.title, dictionary=list(cfg.dictionary))
    try:
        with OpenRouterClient(proxy=cfg.openrouter.proxy) as client:
            client.warm_up()
            if cmd == "file":
                return _run_file(client, cfg, ctx, args)
            if cmd == "ask":
                result = pipeline.ask_text(client, cfg, args.text, ctx, selection=args.selection)
                print(f"[{result.action}]")
                print(result.text)
                print(
                    f"[ask {result.llm.model} via {result.llm.provider}: {result.llm.latency_s:.2f}s]", file=sys.stderr
                )
                return 0
            res = pipeline.polish(client, cfg, args.text, ctx)
            print(res.text)
            print(f"[polish {res.model} via {res.provider}: {res.latency_s:.2f}s]", file=sys.stderr)
            return 0
    except OpenRouterError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def _history(cfg: config.Config):
    from .store import History

    return History(config.config_path().parent / "history.sqlite", keep=cfg.history.keep)  # tests redirect both


def _run_app(cfg: config.Config, args: argparse.Namespace) -> int:
    from .app import App  # imports Win32 bindings; keep the dev commands importable anywhere

    audio = None
    if getattr(args, "fake_audio", None):
        from .audio import FileAudio

        audio = FileAudio(args.fake_audio)
    accept_injected = getattr(args, "accept_injected", False)
    try:
        if getattr(args, "no_ui", False):
            app = App(cfg, audio=audio, history=_history(cfg), accept_injected=accept_injected)
            print("sayrift is running (console). Tap Right Alt to dictate; Ctrl+C to quit.", file=sys.stderr)
            with contextlib.suppress(KeyboardInterrupt):
                app.run()
            return 0
        from .ui.qt import run as run_qt

        print("sayrift is running in the tray. Tap Right Alt to dictate.", file=sys.stderr)
        history = _history(cfg)
        return run_qt(
            cfg,
            lambda ui: App(cfg, audio=audio, ui=ui, history=history, accept_injected=accept_injected),
            history=history,
            minimized=args.minimized,
        )
    except OpenRouterError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def _run_file(client: OpenRouterClient, cfg: config.Config, ctx: prompts.Context, args: argparse.Namespace) -> int:
    fmt = AUDIO_FORMATS.get(args.path.suffix.lower())
    if fmt is None:
        print(
            f"error: unsupported audio type {args.path.suffix!r}; use one of {sorted(AUDIO_FORMATS)}", file=sys.stderr
        )
        return 2
    if args.raw:
        cfg.polish.enabled = False
    run = pipeline.translate if args.translate else pipeline.dictate
    result = run(client, cfg, args.path.read_bytes(), fmt, ctx)
    print(result.text)
    timing = f"asr {result.asr.model}: {result.asr.latency_s:.2f}s"
    if result.polish:
        timing += f" | llm {result.polish.model} via {result.polish.provider}: {result.polish.latency_s:.2f}s"
        print(f"[raw] {result.raw}", file=sys.stderr)
    print(f"[{timing}]", file=sys.stderr)
    return 0
