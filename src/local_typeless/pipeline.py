"""Dictation pipeline: audio -> ASR transcript -> LLM cleanup -> text to insert.

UI-free and synchronous so it can be driven from the CLI, tests, or a worker thread.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from . import prompts
from .config import Config
from .models import chat_extra, provider_prefs
from .openrouter import ChatResult, OpenRouterClient, OpenRouterError, Transcript

log = logging.getLogger(__name__)


@dataclass(slots=True)
class DictationResult:
    raw: str  # ASR output
    text: str  # what gets inserted
    asr: Transcript
    polish: ChatResult | None  # None when cleanup is disabled or skipped


def _routing(cfg: Config, *, low_latency: bool) -> dict:
    o = cfg.openrouter
    return provider_prefs(low_latency=low_latency, deny_data_collection=o.deny_data_collection, zdr=o.zdr)


def asr_timeout(audio: bytes) -> float:
    """Deadline for one transcription request: generous for long audio, short for typical clips.

    Opus at 24 kbps is ~3 KB/s, so 10 KB of audio buys one extra second (~3.3 s of speech).
    """
    return max(15.0, 10.0 + len(audio) / 10_000)


def transcribe(client: OpenRouterClient, cfg: Config, audio: bytes, audio_format: str) -> Transcript:
    models = [m for m in (cfg.asr.model, cfg.asr.fallback_model) if m]
    for i, model in enumerate(models):
        try:
            return client.transcribe(
                audio,
                audio_format,
                model,
                keywords=cfg.dictionary or None,
                languages=cfg.asr.languages or None,
                provider=_routing(cfg, low_latency=False) or None,  # STT models have a single provider
                timeout_s=asr_timeout(audio),
            )
        except OpenRouterError:
            if i == len(models) - 1:
                raise
            log.warning("ASR model %s failed, falling back to %s", model, models[i + 1], exc_info=True)
    raise AssertionError("unreachable")


def _chat_with_fallback(
    client: OpenRouterClient,
    cfg: Config,
    messages: list[dict],
    models: list[str | None],
    *,
    max_tokens: int,
    first_token_timeout_s: float,
    body: dict | None = None,
) -> ChatResult:
    """Try each configured model in turn (errors and timeouts move on to the next one)."""
    candidates = [m for m in models if m]
    for i, model in enumerate(candidates):
        try:
            extra = {**chat_extra(model, _routing(cfg, low_latency=True)), **(body or {})}
            return client.chat(
                messages, model, max_tokens=max_tokens, extra=extra, first_token_timeout_s=first_token_timeout_s
            )
        except OpenRouterError:
            if i == len(candidates) - 1:
                raise
            log.warning("text model %s failed, falling back to %s", model, candidates[i + 1], exc_info=True)
    raise AssertionError("unreachable")


def _chat(client: OpenRouterClient, cfg: Config, messages: list[dict], raw: str, *, check_length: bool) -> ChatResult:
    """Cleanup / translation request with the configured fallback model and the output guard."""
    res = _chat_with_fallback(
        client,
        cfg,
        messages,
        [cfg.polish.model, cfg.polish.fallback_model],
        max_tokens=max(256, 4 * len(raw)),
        first_token_timeout_s=cfg.polish.first_token_timeout_s,
    )
    res.text = guard(raw, tidy(res.text), check_length=check_length)
    return res


def polish(client: OpenRouterClient, cfg: Config, raw: str, ctx: prompts.Context) -> ChatResult:
    messages = prompts.dictation_messages(raw, ctx, cjk_spacing=cfg.polish.cjk_spacing)
    return _chat(client, cfg, messages, raw, check_length=True)


def tidy(text: str) -> str:
    """Deterministic cleanup of LLM output: no trailing spaces (Markdown hard breaks)."""
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


# Placeholders some models emit instead of an empty answer (seen with kimi-k2.6, qwen3.8-flash).
_EMPTY_PLACEHOLDERS = {"（空）", "(空)", "(empty)", "(empty output)", "<empty>", "[empty]"}


def guard(raw: str, cleaned: str, *, check_length: bool = True) -> str:
    """Catch cleanup failures the prompt alone does not prevent.

    - a placeholder instead of empty output -> empty
    - output far longer than the transcript (the model answered or drafted something instead of
      cleaning) -> fall back to the raw transcript; inserting the user's own words is the safe failure.
      Skipped for translation, where length legitimately changes (Chinese -> English ~2-3x chars).
    """
    if cleaned.strip().lower() in _EMPTY_PLACEHOLDERS:
        return ""
    if check_length and len(cleaned) > max(2 * len(raw), len(raw) + 60):
        log.warning("cleanup output is %d chars for a %d-char transcript; using the transcript", len(cleaned), len(raw))
        return raw
    return cleaned


def dictate(
    client: OpenRouterClient, cfg: Config, audio: bytes, audio_format: str, ctx: prompts.Context | None = None
) -> DictationResult:
    ctx = ctx or prompts.Context()
    if cfg.dictionary and not ctx.dictionary:
        ctx.dictionary = list(cfg.dictionary)
    asr = transcribe(client, cfg, audio, audio_format)
    if not asr.text or not cfg.polish.enabled:
        return DictationResult(asr.text, asr.text, asr, None)
    res = polish(client, cfg, asr.text, ctx)
    return DictationResult(asr.text, res.text, asr, res)


def translate(
    client: OpenRouterClient, cfg: Config, audio: bytes, audio_format: str, ctx: prompts.Context | None = None
) -> DictationResult:
    """Typeless Translate mode: speak any language, insert the text in the current target language."""
    ctx = ctx or prompts.Context()
    if cfg.dictionary and not ctx.dictionary:
        ctx.dictionary = list(cfg.dictionary)
    asr = transcribe(client, cfg, audio, audio_format)
    if not asr.text:
        return DictationResult("", "", asr, None)
    target = cfg.translate.targets[0] if cfg.translate.targets else "English"
    messages = prompts.translate_messages(asr.text, ctx, target_language=target)
    res = _chat(client, cfg, messages, asr.text, check_length=False)
    return DictationResult(asr.text, res.text, asr, res)


# --- Ask anything ------------------------------------------------------------------------------

REPLACE, INSERT, ANSWER, NOTHING = "replace", "insert", "answer", "nothing"


@dataclass(slots=True)
class AskResult:
    raw: str  # what the user said (ASR)
    action: str  # replace | insert | answer | nothing
    text: str
    asr: Transcript
    llm: ChatResult | None


def parse_ask(output: str, *, has_selection: bool) -> tuple[str, str]:
    """Model output -> (action, text). Tolerates code fences and prose around the JSON; anything
    unparseable is shown as an answer rather than typed into the user's document."""
    raw = output.strip()
    start, end = raw.find("{"), raw.rfind("}")
    data = None
    if start != -1 and end > start:
        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            data = None
    if not isinstance(data, dict) or not isinstance(data.get("text"), str):
        return ANSWER, raw
    action = data.get("action")
    text = tidy(data["text"])
    if action == REPLACE and not has_selection:
        action = INSERT  # nothing to replace: put it at the cursor
    if action not in (REPLACE, INSERT, ANSWER):
        action = ANSWER
    return action, text


def ask(
    client: OpenRouterClient,
    cfg: Config,
    audio: bytes,
    audio_format: str,
    ctx: prompts.Context | None = None,
    *,
    selection: str | None = None,
) -> AskResult:
    """Typeless Ask anything: edit the selection, write at the cursor, or answer in a card."""
    ctx = ctx or prompts.Context()
    if cfg.dictionary and not ctx.dictionary:
        ctx.dictionary = list(cfg.dictionary)
    asr = transcribe(client, cfg, audio, audio_format)
    if not asr.text:
        return AskResult("", NOTHING, "", asr, None)
    return ask_text(client, cfg, asr.text, ctx, selection=selection, asr=asr)


def ask_text(
    client: OpenRouterClient,
    cfg: Config,
    spoken: str,
    ctx: prompts.Context,
    *,
    selection: str | None = None,
    asr: Transcript | None = None,
) -> AskResult:
    messages = prompts.ask_messages(spoken, ctx, selection=selection)
    res = _chat_with_fallback(
        client,
        cfg,
        messages,
        [cfg.ask.model, cfg.ask.fallback_model],
        max_tokens=4000,
        first_token_timeout_s=cfg.ask.first_token_timeout_s,
        body={"response_format": prompts.ASK_RESPONSE_FORMAT},
    )
    action, text = parse_ask(res.text, has_selection=bool(selection))
    return AskResult(spoken, action if text else NOTHING, text, asr or Transcript(spoken, "text", 0.0), res)
