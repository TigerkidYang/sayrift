package app.localtypeless.android

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

/**
 * History and usage on the phone, the desktop's store.py in miniature. Entries are what you said (pruned by the
 * retention setting); usage rows are only numbers and outlive the entries, so the spend page stays right after
 * history is cleared. No audio is kept: there is no "retry" on the phone yet.
 */
class Store(context: Context) : SQLiteOpenHelper(context, "history.db", null, 1) {
    private val historyPrefs = context.applicationContext.getSharedPreferences("settings", Context.MODE_PRIVATE)
    private val _revision = MutableStateFlow(0)

    /** Bumped on every change, so open screens can reload. */
    val revision: StateFlow<Int> = _revision

    private fun changed() { _revision.value++ }

    data class Entry(
        val id: Long,
        val time: Long,
        val mode: String, // dictate / translate / ask
        val app: String,
        val text: String,
        val raw: String,
        val cost: Double,
        val seconds: Double,
    )

    data class Stats(
        val words: Int,
        val todayWords: Int,
        val sessions: Int,
        val speakingS: Double,
        val timeSavedS: Double,
        val streak: Int,
        val wordsByDay: Map<LocalDate, Int>,
    )

    data class Spend(
        val today: Double,
        val month: Double,
        val monthProjection: Double,
        val total: Double,
        val uses: Int,
        val byDay: Map<LocalDate, Double>,
        val byMode: Map<String, Double>,
    )

    override fun onConfigure(db: SQLiteDatabase) {
        super.onConfigure(db)
        enableSecureDelete(db)
    }

    private fun enableSecureDelete(db: SQLiteDatabase) {
        // This PRAGMA returns a row. Android 11's execPerConnectionSQL routes it through
        // executeNonQuery, which throws on SQLITE_ROW (AOSP android-11.0.0_r1).
        // Consume the cursor; configuring one connection is not a pool-wide guarantee.
        db.rawQuery("PRAGMA secure_delete = ON", null).use { it.moveToFirst() }
    }

    private fun <T> write(block: (SQLiteDatabase) -> T): T {
        val db = writableDatabase
        db.beginTransaction()
        try {
            // On every API, pin the PRAGMA and writes to the same connection, including after
            // idle replacement. Other pooled connections are not guaranteed to be configured.
            enableSecureDelete(db)
            val result = block(db)
            db.setTransactionSuccessful()
            return result
        } finally {
            db.endTransaction()
        }
    }

    private fun retentionDays(): Int? = when (val keep = historyPrefs.getString("keep", "forever")) {
        "never" -> 0
        else -> keep?.toIntOrNull()?.coerceAtLeast(0)
    }

    private fun deleteExpired(db: SQLiteDatabase, days: Int?, now: Long): Int = when (days) {
        null -> 0
        0 -> db.delete("entries", null, null)
        else -> db.delete("entries", "time < ?", arrayOf((now - days * 86_400_000L).toString()))
    }

    private fun enforceRetention() = prune(retentionDays())

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """CREATE TABLE entries (id INTEGER PRIMARY KEY AUTOINCREMENT, time INTEGER NOT NULL, mode TEXT NOT NULL,
               app TEXT NOT NULL, text TEXT NOT NULL, raw TEXT NOT NULL, cost REAL NOT NULL, seconds REAL NOT NULL,
               words INTEGER NOT NULL)"""
        )
        db.execSQL("CREATE INDEX entries_time ON entries(time)")
        db.execSQL("CREATE TABLE usage (time INTEGER NOT NULL, mode TEXT NOT NULL, cost REAL NOT NULL, words INTEGER NOT NULL, seconds REAL NOT NULL)")
        db.execSQL("CREATE INDEX usage_time ON usage(time)")
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {}

    /** Record one finished session. [keepEntry] false = history is off: only the numbers are kept. */
    fun add(time: Long, mode: String, app: String, text: String, raw: String, cost: Double, seconds: Double, keepEntry: Boolean) {
        val words = countWords(text)
        val days = retentionDays()
        val now = System.currentTimeMillis()
        write { db ->
            deleteExpired(db, days, now)
            db.insertOrThrow("usage", null, ContentValues().apply {
                put("time", time); put("mode", mode); put("cost", cost); put("words", words); put("seconds", seconds)
            })
            // Imported or delayed results must obey the same policy as ordinary sessions.
            val withinRetention = days == null || (days > 0 && time >= now - days * 86_400_000L)
            if (keepEntry && withinRetention) db.insertOrThrow("entries", null, ContentValues().apply {
                put("time", time); put("mode", mode); put("app", app); put("text", text); put("raw", raw)
                put("cost", cost); put("seconds", seconds); put("words", words)
            })
        }
        changed()
    }

    fun entries(query: String = "", mode: String? = null, limit: Int = 500): List<Entry> {
        enforceRetention()
        val where = mutableListOf<String>()
        val args = mutableListOf<String>()
        if (query.isNotBlank()) {
            // % and _ typed in the search box are text, not wildcards.
            val q = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            where += "(text LIKE ? ESCAPE '\\' OR raw LIKE ? ESCAPE '\\')"; args += q; args += q
        }
        if (mode != null) { where += "mode = ?"; args += mode }
        val sql = "SELECT id, time, mode, app, text, raw, cost, seconds FROM entries" +
            (if (where.isEmpty()) "" else " WHERE " + where.joinToString(" AND ")) + " ORDER BY time DESC LIMIT $limit"
        return readableDatabase.rawQuery(sql, args.toTypedArray()).use { c ->
            buildList {
                while (c.moveToNext()) add(Entry(c.getLong(0), c.getLong(1), c.getString(2), c.getString(3), c.getString(4),
                    c.getString(5), c.getDouble(6), c.getDouble(7)))
            }
        }
    }

    fun delete(id: Long) {
        write { it.delete("entries", "id = ?", arrayOf(id.toString())) }
        changed()
    }

    fun clear() {
        write { it.delete("entries", null, null) }
        changed()
    }

    /** How many entries a retention of [days] would delete (0 days = all). */
    fun countDeleted(days: Int?): Int {
        enforceRetention()
        if (days == null) return 0
        val where = if (days <= 0) "" else " WHERE time < ?"
        val args = if (days <= 0) null else arrayOf((System.currentTimeMillis() - days * 86_400_000L).toString())
        return readableDatabase.rawQuery("SELECT COUNT(*) FROM entries$where", args)
            .use { if (it.moveToFirst()) it.getInt(0) else 0 }
    }

    /** Drop entries older than [days]; null keeps everything, zero removes even future-dated rows. */
    fun prune(days: Int?) {
        if (days == null) return
        val removed = write { deleteExpired(it, days.coerceAtLeast(0), System.currentTimeMillis()) }
        // Reads also prune. Do not trigger a reload loop when no rows were removed.
        if (removed > 0) changed()
    }

    fun stats(today: LocalDate = LocalDate.now()): Stats {
        enforceRetention()
        val byDay = sortedMapOf<LocalDate, Int>()
        var words = 0
        var sessions = 0
        var speaking = 0.0
        readableDatabase.rawQuery("SELECT time, words, seconds FROM usage", null).use { c ->
            while (c.moveToNext()) {
                val day = day(c.getLong(0))
                byDay[day] = (byDay[day] ?: 0) + c.getInt(1)
                words += c.getInt(1)
                speaking += c.getDouble(2)
                sessions++
            }
        }
        // Typeless compares against typing at 45 words per minute.
        val saved = maxOf(0.0, words / 45.0 * 60 - speaking)
        var streak = 0
        var d = if (byDay.containsKey(today)) today else today.minusDays(1) // a streak survives until the next day ends
        while (byDay.containsKey(d)) { streak++; d = d.minusDays(1) }
        return Stats(words, byDay[today] ?: 0, sessions, speaking, saved, streak, byDay)
    }

    fun spend(today: LocalDate = LocalDate.now()): Spend {
        enforceRetention()
        val byDay = sortedMapOf<LocalDate, Double>()
        val byMode = mutableMapOf<String, Double>()
        var total = 0.0
        var month = 0.0
        var uses = 0
        readableDatabase.rawQuery("SELECT time, mode, cost FROM usage", null).use { c ->
            while (c.moveToNext()) {
                val day = day(c.getLong(0))
                val cost = c.getDouble(2)
                byDay[day] = (byDay[day] ?: 0.0) + cost
                byMode[c.getString(1)] = (byMode[c.getString(1)] ?: 0.0) + cost
                total += cost
                uses++
                if (day.year == today.year && day.month == today.month) month += cost
            }
        }
        val projection = month / today.dayOfMonth * today.lengthOfMonth()
        return Spend(byDay[today] ?: 0.0, month, projection, total, uses, byDay, byMode)
    }

    private fun day(millis: Long): LocalDate = Instant.ofEpochMilli(millis).atZone(ZoneId.systemDefault()).toLocalDate()

    companion object {
        private val CJK = Regex("[぀-ヿ㐀-䶿一-鿿가-힯]")
        private val WORD = Regex("[A-Za-z0-9]+(?:['’][A-Za-z]+)?")

        /** Words the way a user thinks of them: each CJK character is one, each Latin word is one (store.py). */
        fun countWords(text: String): Int = CJK.findAll(text).count() + WORD.findAll(text).count()
    }
}
