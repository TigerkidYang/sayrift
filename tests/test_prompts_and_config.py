from pathlib import Path

import pytest

from local_typeless import config, prompts


def test_system_prompt_is_static_and_spacing_rule_is_filled():
    on = prompts.dictation_system(cjk_spacing=True)
    off = prompts.dictation_system(cjk_spacing=False)
    assert "{{" not in on and "{{" not in off
    assert prompts.CJK_SPACING_ON in on
    assert prompts.CJK_SPACING_OFF in off


def test_dynamic_context_goes_to_user_message_only():
    ctx = prompts.Context(app="Weixin.exe", window_title="微信", dictionary=["OpenRouter"])
    msgs = prompts.dictation_messages("嗯，你好", ctx)
    system, user = msgs[0]["content"], msgs[1]["content"]
    # system prompt must not vary per request (prefix caching)
    assert system == prompts.dictation_messages("别的", prompts.Context())[0]["content"]
    assert "Weixin.exe" in user and "OpenRouter" in user
    assert user.endswith("<transcript>嗯，你好</transcript>")


def test_no_context_block_when_empty():
    user = prompts.dictation_messages("hi")[1]["content"]
    assert user == "<transcript>hi</transcript>"


def test_config_defaults_and_overrides(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text('dictionary = ["Claude Code"]\n[polish]\nmodel = "x/y"\n', encoding="utf-8")
    cfg = config.load(p)
    assert cfg.polish.model == "x/y"
    assert cfg.polish.cjk_spacing is True  # untouched default
    assert cfg.asr.model == "openai/gpt-transcribe"
    assert cfg.dictionary == ["Claude Code"]


def test_config_rejects_unknown_keys(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text("[polish]\nmodle = 'typo'\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"polish\.'modle'"):
        config.load(p)


def test_save_writes_only_changes_and_round_trips(tmp_path: Path):
    cfg = config.Config()
    cfg.dictionary = ['Claude "Code"', "张三"]
    cfg.hotkeys.hold_to_talk = False
    cfg.audio.max_seconds = 300
    cfg.translate.targets = ["日本語", "English"]
    p = tmp_path / "config.toml"
    config.save(cfg, p)
    text = p.read_text(encoding="utf-8")
    assert "[asr]" not in text  # untouched sections are not written
    assert config.load(p) == cfg


def test_missing_config_file_gives_defaults(tmp_path: Path):
    assert config.load(tmp_path / "nope.toml") == config.Config()
