"""Main-window pages: Home, History, Dictionary. (Settings lives in settings_page.py.)"""

from __future__ import annotations

import csv
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import config, keys
from ..store import Entry, History, Stats
from . import icons
from .i18n import tr
from .theme import Palette
from .widgets import Card, FlowLayout, IconButton, Segmented, label


@dataclass
class Context:
    """What the pages need from the rest of the app."""

    cfg: config.Config
    palette: Palette
    history: History | None
    retry: Callable[[int], None]
    capture_key: Callable[[Callable[[int], None]], None]
    cancel_capture: Callable[[], None]
    applied: Callable[[], None]  # settings were changed in memory: persist and apply
    run_onboarding: Callable[[], None] | None = None

    def save(self) -> None:
        config.save(self.cfg)
        self.applied()


MAX_WIDTH = 1000  # beyond this, lines get too long to read comfortably


def scroll_page(margins: int = 32) -> tuple[QScrollArea, QVBoxLayout]:
    """A transparent scrolling page whose content column is centred and capped at MAX_WIDTH."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    inner = QWidget()
    inner.setObjectName("Content")
    row = QHBoxLayout(inner)
    row.setContentsMargins(margins, 20, margins, 36)
    column = QWidget()
    column.setMaximumWidth(MAX_WIDTH)
    lay = QVBoxLayout(column)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(16)
    row.addWidget(column, 1)
    area.setWidget(inner)
    return area, lay


def header(title: str, sub: str = "") -> QWidget:
    w = QWidget()
    col = QVBoxLayout(w)
    col.setContentsMargins(0, 0, 0, 4)
    col.setSpacing(4)
    col.addWidget(label(title, "PageTitle"))
    if sub:
        col.addWidget(label(sub, "PageSub", wrap=True))
    return w


def fmt_duration(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 60:
        return tr("unit.min", n=minutes)
    return tr("unit.hour", h=minutes // 60, m=minutes % 60)


def fmt_number(n: float) -> str:
    return f"{n:,.0f}"


MODE_ICON = {"dictate": "mic", "translate": "translate", "ask": "sparkles"}


# --- Home ---------------------------------------------------------------------------------------


class ClickCard(Card):
    """A frosted card that copies its text when clicked."""

    def __init__(self, on_click: Callable[[], None]) -> None:
        super().__init__(padding=20, spacing=8)
        self._on_click = on_click
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click()
        super().mouseReleaseEvent(event)


class HomePage(QWidget):
    """Today: the orb, one line telling you what to do, the last result, this week and this month."""

    def __init__(self, ctx: Context, open_history: Callable[[], None]) -> None:
        from .glass import Orb

        super().__init__()
        self.ctx = ctx
        area, lay = scroll_page(margins=40)
        lay.setSpacing(0)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(area)

        self.orb = Orb(ctx.palette, 124)
        lay.addWidget(self.orb, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(-30)  # the orb's glow padding already separates it from the headline
        self.headline = QWidget()
        self.headline_row = QHBoxLayout(self.headline)
        self.headline_row.setContentsMargins(0, 0, 0, 0)
        self.headline_row.setSpacing(10)
        lay.addWidget(self.headline, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(10)
        self.also = label("", "Muted")
        lay.addWidget(self.also, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(34)

        cards = QHBoxLayout()
        cards.setSpacing(14)
        self.last = ClickCard(self._copy_last)
        self.last_eyebrow = label("", "Eyebrow")
        self.last_text = label("", "RowText", wrap=True)
        self.last_text.setMinimumHeight(44)
        self.last.body.addWidget(self.last_eyebrow)
        self.last.body.addWidget(self.last_text, 1)
        cards.addWidget(self.last, 16)
        self.week = Card(padding=20, spacing=4)
        self.week.body.addWidget(label(tr("today.week"), "Eyebrow"))
        self.week_value = label("", "BigNumber")
        self.week.body.addWidget(self.week_value)
        self.week_note = label("", "Faint")
        self.week.body.addWidget(self.week_note)
        cards.addWidget(self.week, 10)
        self.month = Card(padding=20, spacing=4)
        self.month.body.addWidget(label(tr("today.month"), "Eyebrow"))
        self.month_value = label("", "BigNumber")
        self.month.body.addWidget(self.month_value)
        self.month_note = label("", "Faint")
        self.month.body.addWidget(self.month_note)
        cards.addWidget(self.month, 10)
        lay.addLayout(cards)
        lay.addSpacing(28)

        top = QHBoxLayout()
        top.addWidget(label(tr("today.recent"), "Eyebrow"))
        top.addStretch(1)
        more = QPushButton(tr("today.view_all"))
        more.setObjectName("Ghost")
        more.setCursor(Qt.CursorShape.PointingHandCursor)
        more.clicked.connect(open_history)
        top.addWidget(more)
        lay.addLayout(top)
        lay.addSpacing(4)
        self.recent_box = QVBoxLayout()
        self.recent_box.setSpacing(0)
        lay.addLayout(self.recent_box)
        lay.addStretch(1)
        self._last_text = ""
        self._state = "ready"

    # --- live state from the controller -------------------------------------------------------

    def set_state(self, state: str) -> None:
        self._state = state
        self.orb.set_state(state)
        self._fill_headline()

    def set_level(self, level: float) -> None:
        self.orb.set_level(level)

    def _fill_headline(self) -> None:
        _clear(self.headline_row)
        if self._state == "listening":
            self.headline_row.addWidget(label(tr("today.listening"), "HeroTitle"))
            return
        if self._state == "processing":
            self.headline_row.addWidget(label(tr("today.processing"), "HeroTitle"))
            return
        self.headline_row.addWidget(label(tr("today.press"), "HeroTitle"))
        cap = QLabel(keys.display(self.ctx.cfg.hotkeys.main))
        cap.setObjectName("KeyCapBig")
        self.headline_row.addWidget(cap, 0, Qt.AlignmentFlag.AlignVCenter)
        self.headline_row.addWidget(label(tr("today.talk"), "HeroTitle"))

    # --- data ---------------------------------------------------------------------------------

    def refresh(self) -> None:
        h, hk = self.ctx.history, self.ctx.cfg.hotkeys
        main = keys.display(hk.main)
        self._fill_headline()
        self.also.setText(tr("today.also", t=f"{main} + {keys.display(hk.translate)}",
                             a=f"{main} + {keys.display(hk.ask)}"))  # fmt: skip

        entries = h.list(limit=6) if h else []
        last = next((e for e in entries if e.text), None)
        if last:
            when = datetime.fromtimestamp(last.created_at).strftime("%H:%M")
            where = f" · {last.app.removesuffix('.exe')}" if last.app else ""
            self.last_eyebrow.setText(f"{tr('today.just_now')} · {when}{where}")
            self.last_text.setText(_one_line(last.text, 160))
            self.last.setToolTip(tr("today.copy_hint"))
            self._last_text = last.text
        else:
            self.last_eyebrow.setText(tr("today.just_now"))
            self.last_text.setText(tr("today.just_now.empty"))
            self._last_text = ""

        s = h.stats() if h else Stats()
        week_start = date.today() - timedelta(days=6)
        words = sum(n for d, n in s.words_by_day.items() if d >= week_start)
        saved = s.time_saved_s * words / s.words if s.words else 0.0
        self.week_value.setText(f"{fmt_number(words)} <span style='font-size:14px;font-weight:500'>"
                                f"{tr('today.week.unit')}</span>")  # fmt: skip
        self.week_note.setText(tr("today.week.saved", v=fmt_duration(saved)))
        spend = h.spend() if h else None
        from .spend_page import fmt_usd

        self.month_value.setText(fmt_usd(spend.month if spend else 0.0))
        self.month_note.setText(tr("today.month.note", n=spend.calls if spend else 0))

        _clear(self.recent_box)
        for e in [e for e in entries if e is not last][:4]:  # the card already shows the latest
            self.recent_box.addWidget(self._recent_row(e))

    def _recent_row(self, e: Entry) -> QWidget:
        w = QWidget()
        w.setObjectName("Row")
        row = QHBoxLayout(w)
        row.setContentsMargins(10, 10, 10, 10)
        row.setSpacing(16)
        when = label(datetime.fromtimestamp(e.created_at).strftime("%H:%M"), "Faint")
        when.setFixedWidth(40)
        row.addWidget(when)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(MODE_ICON.get(e.mode, "mic"), self.ctx.palette.faint, 15))
        row.addWidget(ic)
        text = label(_one_line(e.text or tr(e.error) or e.raw), "RowText")
        text.setMinimumWidth(10)
        row.addWidget(text, 1)
        return w

    def _copy_last(self) -> None:
        if not self._last_text:
            return
        QGuiApplication.clipboard().setText(self._last_text)
        self.last_eyebrow.setText(tr("today.copied"))
        QTimer.singleShot(1200, self.refresh)


# --- History ------------------------------------------------------------------------------------


class EntryRow(QWidget):
    def __init__(self, ctx: Context, e: Entry, on_changed: Callable[[], None]) -> None:
        super().__init__()
        self.ctx, self.e, self.on_changed = ctx, e, on_changed
        self.setObjectName("Row")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 8, 10)
        row.setSpacing(12)
        time_lab = label(datetime.fromtimestamp(e.created_at).strftime("%H:%M"), "Faint")
        time_lab.setFixedWidth(40)
        row.addWidget(time_lab, 0, Qt.AlignmentFlag.AlignTop)

        mid = QVBoxLayout()
        mid.setSpacing(4)
        badges = QHBoxLayout()
        badges.setSpacing(6)
        if e.mode != "dictate":
            badges.addWidget(label(tr(f"mode.{e.mode}"), "Badge"))
        if e.status == "failed":
            badges.addWidget(label(tr("history.failed"), "BadgeMuted"))
        elif e.status == "not_inserted":
            badges.addWidget(label(tr("history.not_inserted"), "BadgeMuted"))
        if e.app:
            badges.addWidget(label(e.app.removesuffix(".exe").removesuffix(".EXE"), "Faint"))
        badges.addStretch(1)
        mid.addLayout(badges)
        body = e.text or (tr(e.error) if e.status == "failed" else e.raw)
        self.text = label(body, "RowText", wrap=True)
        if e.action == "answer":
            self.text.setTextFormat(Qt.TextFormat.MarkdownText)  # Ask answers are Markdown
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        mid.addWidget(self.text)
        self.raw = label(f"{tr('history.raw')}：{e.raw}", "Faint", wrap=True)
        self.raw.setVisible(False)
        mid.addWidget(self.raw)
        row.addLayout(mid, 1)

        p = ctx.palette
        self.copy_btn = IconButton("copy", tr("history.copy"), p, self._copy)
        row.addWidget(self.copy_btn, 0, Qt.AlignmentFlag.AlignTop)
        if ctx.history and ctx.history.audio(e.id) is not None:
            row.addWidget(IconButton("retry", tr("history.retry"), p, self._retry), 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(IconButton("trash", tr("history.delete"), p, self._delete), 0, Qt.AlignmentFlag.AlignTop)

    def mousePressEvent(self, event) -> None:
        if self.e.raw and self.e.raw != self.e.text:
            self.raw.setVisible(not self.raw.isVisible())
        super().mousePressEvent(event)

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.e.text or self.e.raw)
        self.copy_btn.setToolTip(tr("history.copied"))
        self.copy_btn.setIcon(icons.icon("check", self.ctx.palette.success, 16))
        QTimer.singleShot(1200, lambda: self.copy_btn.setIcon(icons.icon("copy", self.ctx.palette.muted, 16)))

    def _retry(self) -> None:
        self.text.setText(tr("history.retrying"))
        self.ctx.retry(self.e.id)

    def _delete(self) -> None:
        if self.ctx.history:
            self.ctx.history.delete(self.e.id)
        self.on_changed()


class HistoryPage(QWidget):
    FILTERS = ("", "dictate", "translate", "ask")

    def __init__(self, ctx: Context) -> None:
        super().__init__()
        self.ctx = ctx
        self.mode = ""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 28, 32, 0)
        outer.setSpacing(14)
        top = QHBoxLayout()
        top.addWidget(header(tr("history.title"), tr("history.sub")), 1)
        clear = QPushButton(tr("history.delete_all"))
        clear.setCursor(Qt.CursorShape.PointingHandCursor)
        clear.clicked.connect(self._delete_all)
        top.addWidget(clear, 0, Qt.AlignmentFlag.AlignTop)
        outer.addLayout(top)

        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("history.search"))
        self.search.addAction(icons.icon("search", ctx.palette.faint, 16), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setClearButtonEnabled(True)
        self._debounce = QTimer(self, singleShot=True, interval=200, timeout=self.refresh)
        self.search.textChanged.connect(lambda _: self._debounce.start())
        bar.addWidget(self.search, 1)
        seg = Segmented(
            [("", tr("history.all")), ("dictate", tr("mode.dictate")), ("translate", tr("mode.translate")),
             ("ask", tr("mode.ask"))],
            "",
        )  # fmt: skip
        seg.changed.connect(self._set_mode)
        bar.addWidget(seg)
        outer.addLayout(bar)

        area = QScrollArea()
        area.setWidgetResizable(True)
        inner = QWidget()
        inner.setObjectName("Content")
        self.list = QVBoxLayout(inner)
        self.list.setContentsMargins(0, 0, 8, 24)
        self.list.setSpacing(2)
        area.setWidget(inner)
        outer.addWidget(area, 1)

    def _set_mode(self, mode: str) -> None:
        self.mode = mode
        self.refresh()

    def _delete_all(self) -> None:
        if not self.ctx.history:
            return
        box = QMessageBox(QMessageBox.Icon.Warning, tr("history.delete_all"), tr("history.delete_all.confirm"),
                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self)  # fmt: skip
        if box.exec() == QMessageBox.StandardButton.Yes:
            self.ctx.history.delete_all()
            self.refresh()

    def refresh(self) -> None:
        _clear(self.list)
        entries = (
            self.ctx.history.list(mode=self.mode or None, search=self.search.text().strip(), limit=300)
            if self.ctx.history
            else []
        )
        if not entries:
            empty = label(tr("history.empty"), "Muted")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.list.addSpacing(40)
            self.list.addWidget(empty)
        day = None
        today = date.today()
        for e in entries:
            d = datetime.fromtimestamp(e.created_at).date()
            if d != day:
                day = d
                text = (
                    tr("history.today")
                    if d == today
                    else tr("history.yesterday")
                    if d == today - timedelta(days=1)
                    else d.strftime("%Y-%m-%d")
                )
                self.list.addWidget(label(text, "DayHeader"))
            self.list.addWidget(EntryRow(self.ctx, e, self.refresh))
        self.list.addStretch(1)


# --- Dictionary ---------------------------------------------------------------------------------


class DictionaryPage(QWidget):
    def __init__(self, ctx: Context) -> None:
        super().__init__()
        self.ctx = ctx
        area, lay = scroll_page()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(area)
        lay.addWidget(header(tr("dict.title"), tr("dict.sub")))

        add = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText(tr("dict.placeholder"))
        self.input.returnPressed.connect(self._add)
        add.addWidget(self.input, 1)
        add_btn = QPushButton(tr("dict.add"))
        add_btn.setObjectName("Primary")
        add_btn.setIcon(icons.icon("plus", ctx.palette.on_accent, 16))
        add_btn.clicked.connect(self._add)
        add.addWidget(add_btn)
        imp = QPushButton(tr("dict.import"))
        imp.setIcon(icons.icon("upload", ctx.palette.muted, 16))
        imp.clicked.connect(self._import)
        add.addWidget(imp)
        lay.addLayout(add)

        card = Card()
        top = QHBoxLayout()
        self.count = label("", "SectionTitle")
        top.addWidget(self.count)
        top.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("dict.search"))
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(220)
        self.search.textChanged.connect(lambda _: self.refresh())
        top.addWidget(self.search)
        card.body.addLayout(top)
        self.flow_host = QWidget()
        self.flow = FlowLayout(8)
        self.flow_host.setLayout(self.flow)
        card.body.addWidget(self.flow_host)
        self.note = label("", "Muted", wrap=True)
        self.note.setVisible(False)
        card.body.addWidget(self.note)
        lay.addWidget(card)
        lay.addStretch(1)

    def _words(self) -> list[str]:
        return self.ctx.cfg.dictionary

    def _add(self) -> None:
        word = self.input.text().strip()
        if word and word not in self._words():
            self.ctx.cfg.dictionary = [*self._words(), word]
            self.ctx.save()
        self.input.clear()
        self.refresh()

    def _remove(self, word: str) -> None:
        self.ctx.cfg.dictionary = [w for w in self._words() if w != word]
        self.ctx.save()
        self.refresh()

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("dict.import"), "", "CSV (*.csv *.txt)")
        if not path:
            return
        with open(path, encoding="utf-8-sig", newline="") as f:
            found = [row[0].strip() for row in csv.reader(f) if row and row[0].strip()]
        new = [w for w in dict.fromkeys(found) if w not in self._words()]
        self.ctx.cfg.dictionary = [*self._words(), *new]
        self.ctx.save()
        self.refresh()
        self.note.setText(tr("dict.import.done", n=len(new)))
        self.note.setVisible(True)

    def refresh(self) -> None:
        while self.flow.count():
            item = self.flow.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
                item.widget().deleteLater()
        words = self._words()
        self.count.setText(tr("dict.count", n=len(words)))
        query = self.search.text().strip().lower()
        shown = [w for w in words if query in w.lower()]
        if not words:
            self.note.setText(tr("dict.empty"))
            self.note.setVisible(True)
        for word in shown:
            chip = QPushButton(word)
            chip.setObjectName("Chip")
            chip.setToolTip(tr("dict.remove"))
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setIcon(icons.icon("x", self.ctx.palette.faint, 12))
            chip.setIconSize(QSize(12, 12))
            chip.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            chip.clicked.connect(lambda _=False, w=word: self._remove(w))
            self.flow.addWidget(chip)
        self.flow_host.updateGeometry()


# --- helpers ------------------------------------------------------------------------------------


def _clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            w = item.widget()
            w.setParent(None)  # off screen now; deleteLater alone leaves it painted until the loop runs
            w.deleteLater()
        elif item.layout():
            _clear(item.layout())


_MARKDOWN = re.compile(r"(\*\*|__|`|^#+\s|^[-*]\s)", re.MULTILINE)


def _one_line(text: str, limit: int = 90) -> str:
    text = " ".join(_MARKDOWN.sub("", text).split())  # answers are Markdown; a one-line preview shows plain text
    return text if len(text) <= limit else text[: limit - 1] + "…"
