"""Thin OpenRouter client: speech-to-text and (streaming) chat completions.

Only the two endpoints the app needs are wrapped:

* ``POST /audio/transcriptions`` - dedicated STT models (gpt-transcribe, Qwen3-ASR, ...)
* ``POST /chat/completions``     - text LLMs for polishing / editing / translating

Network notes: the user reaches openrouter.ai through a local proxy, and the app may be
started from Explorer where ``HTTPS_PROXY`` is not set, so we fall back to the Windows
"Internet Options" proxy (``urllib.request.getproxies`` reads the registry on Windows).
"""

from __future__ import annotations

import base64
import contextlib
import json
import logging
import os
import time
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

API_BASE = "https://openrouter.ai/api/v1"
APP_TITLE = "Sayrift"

# Which `provider.options.<slug>` block receives STT context hints for a model prefix.
# Verified 2026-09: openai/gpt-transcribe honours keywords/languages/prompt there;
# the same fields at the top level are silently ignored. Other STT vendors had no
# effect with any option name we tried, so they get no hints.
_STT_HINT_PROVIDER = {"openai/gpt-transcribe": "openai"}


class OpenRouterError(RuntimeError):
    """Any failure talking to OpenRouter (HTTP error, provider error, bad payload)."""

    def __init__(self, message: str, *, status_code: int | None = None, code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class NetworkError(OpenRouterError):
    """Transport-level failure (connect/read/TLS); the request may be retried."""


class RequestTimeout(OpenRouterError):
    """The provider is too slow. Not retried on the same model: callers switch to a fallback."""


def _response_error(path: str, status: int, reason: str, error: object = None) -> OpenRouterError:
    # Even a provider's "code" can contain echoed input. Only bounded HTTP-style codes are safe to report.
    code = error.get("code") if isinstance(error, dict) else None
    if isinstance(code, str) and len(code) == 3 and code.isascii() and code.isdecimal():
        code = int(code)
    if type(code) is not int or not 100 <= code <= 599:
        code = None
    if code is not None:
        reason += f" (provider HTTP {code})"
    return OpenRouterError(f"HTTP {status} from {path}: {reason}", status_code=status, code=code)


def _decode_json(payload: bytes | str, path: str, status: int) -> dict:
    try:
        data = json.loads(payload)
    except ValueError:
        data = None
    # Raise outside the handler: parser exceptions may retain/quote the response, even with `from None`.
    if not isinstance(data, dict):
        raise _response_error(path, status, "invalid JSON response")
    if "error" in data:
        raise _response_error(path, status, "provider error", data["error"])
    return data


def _response_json(resp: httpx.Response, path: str) -> dict:
    if not resp.is_success:
        raise _response_error(path, resp.status_code, "request failed")
    return _decode_json(resp.content, path, resp.status_code)


@dataclass(slots=True)
class Transcript:
    text: str
    model: str
    latency_s: float
    audio_seconds: float | None = None
    cost_usd: float | None = None


@dataclass(slots=True)
class ChatResult:
    text: str
    model: str
    latency_s: float
    ttft_s: float | None = None
    cost_usd: float | None = None
    provider: str | None = None


@dataclass(slots=True)
class Account:
    """OpenRouter account balance and this key's usage (which includes other apps using the same key)."""

    balance: float | None  # credits bought minus credits used
    total_credits: float | None
    total_usage: float | None
    key_today: float
    key_week: float
    key_month: float
    key_limit_remaining: float | None  # the key's own spending cap, if one is set


def system_proxy() -> str | None:
    """Proxy URL from HTTPS_PROXY/HTTP_PROXY, else the Windows Internet Options proxy."""
    proxies = urllib.request.getproxies()
    url = proxies.get("https") or proxies.get("http")
    if url and "://" not in url:
        url = "http://" + url
    return url or None


class OpenRouterClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = API_BASE,
        proxy: str | None = None,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,  # tests inject httpx.MockTransport
    ) -> None:
        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise OpenRouterError("OPENROUTER_API_KEY is not set")
        self._http = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {key}", "X-Title": APP_TITLE},
            proxy=None if transport else (proxy or system_proxy()),
            transport=transport,
            trust_env=False,  # proxy already resolved above; don't let env vars override it
            timeout=httpx.Timeout(timeout, connect=10.0),
            # Keep the (proxied) TLS connection around between dictations; a cold connect costs ~0.7s.
            limits=httpx.Limits(keepalive_expiry=120.0),
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> OpenRouterClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ----- connection -----

    def warm_up(self) -> None:
        """Open the TLS connection (through the proxy) ahead of time, e.g. on hotkey press."""
        with contextlib.suppress(httpx.HTTPError):  # best effort; the real request surfaces errors
            self._http.get("/key", timeout=5.0)

    def check(self) -> None:
        """Raise OpenRouterError / NetworkError unless the key is accepted (first-run guide)."""
        self._get_data("/key")

    def account(self) -> Account:
        """GET /key and /credits (both free)."""
        key = self._get_data("/key")
        try:
            credits = self._get_data("/credits")
        except OpenRouterError:  # some keys may not read account credits; the key's usage still helps
            credits = {}
        bought, used = credits.get("total_credits"), credits.get("total_usage")
        return Account(
            balance=bought - used if bought is not None and used is not None else None,
            total_credits=bought,
            total_usage=used,
            key_today=key.get("usage_daily") or 0.0,
            key_week=key.get("usage_weekly") or 0.0,
            key_month=key.get("usage_monthly") or 0.0,
            key_limit_remaining=key.get("limit_remaining"),
        )

    def _get_data(self, path: str) -> dict:
        try:
            resp = self._http.get(path, timeout=10.0)
        except httpx.HTTPError as e:
            failure = NetworkError(f"network error calling {path} ({type(e).__name__})")
        else:
            data = _response_json(resp, path).get("data")
            if data is None:
                return {}
            if not isinstance(data, dict):
                raise _response_error(path, resp.status_code, "invalid account data")
            return data
        raise failure

    # ----- speech to text -----

    def transcribe(
        self,
        audio: bytes,
        audio_format: str,
        model: str,
        *,
        keywords: list[str] | None = None,
        languages: list[str] | None = None,
        prompt: str | None = None,
        provider: dict | None = None,  # routing prefs, e.g. {"data_collection": "deny"}
        timeout_s: float | None = None,  # whole-response deadline; raises RequestTimeout
    ) -> Transcript:
        body: dict = {
            "model": model,
            "input_audio": {"data": base64.b64encode(audio).decode("ascii"), "format": audio_format},
        }
        prefs = dict(provider or {})
        slug = _STT_HINT_PROVIDER.get(model)
        if slug:
            hints = {"keywords": keywords, "languages": languages, "prompt": prompt}
            hints = {k: v for k, v in hints.items() if v}
            if hints:
                prefs["options"] = {slug: hints}
        if prefs:
            body["provider"] = prefs
        t0 = time.perf_counter()
        try:
            data = self._post_json("/audio/transcriptions", body, timeout_s)
        except NetworkError:
            log.info("transcription hit a network error; retrying once on a fresh connection")
            data = self._post_json("/audio/transcriptions", body, timeout_s)
        usage = data.get("usage") or {}
        return Transcript(
            text=(data.get("text") or "").strip(),
            model=model,
            latency_s=time.perf_counter() - t0,
            audio_seconds=usage.get("seconds"),
            cost_usd=usage.get("cost"),
        )

    # ----- chat -----

    def chat(
        self,
        messages: list[dict],
        model: str,
        *,
        temperature: float | None = 0.0,
        max_tokens: int | None = None,
        extra: dict | None = None,
        on_delta: Callable[[str], None] | None = None,
        first_token_timeout_s: float | None = None,
    ) -> ChatResult:
        """Streaming chat completion; returns the full text plus timing and cost.

        `first_token_timeout_s`: give up with RequestTimeout when no text has arrived by then
        (OpenRouter's keep-alive comments do not count), so the caller can switch models.
        """
        body: dict = {"model": model, "messages": messages, "stream": True, "usage": {"include": True}}
        if temperature is not None:
            body["temperature"] = temperature
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        body.update(extra or {})

        t0 = time.perf_counter()
        ttft: float | None = None
        parts: list[str] = []
        served_model, provider, cost = model, None, None
        for attempt in (1, 2):
            try:
                for event in self._stream("/chat/completions", body, first_token_timeout_s):
                    if event is None:  # keep-alive comment
                        if ttft is None and first_token_timeout_s and time.perf_counter() - t0 > first_token_timeout_s:
                            raise RequestTimeout(f"{model}: no output after {first_token_timeout_s:.0f}s")
                        continue
                    served_model = event.get("model", served_model)
                    provider = event.get("provider", provider)
                    for choice in event.get("choices") or []:
                        piece = (choice.get("delta") or {}).get("content") or ""
                        if piece:
                            if ttft is None:
                                ttft = time.perf_counter() - t0
                            parts.append(piece)
                            if on_delta:
                                on_delta(piece)
                    if event.get("usage"):
                        cost = event["usage"].get("cost", cost)
                break
            except NetworkError:
                # Stale pooled connections through the local proxy occasionally die with an SSL EOF.
                # Retrying is only safe while nothing has been streamed to the caller yet.
                if attempt == 2 or parts:
                    raise
                log.info("chat stream hit a network error before any output; retrying once")
        return ChatResult(
            text="".join(parts).strip(),
            model=served_model,
            latency_s=time.perf_counter() - t0,
            ttft_s=ttft,
            cost_usd=cost,
            provider=provider,
        )

    # ----- plumbing -----

    @staticmethod
    def _timeout(read_s: float | None) -> httpx.Timeout | object:
        return httpx.Timeout(read_s, connect=10.0) if read_s else httpx.USE_CLIENT_DEFAULT

    def _post_json(self, path: str, body: dict, timeout_s: float | None = None) -> dict:
        try:
            resp = self._http.post(path, json=body, timeout=self._timeout(timeout_s))
        except httpx.TimeoutException as e:
            failure = RequestTimeout(f"timed out calling {path} ({type(e).__name__})")
        except httpx.HTTPError as e:
            failure = NetworkError(f"network error calling {path} ({type(e).__name__})")
        else:
            return _response_json(resp, path)
        raise failure

    def _stream(self, path: str, body: dict, read_timeout_s: float | None = None) -> Iterator[dict | None]:
        """Yield SSE `data:` payloads; yield None for keep-alive comments so callers can enforce deadlines."""
        try:
            with self._http.stream("POST", path, json=body, timeout=self._timeout(read_timeout_s)) as resp:
                if not resp.is_success:
                    raise _response_error(path, resp.status_code, "request failed")
                content_type = resp.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if content_type and content_type != "text/event-stream":
                    resp.read()
                    _decode_json(resp.content, path, resp.status_code)
                    raise _response_error(path, resp.status_code, "expected event stream")
                saw_event = False
                for line in resp.iter_lines():
                    # SSE: "data: {...}" events; ": OPENROUTER PROCESSING" comments keep the stream alive.
                    if not line.startswith("data:"):
                        if line.startswith(":"):
                            yield None
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        return
                    yield _decode_json(payload, path, resp.status_code)
                    saw_event = True
                if not saw_event:
                    raise _response_error(path, resp.status_code, "empty or invalid event stream")
        except httpx.TimeoutException as e:
            failure = RequestTimeout(f"timed out calling {path} ({type(e).__name__})")
        except httpx.HTTPError as e:
            failure = NetworkError(f"network error calling {path} ({type(e).__name__})")
        else:
            return
        raise failure
