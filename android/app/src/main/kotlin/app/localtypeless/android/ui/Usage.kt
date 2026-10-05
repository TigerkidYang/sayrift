package app.localtypeless.android.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.localtypeless.android.MainActivity
import app.localtypeless.core.Account
import app.localtypeless.core.OpenRouterClient
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.time.LocalDate

/** The desktop's Usage page for the phone: what this phone spent (from its own log) and the account balance. */
@Composable
fun UsageScreen(activity: MainActivity, onBack: () -> Unit) {
    val app = activity.app
    val rev = storeRevision(activity)
    val spend = remember(rev) { app.store.spend() }
    var account by remember { mutableStateOf<Account?>(null) }
    var accountError by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) {
        val key = app.prefs.apiKey ?: run { accountError = "还没有填写 key"; return@LaunchedEffect }
        withContext(Dispatchers.IO) { runCatching { OpenRouterClient(key, baseUrl = app.prefs.apiBase).account() } }
            .onSuccess { account = it }
            .onFailure { e ->
                accountError = if (e is app.localtypeless.core.HttpException && e.code in setOf(401, 403)) "OpenRouter 不认这个 key"
                else "读取账户失败，检查一下网络"
            }
    }

    Screen("用量与余额", onBack = onBack) {
        Card {
            Text("本月", color = G.Faint, fontSize = 12.sp)
            Spacer(Modifier.height(6.dp))
            Text(formatUsd(spend.month), color = G.Ink, fontSize = 34.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(2.dp))
            Body(if (spend.month > 0) "照这个速度，全月大约 ${formatUsd(spend.monthProjection)}" else "这个月还没用过", size = 13)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Mini("今天", formatUsd(spend.today), Modifier.weight(1f))
            Mini("累计", formatUsd(spend.total), Modifier.weight(1f))
            Mini("平均每次", if (spend.uses > 0) formatUsd(spend.total / spend.uses) else "—", Modifier.weight(1f))
        }
        Card {
            Text("最近 30 天", color = G.Ink, fontSize = 15.sp, fontWeight = FontWeight.Medium)
            Spacer(Modifier.height(14.dp))
            Bars(spend.byDay)
        }
        if (spend.byMode.isNotEmpty()) {
            SectionLabel("按功能")
            Group {
                spend.byMode.entries.sortedByDescending { it.value }.forEachIndexed { i, (mode, cost) ->
                    if (i > 0) Divider(inset = 16.dp)
                    SettingRow(modeLabel(mode)) { Text(formatUsd(cost), color = G.Muted, fontSize = 14.sp) }
                }
            }
        }
        SectionLabel("OpenRouter 账户")
        Group {
            val a = account
            when {
                a != null -> {
                    SettingRow("账户余额", "所有 key 共用") { Text(a.balance?.let(::formatUsd) ?: "—", color = G.Ink, fontSize = 15.sp) }
                    Divider(inset = 16.dp)
                    SettingRow("这个 key 今天", null) { Text(formatUsd(a.keyToday), color = G.Muted, fontSize = 14.sp) }
                    Divider(inset = 16.dp)
                    SettingRow("这个 key 本月", null) { Text(formatUsd(a.keyMonth), color = G.Muted, fontSize = 14.sp) }
                    a.keyLimitRemaining?.let {
                        Divider(inset = 16.dp)
                        SettingRow("这个 key 剩余额度", null) { Text(formatUsd(it), color = G.Muted, fontSize = 14.sp) }
                    }
                }
                accountError != null -> SettingRow(accountError!!)
                else -> SettingRow("读取中…")
            }
        }
        Body("本机的数字按每次请求 OpenRouter 报的价格累计；账户数字直接来自 OpenRouter。", Modifier.padding(horizontal = 6.dp), size = 12)
    }
}

@Composable
private fun Mini(label: String, value: String, modifier: Modifier) {
    Card(modifier, padding = PaddingValues(14.dp)) {
        Text(label, color = G.Faint, fontSize = 12.sp)
        Spacer(Modifier.height(4.dp))
        Text(value, color = G.Ink, fontSize = 17.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
    }
}

@Composable
private fun Bars(byDay: Map<LocalDate, Double>) {
    val today = LocalDate.now()
    val days = (29 downTo 0).map { today.minusDays(it.toLong()) }
    val max = days.maxOf { byDay[it] ?: 0.0 }.coerceAtLeast(1e-9)
    Canvas(Modifier.fillMaxWidth().height(96.dp)) {
        val gap = 3.dp.toPx()
        val w = (size.width - gap * 29) / 30
        days.forEachIndexed { i, d ->
            val v = byDay[d] ?: 0.0
            val h = if (v <= 0) 3.dp.toPx() else maxOf(4.dp.toPx(), (v / max * size.height).toFloat())
            val brush = if (v <= 0) Brush.linearGradient(listOf(Color(0x14FFFFFF), Color(0x14FFFFFF)))
            else Brush.verticalGradient(listOf(G.Cyan, G.Violet), startY = size.height - h, endY = size.height)
            drawRoundRect(brush, Offset(i * (w + gap), size.height - h), Size(w, h), CornerRadius(w / 3))
        }
    }
    Spacer(Modifier.height(6.dp))
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text("30 天前", color = G.Faint, fontSize = 11.sp, modifier = Modifier.weight(1f))
        Text("今天", color = G.Faint, fontSize = 11.sp)
    }
}
