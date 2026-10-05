"""User interface (Qt): tray icon, Voice bar overlay, answer / result cards.

The controller never touches Qt directly. It calls the `Ui` protocol below from its own thread;
`ui.qt.QtUi` implements it by emitting Qt signals, which Qt delivers to the GUI thread.
"""

from __future__ import annotations

from typing import Protocol


class Ui(Protocol):
    def listening(self, label: str, max_seconds: float) -> None: ...  # label: "", "→ English", "Ask"
    def level(self, rms: float) -> None: ...  # called from the audio thread, ~20 times a second
    def processing(self) -> None: ...
    def done(self, text: str) -> None: ...  # text that was inserted ("" if none)
    def cancelled(self) -> None: ...
    def error(self, message: str) -> None: ...
    def answer(self, question: str, answer: str) -> None: ...  # Ask anything answer card
    def result(self, text: str, reason: str) -> None: ...  # could not insert: show it with a Copy button
    def history_changed(self) -> None: ...  # a history entry was added or updated


class NullUi:
    """Console mode and tests: no UI."""

    def listening(self, label: str, max_seconds: float) -> None:
        pass

    def level(self, rms: float) -> None:
        pass

    def processing(self) -> None:
        pass

    def done(self, text: str) -> None:
        pass

    def cancelled(self) -> None:
        pass

    def error(self, message: str) -> None:
        pass

    def answer(self, question: str, answer: str) -> None:
        pass

    def result(self, text: str, reason: str) -> None:
        pass

    def history_changed(self) -> None:
        pass
