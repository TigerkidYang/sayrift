"""Settings page. Every change is saved and applied immediately (no Save button)."""

from __future__ import annotations

import os
import sys
import threading

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QProgressBar, QPushButton, QVBoxLayout, QWidget

from .. import __version__, config, keys
from .i18n import tr
from .pages import Context, header, scroll_page
from .widgets import IconButton, KeyCap, SettingRow, Toggle, divider, label, section

# Target languages offered in the picker: (value sent to the model, label in Chinese, label in English).
LANGUAGES = [
    ("English", "英语", "English"),
    ("Simplified Chinese", "简体中文", "Simplified Chinese"),
    ("Traditional Chinese", "繁体中文", "Traditional Chinese"),
    ("Japanese", "日语", "Japanese"),
    ("Korean", "韩语", "Korean"),
    ("French", "法语", "French"),
    ("German", "德语", "German"),
    ("Spanish", "西班牙语", "Spanish"),
    ("Portuguese", "葡萄牙语", "Portuguese"),
    ("Russian", "俄语", "Russian"),
    ("Italian", "意大利语", "Italian"),
]
MAX_TARGETS = 3  # Typeless: up to 3 translation targets


def lang_label(value: str) -> str:
    from .i18n import language

    for v, zh, en in LANGUAGES:
        if v == value:
            return zh if language() == "zh" else en
    return value


class _KeySignal(QObject):
    got = Signal(int)


class HotkeyField(QWidget):
    """Shows the current key as a key cap; 'Change' records the next key press."""

    def __init__(self, ctx: Context, attr: str) -> None:
        super().__init__()
        self.ctx, self.attr = ctx, attr
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.cap = KeyCap("")
        row.addWidget(self.cap)
        self.button = QPushButton(tr("set.shortcut.change"))
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.clicked.connect(self._start)
        row.addWidget(self.button)
        self._signal = _KeySignal()
        self._signal.got.connect(self._got)
        self._recording = False
        self._show()

    def _show(self) -> None:
        self.cap.setText(keys.display(getattr(self.ctx.cfg.hotkeys, self.attr)))

    def _start(self) -> None:
        if self._recording:  # second click cancels
            self.ctx.cancel_capture()
            self._stop()
            return
        self._recording = True
        self.cap.setText(tr("set.shortcut.press"))
        self.button.setText(tr("set.shortcut.cancel"))
        self.ctx.capture_key(self._signal.got.emit)  # called on the hook thread; the signal hops to the GUI

    def _stop(self) -> None:
        self._recording = False
        self.button.setText(tr("set.shortcut.change"))
        self._show()

    def _got(self, vk: int) -> None:
        name = keys.name_for(vk)
        if name:
            setattr(self.ctx.cfg.hotkeys, self.attr, name)
            self.ctx.save()
        self._stop()


class MicTest(QWidget):
    """Five-second live level meter for the chosen microphone."""

    def __init__(self, ctx: Context, seconds: float | None = 5.0) -> None:
        """`seconds=None` keeps listening until hidden (the first-run guide)."""
        super().__init__()
        self.ctx = ctx
        self.seconds = seconds
        self.peak = 0.0  # loudest level seen since start, 0..1
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.bar.setStyleSheet(
            f"QProgressBar {{ background: {ctx.palette.surface2}; border: none; border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {ctx.palette.accent}; border-radius: 3px; }}"
        )
        row.addWidget(self.bar, 1)
        self.button = QPushButton(tr("set.mic.test"))
        self.button.clicked.connect(self.start)
        row.addWidget(self.button)
        self._level = 0.0
        self._stream = None
        self._poll = QTimer(self, interval=40, timeout=self._update)
        self._stop_timer = QTimer(self, singleShot=True, interval=5000, timeout=self.stop)

    def start(self) -> None:
        import numpy as np
        import sounddevice as sd

        from ..audio import SAMPLE_RATE, resolve_device

        self.stop()
        device, extra = resolve_device(self.ctx.cfg.audio.device or None)

        def callback(indata, frames, t, status) -> None:
            self._level = float(np.sqrt(np.mean(indata[:, 0].astype(np.float32) ** 2)))

        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                device=device,
                extra_settings=extra,
                callback=callback,
            )
            self._stream.start()
        except sd.PortAudioError:
            self.button.setText("✕")
            return
        self.button.setText(tr("set.mic.testing"))
        self.peak = 0.0
        self._poll.start()
        if self.seconds is not None:
            self._stop_timer.start(int(self.seconds * 1000))

    def _update(self) -> None:
        from .overlay import level_to_height

        height = level_to_height(self._level)
        self.peak = max(self.peak, height)
        self.bar.setValue(int(height * 100))

    def stop(self) -> None:
        self._poll.stop()
        if self._stream is not None:
            stream, self._stream = self._stream, None
            threading.Thread(target=stream.close, daemon=True).start()  # closing can take ~40 ms
        self.bar.setValue(0)
        self.button.setText(tr("set.mic.test"))

    def hideEvent(self, event) -> None:
        self.stop()
        super().hideEvent(event)


class TargetList(QWidget):
    """Ordered translation targets (first = current), up to three."""

    def __init__(self, ctx: Context) -> None:
        super().__init__()
        self.ctx = ctx
        self.col = QVBoxLayout(self)
        self.col.setContentsMargins(0, 4, 0, 0)
        self.col.setSpacing(6)
        self.refresh()

    def refresh(self) -> None:
        while self.col.count():
            item = self.col.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
                item.widget().deleteLater()
        targets = self.ctx.cfg.translate.targets
        p = self.ctx.palette
        for i, lang in enumerate(targets):
            row = QWidget()
            lay = QHBoxLayout(row)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(label(f"{i + 1}.", "Faint"))
            lay.addWidget(label(lang_label(lang)), 1)
            if i > 0:
                lay.addWidget(IconButton("up", "↑", p, lambda _=False, i=i: self._move(i, -1)))
            if len(targets) > 1:
                lay.addWidget(IconButton("x", "✕", p, lambda _=False, i=i: self._remove(i)))
            self.col.addWidget(row)
        if len(targets) < MAX_TARGETS:
            pick = QComboBox()
            pick.addItem(tr("set.targets.add"), None)
            for value, _zh, _en in LANGUAGES:
                if value not in targets:
                    pick.addItem(lang_label(value), value)
            pick.activated.connect(lambda idx, box=pick: self._add(box.itemData(idx)))
            self.col.addWidget(pick)

    def _save(self, targets: list[str]) -> None:
        self.ctx.cfg.translate.targets = targets
        self.ctx.save()
        QTimer.singleShot(0, self.refresh)

    def _move(self, i: int, delta: int) -> None:
        t = list(self.ctx.cfg.translate.targets)
        t[i], t[i + delta] = t[i + delta], t[i]
        self._save(t)

    def _remove(self, i: int) -> None:
        self._save([x for j, x in enumerate(self.ctx.cfg.translate.targets) if j != i])

    def _add(self, value: str | None) -> None:
        if value:
            self._save([*self.ctx.cfg.translate.targets, value])


def combo(options: list[tuple[str, str]], current: str, on_change) -> QComboBox:
    box = QComboBox()
    for value, text in options:
        box.addItem(text, value)
    idx = box.findData(current)
    box.setCurrentIndex(max(0, idx))
    box.currentIndexChanged.connect(lambda i: on_change(box.itemData(i)))
    box.setMinimumWidth(180)
    box.setMaximumWidth(340)  # long microphone names must not stretch the row
    return box


def mic_options() -> list[tuple[str, str]]:
    options = [("", tr("set.mic.auto"))]
    try:
        import sounddevice as sd

        wasapi = next((i for i, a in enumerate(sd.query_hostapis()) if a["name"] == "Windows WASAPI"), None)
        for dev in sd.query_devices():
            if dev["max_input_channels"] > 0 and dev["hostapi"] == wasapi:
                options.append((dev["name"], dev["name"]))
    except Exception:  # no audio stack: offer the default only
        pass
    return options


class SettingsPage(QWidget):
    def __init__(self, ctx: Context, *, on_theme_or_language: callable) -> None:
        super().__init__()
        self.ctx = ctx
        cfg, p = ctx.cfg, ctx.palette
        area, lay = scroll_page()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(area)
        lay.addWidget(header(tr("settings.title")))

        def toggle(obj, attr: str, after=None) -> Toggle:
            t = Toggle(p, bool(getattr(obj, attr)))

            def changed(on: bool) -> None:
                setattr(obj, attr, on)
                ctx.save()
                if after:
                    after(on)

            t.toggled.connect(changed)
            return t

        def setter(obj, attr: str, after=None):
            def apply(value) -> None:
                setattr(obj, attr, value)
                ctx.save()
                if after:
                    after(value)

            return apply

        # Shortcuts
        card, body = section(tr("set.shortcuts"))
        body.addWidget(SettingRow(tr("set.shortcut.main"), HotkeyField(ctx, "main"), tr("set.shortcut.main.desc")))
        body.addWidget(divider(p))
        body.addWidget(
            SettingRow(tr("set.shortcut.translate"), HotkeyField(ctx, "translate"), tr("set.shortcut.translate.desc"))
        )
        body.addWidget(divider(p))
        body.addWidget(SettingRow(tr("set.shortcut.ask"), HotkeyField(ctx, "ask"), tr("set.shortcut.ask.desc")))
        body.addWidget(divider(p))
        body.addWidget(SettingRow(tr("set.hold"), toggle(cfg.hotkeys, "hold_to_talk"), tr("set.hold.desc")))
        lay.addWidget(card)

        # Microphone & sounds
        card, body = section(tr("set.audio"))
        body.addWidget(SettingRow(tr("set.mic"), combo(mic_options(), cfg.audio.device, setter(cfg.audio, "device"))))
        body.addWidget(MicTest(ctx))
        body.addWidget(divider(p))
        body.addWidget(SettingRow(tr("set.sounds"), toggle(cfg.audio, "sounds"), tr("set.sounds.desc")))
        lay.addWidget(card)

        # Translation
        card, body = section(tr("set.translate"))
        body.addWidget(label(tr("set.targets.desc"), "Faint"))
        body.addWidget(TargetList(ctx))
        lay.addWidget(card)

        # History
        card, body = section(tr("set.history"))
        keep = [(k, tr(f"keep.{k}")) for k in ("forever", "1y", "1m", "1w", "24h", "never")]
        body.addWidget(SettingRow(tr("set.keep"), combo(keep, cfg.history.keep, setter(cfg.history, "keep"))))
        body.addWidget(divider(p))
        body.addWidget(SettingRow(tr("set.keep_audio"), toggle(cfg.history, "keep_audio"), tr("set.keep_audio.desc")))
        lay.addWidget(card)

        # General
        card, body = section(tr("set.general"))
        auto = Toggle(p, _autostart_enabled())
        auto.toggled.connect(_set_autostart)
        body.addWidget(SettingRow(tr("set.autostart"), auto))
        body.addWidget(divider(p))
        themes = [(k, tr(f"theme.{k}")) for k in ("system", "light", "dark")]
        body.addWidget(
            SettingRow(tr("set.theme"), combo(themes, cfg.app.theme, setter(cfg.app, "theme", on_theme_or_language)))
        )
        body.addWidget(divider(p))
        langs = [("auto", tr("lang.auto")), ("zh", "中文"), ("en", "English")]
        body.addWidget(
            SettingRow(
                tr("set.language"), combo(langs, cfg.app.language, setter(cfg.app, "language", on_theme_or_language))
            )
        )
        lay.addWidget(card)

        # Advanced
        card, body = section(tr("set.advanced"))
        for title, obj, attr, placeholder in (
            (tr("set.asr_model"), cfg.asr, "model", ""),
            (tr("set.llm_model"), cfg.polish, "model", ""),
            (tr("set.proxy"), cfg.openrouter, "proxy", tr("set.proxy.placeholder")),
        ):
            edit = QLineEdit(getattr(obj, attr) or "")
            edit.setPlaceholderText(placeholder)
            edit.setMinimumWidth(280)
            edit.editingFinished.connect(
                lambda e=edit, o=obj, a=attr: setter(o, a)(
                    e.text().strip() or (None if a == "proxy" else getattr(o, a))
                )
            )
            body.addWidget(SettingRow(title, edit))
        lay.addWidget(card)

        # About
        card, body = section(tr("set.about"))
        body.addWidget(label(f"Sayrift {__version__}", "Muted"))
        row = QHBoxLayout()
        logs = QPushButton(tr("set.open_logs"))
        logs.clicked.connect(lambda: os.startfile(config.config_dir() / "logs"))
        conf = QPushButton(tr("set.open_config"))
        conf.clicked.connect(_open_config)
        row.addWidget(logs)
        row.addWidget(conf)
        if ctx.run_onboarding:
            guide = QPushButton(tr("set.onboarding"))
            guide.clicked.connect(ctx.run_onboarding)
            row.addWidget(guide)
        row.addStretch(1)
        body.addLayout(row)
        lay.addWidget(card)
        lay.addStretch(1)


def _autostart_enabled() -> bool:
    if sys.platform != "win32":
        return False
    from ..win import autostart

    try:
        return autostart.enabled()
    except OSError:
        return False


def _set_autostart(on: bool) -> None:
    from ..win import autostart

    autostart.set_enabled(on)


def _open_config() -> None:
    path = config.config_path()
    if not path.exists():
        config.save(config.load())
    os.startfile(path)
