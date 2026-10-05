"""Microphone capture with on-the-fly Opus encoding (docs/architecture.md §5.2).

Measured on the dev machine (2026-09-23):
- Opening the default input via MME takes ~530 ms, via WASAPI ~120 ms -> use WASAPI.
- One-shot Opus encoding costs ~10 ms per second of audio (0.6 s for a minute); writing
  50 ms blocks while recording costs ~0.5 ms each and closing the file < 1 ms.
- Room noise floor ~100 RMS (int16); speech is typically well above 1000.
"""

from __future__ import annotations

import io
import logging
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
BLOCK = SAMPLE_RATE // 20  # 50 ms

# Speech detection on per-block RMS (int16 scale): a block is "voiced" when it clearly exceeds
# both an absolute floor and the recording's own noise floor. Needs ~0.3 s of voiced blocks so
# the start chime alone does not count.
_ABS_VOICED_RMS = 250.0
_NOISE_FACTOR = 3.0
_MIN_VOICED_BLOCKS = 6


class MicrophoneError(RuntimeError):
    """The input device could not be opened (unplugged, blocked by privacy settings, ...)."""


@dataclass(slots=True)
class Recording:
    data: bytes  # OGG/Opus, ready to upload
    format: str
    duration_s: float
    speech_detected: bool
    peak_rms: float


def speech_present(block_rms: list[float]) -> bool:
    if len(block_rms) < _MIN_VOICED_BLOCKS:
        return False
    noise_floor = float(np.percentile(block_rms, 20))
    threshold = max(_ABS_VOICED_RMS, _NOISE_FACTOR * noise_floor)
    return sum(r > threshold for r in block_rms) >= _MIN_VOICED_BLOCKS


def wasapi_default_input() -> int | None:
    for api in sd.query_hostapis():
        if api["name"] == "Windows WASAPI" and api["default_input_device"] >= 0:
            return api["default_input_device"]
    return None


def resolve_device(name: str | None) -> tuple[int | None, sd.WasapiSettings | None]:
    """Config device name (substring, case-insensitive) -> (device index, extra settings)."""
    wasapi = next((i for i, a in enumerate(sd.query_hostapis()) if a["name"] == "Windows WASAPI"), None)
    if name:
        for idx, dev in enumerate(sd.query_devices()):
            if dev["max_input_channels"] > 0 and dev["hostapi"] == wasapi and name.lower() in dev["name"].lower():
                return idx, sd.WasapiSettings(auto_convert=True)
        log.warning("input device %r not found; using the default microphone", name)
    idx = wasapi_default_input()
    return (idx, sd.WasapiSettings(auto_convert=True)) if idx is not None else (None, None)


class Recorder:
    """start() opens the mic; stop() returns the encoded recording. One session at a time."""

    def __init__(self, *, device: str | None = None, on_level: Callable[[float], None] | None = None) -> None:
        self._device_name = device
        self._on_level = on_level
        self._stream: sd.InputStream | None = None
        self._queue: queue.Queue[np.ndarray | None] = queue.Queue()
        self._writer: threading.Thread | None = None
        self._buf = io.BytesIO()
        self._rms: list[float] = []
        self._started_at = 0.0

    @property
    def active(self) -> bool:
        return self._stream is not None

    def warm_up(self) -> None:
        """Open and close the input once. The first open in a process has been measured at
        ~0.5 s vs ~0.12 s afterwards, which would clip the start of the first dictation."""
        device, extra = resolve_device(self._device_name)
        try:
            sd.InputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="int16", device=device, extra_settings=extra
            ).close()
        except sd.PortAudioError:
            log.warning("microphone warm-up failed", exc_info=True)

    def start(self) -> None:
        if self._stream is not None:
            raise RuntimeError("recording already in progress")
        device, extra = resolve_device(self._device_name)
        self._queue = queue.Queue()
        self._buf = io.BytesIO()
        self._rms = []
        try:
            stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=BLOCK,
                device=device,
                extra_settings=extra,
                callback=self._callback,
            )
            stream.start()
        except sd.PortAudioError as e:
            raise MicrophoneError(str(e)) from e
        self._stream = stream
        self._started_at = time.monotonic()
        self._writer = threading.Thread(target=self._write_loop, name="opus-writer", daemon=True)
        self._writer.start()

    def stop(self) -> Recording:
        duration = self._close_stream()
        self._queue.put(None)
        if self._writer:
            self._writer.join(5)
        return Recording(
            data=self._buf.getvalue(),
            format="ogg",
            duration_s=duration,
            speech_detected=speech_present(self._rms),
            peak_rms=max(self._rms, default=0.0),
        )

    def cancel(self) -> None:
        if self._stream is None:
            return
        self._close_stream()
        self._queue.put(None)
        if self._writer:
            self._writer.join(5)

    # --- internals -----------------------------------------------------------------------------

    def _close_stream(self) -> float:
        stream, self._stream = self._stream, None
        if stream is None:
            return 0.0
        try:
            stream.stop()
            stream.close()
        except sd.PortAudioError:
            log.warning("error while closing the input stream", exc_info=True)
        return time.monotonic() - self._started_at

    def _callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        block = indata[:, 0].copy()
        self._queue.put(block)
        if self._on_level:
            self._on_level(float(np.sqrt(np.mean(block.astype(np.float32) ** 2))))

    def _write_loop(self) -> None:
        with sf.SoundFile(self._buf, "w", SAMPLE_RATE, 1, format="OGG", subtype="OPUS") as out:
            while (block := self._queue.get()) is not None:
                self._rms.append(float(np.sqrt(np.mean(block.astype(np.float32) ** 2))))
                out.write(block)


class FileAudio:
    """Drop-in Recorder replacement that 'records' an audio file (tests and demos)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._started_at: float | None = None

    @property
    def active(self) -> bool:
        return self._started_at is not None

    def start(self) -> None:
        self._started_at = time.monotonic()

    def stop(self) -> Recording:
        duration = time.monotonic() - (self._started_at or time.monotonic())
        self._started_at = None
        fmt = {".ogg": "ogg", ".opus": "ogg", ".mp3": "mp3", ".wav": "wav"}[self.path.suffix.lower()]
        return Recording(self.path.read_bytes(), fmt, duration, speech_detected=True, peak_rms=0.0)

    def cancel(self) -> None:
        self._started_at = None
