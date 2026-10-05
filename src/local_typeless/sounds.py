"""Start / stop / error cues (Typeless plays a sound when listening starts and finishes).

The WAVs are synthesized once into the user cache dir: winsound cannot play from memory
asynchronously, and we must never block the calling thread on audio playback.
"""

from __future__ import annotations

import logging
import math
import os
import struct
import wave
from pathlib import Path

log = logging.getLogger(__name__)

_RATE = 22_050
# (frequency Hz, duration s) sequences; gentle sine blips with short fades.
_CUES: dict[str, list[tuple[float, float]]] = {
    "start": [(660.0, 0.07), (880.0, 0.09)],
    "stop": [(880.0, 0.07), (660.0, 0.09)],
    "error": [(330.0, 0.12), (0.0, 0.05), (330.0, 0.12)],
    "cancel": [(520.0, 0.08)],
}


def _cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "local-typeless" / "sounds"


def _synth(path: Path, notes: list[tuple[float, float]], volume: float = 0.22) -> None:
    frames = bytearray()
    for freq, dur in notes:
        n = int(_RATE * dur)
        fade = max(1, int(_RATE * 0.01))
        for i in range(n):
            env = min(1.0, i / fade, (n - i) / fade)
            sample = volume * env * math.sin(2 * math.pi * freq * i / _RATE) if freq else 0.0
            frames += struct.pack("<h", int(sample * 32767))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(_RATE)
        wf.writeframes(bytes(frames))


class Sounds:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled  # can be toggled at runtime from the settings
        self._paths: dict[str, Path] = {}
        if enabled:
            self._prepare()

    def _prepare(self) -> None:
        try:
            d = _cache_dir()
            d.mkdir(parents=True, exist_ok=True)
            for name, notes in _CUES.items():
                p = d / f"{name}.wav"
                if not p.exists():
                    _synth(p, notes)
                self._paths[name] = p
        except OSError:
            log.warning("could not prepare sound cues; continuing silently", exc_info=True)

    def play(self, name: str) -> None:
        if not self.enabled:
            return
        if not self._paths:  # enabled after start-up
            self._prepare()
        if name not in self._paths:
            return
        try:
            import winsound

            winsound.PlaySound(
                str(self._paths[name]), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
            )
        except (ImportError, RuntimeError):
            log.debug("sound playback failed", exc_info=True)
