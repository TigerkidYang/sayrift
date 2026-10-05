import pytest

from local_typeless.hotkeys import Bindings, HotkeyEngine, Mode, Phase
from local_typeless.keys import VK_ESCAPE, VK_LMENU, VK_RMENU, VK_RSHIFT, VK_SPACE, VK_TAB, parse_key

VK_A = ord("A")


class Rec:
    def __init__(self):
        self.events = []

    def on_start(self, mode):
        self.events.append(("start", mode))

    def on_mode(self, mode):
        self.events.append(("mode", mode))

    def on_finish(self):
        self.events.append(("finish",))

    def on_cancel(self):
        self.events.append(("cancel",))

    def on_abort(self):
        self.events.append(("abort",))


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def make(**kw):
    rec, clock, replays = Rec(), Clock(), []
    eng = HotkeyEngine(Bindings(), rec, clock=clock, replay_main_down=lambda: replays.append(1), **kw)
    return eng, rec, clock, replays


def test_tap_starts_and_second_tap_finishes():
    eng, rec, clock, _ = make()
    assert eng.handle(VK_RMENU, True) is True  # swallowed: apps never see Alt, no menu bar
    clock.t += 0.15
    assert eng.handle(VK_RMENU, False) is True
    assert eng.phase is Phase.LATCHED
    assert rec.events == [("start", Mode.DICTATE)]
    clock.t += 5  # speaking hands-free
    assert eng.handle(VK_RMENU, True) is True
    assert rec.events[-1] == ("finish",)
    assert eng.handle(VK_RMENU, False) is True
    assert eng.phase is Phase.IDLE


def test_hold_and_release_finishes_push_to_talk():
    eng, rec, clock, _ = make()
    eng.handle(VK_RMENU, True)
    clock.t += 3.0
    eng.handle(VK_RMENU, False)
    assert rec.events == [("start", Mode.DICTATE), ("finish",)]
    assert eng.phase is Phase.IDLE


def test_hold_to_talk_can_be_disabled_for_strict_toggle():
    rec, clock = Rec(), Clock()
    eng = HotkeyEngine(Bindings(hold_to_talk=False), rec, clock=clock)
    eng.handle(VK_RMENU, True)
    clock.t += 3.0
    eng.handle(VK_RMENU, False)  # long hold, but releasing does not finish
    assert eng.phase is Phase.LATCHED
    eng.handle(VK_RMENU, True)
    assert rec.events == [("start", Mode.DICTATE), ("finish",)]


def test_autorepeat_of_held_main_key_is_swallowed_and_ignored():
    eng, rec, _clock, _ = make()
    eng.handle(VK_RMENU, True)
    for _ in range(5):
        assert eng.handle(VK_RMENU, True) is True
    assert rec.events == [("start", Mode.DICTATE)]


@pytest.mark.parametrize(("chord", "mode"), [(VK_RSHIFT, Mode.TRANSLATE), (VK_SPACE, Mode.ASK)])
def test_chords_switch_mode_and_swallow_both_edges(chord, mode):
    eng, rec, clock, _ = make()
    eng.handle(VK_RMENU, True)
    assert eng.handle(chord, True) is True
    assert eng.handle(chord, True) is True  # auto-repeat
    assert eng.handle(chord, False) is True
    clock.t += 0.2
    eng.handle(VK_RMENU, False)  # quick chord tap -> latched, speak, press main to finish
    assert eng.phase is Phase.LATCHED
    eng.handle(VK_RMENU, True)
    assert rec.events == [("start", Mode.DICTATE), ("mode", mode), ("finish",)]


@pytest.mark.parametrize(("chord", "mode"), [(VK_RSHIFT, Mode.TRANSLATE), (VK_SPACE, Mode.ASK)])
def test_slow_chord_still_latches_like_the_official_docs(chord, mode):
    # Typeless: "press the Translate shortcut once ... speak ... press the main shortcut once".
    eng, rec, clock, _ = make()
    eng.handle(VK_RMENU, True)
    clock.t += 0.8
    eng.handle(chord, True)
    eng.handle(chord, False)
    clock.t += 1.0
    eng.handle(VK_RMENU, False)  # held well past the push-to-talk threshold
    assert eng.phase is Phase.LATCHED
    eng.handle(VK_RMENU, True)
    assert rec.events == [("start", Mode.DICTATE), ("mode", mode), ("finish",)]


def test_shift_first_then_main_also_latches():
    eng, _rec, clock, _ = make(is_down=lambda vk: vk == VK_RSHIFT)
    eng.handle(VK_RMENU, True)
    clock.t += 2.0
    eng.handle(VK_RMENU, False)
    assert eng.phase is Phase.LATCHED


def test_shift_already_down_when_main_pressed_starts_translate():
    eng, rec, _clock, _ = make(is_down=lambda vk: vk == VK_RSHIFT)
    eng.handle(VK_RMENU, True)
    assert rec.events == [("start", Mode.TRANSLATE)]


def test_escape_cancels_recording_and_is_swallowed():
    eng, rec, clock, _ = make()
    eng.handle(VK_RMENU, True)
    clock.t += 0.1
    eng.handle(VK_RMENU, False)
    assert eng.handle(VK_ESCAPE, True) is True
    assert eng.handle(VK_ESCAPE, False) is True
    assert rec.events[-1] == ("cancel",)
    assert eng.phase is Phase.IDLE


def test_escape_while_holding_main_swallows_the_later_main_release():
    eng, rec, clock, _ = make()
    eng.handle(VK_RMENU, True)
    eng.handle(VK_ESCAPE, True)
    clock.t += 2
    assert eng.handle(VK_RMENU, False) is True
    assert rec.events == [("start", Mode.DICTATE), ("cancel",)]  # no finish after cancel


def test_escape_cancels_processing_but_passes_through_when_idle():
    eng, rec, _clock, _ = make()
    assert eng.handle(VK_ESCAPE, True) is False
    eng.busy = True
    assert eng.handle(VK_ESCAPE, True) is True
    assert rec.events == [("cancel",)]


def test_main_key_ignored_while_busy():
    eng, rec, _clock, _ = make()
    eng.busy = True
    assert eng.handle(VK_RMENU, True) is True
    assert eng.handle(VK_RMENU, False) is True
    assert rec.events == []


def test_other_key_while_main_held_is_an_ordinary_shortcut():
    eng, rec, _clock, replays = make()
    eng.handle(VK_RMENU, True)
    assert eng.handle(VK_TAB, True) is False  # Tab goes through ...
    assert replays == [1]  # ... after the swallowed Alt key-down was replayed
    assert rec.events == [("start", Mode.DICTATE), ("abort",)]
    assert eng.handle(VK_TAB, False) is False
    assert eng.handle(VK_RMENU, False) is False  # the real key-up now goes through too
    assert eng.phase is Phase.IDLE


def test_typing_during_hands_free_recording_passes_through():
    eng, _rec, _clock, _ = make()
    eng.handle(VK_RMENU, True)
    eng.handle(VK_RMENU, False)
    assert eng.handle(VK_A, True) is False
    assert eng.handle(VK_A, False) is False
    assert eng.phase is Phase.LATCHED


def test_unrelated_keys_pass_when_idle():
    eng, rec, _clock, _ = make()
    for vk in (VK_A, VK_LMENU, VK_SPACE, VK_RSHIFT):
        assert eng.handle(vk, True) is False
        assert eng.handle(vk, False) is False
    assert rec.events == []


def test_main_key_up_without_down_passes_through():
    eng, _rec, _clock, _ = make()
    assert eng.handle(VK_RMENU, False) is False


def test_parse_key_names():
    assert parse_key("RightAlt") == VK_RMENU
    assert parse_key("right_shift") == VK_RSHIFT
    assert parse_key("F13") == 0x7C
    assert parse_key("a") == VK_A
    with pytest.raises(ValueError):
        parse_key("hyper")
