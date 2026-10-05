"""Hotkey state machine implementing Typeless' key behaviour (pure logic, no Win32 calls).

Typeless on Windows (docs/product-spec.md §1):
- Right Alt = Dictate, Right Alt + Right Shift = Translate, Right Alt + Space = Ask anything.
- Tap the main key to start and tap it again to finish; holding it and releasing also
  finishes (push-to-talk). The microphone opens on key-down.
- Chords are always "press once, speak, press the main key once": the official Translate / Ask anything
  docs say so, and holding Right Alt while reaching for Shift or Space easily passes the push-to-talk
  threshold, so releasing it after a chord must not end the session.
- Esc cancels a running or processing session.

The low-level keyboard hook feeds every key event to `HotkeyEngine.handle`, which decides
whether to swallow it. It runs on the hook thread, so it must stay fast: listener callbacks
only enqueue work for the app.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, StrEnum, auto
from typing import Protocol

from .keys import VK_ESCAPE, VK_RMENU, VK_RSHIFT, VK_SPACE

log = logging.getLogger(__name__)


class Mode(StrEnum):
    DICTATE = "dictate"
    TRANSLATE = "translate"
    ASK = "ask"


@dataclass(frozen=True, slots=True)
class Bindings:
    main: int = VK_RMENU
    translate: int = VK_RSHIFT  # chord key held together with `main`
    ask: int = VK_SPACE  # chord key held together with `main`
    cancel: int = VK_ESCAPE
    # Holding `main` at least this long and releasing finishes the session (push-to-talk, the
    # behaviour of older Typeless docs); a shorter tap latches recording until `main` is pressed
    # again (the current docs' toggle). hold_to_talk=False makes every press a toggle.
    hold_threshold_s: float = 0.5
    hold_to_talk: bool = True


class Listener(Protocol):
    def on_start(self, mode: Mode) -> None: ...  # main key went down: open the mic now
    def on_mode(self, mode: Mode) -> None: ...  # a chord key upgraded the running session
    def on_finish(self) -> None: ...
    def on_cancel(self) -> None: ...  # Esc
    def on_abort(self) -> None: ...  # main key was part of an ordinary shortcut (e.g. Alt+Tab)


class Phase(Enum):
    IDLE = auto()
    HELD = auto()  # main key down, session running
    LATCHED = auto()  # main key released after a tap, session running hands-free
    FINISHING = auto()  # a second press finished the session; waiting for its key-up


class HotkeyEngine:
    def __init__(
        self,
        bindings: Bindings,
        listener: Listener,
        *,
        clock: Callable[[], float] = time.monotonic,
        replay_main_down: Callable[[], None] | None = None,
        is_down: Callable[[int], bool] | None = None,
    ) -> None:
        self.b = bindings
        self.listener = listener
        self._clock = clock
        self._replay_main_down = replay_main_down  # re-injects the swallowed main key-down
        self._is_down = is_down or (lambda vk: False)  # physical state of keys we did not swallow
        self.phase = Phase.IDLE
        self.mode = Mode.DICTATE
        self.busy = False  # set by the app while a finished session is being processed
        self._main_down = False
        self._pressed_at = 0.0
        self._chorded = False
        self._passthrough_main = False
        self._swallowed_downs: set[int] = set()

    def reset(self) -> None:
        """The app ended the session on its own (error, max length): go back to idle."""
        self.phase = Phase.IDLE

    def handle(self, vk: int, down: bool) -> bool:
        """Process one key event; return True to swallow it."""
        if vk == self.b.main:
            return self._main(down)
        if down:
            return self._other_down(vk)
        if vk in self._swallowed_downs:  # key-up of a key-down we swallowed
            self._swallowed_downs.discard(vk)
            return True
        return False

    # --- main key ----------------------------------------------------------------------------

    def _main(self, down: bool) -> bool:
        if down:
            if self._main_down:  # auto-repeat while held
                return not self._passthrough_main
            self._main_down = True
            if self.phase is Phase.IDLE:
                if self.busy:
                    log.debug("main key ignored: previous session still processing")
                    return True
                self.phase = Phase.HELD
                self._pressed_at = self._clock()
                self.mode = Mode.TRANSLATE if self._is_down(self.b.translate) else Mode.DICTATE
                self._chorded = self.mode is Mode.TRANSLATE
                self.listener.on_start(self.mode)
            elif self.phase is Phase.LATCHED:
                self.phase = Phase.FINISHING
                self.listener.on_finish()
            return True

        # key-up
        if not self._main_down:
            return False  # we never saw the key-down (hook installed while it was held)
        self._main_down = False
        if self._passthrough_main:
            self._passthrough_main = False
            return False
        if self.phase is Phase.HELD:
            held = self._clock() - self._pressed_at >= self.b.hold_threshold_s
            if self.b.hold_to_talk and held and not self._chorded:
                self.phase = Phase.IDLE
                self.listener.on_finish()
            else:
                self.phase = Phase.LATCHED
        elif self.phase is Phase.FINISHING:
            self.phase = Phase.IDLE
        return True

    # --- everything else ---------------------------------------------------------------------

    def _other_down(self, vk: int) -> bool:
        if vk == self.b.cancel and (self.phase is not Phase.IDLE or self.busy):
            self.phase = Phase.IDLE
            self._swallowed_downs.add(vk)
            self.listener.on_cancel()
            return True
        if self.phase is not Phase.HELD or not self._main_down:
            return False
        if vk in (self.b.translate, self.b.ask):
            if vk in self._swallowed_downs:  # auto-repeat of the chord key
                return True
            self.mode = Mode.TRANSLATE if vk == self.b.translate else Mode.ASK
            self._chorded = True
            self._swallowed_downs.add(vk)
            self.listener.on_mode(self.mode)
            return True
        if self._chorded:
            return False  # typing while holding a chord: let it through
        # Any other key while the main key is held means the user wanted an ordinary shortcut
        # (Alt+Tab, AltGr+letter...). Give the key-down we swallowed back to the system.
        self.phase = Phase.IDLE
        self._passthrough_main = True
        self.listener.on_abort()
        if self._replay_main_down:
            self._replay_main_down()
        return False
