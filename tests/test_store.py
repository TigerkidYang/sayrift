import sqlite3
from datetime import date, datetime
from pathlib import Path

import pytest

from local_typeless.store import RETENTION_SECONDS, Entry, History, Usage, count_words


def ts(y, m, d, h=12):
    return datetime(y, m, d, h).timestamp()


def legacy_entry_ids(db):
    """Recreate the pre-v3 table, whose INTEGER PRIMARY KEY could reuse deleted IDs."""
    schema = db.execute("SELECT sql FROM sqlite_schema WHERE name='entries'").fetchone()[0]
    db.execute("BEGIN")
    db.execute("ALTER TABLE entries RENAME TO old_entries")
    db.execute(schema.replace(" AUTOINCREMENT", ""))
    db.execute("INSERT INTO entries SELECT * FROM old_entries")
    db.execute("DROP TABLE old_entries")
    db.execute("CREATE INDEX entries_created ON entries(created_at)")
    db.commit()


def test_count_words_mixes_cjk_characters_and_latin_words():
    assert count_words("我们用 Python 写") == 5
    assert count_words("I'll push the release notes") == 5
    assert count_words("") == 0


def test_add_list_filter_search_and_audio(tmp_path):
    h = History(tmp_path / "h.sqlite")
    a = h.add(
        Entry("dictate", "insert", "inserted", app="Weixin.exe", text="你好世界", audio=b"ogg", audio_format="ogg")
    )
    h.add(Entry("ask", "answer", "shown", text="巴黎"))
    assert [e.text for e in h.list()] == ["巴黎", "你好世界"]
    assert [e.text for e in h.list(mode="dictate")] == ["你好世界"]
    assert [e.text for e in h.list(search="世界")] == ["你好世界"]
    assert h.audio(a) == (b"ogg", "ogg")
    h.delete(a)
    assert [e.text for e in h.list()] == ["巴黎"]
    h.delete_all()
    assert h.list() == []


def test_retention_prunes_old_entries_and_never_stores_nothing(tmp_path):
    h = History(tmp_path / "h.sqlite", keep="1w", clock=lambda: ts(2026, 9, 26))
    h.add(Entry("dictate", "insert", "inserted", text="old", created_at=ts(2026, 9, 1)))
    h.add(Entry("dictate", "insert", "inserted", text="new", created_at=ts(2026, 9, 25)))
    h.prune(now=ts(2026, 9, 26))
    assert [e.text for e in h.list()] == ["new"]
    h.keep = "never"
    assert h.add(Entry("dictate", "insert", "inserted", text="x")) is None


def test_stats_words_speed_and_streaks(tmp_path):
    h = History(tmp_path / "h.sqlite")
    for day in (20, 21, 22, 25, 26):
        h.add(Entry("dictate", "insert", "inserted", text="一二三四五六", duration_s=6.0, created_at=ts(2026, 9, day)))
    h.add(Entry("dictate", "insert", "failed", text="", created_at=ts(2026, 9, 26)))
    s = h.stats(today=date(2026, 9, 26))
    assert (s.sessions, s.words, s.days_active) == (5, 30, 5)
    assert s.wpm == 60.0
    assert (s.streak, s.longest_streak) == (2, 3)
    assert s.time_saved_s > 0


def test_spend_totals_by_day_model_mode_and_projection(tmp_path):
    from local_typeless.store import Usage

    h = History(tmp_path / "h.sqlite")
    t1, t2, old = ts(2026, 9, 10), ts(2026, 9, 15), ts(2026, 8, 30)
    h.log_usage(Usage("dictate", "asr", "openai/gpt-transcribe", cost_usd=0.001, created_at=t1))
    h.log_usage(Usage("dictate", "llm", "deepseek/x", "DeepInfra", cost_usd=0.0002, created_at=t1))
    h.log_usage(Usage("translate", "asr", "openai/gpt-transcribe", cost_usd=0.002, created_at=t2))
    h.log_usage(Usage("translate", "llm", "some/unpriced", created_at=t2))  # no price reported
    h.log_usage(Usage("ask", "asr", "openai/gpt-transcribe", cost_usd=0.01, created_at=old))
    s = h.spend(today=date(2026, 9, 15))
    assert round(s.total, 6) == 0.0132 and round(s.month, 6) == 0.0032 and round(s.today, 6) == 0.002
    assert s.calls == 5 and s.unpriced_calls == 1 and s.sessions == 3
    model, calls, usd = s.by_model[0]
    assert (model, calls, round(usd, 6)) == ("openai/gpt-transcribe", 3, 0.013)
    assert round(s.by_day[date(2026, 9, 10)]["asr"], 6) == 0.001
    assert round(s.month_projection, 6) == round(0.0032 / 15 * 30, 6)
    assert {u.model for u in h.usage_log(limit=2)} == {"openai/gpt-transcribe", "some/unpriced"}


def test_spend_log_survives_history_deletion_and_never_keep(tmp_path):
    from local_typeless.store import Usage

    h = History(tmp_path / "h.sqlite", keep="never")
    h.add(Entry("dictate", "insert", "inserted", text="x"))
    h.log_usage(Usage("dictate", "asr", "m", cost_usd=0.001))
    h.delete_all()
    h.prune()
    assert h.list() == [] and h.spend().calls == 1


def test_old_session_costs_are_backfilled_into_the_spend_log(tmp_path):
    import sqlite3

    path = tmp_path / "h.sqlite"
    h = History(path)
    h.add(Entry("dictate", "insert", "inserted", text="x", cost_usd=0.003))
    h.close()
    db = sqlite3.connect(path)  # simulate a database from before the spend log existed
    db.execute("DELETE FROM usage")
    db.execute("PRAGMA user_version = 0")
    db.commit()
    db.close()
    s = History(path).spend()
    assert s.calls == 1 and round(s.total, 6) == 0.003


@pytest.fixture
def clock():
    class Clock:
        now = ts(2026, 9, 26)

        def __call__(self):
            return self.now

    return Clock()


@pytest.mark.parametrize("keep", ["24h", "1w", "1m", "1y"])
@pytest.mark.parametrize("memory", [False, True])
def test_retention_boundary_and_late_insert(tmp_path, clock, keep, memory):
    h = History(Path(":memory:") if memory else tmp_path / "h.sqlite", keep=keep, clock=clock)
    try:
        cutoff = clock.now - RETENTION_SECONDS[keep]
        assert h.add(Entry("dictate", "insert", "inserted", created_at=cutoff - 0.1)) is None
        entry_id = h.add(Entry("dictate", "insert", "inserted", created_at=cutoff, audio=b"ogg"))
        assert [e.id for e in h.list()] == [entry_id]
        clock.now += 0.1
        assert h.audio(entry_id) is None
        assert h.list() == []
    finally:
        h.close()


@pytest.mark.parametrize(
    "operation",
    ["list", "audio", "stats", "add", "update_result", "delete", "delete_all", "log_usage", "usage_log", "spend"],
)
def test_each_operation_prunes_without_restart(tmp_path, clock, operation):
    h = History(tmp_path / "h.sqlite", keep="24h", clock=clock)
    try:
        entry_id = h.add(Entry("dictate", "insert", "inserted", text="expired", audio=b"audio", created_at=clock.now))
        h.log_usage(Usage("dictate", "asr", cost_usd=0.1, created_at=clock.now))
        clock.now += 86401
        args = {
            "audio": (entry_id,),
            "delete": (-1,),
            "update_result": (entry_id,),
            "add": (Entry("dictate", "insert", "inserted", text="fresh", created_at=clock.now),),
            "log_usage": (Usage("dictate", "llm", cost_usd=0.2, created_at=clock.now),),
        }
        kwargs = {"raw": "retry", "text": "retry", "action": "insert", "status": "inserted"}
        result = getattr(h, operation)(*args.get(operation, ()), **(kwargs if operation == "update_result" else {}))
        if operation == "list":
            assert result == []
        elif operation == "audio":
            assert result is None
        elif operation == "stats":
            assert result.sessions == result.words == 0
        # Inspect committed storage directly: another pruning read must not mask a missing hook.
        with sqlite3.connect(tmp_path / "h.sqlite") as db:
            assert db.execute("SELECT text FROM entries").fetchall() == ([("fresh",)] if operation == "add" else [])
            assert db.execute("SELECT COUNT(*) FROM usage").fetchone()[0] == (2 if operation == "log_usage" else 1)
    finally:
        h.close()


def test_policy_change_clears_future_rows_and_preserves_usage(tmp_path, clock):
    h = History(tmp_path / "h.sqlite", clock=clock)
    try:
        for created in (clock.now - 86401, clock.now, clock.now + 999999):
            h.add(Entry("dictate", "insert", "inserted", created_at=created, audio=b"ogg"))
        h.log_usage(Usage("dictate", "asr", cost_usd=0.1))
        h.keep = "24h"
        assert h._db.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 2
        h.keep = "never"
        assert h._db.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 0
        assert h.add(Entry("dictate", "insert", "inserted", created_at=clock.now + 999999)) is None
        assert h.spend().total == 0.1
        h.keep = "forever"
        assert h.add(Entry("dictate", "insert", "inserted", created_at=0)) is not None
        clock.now += 999999999
        assert len(h.list()) == 1
    finally:
        h.close()


def test_prune_accepts_epoch_zero(tmp_path):
    h = History(tmp_path / "h.sqlite", clock=lambda: -1)
    try:
        h.add(Entry("dictate", "insert", "inserted", created_at=-86400))
        h.add(Entry("dictate", "insert", "inserted", created_at=-86400.5))
        h.keep = "24h"
        h.prune(now=0)
        assert [e.created_at for e in h.list()] == [-86400]
    finally:
        h.close()


@pytest.mark.parametrize("operation", ["delete", "delete_all", "prune", "update_result", "never"])
def test_removed_payloads_are_absent_from_database_bytes(tmp_path, clock, operation):
    path = tmp_path / "h.sqlite"
    # Distinct repeated markers exercise both in-page fragments and BLOB overflow pages.
    text_marker = "DELETED_TEXT_7a19_"
    audio_marker = b"DELETED_AUDIO_c3b8_"
    h = History(path, clock=clock)
    try:
        entry_id = h.add(
            Entry(
                "dictate",
                "insert",
                "inserted",
                raw=text_marker * 50,
                text=text_marker * 100,
                error=text_marker,
                audio=audio_marker * 10000,
                created_at=clock.now,
            )
        )
        survivor = h.add(Entry("ask", "answer", "shown", text="live", audio=b"live audio", created_at=clock.now + 10))
        h.log_usage(Usage("dictate", "asr", cost_usd=0.1))
        assert text_marker.encode() in path.read_bytes() and audio_marker in path.read_bytes()
        if operation == "never":
            h.keep = "never"
        elif operation == "prune":
            h.keep = "24h"
            clock.now += 86401
            h.prune()
        elif operation == "update_result":
            h.update_result(entry_id, raw="new", text="new", action="insert", status="inserted")
        else:
            getattr(h, operation)(*([entry_id] if operation == "delete" else []))
        assert text_marker.encode() not in path.read_bytes()
        if operation != "update_result":
            assert audio_marker not in path.read_bytes()
        else:
            assert h.audio(entry_id)[0] == audio_marker * 10000
        if operation not in {"delete_all", "never"}:
            assert h.audio(survivor) == (b"live audio", None)
        assert h.spend().total == 0.1
        assert not Path(str(path) + "-wal").exists()
        assert not Path(str(path) + "-journal").exists()
        assert h._db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        h.close()


@pytest.mark.parametrize("journal", ["DELETE", "WAL"])
def test_legacy_free_pages_scrubbed_once_without_losing_live_rows(tmp_path, journal):
    path = tmp_path / "h.sqlite"
    h = History(path)
    live_id = h.add(Entry("dictate", "insert", "inserted", text="live", audio=b"live audio", cost_usd=0.2))
    h.log_usage(Usage("dictate", "asr", cost_usd=0.1))
    dead_id = h.add(Entry("dictate", "insert", "inserted", text="LEGACY_TEXT_" * 200, audio=b"LEGACY_AUDIO_" * 10000))
    h.close()
    with sqlite3.connect(path) as db:
        db.execute(f"PRAGMA journal_mode = {journal}")
        legacy_entry_ids(db)
        db.execute("PRAGMA secure_delete = OFF")
        db.execute("DELETE FROM entries WHERE id=?", (dead_id,))
        db.execute("PRAGMA user_version = 2")
    db.close()
    assert b"LEGACY_AUDIO_" in path.read_bytes()
    h = History(path)
    try:
        assert b"LEGACY_AUDIO_" not in path.read_bytes()
        assert b"LEGACY_TEXT_" not in path.read_bytes()
        assert [(e.id, e.text) for e in h.list()] == [(live_id, "live")]
        assert h.audio(live_id) == (b"live audio", None)
        assert h.spend().calls == 1 and h.spend().total == 0.1
        assert h._db.execute("PRAGMA user_version").fetchone()[0] == 3
        assert h._db.execute("PRAGMA secure_delete").fetchone()[0] == 1
        assert h._db.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        statements = []
        h._db.set_trace_callback(statements.append)
        h._migrate()
        assert "VACUUM" not in statements
    finally:
        h.close()
    h = History(path)
    try:
        assert h._db.execute("PRAGMA secure_delete").fetchone()[0] == 1
        assert h.spend().calls == 1
    finally:
        h.close()


@pytest.mark.parametrize("fail_sql", ["VACUUM", "DROP TABLE entries_retention_legacy"])
def test_failed_migration_retries_without_duplicate_usage_or_lost_data(tmp_path, monkeypatch, fail_sql):
    path = tmp_path / "h.sqlite"
    h = History(path)
    entry_id = h.add(Entry("dictate", "insert", "inserted", text="live", audio=b"audio", cost_usd=0.3))
    h.close()
    with sqlite3.connect(path) as db:
        legacy_entry_ids(db)
        db.execute("PRAGMA user_version = 0")
    db.close()
    connect = sqlite3.connect
    connections = []

    class FailingMigration(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            if sql == fail_sql:
                raise sqlite3.OperationalError("simulated disk full")
            return super().execute(sql, *args, **kwargs)

    def failing_connect(*args, **kwargs):
        connection = connect(*args, **kwargs, factory=FailingMigration)
        connections.append(connection)
        return connection

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", failing_connect)
        with pytest.raises(sqlite3.OperationalError, match="simulated disk full"):
            History(path)
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connections[0].execute("SELECT 1")
    with connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM usage").fetchone()[0] == 1
    db.close()
    h = History(path)
    try:
        assert h.audio(entry_id) == (b"audio", None)
        assert h.list()[0].text == "live"
        assert h.spend().calls == 1 and h.spend().total == 0.3
        assert h._db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        h.close()


def test_migration_scrubs_in_page_remnants_even_without_free_pages(tmp_path):
    path = tmp_path / "h.sqlite"
    h = History(path)
    h.add(Entry("dictate", "insert", "inserted", text="live"))
    dead_id = h.add(Entry("dictate", "insert", "inserted", text="IN_PAGE_SECRET_" * 10))
    h.close()
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA secure_delete = OFF")
        db.execute("DELETE FROM entries WHERE id=?", (dead_id,))
        db.execute("PRAGMA user_version = 2")
        assert db.execute("PRAGMA freelist_count").fetchone()[0] == 0
    db.close()
    assert b"IN_PAGE_SECRET_" in path.read_bytes()
    h = History(path)
    try:
        assert b"IN_PAGE_SECRET_" not in path.read_bytes()
        assert [e.text for e in h.list()] == ["live"]
    finally:
        h.close()


def test_never_on_reopen_clears_all_history_but_backfills_cost(tmp_path, clock):
    path = tmp_path / "h.sqlite"
    h = History(path, clock=clock)
    h.add(
        Entry(
            "dictate", "insert", "inserted", text="future", audio=b"audio", created_at=clock.now + 999999, cost_usd=0.2
        )
    )
    h.close()
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version = 0")
    db.close()
    h = History(path, keep="never", clock=clock)
    try:
        assert h._db.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 0
        assert h.spend().calls == 1 and h.spend().total == 0.2
    finally:
        h.close()


@pytest.mark.parametrize("reopen", [False, True])
def test_expired_retry_id_cannot_overwrite_new_history(tmp_path, clock, reopen):
    path = tmp_path / "h.sqlite"
    h = History(path, keep="24h", clock=clock)
    old_id = h.add(Entry("dictate", "insert", "inserted", text="old", created_at=clock.now))
    clock.now += 86401
    assert h.list() == []
    if reopen:
        h.close()
        h = History(path, keep="24h", clock=clock)
    try:
        new_id = h.add(Entry("dictate", "insert", "inserted", text="new", created_at=clock.now))
        assert new_id != old_id
        h.update_result(old_id, raw="expired", text="expired", action="insert", status="inserted")
        assert [(e.id, e.text) for e in h.list()] == [(new_id, "new")]
    finally:
        h.close()
