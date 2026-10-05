"""Local history (SQLite): every dictation / translation / ask, plus usage stats and the spend log.

Mirrors Typeless: history stays on this machine, keeps the original audio so an entry can be
retried, and is pruned by the "keep history" setting (forever / 1y / 1m / 1w / 24h / never).

The spend log (`usage`, one row per model call) is separate on purpose: money spent stays spent, so
deleting or not keeping history never removes it. It holds numbers only, no text or audio.
"""

from __future__ import annotations

import re
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

RETENTION_SECONDS: dict[str, float | None] = {
    "forever": None,
    "1y": 365 * 86400,
    "1m": 30 * 86400,
    "1w": 7 * 86400,
    "24h": 86400,
    "never": 0,
}

_ENTRY_SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL NOT NULL,
    mode TEXT NOT NULL,          -- dictate | translate | ask
    action TEXT NOT NULL,        -- insert | replace | answer | nothing
    status TEXT NOT NULL,        -- inserted | shown | not_inserted | failed
    app TEXT NOT NULL DEFAULT '',
    raw TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    duration_s REAL NOT NULL DEFAULT 0,
    words INTEGER NOT NULL DEFAULT 0,
    latency_s REAL,
    cost_usd REAL,
    audio BLOB,
    audio_format TEXT
);
"""
_SCHEMA = (
    _ENTRY_SCHEMA
    + """
CREATE INDEX IF NOT EXISTS entries_created ON entries(created_at);
CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY,
    created_at REAL NOT NULL,
    mode TEXT NOT NULL,          -- dictate | translate | ask
    stage TEXT NOT NULL,         -- asr | llm | session (rows backfilled from entries, split unknown)
    model TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL DEFAULT '',
    cost_usd REAL,               -- NULL when the service did not report a price
    audio_s REAL,
    latency_s REAL,
    retry INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS usage_created ON usage(created_at);
"""
)
_SCHEMA_VERSION = 3  # 2: usage backfill; 3: scrub legacy deleted content with VACUUM

_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")
_WORD = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z]+)?")


def count_words(text: str) -> int:
    """Words the way a user thinks of them: each CJK character counts as one, Latin words as one."""
    return len(_CJK.findall(text)) + len(_WORD.findall(text))


@dataclass
class Entry:
    mode: str
    action: str
    status: str
    app: str = ""
    raw: str = ""
    text: str = ""
    error: str = ""
    duration_s: float = 0.0
    latency_s: float | None = None
    cost_usd: float | None = None
    audio: bytes | None = field(default=None, repr=False)
    audio_format: str | None = None
    created_at: float = field(default_factory=time.time)
    id: int | None = None
    words: int = 0


@dataclass
class Stats:
    sessions: int = 0
    words: int = 0
    speaking_s: float = 0.0
    cost_usd: float = 0.0
    wpm: float = 0.0  # words per minute of speech
    time_saved_s: float = 0.0  # vs typing at 45 wpm (Typeless' comparison)
    days_active: int = 0
    streak: int = 0
    longest_streak: int = 0
    words_by_day: dict[date, int] = field(default_factory=dict)


@dataclass
class Usage:
    mode: str
    stage: str
    model: str = ""
    provider: str = ""
    cost_usd: float | None = None
    audio_s: float | None = None
    latency_s: float | None = None
    retry: bool = False
    created_at: float = field(default_factory=time.time)
    id: int | None = None


@dataclass
class Spend:
    total: float = 0.0
    month: float = 0.0
    today: float = 0.0
    month_projection: float = 0.0  # this month's pace extended to the whole month
    calls: int = 0
    unpriced_calls: int = 0  # the service returned no price
    sessions: int = 0  # distinct dictations / translations / asks that cost something
    by_day: dict[date, dict[str, float]] = field(default_factory=dict)  # day -> {stage: usd}
    by_model: list[tuple[str, int, float]] = field(default_factory=list)  # (model, calls, usd), priciest first
    by_mode: dict[str, float] = field(default_factory=dict)


_USAGE_COLUMNS = ["id", "created_at", "mode", "stage", "model", "provider", "cost_usd", "audio_s", "latency_s", "retry"]

_COLUMNS = [
    "id", "created_at", "mode", "action", "status", "app", "raw", "text", "error",
    "duration_s", "words", "latency_s", "cost_usd", "audio_format",
]  # fmt: skip


class History:
    def __init__(self, path: Path, *, keep: str = "forever", clock: Callable[[], float] | None = None) -> None:
        if keep not in RETENTION_SECONDS:
            raise ValueError(f"Unknown history retention: {keep}")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock or time.time
        self._lock = threading.Lock()
        self._keep = keep
        self._db = sqlite3.connect(path, check_same_thread=False)
        try:
            self._db.execute("PRAGMA secure_delete = ON")
            # Avoid retaining old page images in WAL / persistent rollback journals.
            mode = self._db.execute("PRAGMA journal_mode = DELETE").fetchone()[0]
            if mode not in {"delete", "memory"}:
                raise sqlite3.OperationalError("History requires DELETE journaling")
            self._db.executescript(_SCHEMA)
            self._migrate()
            self.prune()
        except BaseException:
            self._db.close()
            raise

    def _migrate(self) -> None:
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if version < 2:  # sessions recorded before the spend log: keep their cost, model split unknown
            with self._db:
                self._db.execute(
                    "INSERT INTO usage (created_at, mode, stage, cost_usd, audio_s, latency_s)"
                    " SELECT created_at, mode, 'session', cost_usd, duration_s, latency_s FROM entries"
                    " WHERE cost_usd IS NOT NULL"
                )
                # Commit the backfill marker with its rows, even if VACUUM later fails.
                self._db.execute("PRAGMA user_version = 2")
        if version < 3:
            schema = self._db.execute("SELECT sql FROM sqlite_schema WHERE name='entries'").fetchone()[0]
            if "AUTOINCREMENT" not in schema.upper():
                # Retrying an expired row must never overwrite a new row that reused its ID.
                with self._db:
                    self._db.execute("BEGIN")
                    self._db.execute("ALTER TABLE entries RENAME TO entries_retention_legacy")
                    self._db.execute(_ENTRY_SCHEMA)
                    self._db.execute("INSERT INTO entries SELECT * FROM entries_retention_legacy")
                    self._db.execute("DROP TABLE entries_retention_legacy")
                    self._db.execute("CREATE INDEX entries_created ON entries(created_at)")
            # secure_delete only covers future changes. Rebuild once for old free pages
            # and free space inside live pages; retain all live rows and explicit IDs.
            self._db.execute("VACUUM")
            with self._db:
                self._db.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")

    @property
    def keep(self) -> str:
        with self._lock:
            return self._keep

    @keep.setter
    def keep(self, value: str) -> None:
        if value not in RETENTION_SECONDS:
            raise ValueError(f"Unknown history retention: {value}")
        with self._lock, self._db:
            self._keep = value
            self._prune(self._clock())

    def _prune(self, now: float) -> None:
        """Caller owns the lock and transaction. 'never' also removes future-dated rows."""
        seconds = RETENTION_SECONDS[self._keep]
        if seconds == 0:
            self._db.execute("DELETE FROM entries")
        elif seconds is not None:
            self._db.execute("DELETE FROM entries WHERE created_at < ?", (now - seconds,))

    @contextmanager
    def _access(self) -> Iterator[float]:
        # A single clock sample and transaction cover pruning plus the requested operation.
        with self._lock, self._db:
            now = self._clock()
            self._prune(now)
            yield now

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # --- writing -------------------------------------------------------------------------------

    def add(self, e: Entry) -> int | None:
        """Store an unexpired entry (unless retention is 'never'); returns its id."""
        with self._access() as now:
            seconds = RETENTION_SECONDS[self._keep]
            if seconds == 0 or (seconds is not None and e.created_at < now - seconds):
                return None
            e.words = count_words(e.text)
            cur = self._db.execute(
                "INSERT INTO entries (created_at, mode, action, status, app, raw, text, error, duration_s, words,"
                " latency_s, cost_usd, audio, audio_format) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (e.created_at, e.mode, e.action, e.status, e.app, e.raw, e.text, e.error, e.duration_s, e.words,
                 e.latency_s, e.cost_usd, e.audio, e.audio_format),
            )  # fmt: skip
            e.id = cur.lastrowid
        return e.id

    def update_result(self, entry_id: int, *, raw: str, text: str, action: str, status: str, error: str = "") -> None:
        with self._access():
            self._db.execute(
                "UPDATE entries SET raw=?, text=?, action=?, status=?, error=?, words=? WHERE id=?",
                (raw, text, action, status, error, count_words(text), entry_id),
            )

    def delete(self, entry_id: int) -> None:
        with self._access():
            self._db.execute("DELETE FROM entries WHERE id=?", (entry_id,))

    def delete_all(self) -> None:
        with self._access():
            self._db.execute("DELETE FROM entries")

    def prune(self, now: float | None = None) -> None:
        with self._lock, self._db:
            self._prune(self._clock() if now is None else now)

    def log_usage(self, u: Usage) -> None:
        """One model call. Kept whatever the history retention is (numbers only)."""
        with self._access():
            self._db.execute(
                "INSERT INTO usage (created_at, mode, stage, model, provider, cost_usd, audio_s, latency_s, retry)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (u.created_at, u.mode, u.stage, u.model, u.provider, u.cost_usd, u.audio_s, u.latency_s, int(u.retry)),
            )

    # --- reading -------------------------------------------------------------------------------

    def list(self, *, mode: str | None = None, search: str = "", limit: int = 200, offset: int = 0) -> list[Entry]:
        sql = f"SELECT {', '.join(_COLUMNS)} FROM entries WHERE 1=1"
        args: list = []
        if mode:
            sql += " AND mode=?"
            args.append(mode)
        if search:
            sql += " AND (text LIKE ? OR raw LIKE ?)"
            args += [f"%{search}%"] * 2
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        args += [limit, offset]
        with self._access():
            rows = self._db.execute(sql, args).fetchall()
        return [Entry(**dict(zip(_COLUMNS, row, strict=True))) for row in rows]

    def audio(self, entry_id: int) -> tuple[bytes, str] | None:
        with self._access():
            row = self._db.execute("SELECT audio, audio_format FROM entries WHERE id=?", (entry_id,)).fetchone()
        return (row[0], row[1]) if row and row[0] else None

    def stats(self, today: date | None = None) -> Stats:
        with self._access():
            rows = self._db.execute(
                "SELECT created_at, words, duration_s, cost_usd FROM entries WHERE status != 'failed'"
            ).fetchall()
        s = Stats(sessions=len(rows))
        for created, words, duration, cost in rows:
            s.words += words
            s.speaking_s += duration
            s.cost_usd += cost or 0.0
            day = datetime.fromtimestamp(created).date()
            s.words_by_day[day] = s.words_by_day.get(day, 0) + words
        if s.speaking_s > 0:
            s.wpm = s.words / (s.speaking_s / 60)
        s.time_saved_s = max(0.0, s.words / 45 * 60 - s.speaking_s)
        days = sorted(s.words_by_day)
        s.days_active = len(days)
        run, prev = 0, None
        for d in days:
            run = run + 1 if prev and d - prev == timedelta(days=1) else 1
            s.longest_streak = max(s.longest_streak, run)
            prev = d
        today = today or date.today()
        if days and (today - days[-1]).days <= 1:  # a streak survives until the end of the next day
            s.streak = run
        return s

    def usage_log(self, *, limit: int = 100, offset: int = 0) -> list[Usage]:
        with self._access():
            rows = self._db.execute(
                f"SELECT {', '.join(_USAGE_COLUMNS)} FROM usage ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [Usage(**{**dict(zip(_USAGE_COLUMNS, r, strict=True)), "retry": bool(r[-1])}) for r in rows]

    def spend(self, today: date | None = None) -> Spend:
        today = today or date.today()
        with self._access():
            rows = self._db.execute("SELECT created_at, mode, stage, model, cost_usd FROM usage").fetchall()
        s = Spend(calls=len(rows))
        models: dict[str, list] = {}
        sessions: set[float] = set()  # the calls of one session share its timestamp
        for created, mode, stage, model, cost in rows:
            if cost is None:
                s.unpriced_calls += 1
                continue
            day = datetime.fromtimestamp(created).date()
            s.total += cost
            if (day.year, day.month) == (today.year, today.month):
                s.month += cost
            if day == today:
                s.today += cost
            per_day = s.by_day.setdefault(day, {})
            per_day[stage] = per_day.get(stage, 0.0) + cost
            m = models.setdefault(model, [0, 0.0])
            m[0] += 1
            m[1] += cost
            s.by_mode[mode] = s.by_mode.get(mode, 0.0) + cost
            sessions.add(created)
        s.sessions = len(sessions)
        s.by_model = sorted(((k, n, c) for k, (n, c) in models.items()), key=lambda x: -x[2])
        days_in_month = ((today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)).day
        s.month_projection = s.month / today.day * days_in_month
        return s
