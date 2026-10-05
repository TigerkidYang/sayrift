from local_typeless import pipeline, prompts
from local_typeless.config import Config
from local_typeless.openrouter import ChatResult, OpenRouterError, Transcript


class FakeClient:
    """Stands in for OpenRouterClient; records calls, fails for models in `broken`."""

    def __init__(self, transcript="嗯，你好", polished="你好", broken=()):
        self.transcript, self.polished, self.broken = transcript, polished, set(broken)
        self.calls = []

    def transcribe(self, audio, fmt, model, **hints):
        self.calls.append(("asr", model, hints))
        if model in self.broken:
            raise OpenRouterError("down")
        return Transcript(self.transcript, model, 0.1)

    def chat(self, messages, model, **kw):
        self.calls.append(("chat", model, messages))
        self.chat_kwargs = kw
        if model in self.broken:
            raise OpenRouterError("down")
        return ChatResult(self.polished + "  \n", model, 0.2)


def test_dictate_runs_asr_then_polish_with_dictionary_hints():
    cfg = Config(dictionary=["OpenRouter"])
    client = FakeClient()
    res = pipeline.dictate(client, cfg, b"audio", "ogg", prompts.Context(app="Weixin.exe"))
    assert (res.raw, res.text) == ("嗯，你好", "你好")  # trailing whitespace tidied
    kind, model, hints = client.calls[0]
    assert (kind, model) == ("asr", cfg.asr.model)
    assert hints["keywords"] == ["OpenRouter"]
    assert hints["provider"] == {"data_collection": "deny"}  # privacy routing on by default
    user_msg = client.calls[1][2][1]["content"]
    assert "Weixin.exe" in user_msg and "OpenRouter" in user_msg


def test_chat_request_carries_preset_and_routing():
    cfg = Config()
    cfg.openrouter.zdr = True
    client = FakeClient()
    pipeline.dictate(client, cfg, b"audio", "ogg")
    extra = client.chat_kwargs["extra"]
    assert extra["reasoning"] == {"enabled": False}  # deepseek preset
    assert extra["provider"] == {"sort": "latency", "data_collection": "deny", "zdr": True}


def test_falls_back_when_primary_models_fail():
    cfg = Config()
    client = FakeClient(broken={cfg.asr.model, cfg.polish.model})
    res = pipeline.dictate(client, cfg, b"audio", "ogg")
    assert res.asr.model == cfg.asr.fallback_model
    assert res.polish.model == cfg.polish.fallback_model


def test_request_deadlines_are_passed_down():
    cfg = Config()
    client = FakeClient()
    pipeline.dictate(client, cfg, b"x" * 30_000, "ogg")
    assert client.calls[0][2]["timeout_s"] == 15.0  # short clip -> floor
    assert client.chat_kwargs["first_token_timeout_s"] == cfg.polish.first_token_timeout_s
    assert pipeline.asr_timeout(b"x" * 1_600_000) == 170.0  # ~9 min of Opus


def test_polish_disabled_returns_raw():
    cfg = Config()
    cfg.polish.enabled = False
    client = FakeClient()
    res = pipeline.dictate(client, cfg, b"audio", "ogg")
    assert res.text == "嗯，你好" and res.polish is None
    assert [c[0] for c in client.calls] == ["asr"]


def test_guard_maps_placeholders_to_empty():
    assert pipeline.guard("嗯。", "（空）") == ""
    assert pipeline.guard("um", "(empty)") == ""


def test_guard_falls_back_to_transcript_when_model_answers():
    raw = "你觉得我们应该用 Python 还是 Rust？"
    answer = "这取决于你的需求。" * 20
    assert pipeline.guard(raw, answer) == raw


def test_guard_keeps_normal_cleanup_including_list_formatting():
    raw = "这周要做三件事第一把录音模块写完第二接上OpenRouter的接口第三写一个简单的设置界面"
    cleaned = "这周要做三件事：\n1. 把录音模块写完\n2. 接上 OpenRouter 的接口\n3. 写一个简单的设置界面"
    assert pipeline.guard(raw, cleaned) == cleaned


def test_parse_ask_accepts_json_with_noise_and_falls_back_safely():
    assert pipeline.parse_ask('{"action":"replace","text":"新"}', has_selection=True) == ("replace", "新")
    assert pipeline.parse_ask('Sure!\n```json\n{"action":"answer","text":"巴黎"}\n```', has_selection=False) == (
        "answer",
        "巴黎",
    )
    # "replace" without a selection has nothing to replace: insert at the cursor instead
    assert pipeline.parse_ask('{"action":"replace","text":"x"}', has_selection=False) == ("insert", "x")
    # unknown action / not JSON: show it rather than typing it into the document
    assert pipeline.parse_ask('{"action":"delete","text":"x"}', has_selection=True) == ("answer", "x")
    assert pipeline.parse_ask("just some prose", has_selection=False) == ("answer", "just some prose")


def test_empty_transcript_skips_polish():
    client = FakeClient(transcript="")
    res = pipeline.dictate(client, Config(), b"audio", "ogg")
    assert res.text == "" and [c[0] for c in client.calls] == ["asr"]
