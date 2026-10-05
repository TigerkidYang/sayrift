package app.localtypeless.android.ui

import android.content.Context
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import app.localtypeless.android.App
import app.localtypeless.android.NavBarSpace
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/** A tab's page: large title, optional actions, scrolling content that clears the floating navigation. */
@Composable
fun Screen(
    title: String,
    onBack: (() -> Unit)? = null,
    actions: @Composable () -> Unit = {},
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(
        Modifier.fillMaxSize().statusBarsPadding().imePadding().verticalScroll(rememberScrollState())
            .padding(horizontal = 18.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        ScreenHeader(title, onBack, actions)
        content()
        Spacer(Modifier.height(if (onBack == null) NavBarSpace else 24.dp))
    }
}

@Composable
fun ScreenHeader(title: String, onBack: (() -> Unit)?, actions: @Composable () -> Unit = {}) {
    Column {
        Spacer(Modifier.height(if (onBack != null) 4.dp else 18.dp))
        if (onBack != null) IconButton(Icons.AutoMirrored.Outlined.ArrowBack, "返回", onClick = onBack)
        Row(Modifier.fillMaxWidth().padding(start = 4.dp, bottom = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            Title(title, Modifier.weight(1f))
            actions()
        }
    }
}

/** Reload-on-change key for anything read from the store. */
@Composable
fun storeRevision(context: Context): Int {
    val rev by (context.applicationContext as App).store.revision.collectAsState()
    return rev
}

private val labelCache = mutableMapOf<String, String>()

/** "com.tencent.mm" -> "微信", via the launcher entry (the manifest declares the launcher query). */
fun appLabel(context: Context, pkg: String): String {
    if (pkg.isBlank()) return ""
    return labelCache.getOrPut(pkg) {
        runCatching {
            val pm = context.packageManager
            @Suppress("DEPRECATION") // the flags overload is API 33+
            pm.getApplicationLabel(pm.getApplicationInfo(pkg, 0)).toString()
        }.getOrElse { pkg.substringAfterLast('.') }
    }
}

fun modeLabel(mode: String) = when (mode) {
    "translate" -> "翻译"
    "ask" -> "Ask"
    else -> "听写"
}

private val timeFmt = DateTimeFormatter.ofPattern("HH:mm")
private val dateFmt = DateTimeFormatter.ofPattern("M月d日 EEEE", Locale.CHINA)

fun localDate(millis: Long): LocalDate = Instant.ofEpochMilli(millis).atZone(ZoneId.systemDefault()).toLocalDate()

fun timeOf(millis: Long): String = Instant.ofEpochMilli(millis).atZone(ZoneId.systemDefault()).format(timeFmt)

fun dayLabel(day: LocalDate, today: LocalDate = LocalDate.now()): String = when (day) {
    today -> "今天"
    today.minusDays(1) -> "昨天"
    else -> day.format(dateFmt)
}

fun formatWords(n: Int): String = when {
    n >= 10_000 -> String.format(Locale.US, "%.1f 万", n / 10_000.0)
    else -> n.toString()
}

/** Number and unit apart, so the number can be set large: (12, "分钟"). */
fun durationParts(seconds: Double): Pair<String, String> {
    val m = (seconds / 60).toInt()
    return when {
        m >= 60 -> String.format(Locale.US, "%.1f", seconds / 3600) to "小时"
        m >= 1 -> m.toString() to "分钟"
        else -> seconds.toInt().toString() to "秒"
    }
}

fun formatUsd(v: Double): String = when {
    v == 0.0 -> "$0"
    v < 0.01 -> String.format(Locale.US, "$%.4f", v)
    v < 1 -> String.format(Locale.US, "$%.3f", v)
    else -> String.format(Locale.US, "$%.2f", v)
}

/** Translation targets, as on the desktop (settings_page.LANGUAGES). */
val LANGUAGES = listOf(
    "English" to "英语",
    "Simplified Chinese" to "简体中文",
    "Traditional Chinese" to "繁体中文",
    "Japanese" to "日语",
    "Korean" to "韩语",
    "French" to "法语",
    "German" to "德语",
    "Spanish" to "西班牙语",
    "Portuguese" to "葡萄牙语",
    "Russian" to "俄语",
    "Italian" to "意大利语",
)

fun languageLabel(value: String) = LANGUAGES.firstOrNull { it.first == value }?.second ?: value
