"""Spend page: what this app paid per model call (local spend log) plus the OpenRouter account balance."""

from __future__ import annotations

import csv
import math
import threading
import webbrowser
from datetime import date, datetime, timedelta

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from .. import config
from ..store import Spend, Stats, Usage
from . import icons
from .i18n import tr
from .pages import Context, _clear, header, scroll_page
from .theme import Palette
from .widgets import Card, Heatmap, StatCard, label

TOPUP_URL = "https://openrouter.ai/settings/credits"
STAGES = ("asr", "llm", "session")
LOG_PAGE = 30


def fmt_usd(x: float | None) -> str:
    if x is None:
        return "—"
    if x == 0:
        return "$0"
    if abs(x) < 0.01:
        return f"${x:.4f}"
    if abs(x) < 1:
        return f"${x:.3f}"
    return f"${x:,.2f}"


def nice_ceiling(x: float) -> float:
    """Round an axis maximum up to 1, 2 or 5 times a power of ten, so gridline labels are round numbers."""
    exp = math.floor(math.log10(x))
    for step in (1, 2, 5, 10):
        if step * 10**exp >= x:
            return step * 10**exp
    return 10 ** (exp + 1)


def stage_colors(p: Palette) -> dict[str, QColor]:
    return {"asr": QColor(p.accent), "llm": QColor(p.accent2), "session": QColor(p.faint)}


class DailyBars(QWidget):
    """Stacked bars per day (speech recognition / cleanup), last 30 days; hover shows the day's total."""

    DAYS = 30

    def __init__(self, palette: Palette) -> None:
        super().__init__()
        self.p = palette
        self.data: dict[date, dict[str, float]] = {}
        self.setMinimumHeight(170)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

    def set_data(self, data: dict[date, dict[str, float]]) -> None:
        self.data = data
        self.update()

    def _days(self) -> list[date]:
        today = date.today()
        return [today - timedelta(days=self.DAYS - 1 - i) for i in range(self.DAYS)]

    def _geometry(self) -> tuple[float, float, float, float]:
        left, bottom = 52.0, 22.0
        plot_w = self.width() - left - 4
        plot_h = self.height() - bottom - 8
        return left, 8.0, plot_w, plot_h

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        left, top, w, h = self._geometry()
        days = self._days()
        totals = [sum(self.data.get(d, {}).values()) for d in days]
        peak = nice_ceiling(max(totals, default=0) or 0.01)
        font = QFont(self.font())
        font.setPointSizeF(max(7.5, font.pointSizeF() - 1.5))
        p.setFont(font)
        muted = QColor(self.p.faint)

        grid = QPen(QColor(self.p.border))
        grid.setWidthF(1)
        for frac in (0.0, 0.5, 1.0):  # gridlines with their values
            y = top + h - frac * h
            p.setPen(grid)
            p.drawLine(QPointF(left, y), QPointF(left + w, y))
            p.setPen(muted)
            p.drawText(QRectF(0, y - 8, left - 8, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       fmt_usd(peak * frac))  # fmt: skip

        colors = stage_colors(self.p)
        slot = w / len(days)
        bar = max(3.0, slot * 0.62)
        p.setPen(Qt.PenStyle.NoPen)
        for i, d in enumerate(days):
            x = left + i * slot + (slot - bar) / 2
            y = top + h
            for stage in STAGES:
                v = self.data.get(d, {}).get(stage, 0.0)
                if v <= 0:
                    continue
                bh = max(1.5, v / peak * h)
                p.setBrush(colors[stage])
                p.drawRoundedRect(QRectF(x, y - bh, bar, bh), 2, 2)
                y -= bh
            if i % 7 == (len(days) - 1) % 7:  # label every 7th day, ending on today
                p.setPen(muted)
                p.drawText(QRectF(x - 20, top + h + 4, bar + 40, 16), Qt.AlignmentFlag.AlignHCenter,
                           f"{d.month}/{d.day}")  # fmt: skip
                p.setPen(Qt.PenStyle.NoPen)

    def mouseMoveEvent(self, event) -> None:
        left, _top, w, _h = self._geometry()
        days = self._days()
        i = int((event.position().x() - left) / (w / len(days)))
        if 0 <= i < len(days):
            d = days[i]
            parts = self.data.get(d, {})
            lines = [f"{d.isoformat()}  {fmt_usd(sum(parts.values()))}"]
            lines += [f"{tr(f'spend.stage.{s}')}: {fmt_usd(parts[s])}" for s in STAGES if parts.get(s)]
            QToolTip.showText(event.globalPosition().toPoint(), "\n".join(lines), self)
        else:
            QToolTip.hideText()


class ShareRow(QWidget):
    """Name, a proportional bar, and the amount."""

    def __init__(self, palette: Palette, name: str, detail: str, value: float, share: float) -> None:
        super().__init__()
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 4, 0, 4)
        col.setSpacing(4)
        top = QHBoxLayout()
        name_label = label(name)
        name_label.setMinimumWidth(10)
        top.addWidget(name_label, 1)
        if detail:
            top.addWidget(label(detail, "Faint"))
        top.addWidget(label(fmt_usd(value), "SectionTitle"))
        col.addLayout(top)
        bar = QWidget()
        bar.setFixedHeight(6)
        bar.setStyleSheet(f"background: {palette.surface2}; border-radius: 3px;")
        fill = QWidget(bar)
        fill.setStyleSheet(f"background: {palette.accent}; border-radius: 3px;")
        fill.setFixedHeight(6)
        bar.resizeEvent = lambda e, f=fill: f.setFixedWidth(max(4, int(e.size().width() * share)))
        col.addWidget(bar)


class _AccountResult(QObject):
    got = Signal(object, str)  # Account | None, error text


class SpendPage(QWidget):
    def __init__(self, ctx: Context) -> None:
        super().__init__()
        self.ctx = ctx
        p = ctx.palette
        area, lay = scroll_page()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(area)
        lay.addWidget(header(tr("spend.title"), tr("spend.sub")))

        # Your voice: the word statistics and activity grid that used to be on the home page.
        lay.addWidget(label(tr("usage.voice"), "SectionTitle"))
        voice = QGridLayout()
        voice.setSpacing(12)
        self.v_words = StatCard(p, "type", tr("stat.words"))
        self.v_saved = StatCard(p, "timer", tr("stat.saved"))
        self.v_wpm = StatCard(p, "zap", tr("stat.wpm"))
        self.v_streak = StatCard(p, "flame", tr("stat.streak"))
        for i, card in enumerate((self.v_words, self.v_saved, self.v_wpm, self.v_streak)):
            voice.addWidget(card, 0, i)
        lay.addLayout(voice)
        activity = Card()
        top = QHBoxLayout()
        top.addWidget(label(tr("home.activity"), "SectionTitle"))
        top.addStretch(1)
        top.addWidget(label(tr("home.activity.sub"), "Faint"))
        activity.body.addLayout(top)
        self.heatmap = Heatmap(p)
        activity.body.addWidget(self.heatmap)
        lay.addWidget(activity)
        lay.addSpacing(10)
        lay.addWidget(label(tr("usage.money"), "SectionTitle"))

        stats = QGridLayout()
        stats.setSpacing(12)
        self.s_month = StatCard(p, "calendar", tr("spend.month"))
        self.s_today = StatCard(p, "zap", tr("spend.today"))
        self.s_total = StatCard(p, "coins", tr("spend.total"))
        self.s_avg = StatCard(p, "trend", tr("spend.per_session"))
        for i, card in enumerate((self.s_month, self.s_today, self.s_total, self.s_avg)):
            stats.addWidget(card, 0, i)
        lay.addLayout(stats)

        lay.addWidget(self._account_card())

        daily = Card()
        top = QHBoxLayout()
        top.addWidget(label(tr("spend.daily"), "SectionTitle"))
        top.addStretch(1)
        colors = stage_colors(p)
        for stage in ("asr", "llm"):
            dot = QWidget()
            dot.setFixedSize(10, 10)
            dot.setStyleSheet(f"background: {colors[stage].name(QColor.NameFormat.HexArgb)}; border-radius: 3px;")
            top.addWidget(dot)
            top.addWidget(label(tr(f"spend.stage.{stage}"), "Faint"))
            top.addSpacing(8)
        top.addWidget(label(tr("spend.daily.sub"), "Faint"))
        daily.body.addLayout(top)
        self.bars = DailyBars(p)
        daily.body.addWidget(self.bars)
        lay.addWidget(daily)

        split = QHBoxLayout()
        split.setSpacing(12)
        self.by_model = Card()
        self.by_mode = Card()
        split.addWidget(self.by_model, 3)
        split.addWidget(self.by_mode, 2)
        lay.addLayout(split)

        log_card = Card()
        top = QHBoxLayout()
        top.addWidget(label(tr("spend.log"), "SectionTitle"))
        top.addStretch(1)
        export = QPushButton(tr("spend.log.export"))
        export.setIcon(icons.icon("download", p.muted, 16))
        export.setCursor(Qt.CursorShape.PointingHandCursor)
        export.clicked.connect(self._export)
        top.addWidget(export)
        log_card.body.addLayout(top)
        self.unpriced = label("", "Faint")
        log_card.body.addWidget(self.unpriced)
        self.log_grid = QGridLayout()
        self.log_grid.setHorizontalSpacing(18)
        self.log_grid.setVerticalSpacing(8)
        self.log_grid.setColumnStretch(3, 1)
        log_card.body.addLayout(self.log_grid)
        self.more = QPushButton(tr("spend.log.more"))
        self.more.setObjectName("Ghost")
        self.more.setCursor(Qt.CursorShape.PointingHandCursor)
        self.more.clicked.connect(self._more)
        log_card.body.addWidget(self.more, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(log_card)
        lay.addStretch(1)

        self._shown = 0
        self._account_loaded = False
        self._result = _AccountResult()
        self._result.got.connect(self._account_done)

    # --- account ------------------------------------------------------------------------------

    def _account_card(self) -> Card:
        p = self.ctx.palette
        card = Card()
        top = QHBoxLayout()
        top.addWidget(label(tr("spend.account"), "SectionTitle"))
        top.addStretch(1)
        refresh = QPushButton(tr("spend.refresh"))
        refresh.setIcon(icons.icon("retry", p.muted, 16))
        refresh.clicked.connect(self.load_account)
        topup = QPushButton(tr("spend.topup"))
        topup.setObjectName("Primary")
        topup.clicked.connect(lambda: webbrowser.open(TOPUP_URL))
        for b in (refresh, topup):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            top.addWidget(b)
        card.body.addLayout(top)

        row = QHBoxLayout()
        row.setSpacing(28)
        balance = QVBoxLayout()
        balance.setSpacing(2)
        balance.addWidget(label(tr("spend.balance"), "StatLabel"))
        self.a_balance = label("—", "StatValue")
        balance.addWidget(self.a_balance)
        self.a_balance_note = label("", "Faint")
        balance.addWidget(self.a_balance_note)
        row.addLayout(balance)
        row.addStretch(1)
        self.a_key: dict[str, object] = {}
        for key in ("today", "week", "month"):
            col = QVBoxLayout()
            col.setSpacing(2)
            col.addWidget(label(tr(f"spend.key.{key}"), "StatLabel"))
            value = label("—", "SectionTitle")
            col.addWidget(value)
            self.a_key[key] = value
            row.addLayout(col)
        card.body.addLayout(row)
        self.a_status = label("", "Faint", wrap=True)
        card.body.addWidget(self.a_status)
        return card

    def load_account(self) -> None:
        key = config.api_key()
        if not key:
            self.a_status.setText(tr("spend.account.nokey"))
            return
        self.a_status.setText(tr("spend.loading"))
        proxy = self.ctx.cfg.openrouter.proxy

        def work() -> None:
            from ..openrouter import OpenRouterClient, OpenRouterError

            try:
                with OpenRouterClient(api_key=key, proxy=proxy) as client:
                    self._result.got.emit(client.account(), "")
            except OpenRouterError as e:
                self._result.got.emit(None, str(e)[:160])

        threading.Thread(target=work, name="account", daemon=True).start()

    def _account_done(self, account, error: str) -> None:
        if account is None:
            self.a_status.setText(tr("spend.account.failed", why=error))
            return
        self._account_loaded = True
        self.a_balance.setText(fmt_usd(account.balance))
        if account.total_credits is not None:
            self.a_balance_note.setText(
                tr("spend.balance.note", bought=fmt_usd(account.total_credits), used=fmt_usd(account.total_usage))
            )
        for key, value in (("today", account.key_today), ("week", account.key_week), ("month", account.key_month)):
            self.a_key[key].setText(fmt_usd(value))
        note = tr("spend.key") + " · " + tr("spend.key.note")
        if account.key_limit_remaining is not None:
            note += f" · {tr('spend.key.limit')} {fmt_usd(account.key_limit_remaining)}"
        self.a_status.setText(note)

    # --- local spend --------------------------------------------------------------------------

    def refresh(self) -> None:
        from .pages import fmt_duration, fmt_number

        h = self.ctx.history
        st = h.stats() if h else Stats()
        self.v_words.set(fmt_number(st.words), tr("stat.sessions", n=st.sessions))
        self.v_saved.set(fmt_duration(st.time_saved_s))
        self.v_wpm.set(fmt_number(st.wpm) if st.wpm else "—", tr("stat.wpm.unit"))
        self.v_streak.set(tr("unit.day", n=st.streak), tr("stat.streak.best", n=st.longest_streak))
        self.heatmap.set_data(st.words_by_day)
        s = h.spend() if h else Spend()
        self.s_month.set(fmt_usd(s.month), tr("spend.projection", v=fmt_usd(s.month_projection)))
        self.s_today.set(fmt_usd(s.today))
        self.s_total.set(fmt_usd(s.total), tr("spend.calls", n=s.calls))
        self.s_avg.set(fmt_usd(s.total / s.sessions) if s.sessions else "—", tr("spend.sessions", n=s.sessions))
        self.bars.set_data(s.by_day)
        self._fill_shares(s)
        self.unpriced.setText(tr("spend.unpriced", n=s.unpriced_calls) if s.unpriced_calls else "")
        self.unpriced.setVisible(bool(s.unpriced_calls))
        self._shown = 0
        _clear(self.log_grid)
        self._more()
        if not self._account_loaded:
            self.load_account()

    def _fill_shares(self, s: Spend) -> None:
        p = self.ctx.palette
        for card, title, rows in (
            (self.by_model, tr("spend.by_model"),
             [(m or tr("spend.stage.session"), tr("spend.calls", n=n), c) for m, n, c in s.by_model]),
            (self.by_mode, tr("spend.by_mode"),
             [(tr(f"mode.{m}"), "", c) for m, c in sorted(s.by_mode.items(), key=lambda x: -x[1])]),
        ):  # fmt: skip
            _clear(card.body)
            card.body.addWidget(label(title, "SectionTitle"))
            if not rows:
                card.body.addWidget(label("—", "Muted"))
            for name, detail, value in rows:
                card.body.addWidget(ShareRow(p, name, detail, value, value / s.total if s.total else 0))
            card.body.addStretch(1)

    def _more(self) -> None:
        h = self.ctx.history
        rows = h.usage_log(limit=LOG_PAGE, offset=self._shown) if h else []
        g = self.log_grid
        if self._shown == 0:
            if not rows:
                g.addWidget(label(tr("spend.log.empty"), "Muted"), 0, 0, 1, 5)
                self.more.hide()
                return
            for c, key in enumerate(("time", "mode", "stage", "model", "cost")):
                head = label(tr(f"spend.col.{key}"), "StatLabel")
                g.addWidget(head, 0, c, Qt.AlignmentFlag.AlignRight if key == "cost" else Qt.AlignmentFlag.AlignLeft)
        for r, u in enumerate(rows, start=self._shown + 1):
            self._log_row(r, u)
        self._shown += len(rows)
        self.more.setVisible(len(rows) == LOG_PAGE)

    def _log_row(self, r: int, u: Usage) -> None:
        g = self.log_grid
        when = datetime.fromtimestamp(u.created_at).strftime("%m-%d %H:%M")
        stage = tr(f"spend.stage.{u.stage}") + (f" · {tr('spend.log.retry')}" if u.retry else "")
        model = u.model + (f"  ({u.provider})" if u.provider else "")
        cells = [label(when, "Faint"), label(tr(f"mode.{u.mode}")), label(stage, "Muted"), label(model or "—", "Muted"),
                 label(fmt_usd(u.cost_usd))]  # fmt: skip
        for c, w in enumerate(cells):
            w.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            g.addWidget(w, r, c, Qt.AlignmentFlag.AlignRight if c == 4 else Qt.AlignmentFlag.AlignLeft)

    def _export(self) -> None:
        if not self.ctx.history:
            return
        path, _ = QFileDialog.getSaveFileName(self, tr("spend.log.export"), "sayrift-spend.csv", "CSV (*.csv)")
        if not path:
            return
        rows = self.ctx.history.usage_log(limit=10_000_000)
        with open(path, "w", newline="", encoding="utf-8-sig") as f:  # BOM: Excel opens UTF-8 correctly
            w = csv.writer(f)
            w.writerow(["time", "mode", "stage", "model", "provider", "cost_usd", "audio_s", "latency_s", "retry"])
            for u in reversed(rows):
                w.writerow([datetime.fromtimestamp(u.created_at).isoformat(timespec="seconds"), u.mode, u.stage,
                            u.model, u.provider, u.cost_usd, u.audio_s, u.latency_s, int(u.retry)])  # fmt: skip
