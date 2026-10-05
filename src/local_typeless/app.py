"""The dictation app: hotkey -> microphone -> ASR + cleanup -> paste (M1: console, no UI yet).

Threads (docs/architecture.md §2):
- keyboard-hook: WH_KEYBOARD_LL callback -> HotkeyEngine; listener callbacks only enqueue.
- controller (the thread calling `run`): owns all session state; handles events in order.
- pipeline worker: network calls; posts ("done", ...) back to the controller.
"""

from __future__ import annotations

import contextlib
import logging
import queue
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum, auto
from itertools import count
from typing import Protocol

from . import pipeline, prompts
from .audio import MicrophoneError, Recorder, Recording
from .config import Config, api_key
from .hotkeys import Bindings, HotkeyEngine, Mode, Phase
from .keys import parse_key
from .openrouter import NetworkError, OpenRouterClient, OpenRouterError, RequestTimeout
from .sounds import Sounds
from .store import Entry, History, Usage
from .ui import NullUi, Ui

log = logging.getLogger(__name__)

MIN_RECORDING_S = 0.3


class State(Enum):
    IDLE = auto()
    RECORDING = auto()
    PROCESSING = auto()


class AudioSource(Protocol):
    def start(self) -> None: ...
    def stop(self) -> Recording: ...
    def cancel(self) -> None: ...


@dataclass
class Session:
    id: int
    mode: Mode
    target: object  # win.foreground.WindowInfo (kept loose so the app logic is testable off Windows)
    started_at: float = field(default_factory=time.monotonic)
    finished_at: float = 0.0
    selection: str | None = None  # Ask anything: text selected when the Ask chord was pressed
    recording: Recording | None = None


def user_message(error: BaseException) -> str:
    """Message key for the Voice bar and history (the UI translates it); details go to the log."""
    text = str(error)
    if "OPENROUTER_API_KEY" in text:
        return "err.no_key"
    if isinstance(error, RequestTimeout):
        return "err.slow"
    if isinstance(error, NetworkError):
        return "err.network"
    if "HTTP 401" in text or "HTTP 403" in text:
        return "err.key_rejected"
    if "HTTP 402" in text:
        return "err.credits"
    if "HTTP 429" in text:
        return "err.rate"
    return "err.generic"


def bindings_from(cfg: Config) -> Bindings:
    h = cfg.hotkeys
    return Bindings(
        main=parse_key(h.main),
        translate=parse_key(h.translate),
        ask=parse_key(h.ask),
        cancel=parse_key(h.cancel),
        hold_threshold_s=h.hold_threshold_s,
        hold_to_talk=h.hold_to_talk,
    )


class App:
    def __init__(
        self,
        cfg: Config,
        *,
        client: OpenRouterClient | None = None,
        audio: AudioSource | None = None,
        paster=None,
        sounds: Sounds | None = None,
        foreground=None,
        select_text=None,
        show_card=None,
        ui: Ui | None = None,
        history: History | None = None,
        accept_injected: bool = False,
        install_hook: bool = True,
    ) -> None:
        self.cfg = cfg
        self.ui: Ui = ui or NullUi()
        self.history = history
        self._client = client  # created on first use: the app must start even before a key is set
        self.audio: AudioSource = audio or Recorder(device=cfg.audio.device or None, on_level=self.ui.level)
        self.sounds = sounds or Sounds(cfg.audio.sounds)
        self.select_text = select_text  # (target) -> selected text | None
        self.show_card = show_card or (self.ui.answer if ui else None)  # (question, answer) -> None
        bindings = bindings_from(cfg)
        if install_hook:  # real Windows plumbing; tests inject fakes instead
            from . import card
            from .win import _api, inject, selection
            from .win.foreground import foreground as _foreground
            from .win.keyboard_hook import KeyboardHook

            self.paster = paster or inject.Paster()
            self.foreground = foreground or _foreground
            self.select_text = select_text or selection.capture
            self.show_card = self.show_card or card.show  # console mode: stand-alone Tk card
            self.engine = HotkeyEngine(
                bindings, self, replay_main_down=lambda: inject.press(bindings.main), is_down=_api.key_is_down
            )
            self.hook = KeyboardHook(
                self._on_key,
                accept_injected=accept_injected,
                can_reinstall=lambda: self.engine.phase is Phase.IDLE,
            )
        else:
            self.paster, self.foreground = paster, foreground
            self.engine = HotkeyEngine(bindings, self)
            self.hook = None
        self.state = State.IDLE
        self.session: Session | None = None
        self._ids = count(1)
        self._events: queue.Queue[tuple] = queue.Queue()
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pipeline")
        self._stop = threading.Event()
        self._max_timer: threading.Timer | None = None
        self._capture: Callable[[int], None] | None = None
        self._captured_downs: set[int] = set()

    # --- HotkeyEngine listener (called on the hook thread: enqueue only) -------------------------

    def on_start(self, mode: Mode) -> None:
        self._events.put(("start", mode))

    def on_mode(self, mode: Mode) -> None:
        self._events.put(("mode", mode))

    def on_finish(self) -> None:
        self._events.put(("finish", "hotkey"))

    def on_cancel(self) -> None:
        self._events.put(("cancel", None))

    def on_abort(self) -> None:
        self._events.put(("abort", None))

    # --- UI requests (Voice bar × / ✓ buttons; any thread) ----------------------------------------

    def request_cancel(self) -> None:
        self._events.put(("cancel", None))

    def capture_next_key(self, callback: Callable[[int], None]) -> None:
        """Settings: deliver the next key press (virtual-key code) to `callback` instead of acting on it.

        Uses the low-level hook so left/right modifiers (Right Alt vs Left Alt) are told apart.
        `callback` runs on the hook thread; it must only hand the value over (e.g. emit a Qt signal)."""
        self._capture = callback

    def cancel_capture(self) -> None:
        self._capture = None

    def _on_key(self, ev) -> bool:
        if self._capture is not None:
            if ev.down:
                callback, self._capture = self._capture, None
                self._captured_downs.add(ev.vk)
                callback(ev.vk)
            return True  # while capturing, nothing reaches the hotkey engine or the focused app
        if not ev.down and ev.vk in self._captured_downs:
            self._captured_downs.discard(ev.vk)
            return True  # the key-up of the captured key
        return self.engine.handle(ev.vk, ev.down)

    def retry(self, entry_id: int) -> None:
        """History > Retry: run the stored audio through the pipeline again and update the entry."""
        self._worker.submit(self._retry, entry_id)

    def _retry(self, entry_id: int) -> None:
        if not self.history:
            return
        found = self.history.audio(entry_id)
        entry = next((e for e in self.history.list(limit=100_000) if e.id == entry_id), None)
        if not found or not entry:
            return
        audio, fmt = found
        ctx = prompts.Context(app=entry.app or None, dictionary=list(self.cfg.dictionary))
        try:
            if entry.mode == Mode.TRANSLATE:
                result = pipeline.translate(self.client, self.cfg, audio, fmt, ctx)
            elif entry.mode == Mode.ASK:
                result = pipeline.ask(self.client, self.cfg, audio, fmt, ctx)
            else:
                result = pipeline.dictate(self.client, self.cfg, audio, fmt, ctx)
            self._log_usage(entry.mode, result, retry=True)
            action = getattr(result, "action", pipeline.INSERT)
            status = "shown" if action == pipeline.ANSWER else "retried"
            self.history.update_result(entry_id, raw=result.raw, text=result.text, action=action, status=status)
        except Exception as e:  # keep the entry; show why it failed again
            log.warning("retry of history entry %d failed: %s", entry_id, e)
            self.history.update_result(
                entry_id, raw=entry.raw, text=entry.text, action=entry.action, status="failed", error=user_message(e)
            )
        self.ui.history_changed()

    def request_finish(self) -> None:
        self._events.put(("finish", "button"))

    # --- main loop -----------------------------------------------------------------------------

    @property
    def client(self) -> OpenRouterClient:
        if self._client is None:
            key = api_key()
            if not key:  # the session reports it; the client's own env lookup would miss a key set after launch
                raise OpenRouterError("OPENROUTER_API_KEY is not set")
            self._client = OpenRouterClient(api_key=key, proxy=self.cfg.openrouter.proxy)
        return self._client

    def _warm_up(self) -> None:
        with contextlib.suppress(OpenRouterError):
            self.client.warm_up()

    def run(self) -> None:
        if self.hook:
            self.hook.start()
        if hasattr(self.audio, "warm_up"):
            threading.Thread(target=self.audio.warm_up, name="mic-warm-up", daemon=True).start()
        threading.Thread(target=self._warm_up, name="warm-up", daemon=True).start()
        h = self.cfg.hotkeys
        log.info("ready: %s = dictate, %s+%s = translate, %s+%s = ask, %s = cancel",
                 h.main, h.main, h.translate, h.main, h.ask, h.cancel)  # fmt: skip
        try:
            while not self._stop.is_set():
                try:
                    event = self._events.get(timeout=0.25)
                except queue.Empty:
                    continue
                self.dispatch(event)
        finally:
            self.shutdown()

    def stop(self) -> None:
        self._stop.set()

    def shutdown(self) -> None:
        if self.hook:
            self.hook.stop()
        if self.state is State.RECORDING:
            self.audio.cancel()
        if self.paster and hasattr(self.paster, "flush"):
            self.paster.flush()
        self._worker.shutdown(wait=False, cancel_futures=True)

    def process_pending(self, timeout: float = 5.0) -> None:
        """Handle queued events until the app is idle again (tests)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                self.dispatch(self._events.get(timeout=0.05))
            except queue.Empty:
                if self.state is State.IDLE:
                    return

    def dispatch(self, event: tuple) -> None:
        kind, arg = event
        handler = getattr(self, f"_on_{kind}")
        try:
            handler(arg)
        except Exception:
            log.exception("error while handling %s", kind)
            self.sounds.play("error")
            self.ui.error("err.generic")
            self._to_idle()

    def apply_settings(self) -> None:
        """Pick up edited settings without a restart (called after the settings UI saves).

        Everything else (models, dictionary, targets, limits) is read from `self.cfg` per session."""
        self.engine.b = bindings_from(self.cfg)  # a bad key name raises here, before anything changes
        self.sounds.enabled = self.cfg.audio.sounds
        if self.history:
            self.history.keep = self.cfg.history.keep
            self.history.prune()
        if hasattr(self.audio, "_device_name"):
            self.audio._device_name = self.cfg.audio.device or None

    def mode_label(self, mode: Mode) -> str:
        """What the Voice bar shows for the mode, as data the UI renders: dictate / ask / translate:<target>."""
        if mode is Mode.TRANSLATE:
            return f"translate:{self.cfg.translate.targets[0] if self.cfg.translate.targets else 'English'}"
        return "ask" if mode is Mode.ASK else "dictate"

    # --- event handlers (controller thread) ----------------------------------------------------

    def _on_start(self, mode: Mode) -> None:
        if self.state is not State.IDLE:
            return
        target = self.foreground() if self.foreground else None
        try:
            self.audio.start()
        except MicrophoneError as e:
            log.error("Microphone unavailable: %s", e)  # Typeless shows the same message
            self.sounds.play("error")
            self.ui.error("err.mic")
            self.engine.reset()
            return
        self.sounds.play("start")  # Typeless: "start speaking when you hear the start sound"
        self.state = State.RECORDING
        self.session = Session(next(self._ids), mode, target)
        self.ui.listening(self.mode_label(mode), self.cfg.audio.max_seconds)
        threading.Thread(target=self._warm_up, name="warm-up", daemon=True).start()
        limit_event = ("finish", ("limit", self.session.id))  # bound to this session, never ends a later one
        self._max_timer = threading.Timer(self.cfg.audio.max_seconds, self._events.put, args=(limit_event,))
        self._max_timer.daemon = True
        self._max_timer.start()
        # Window titles can carry private details (mail subjects, chat names): exe at INFO, title at DEBUG.
        log.info("session %d: listening (%s) in %s", self.session.id, mode, getattr(target, "exe", "?") or "?")
        log.debug("session %d: window title %r", self.session.id, getattr(target, "title", ""))

    def _on_mode(self, mode: Mode) -> None:
        if self.session and self.state is State.RECORDING:
            self.session.mode = mode
            log.info("session %d: mode -> %s", self.session.id, mode)
            self.ui.listening(self.mode_label(mode), self.cfg.audio.max_seconds)
            if mode is Mode.ASK and self.select_text:
                # Grab the selection now, while the target app still has it (Typeless: select, then Ask).
                if self.paster and hasattr(self.paster, "flush"):
                    self.paster.flush()  # a pending clipboard restore must not be mistaken for the selection
                self.session.selection = self.select_text(self.session.target)
                log.info(
                    "session %d: %s", self.session.id,
                    f"selection of {len(self.session.selection)} chars" if self.session.selection else "no selection",
                )  # fmt: skip

    def _on_finish(self, reason: str | tuple[str, int]) -> None:
        if self.state is not State.RECORDING or not self.session:
            return
        if isinstance(reason, tuple):  # ("limit", session_id) from the max-length timer
            if reason[1] != self.session.id:
                return
            reason = reason[0]
        self._cancel_timer()
        if reason == "limit":
            log.info("session %d: reached the %ds limit", self.session.id, self.cfg.audio.max_seconds)
        if reason != "hotkey":  # finished by the timer or the ✓ button: the hotkey is no longer latched
            self.engine.reset()
        rec = self.audio.stop()
        self.sounds.play("stop")
        s = self.session
        s.finished_at = time.monotonic()
        if rec.duration_s < MIN_RECORDING_S or not rec.speech_detected:
            log.info("session %d: no speech detected (%.1fs, peak rms %.0f)", s.id, rec.duration_s, rec.peak_rms)
            self.ui.error("err.no_speech")
            self._to_idle()
            return
        self.state = State.PROCESSING
        self.engine.busy = True
        self.ui.processing()
        log.info("session %d: %.1fs of audio (%d KB), processing", s.id, rec.duration_s, len(rec.data) // 1024)
        s.recording = rec
        self._worker.submit(self._process, s, rec)

    def _on_cancel(self, _: object) -> None:
        if self.state is State.RECORDING:
            self._cancel_timer()
            self.audio.cancel()
        if self.state is not State.IDLE and self.session:
            log.info("session %d: cancelled", self.session.id)
            self.sounds.play("cancel")
        self.ui.cancelled()
        self._to_idle()

    def _on_abort(self, _: object) -> None:
        if self.state is State.RECORDING:
            self._cancel_timer()
            self.audio.cancel()
            log.info("session %d: main key was part of a shortcut; discarded", self.session.id if self.session else 0)
        self.ui.cancelled()
        self._to_idle()

    def _on_done(self, payload: tuple) -> None:
        session_id, result, error = payload
        s = self.session
        if self.state is not State.PROCESSING or not s or s.id != session_id:
            log.info("session %d: result discarded (cancelled)", session_id)
            return
        if error is not None:
            log.error("session %d: failed: %s", s.id, error)
            self.sounds.play("error")
            self.ui.error(user_message(error))
            self._record(s, "failed", error=error)
            self._to_idle()
            return
        text = result.text
        action = getattr(result, "action", pipeline.INSERT)  # dictation / translation always insert
        if self.cfg.app.log_text:
            log.info("session %d: raw=%r %s=%r", s.id, result.raw, action, text)
        if not text or action == pipeline.NOTHING:
            log.info("session %d: nothing to insert", s.id)
            self.ui.done("")
            self._to_idle()
            return
        llm = getattr(result, "polish", None) or getattr(result, "llm", None)
        timing = f"asr {result.asr.latency_s:.2f}s" + (f", llm {llm.latency_s:.2f}s" if llm else "")
        if action == pipeline.ANSWER:
            # Typeless shows answers in a pop-up card; the document is left untouched.
            if self.show_card:
                self.show_card(result.raw, text)
            self.ui.done("")
            self._record(s, "shown", result)
            log.info(
                "session %d: answer shown in %.2fs after stop (%s)", s.id, time.monotonic() - s.finished_at, timing
            )
            self._to_idle()
            return
        pasted = self.paster.paste(text, s.target) if self.paster else None
        if pasted is None or pasted.ok:
            self.ui.done(text)
        else:  # keep the result reachable: a card with a Copy button (Typeless does the same)
            self.ui.error("err.insert")
            self.ui.result(text, pasted.detail)
        self._record(s, "inserted" if pasted is None or pasted.ok else "not_inserted", result)
        log.info(
            "session %d: %s (%s) via %s in %.2fs after stop (%s), %d chars",
            s.id,
            "inserted" if pasted is None or pasted.ok else "NOT inserted",
            action,
            getattr(pasted, "method", "-"),
            time.monotonic() - s.finished_at,
            timing,
            len(text),
        )
        if pasted is not None and not pasted.ok:
            log.warning("session %d: %s", s.id, pasted.detail)
            self.sounds.play("error")
        self._to_idle()

    def _log_usage(self, mode: str, result, *, retry: bool = False) -> None:
        """Spend log: one row per model call of a session (all sharing one timestamp)."""
        if not self.history or result is None:
            return
        now = time.time()
        asr = getattr(result, "asr", None)
        llm = getattr(result, "polish", None) or getattr(result, "llm", None)
        try:
            if asr is not None:
                self.history.log_usage(Usage(mode, "asr", asr.model, "", asr.cost_usd, asr.audio_seconds,
                                             asr.latency_s, retry, created_at=now))  # fmt: skip
            if llm is not None:
                self.history.log_usage(Usage(mode, "llm", llm.model, llm.provider or "", llm.cost_usd, None,
                                             llm.latency_s, retry, created_at=now))  # fmt: skip
        except Exception:  # bookkeeping must never break dictation
            log.exception("could not write the spend log")

    def _record(self, s: Session, status: str, result=None, error: BaseException | None = None) -> None:
        """Write the session to the local history (Typeless keeps failed ones too, for Retry)."""
        if not self.history:
            return
        self._log_usage(str(s.mode), result)
        rec = s.recording
        llm = getattr(result, "polish", None) or getattr(result, "llm", None)
        costs = [
            c for c in (getattr(getattr(result, "asr", None), "cost_usd", None), getattr(llm, "cost_usd", None)) if c
        ]
        keep_audio = rec is not None and self.cfg.history.keep_audio
        try:
            self.history.add(Entry(
                mode=str(s.mode),
                action=getattr(result, "action", pipeline.INSERT) if result else pipeline.NOTHING,
                status=status,
                app=getattr(s.target, "exe", "") or "",
                raw=getattr(result, "raw", "") if result else "",
                text=getattr(result, "text", "") if result else "",
                error=user_message(error) if error else "",
                duration_s=rec.duration_s if rec else 0.0,
                latency_s=time.monotonic() - s.finished_at if s.finished_at else None,
                cost_usd=sum(costs) if costs else None,
                audio=rec.data if keep_audio else None,
                audio_format=rec.format if keep_audio else None,
            ))  # fmt: skip
        except Exception:  # history must never break dictation
            log.exception("could not write the history entry")
        else:
            self.ui.history_changed()

    # --- worker thread -------------------------------------------------------------------------

    def _process(self, session: Session, rec: Recording) -> None:
        target = session.target
        ctx = prompts.Context(
            app=getattr(target, "exe", None) or None,
            window_title=getattr(target, "title", None) or None,
            dictionary=list(self.cfg.dictionary),
        )
        try:
            if session.mode is Mode.TRANSLATE:
                result = pipeline.translate(self.client, self.cfg, rec.data, rec.format, ctx)
            elif session.mode is Mode.ASK:
                result = pipeline.ask(self.client, self.cfg, rec.data, rec.format, ctx, selection=session.selection)
            else:
                result = pipeline.dictate(self.client, self.cfg, rec.data, rec.format, ctx)
            self._events.put(("done", (session.id, result, None)))
        except OpenRouterError as e:
            self._events.put(("done", (session.id, None, e)))
        except Exception as e:  # keep the controller informed no matter what
            log.exception("pipeline crashed")
            self._events.put(("done", (session.id, None, e)))

    # --- helpers -------------------------------------------------------------------------------

    def _cancel_timer(self) -> None:
        if self._max_timer:
            self._max_timer.cancel()
            self._max_timer = None

    def _to_idle(self) -> None:
        self._cancel_timer()
        self.state = State.IDLE
        self.engine.busy = False
        self.engine.reset()
