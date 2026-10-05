"""Prompt templates and message builders.

Layout rule (keeps provider prefix caching effective): the *system* message depends only
on stable user settings; everything that changes per request (app, window title,
selected text, transcript) goes into the *user* message.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from importlib.resources import files

CJK_SPACING_ON = (
    "Put one space between Chinese characters and an adjacent Latin-letter word "
    "(用 Python 写, 更新 README 文件); do not add spaces around numbers (下午4点, 3个)."
)
CJK_SPACING_OFF = (
    "Do not insert spaces between Chinese characters and English words or numbers "
    "(this overrides the spacing shown in the examples)."
)


@cache
def load(name: str) -> str:
    return files(__package__).joinpath(f"{name}.md").read_text(encoding="utf-8")


@dataclass(slots=True)
class Context:
    """Per-request context gathered from the foreground app and user settings."""

    app: str | None = None  # process name, e.g. "WeChat.exe"
    window_title: str | None = None
    dictionary: list[str] = field(default_factory=list)
    style: str | None = None  # free-form user style note for this app, if any


def _context_block(ctx: Context) -> str:
    lines = []
    if ctx.app:
        lines.append(f"App: {ctx.app}")
    if ctx.window_title:
        lines.append(f"Window title: {ctx.window_title}")
    if ctx.style:
        lines.append(f"User style preference: {ctx.style}")
    if ctx.dictionary:
        lines.append("Personal dictionary: " + ", ".join(ctx.dictionary))
    return "<context>\n" + "\n".join(lines) + "\n</context>\n" if lines else ""


def dictation_system(*, cjk_spacing: bool = True) -> str:
    return load("dictation").replace("{{cjk_spacing_rule}}", CJK_SPACING_ON if cjk_spacing else CJK_SPACING_OFF)


def _user_message(transcript: str, ctx: Context | None) -> str:
    return _context_block(ctx or Context()) + f"<transcript>{transcript}</transcript>"


def dictation_messages(transcript: str, ctx: Context | None = None, *, cjk_spacing: bool = True) -> list[dict]:
    return [
        {"role": "system", "content": dictation_system(cjk_spacing=cjk_spacing)},
        {"role": "user", "content": _user_message(transcript, ctx)},
    ]


def translate_messages(transcript: str, ctx: Context | None = None, *, target_language: str) -> list[dict]:
    system = load("translate").replace("{{target_language}}", target_language)
    return [{"role": "system", "content": system}, {"role": "user", "content": _user_message(transcript, ctx)}]


def ask_messages(spoken: str, ctx: Context | None = None, *, selection: str | None = None) -> list[dict]:
    user = _context_block(ctx or Context())
    if selection:
        user += f"<selection>\n{selection}\n</selection>\n"
    user += f"<spoken>{spoken}</spoken>"
    return [{"role": "system", "content": load("ask")}, {"role": "user", "content": user}]


ASK_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "ask_result",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["replace", "insert", "answer"]},
                "text": {"type": "string"},
            },
            "required": ["action", "text"],
            "additionalProperties": False,
        },
    },
}
