"""User settings: built-in defaults, optionally overridden by a TOML file.

Location: %APPDATA%/local-typeless/config.toml (override with SAYRIFT_CONFIG).
The data directory and LOCAL_TYPELESS_CONFIG alias are retained for existing installations.
Only keys present in the file override defaults; unknown keys are rejected so typos
surface immediately. The API key is never stored here - it comes from OPENROUTER_API_KEY.
"""

from __future__ import annotations

import json
import os
import sys
import tomllib
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path


@dataclass
class AsrConfig:
    model: str = "openai/gpt-transcribe"
    fallback_model: str | None = "microsoft/mai-transcribe-2"
    # Expected spoken languages; sent as a hint to models that accept it (gpt-transcribe).
    languages: list[str] = field(default_factory=lambda: ["zh-cn", "en"])


@dataclass
class PolishConfig:
    enabled: bool = True
    model: str = "deepseek/deepseek-v4.1-flash"
    fallback_model: str | None = "openai/gpt-6-luna"
    cjk_spacing: bool = True  # "用 Python 写" vs "用Python写"
    # No text after this long -> give up on the model and use the fallback. Typical first token
    # arrives in ~0.5 s; a stuck request was observed to hang > 15 s.
    first_token_timeout_s: float = 6.0


@dataclass
class AskConfig:
    # Ask anything: edit the selection, write something, or answer a question.
    model: str = "deepseek/deepseek-v4.1-flash"
    fallback_model: str | None = "openai/gpt-6-luna"
    first_token_timeout_s: float = 8.0


@dataclass
class TranslateConfig:
    # Ordered target languages (Typeless: Settings > Language > Translation targets); the first
    # one is used until the overlay lets you switch (M2).
    targets: list[str] = field(default_factory=lambda: ["English"])


@dataclass
class HotkeyConfig:
    # Typeless defaults on Windows. Key names: see keys.KEY_NAMES (RightAlt, Space, F13, ...).
    main: str = "RightAlt"  # tap to start / tap to finish, or hold and release
    translate: str = "RightShift"  # held together with `main`
    ask: str = "Space"  # held together with `main`
    cancel: str = "Escape"
    hold_threshold_s: float = 0.5  # held at least this long -> releasing finishes (push-to-talk)
    hold_to_talk: bool = True  # False: strictly the current Typeless toggle (press to start, press to finish)


@dataclass
class AudioConfig:
    device: str = ""  # substring of the input device name; empty = system default microphone
    sounds: bool = True  # start / stop / error cues
    max_seconds: int = 540  # Typeless: 9 minutes per dictation


@dataclass
class HistoryConfig:
    # Typeless: Keep history = forever / 1y / 1m / 1w / 24h / never; history stays on this machine.
    keep: str = "forever"
    keep_audio: bool = True  # needed for "Retry" on an entry; stored locally, pruned with the entry


@dataclass
class AppConfig:
    log_text: bool = False  # write transcripts to the log (debugging only)
    language: str = "auto"  # interface language: auto (follow Windows) / zh / en
    theme: str = "system"  # appearance: system / light / dark (Typeless has the same three)
    onboarded: bool = False  # the first-run guide was finished or skipped


@dataclass
class OpenRouterConfig:
    # Explicit proxy URL; unset means HTTPS_PROXY/HTTP_PROXY, then the Windows system proxy.
    proxy: str | None = None
    # Privacy routing (applies to STT and chat): skip providers that store/train on data.
    deny_data_collection: bool = True
    # Stricter: zero-data-retention endpoints only. Requests fail for models without one.
    zdr: bool = False


@dataclass
class Config:
    asr: AsrConfig = field(default_factory=AsrConfig)
    polish: PolishConfig = field(default_factory=PolishConfig)
    translate: TranslateConfig = field(default_factory=TranslateConfig)
    ask: AskConfig = field(default_factory=AskConfig)
    hotkeys: HotkeyConfig = field(default_factory=HotkeyConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    app: AppConfig = field(default_factory=AppConfig)
    history: HistoryConfig = field(default_factory=HistoryConfig)
    openrouter: OpenRouterConfig = field(default_factory=OpenRouterConfig)
    # Personal dictionary: names/terms the user says often. Fed to ASR as keyword hints
    # and to the LLM as preferred spellings.
    dictionary: list[str] = field(default_factory=list)


def config_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "local-typeless"


def api_key() -> str | None:
    """OPENROUTER_API_KEY from the environment, or from the user's stored variables if it was set after launch."""
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key and sys.platform == "win32":
        from .win.env import user_env

        key = user_env("OPENROUTER_API_KEY") or ""
    return key or None


def config_path() -> Path:
    env = os.environ.get("SAYRIFT_CONFIG") or os.environ.get("LOCAL_TYPELESS_CONFIG")
    return Path(env) if env else config_dir() / "config.toml"


def _apply(obj: object, data: dict, where: str) -> None:
    known = {f.name: f for f in fields(obj)}  # type: ignore[arg-type]
    for key, value in data.items():
        if key not in known:
            raise ValueError(f"unknown config key {where}{key!r}")
        current = getattr(obj, key)
        if is_dataclass(current):
            if not isinstance(value, dict):
                raise ValueError(f"config key {where}{key!r} must be a table")
            _apply(current, value, f"{where}{key}.")
        else:
            setattr(obj, key, value)


def load(path: Path | None = None) -> Config:
    cfg = Config()
    path = path or config_path()
    if path.exists():
        with path.open("rb") as f:
            _apply(cfg, tomllib.load(f), "")
    return cfg


# --- writing (settings UI) ---------------------------------------------------------------------


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)  # JSON string escapes are valid TOML basic strings
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    raise TypeError(f"cannot write {type(value).__name__} to TOML")


def _diff(obj: object, default: object) -> dict:
    """Fields of `obj` that differ from `default`; nested dataclasses become sub-tables."""
    out: dict = {}
    for f in fields(obj):  # type: ignore[arg-type]
        value, base = getattr(obj, f.name), getattr(default, f.name)
        if is_dataclass(value):
            sub = _diff(value, base)
            if sub:
                out[f.name] = sub
        elif value != base and value is not None:
            out[f.name] = value
    return out


def dumps(cfg: Config) -> str:
    """Only non-default settings are written, so later default changes still reach the user."""
    data = _diff(cfg, Config())
    lines = ["# Sayrift settings, written by the app. Options: config.example.toml in the repo.", ""]
    lines += [f"{k} = {_toml_value(v)}" for k, v in data.items() if not isinstance(v, dict)]
    for table, values in data.items():
        if isinstance(values, dict):
            lines += ["", f"[{table}]"] + [f"{k} = {_toml_value(v)}" for k, v in values.items()]
    return "\n".join(lines) + "\n"


def save(cfg: Config, path: Path | None = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(dumps(cfg), encoding="utf-8", newline="\n")
    tmp.replace(path)  # atomic on the same volume: a crash never leaves a half-written file
