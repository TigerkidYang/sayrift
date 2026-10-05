"""Controller logic with fakes: no hook, no microphone, no network, no clipboard."""

import threading
from dataclasses import dataclass

from local_typeless.app import App, State
from local_typeless.audio import Recording
from local_typeless.config import Config
from local_typeless.hotkeys import Mode
from local_typeless.keys import VK_ESCAPE, VK_RMENU, VK_RSHIFT, VK_SPACE
from local_typeless.openrouter import ChatResult, OpenRouterError, Transcript
from local_typeless.sounds import Sounds


@dataclass
class Target:
    exe: str = "Weixin.exe"
    title: str = "微信"


class FakeAudio:
    def __init__(self, speech=True, duration=2.0):
        self.speech, self.duration, self.calls = speech, duration, []

    def start(self):
        self.calls.append("start")

    def stop(self):
        self.calls.append("stop")
        return Recording(b"ogg", "ogg", self.duration, self.speech, 1000.0)

    def cancel(self):
        self.calls.append("cancel")


class FakeClient:
    def __init__(self, text="嗯，你好", polished="你好", fail=False, gate=None):
        self.text, self.polished, self.fail, self.gate = text, polished, fail, gate
        self.chats = []

    def warm_up(self):
        pass

    def transcribe(self, audio, fmt, model, **kw):
        if self.gate:
            self.gate.wait(2)
        if self.fail:
            raise OpenRouterError("boom")
        return Transcript(self.text, model, 0.1)

    def chat(self, messages, model, **kw):
        self.chats.append(messages)
        return ChatResult(self.polished, model, 0.1)


class FakePaster:
    def __init__(self):
        self.pasted = []

    def paste(self, text, target):
        self.pasted.append((text, target))

        class R:
            ok, method, detail = True, "fake", ""

        return R()


def make_app(**kw):
    cfg = Config()
    audio = kw.pop("audio", FakeAudio())
    client = kw.pop("client", FakeClient())
    paster = FakePaster()
    app = App(
        cfg,
        client=client,
        audio=audio,
        paster=paster,
        sounds=Sounds(enabled=False),
        foreground=lambda: Target(),
        select_text=kw.pop("select_text", lambda target: None),
        show_card=kw.pop("show_card", None),
        install_hook=False,
    )
    return app, audio, client, paster


def ask_chord(app):
    app.engine.handle(VK_RMENU, True)
    app.engine.handle(VK_SPACE, True)
    app.engine.handle(VK_SPACE, False)
    app.engine.handle(VK_RMENU, False)


def tap(app, vk=VK_RMENU):
    app.engine.handle(vk, True)
    app.engine.handle(vk, False)


def test_tap_speak_tap_inserts_cleaned_text_into_the_starting_window():
    app, audio, client, paster = make_app()
    tap(app)  # start (latched)
    app.process_pending(0.2)
    assert app.state is State.RECORDING
    tap(app)  # finish
    app.process_pending()
    assert audio.calls == ["start", "stop"]
    assert paster.pasted == [("你好", Target())]
    assert "Weixin.exe" in client.chats[0][1]["content"]  # app context reaches the prompt
    assert app.state is State.IDLE and app.engine.busy is False


def test_no_speech_means_no_api_call_and_no_paste():
    app, _audio, client, paster = make_app(audio=FakeAudio(speech=False))
    tap(app)
    tap(app)
    app.process_pending()
    assert paster.pasted == [] and client.chats == []
    assert app.state is State.IDLE


def test_escape_while_recording_discards_audio():
    app, audio, _client, paster = make_app()
    tap(app)
    app.process_pending(0.2)
    tap(app, VK_ESCAPE)
    app.process_pending()
    assert audio.calls == ["start", "cancel"]
    assert paster.pasted == []


def test_escape_while_processing_drops_the_result():
    gate = threading.Event()
    app, _audio, _client, paster = make_app(client=FakeClient(gate=gate))
    tap(app)
    tap(app)
    app.process_pending(0.2)
    assert app.state is State.PROCESSING and app.engine.busy
    tap(app, VK_ESCAPE)  # Esc cancels processing (swallowed because busy)
    app.process_pending(0.2)
    assert app.state is State.IDLE
    gate.set()
    app.process_pending(1.0)  # the late result arrives and is discarded
    assert paster.pasted == []


def test_api_failure_returns_to_idle_without_pasting():
    app, _audio, _client, paster = make_app(client=FakeClient(fail=True))
    tap(app)
    tap(app)
    app.process_pending()
    assert paster.pasted == [] and app.state is State.IDLE


def test_missing_api_key_starts_anyway_and_reports_it(monkeypatch):
    monkeypatch.setattr("local_typeless.app.api_key", lambda: None)
    app, _audio, _client, paster = make_app(client=None)  # constructing the controller must not need a key
    errors = []
    app.ui.error = errors.append
    tap(app)
    tap(app)
    app.process_pending()
    assert paster.pasted == [] and app.state is State.IDLE
    assert errors == ["err.no_key"]


def test_translate_chord_uses_translation_prompt():
    app, _audio, client, paster = make_app(client=FakeClient(text="你好", polished="Hello"))
    app.engine.handle(VK_RMENU, True)
    app.engine.handle(VK_RSHIFT, True)
    app.engine.handle(VK_RSHIFT, False)
    app.engine.handle(VK_RMENU, False)
    app.process_pending(0.2)
    assert app.session.mode is Mode.TRANSLATE
    tap(app)
    app.process_pending()
    assert "translated into English" in client.chats[0][0]["content"]
    assert paster.pasted[0][0] == "Hello"


def test_ask_with_selection_replaces_it():
    reply = '{"action": "replace", "text": "明天我因身体不适无法到岗。"}'
    app, _audio, client, paster = make_app(
        client=FakeClient(text="改正式一点", polished=reply), select_text=lambda target: "明天我不来了"
    )
    ask_chord(app)
    app.process_pending(0.2)
    assert app.session.selection == "明天我不来了"
    tap(app)
    app.process_pending()
    assert "<selection>\n明天我不来了\n</selection>" in client.chats[0][1]["content"]
    assert paster.pasted == [("明天我因身体不适无法到岗。", Target())]  # pasting over the selection replaces it


def test_ask_question_shows_an_answer_card_and_leaves_the_document_alone():
    cards = []
    reply = '{"action": "answer", "text": "巴黎。"}'
    app, _audio, _client, paster = make_app(
        client=FakeClient(text="法国的首都是哪里", polished=reply), show_card=lambda q, a: cards.append((q, a))
    )
    ask_chord(app)
    tap(app)
    app.process_pending()
    assert cards == [("法国的首都是哪里", "巴黎。")]
    assert paster.pasted == []


def test_ask_help_me_write_inserts_at_the_cursor():
    reply = '```json\n{"action": "insert", "text": "王经理您好，项目需要延期一周。"}\n```'
    app, _audio, _client, paster = make_app(client=FakeClient(text="帮我写封邮件", polished=reply))
    ask_chord(app)
    tap(app)
    app.process_pending()
    assert paster.pasted == [("王经理您好，项目需要延期一周。", Target())]


def test_voice_bar_buttons_finish_and_cancel():
    app, audio, _client, paster = make_app()
    tap(app)  # latched
    app.process_pending(0.2)
    app.request_finish()  # ✓ on the Voice bar
    app.process_pending()
    assert paster.pasted == [("你好", Target())]
    assert app.engine.phase.name == "IDLE"  # the next Right Alt press starts a new session

    tap(app)
    app.process_pending(0.2)
    app.request_cancel()  # × on the Voice bar
    app.process_pending()
    assert audio.calls[-1] == "cancel" and len(paster.pasted) == 1


def test_apply_settings_rebinds_hotkeys_without_restart():
    app, audio, _client, _paster = make_app()
    app.cfg.hotkeys.main = "F13"
    app.apply_settings()
    tap(app, VK_RMENU)  # the old key no longer starts anything
    app.process_pending(0.2)
    assert audio.calls == []
    tap(app, 0x7C)  # F13
    app.process_pending(0.2)
    assert audio.calls == ["start"]


def test_stale_limit_event_does_not_end_a_later_session():
    app, audio, _client, _paster = make_app()
    tap(app)
    app.process_pending(0.2)
    app.dispatch(("finish", ("limit", app.session.id + 1)))  # a timer from some other session
    assert app.state is State.RECORDING
    app.dispatch(("finish", ("limit", app.session.id)))
    assert audio.calls == ["start", "stop"]


def test_max_length_finishes_the_session():
    app, _audio, _client, paster = make_app()
    app.cfg.audio.max_seconds = 0.05
    tap(app)
    app.process_pending(1.0)
    assert paster.pasted == [("你好", Target())]
    assert app.engine.phase.name == "IDLE"


def test_sessions_are_recorded_in_history_with_audio(tmp_path):
    from local_typeless.store import History

    app, _audio, _client, _paster = make_app()
    app.history = History(tmp_path / "h.sqlite")
    tap(app)
    tap(app)
    app.process_pending()
    (entry,) = app.history.list()
    assert (entry.mode, entry.status, entry.app, entry.raw, entry.text) == (
        "dictate", "inserted", "Weixin.exe", "嗯，你好", "你好",
    )  # fmt: skip
    assert app.history.audio(entry.id) == (b"ogg", "ogg")
    asr, llm = sorted(app.history.usage_log(), key=lambda u: u.stage)  # one spend-log row per model call
    assert (asr.stage, asr.mode, llm.stage) == ("asr", "dictate", "llm") and asr.created_at == llm.created_at


def test_failed_sessions_are_recorded_for_retry(tmp_path):
    from local_typeless.store import History

    app, _audio, _client, _paster = make_app(client=FakeClient(fail=True))
    app.history = History(tmp_path / "h.sqlite")
    tap(app)
    tap(app)
    app.process_pending()
    (entry,) = app.history.list()
    assert entry.status == "failed" and entry.error
    assert app.history.audio(entry.id) is not None


def test_capture_next_key_takes_the_key_instead_of_starting_a_session():
    from types import SimpleNamespace as K

    app, audio, _client, _paster = make_app()
    got = []
    app.capture_next_key(got.append)
    assert app._on_key(K(vk=VK_RMENU, down=True)) is True  # swallowed, delivered to the settings UI
    assert app._on_key(K(vk=VK_RMENU, down=False)) is True
    app.process_pending(0.2)
    assert got == [VK_RMENU] and audio.calls == []
    assert app._on_key(K(vk=VK_RMENU, down=True)) is True  # capture is one-shot: hotkeys work again
    app.process_pending(0.2)
    assert audio.calls == ["start"]


def test_retry_reprocesses_stored_audio(tmp_path):
    from local_typeless.store import History

    app, _audio, client, _paster = make_app(client=FakeClient(fail=True))
    app.history = History(tmp_path / "h.sqlite")
    tap(app)
    tap(app)
    app.process_pending()
    (entry,) = app.history.list()
    assert entry.status == "failed"
    client.fail = False
    app._retry(entry.id)
    (entry,) = app.history.list()
    assert (entry.status, entry.text) == ("retried", "你好")
