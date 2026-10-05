package app.localtypeless.android.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowForward
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.localtypeless.android.Health
import app.localtypeless.android.LocalResume
import app.localtypeless.android.MainActivity
import app.localtypeless.android.Store
import app.localtypeless.android.VoiceAccessibilityService
import androidx.compose.runtime.collectAsState
import java.time.LocalDate
import java.time.LocalTime

@Composable
fun TodayScreen(activity: MainActivity, onOpenHistory: () -> Unit, onOpenKey: () -> Unit) {
    val app = activity.app
    val resume = LocalResume.current
    val running by VoiceAccessibilityService.running.collectAsState()
    val issues = remember(resume, running) { Health.issues(activity, app.prefs) }
    val rev = storeRevision(activity)
    // Keyed on resume and the date too: opened the next morning, "today" must not still be yesterday.
    val stats = remember(rev, resume, java.time.LocalDate.now()) { app.store.stats() }
    val recent = remember(rev) { app.store.entries(limit = 3) }

    Screen(greeting()) {
        if (issues.isNotEmpty()) IssueCard(activity, issues.first(), issues.size - 1, onOpenKey)
        else ReadyCard()

        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Stat("今天", formatWords(stats.todayWords), "字", Modifier.weight(1f))
            Stat("累计", formatWords(stats.words), "字", Modifier.weight(1f))
        }
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            val (saved, unit) = durationParts(stats.timeSavedS)
            Stat("比打字省下", if (stats.timeSavedS > 0) saved else "—", unit.takeIf { stats.timeSavedS > 0 }, Modifier.weight(1f))
            Stat("连续使用", stats.streak.toString(), "天", Modifier.weight(1f))
        }

        Card {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("最近 20 周", color = G.Ink, fontSize = 15.sp, fontWeight = FontWeight.Medium, modifier = Modifier.weight(1f))
                Text("累计 ${stats.sessions} 次", color = G.Faint, fontSize = 12.sp)
            }
            Spacer(Modifier.height(12.dp))
            Heatmap(stats)
        }

        TryCard()

        if (recent.isNotEmpty()) {
            Row(Modifier.padding(top = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                SectionLabel("最近", Modifier.weight(1f))
                LinkText("全部", onOpenHistory)
            }
            Group {
                recent.forEachIndexed { i, e ->
                    if (i > 0) Divider(inset = 16.dp)
                    RecentRow(activity, e, onOpenHistory)
                }
            }
        }
    }
}

private fun greeting(): String {
    val h = LocalTime.now().hour
    return when (h) {
        in 5..10 -> "早上好"
        in 11..12 -> "中午好"
        in 13..17 -> "下午好"
        else -> "晚上好"
    }
}

@Composable
private fun ReadyCard() {
    Card {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Orb(40.dp)
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    StatusDot(G.Good)
                    Spacer(Modifier.width(8.dp))
                    Text("一切就绪", color = G.Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                }
                Spacer(Modifier.height(3.dp))
                Body("点进任何输入框，屏幕边缘会出现细线。点它说话，长按可以选翻译或 Ask。", size = 13)
            }
        }
    }
}

@Composable
private fun Stat(label: String, value: String, unit: String?, modifier: Modifier) {
    Card(modifier, padding = androidx.compose.foundation.layout.PaddingValues(16.dp)) {
        Text(label, color = G.Faint, fontSize = 12.sp)
        Spacer(Modifier.height(6.dp))
        Row(verticalAlignment = Alignment.Bottom) {
            Text(value, color = G.Ink, fontSize = 24.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
            if (unit != null) {
                Spacer(Modifier.width(4.dp))
                Text(unit, color = G.Muted, fontSize = 13.sp, modifier = Modifier.padding(bottom = 3.dp))
            }
        }
    }
}

/** Words per day, 20 weeks by 7 days, like the desktop's activity map. */
@Composable
private fun Heatmap(stats: Store.Stats) {
    val today = LocalDate.now()
    val weeks = 20
    val start = today.minusDays(today.dayOfWeek.value - 1L).minusWeeks(weeks - 1L) // Monday, 20 weeks back
    val max = (stats.wordsByDay.values.maxOrNull() ?: 0).coerceAtLeast(1)
    Canvas(Modifier.fillMaxWidth().aspectRatio(weeks / 7f)) {
        val gap = 3.dp.toPx()
        val cell = (size.width - gap * (weeks - 1)) / weeks
        for (w in 0 until weeks) for (d in 0 until 7) {
            val day = start.plusWeeks(w.toLong()).plusDays(d.toLong())
            if (day.isAfter(today)) continue
            val words = stats.wordsByDay[day] ?: 0
            val color = if (words == 0) Color(0x12FFFFFF)
            else lerp(G.Violet.copy(alpha = 0.35f), G.Cyan, (words.toFloat() / max).coerceIn(0.15f, 1f))
            drawRoundRect(color, Offset(w * (cell + gap), d * (cell + gap)), Size(cell, cell), CornerRadius(cell * 0.28f))
        }
    }
}

@Composable
private fun TryCard() {
    var text by rememberSaveable { mutableStateOf("") }
    Card {
        Text("试一试", color = G.Ink, fontSize = 15.sp, fontWeight = FontWeight.Medium)
        Spacer(Modifier.height(4.dp))
        Body("点下面的框，再点屏幕边缘的细线，说一句话。", size = 13)
        Spacer(Modifier.height(12.dp))
        Field(text, { text = it }, "说点什么…", minLines = 3)
    }
}

@Composable
private fun RecentRow(activity: MainActivity, e: Store.Entry, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().clickable(onClick = onClick).padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(e.text, color = G.Ink, fontSize = 14.5.sp, maxLines = 2, overflow = TextOverflow.Ellipsis, lineHeight = 20.sp)
            Spacer(Modifier.height(4.dp))
            Text(listOf(timeOf(e.time), appLabel(activity, e.app), modeLabel(e.mode).takeIf { e.mode != "dictate" })
                .filter { !it.isNullOrBlank() }.joinToString("  ·  "), color = G.Faint, fontSize = 12.sp)
        }
        Spacer(Modifier.width(8.dp))
        Icon(Icons.AutoMirrored.Outlined.ArrowForward, null, tint = G.Faint, modifier = Modifier.width(16.dp))
    }
}
