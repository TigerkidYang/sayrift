"""Known-good OpenRouter request settings per model, plus provider routing prefs.

Latency matters more than depth for dictation, so every text model runs with reasoning
disabled or at its minimum effort. Numbers in comments come from tools/bench_*.py runs;
see docs/models.md for the full results and how the defaults were chosen.
"""

from __future__ import annotations

# Request extras for chat models, merged into the /chat/completions body.
CHAT_PRESETS: dict[str, dict] = {
    "deepseek/deepseek-v4.1-flash": {"reasoning": {"enabled": False}},  # default: 57/57 checks, ~0.5-1.3s
    "qwen/qwen3.8-flash": {"reasoning": {"enabled": False}},  # former fallback: 55/57; upstream 429s in 2026-09
    "openai/gpt-5.6-luna": {"reasoning": {"effort": "none"}},
    "openai/gpt-6-luna": {"reasoning": {"effort": "none"}},  # fallback since 2026-09-27: polish 74/81, Ask 27/28
    "openai/gpt-5.4-nano": {"reasoning": {"effort": "none"}},
    "google/gemini-3.1-flash-lite": {"reasoning": {"effort": "minimal"}},  # dropped content on long input
    "google/gemini-3.5-flash-lite": {"reasoning": {"effort": "minimal"}},
    "google/gemini-3.8-flash": {"reasoning": {"effort": "low"}},
    "qwen/qwen3.7-flash": {"reasoning": {"enabled": False}},
    "xiaomi/mimo-v2.6-flash": {"reasoning": {"enabled": False}},
    "bytedance-seed/seed-2.0-mini": {"reasoning": {"effort": "minimal"}},
    "mistralai/mistral-small-2603": {"reasoning": {"effort": "none"}},
    "inception/mercury-2.5": {"reasoning": {"effort": "none"}},
    "nvidia/nemotron-3.5-lightning": {"reasoning": {"enabled": False}},
    "moonshotai/kimi-k2.6": {"reasoning": {"enabled": False}},
    "anthropic/claude-haiku-4.5": {},
}


def provider_prefs(*, low_latency: bool = True, deny_data_collection: bool = True, zdr: bool = False) -> dict:
    """OpenRouter `provider` routing object.

    - sort=latency: pick the endpoint with the lowest recent time-to-first-token.
    - data_collection=deny: skip providers that store/train on prompts.
    - zdr: only zero-data-retention endpoints (stricter; a model without one will fail).
    """
    prefs: dict = {}
    if low_latency:
        prefs["sort"] = "latency"
    if deny_data_collection:
        prefs["data_collection"] = "deny"
    if zdr:
        prefs["zdr"] = True
    return prefs


def chat_extra(model: str, provider: dict | None = None) -> dict:
    """Body extras for a chat request: model preset + provider routing prefs."""
    extra = dict(CHAT_PRESETS.get(model, {}))
    extra["provider"] = provider if provider is not None else provider_prefs()
    return extra
