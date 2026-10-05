package app.localtypeless.android.ui

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.widget.Toast
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ContentCopy
import androidx.compose.material.icons.outlined.DeleteOutline
import androidx.compose.material.icons.outlined.DeleteSweep
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.localtypeless.android.MainActivity
import app.localtypeless.android.Store

@Composable
fun HistoryScreen(activity: MainActivity) {
    val store = activity.app.store
    val prefs = activity.app.prefs
    var query by rememberSaveable { mutableStateOf("") }
    var mode by rememberSaveable { mutableStateOf<String?>(null) }
    var open by rememberSaveable { mutableStateOf<Long?>(null) }
    var confirmClear by remember { mutableStateOf(false) }
    val rev = storeRevision(activity)
    val entries = remember(rev, query, mode) { store.entries(query.trim(), mode) }

    Screen("历史", actions = {
        if (entries.isNotEmpty() && query.isBlank() && mode == null) IconButton(Icons.Outlined.DeleteSweep, "清空历史") { confirmClear = true }
    }) {
        Field(query, { query = it }, "搜索说过的话", singleLine = true, leading = Icons.Outlined.Search)
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf(null to "全部", "dictate" to "听写", "translate" to "翻译", "ask" to "Ask").forEach { (m, label) ->
                Chip(label, mode == m) { mode = m }
            }
        }

        when {
            prefs.keep == "never" && entries.isEmpty() -> Empty("历史记录已关闭", "在设置 → 历史记录里可以重新打开。")
            entries.isEmpty() && (query.isNotBlank() || mode != null) -> Empty("没有找到", "换个关键词试试。")
            entries.isEmpty() -> Empty("还没有记录", "说的每一句话都会出现在这里，只保存在这台手机上。")
            else -> entries.groupBy { localDate(it.time) }.forEach { (day, list) ->
                SectionLabel(dayLabel(day), Modifier.padding(top = 6.dp))
                Group {
                    list.forEachIndexed { i, e ->
                        if (i > 0) Divider(inset = 16.dp)
                        EntryRow(activity, e, expanded = open == e.id, onToggle = { open = if (open == e.id) null else e.id })
                    }
                }
            }
        }
    }

    if (confirmClear) AlertDialog(
        onDismissRequest = { confirmClear = false },
        containerColor = androidx.compose.ui.graphics.Color(0xFF15161F),
        title = { Text("清空全部历史？", color = G.Ink) },
        text = { Text("删除后无法恢复。用量统计会保留。", color = G.Muted) },
        confirmButton = { TextButton({ store.clear(); confirmClear = false }) { Text("清空", color = G.Bad) } },
        dismissButton = { TextButton({ confirmClear = false }) { Text("取消", color = G.Muted) } },
    )
}

@Composable
private fun Empty(title: String, body: String) {
    Column(Modifier.fillMaxWidth().padding(vertical = 56.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Orb(44.dp)
        Spacer(Modifier.height(16.dp))
        Text(title, color = G.Ink, fontSize = 16.sp, fontWeight = FontWeight.Medium)
        Spacer(Modifier.height(6.dp))
        Body(body, size = 13)
    }
}

@Composable
private fun EntryRow(activity: MainActivity, e: Store.Entry, expanded: Boolean, onToggle: () -> Unit) {
    Column(Modifier.fillMaxWidth().clickable(onClick = onToggle).padding(horizontal = 16.dp, vertical = 13.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(timeOf(e.time), color = G.Faint, fontSize = 12.sp)
            val app = appLabel(activity, e.app)
            if (app.isNotBlank()) Text("  ·  $app", color = G.Faint, fontSize = 12.sp)
            Spacer(Modifier.weight(1f))
            if (e.mode != "dictate") Tag(modeLabel(e.mode), if (e.mode == "ask") G.Violet else G.Cyan)
        }
        Spacer(Modifier.height(5.dp))
        Text(e.text, color = G.Ink, fontSize = 15.sp, lineHeight = 22.sp, maxLines = if (expanded) Int.MAX_VALUE else 3)
        AnimatedVisibility(expanded) {
            Column {
                if (e.raw.isNotBlank() && e.raw != e.text) {
                    Spacer(Modifier.height(10.dp))
                    Text("原话", color = G.Faint, fontSize = 12.sp)
                    Spacer(Modifier.height(2.dp))
                    Text(e.raw, color = G.Muted, fontSize = 13.5.sp, lineHeight = 20.sp)
                }
                Spacer(Modifier.height(10.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
                    IconButton(Icons.Outlined.ContentCopy, "复制") {
                        activity.getSystemService(ClipboardManager::class.java).setPrimaryClip(ClipData.newPlainText("history", e.text))
                        Toast.makeText(activity, "已复制", Toast.LENGTH_SHORT).show()
                    }
                    IconButton(Icons.Outlined.Share, "分享") {
                        activity.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain")
                            .putExtra(Intent.EXTRA_TEXT, e.text), null))
                    }
                    Spacer(Modifier.weight(1f))
                    if (e.cost > 0) Text(formatUsd(e.cost), color = G.Faint, fontSize = 12.sp)
                    IconButton(Icons.Outlined.DeleteOutline, "删除", tint = G.Bad) { activity.app.store.delete(e.id) }
                }
            }
        }
    }
}
