package app.localtypeless.android.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowForwardIos
import androidx.compose.material.icons.outlined.Accessibility
import androidx.compose.material.icons.outlined.BatteryChargingFull
import androidx.compose.material.icons.outlined.Check
import androidx.compose.material.icons.outlined.DeveloperMode
import androidx.compose.material.icons.outlined.History
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material.icons.outlined.Key
import androidx.compose.material.icons.outlined.Mic
import androidx.compose.material.icons.outlined.Notifications
import androidx.compose.material.icons.outlined.PieChart
import androidx.compose.material.icons.outlined.PlayCircleOutline
import androidx.compose.material.icons.outlined.RestartAlt
import androidx.compose.material.icons.outlined.RocketLaunch
import androidx.compose.material.icons.outlined.Shield
import androidx.compose.material.icons.outlined.SwapHoriz
import androidx.compose.material.icons.outlined.Translate
import androidx.compose.material.icons.outlined.Vibration
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.localtypeless.android.BuildConfig
import app.localtypeless.android.Health
import app.localtypeless.android.LocalResume
import app.localtypeless.android.MainActivity
import app.localtypeless.android.VoiceAccessibilityService

val KEEP_OPTIONS = listOf("forever" to "永久保存", "30" to "30 天", "7" to "7 天", "1" to "1 天", "never" to "不保存")

@Composable
fun SettingsScreen(activity: MainActivity, onOpenUsage: () -> Unit, onOpenKey: () -> Unit, onRestartGuide: () -> Unit) {
    val prefs = activity.app.prefs
    val resume = LocalResume.current
    val running by VoiceAccessibilityService.running.collectAsState()
    var target by remember { mutableStateOf(prefs.translateTarget) }
    var right by remember { mutableStateOf(prefs.handleRight) }
    var haptics by remember { mutableStateOf(prefs.haptics) }
    var keep by remember { mutableStateOf(prefs.keep) }
    var testAudio by remember { mutableStateOf(prefs.useTestAudio) }
    var dialog by remember { mutableStateOf<String?>(null) }
    var pendingKeep by remember { mutableStateOf<String?>(null) }
    val keySet = remember(resume, dialog) { prefs.apiKey != null }

    Screen("设置") {
        SectionLabel("说话")
        Group {
            SettingRow("翻译成", "长按细线选“翻译”时的目标语言", Icons.Outlined.Translate, onClick = { dialog = "lang" }) {
                Value(languageLabel(target))
            }
        }

        SectionLabel("边缘细线")
        Group {
            SettingRow("位置", "也可以直接拖动细线换边、换高度", Icons.Outlined.SwapHoriz) {
                Segmented(listOf(false to "左", true to "右"), right, { right = it; prefs.handleRight = it })
            }
            Divider()
            SettingRow("震动反馈", "开始和结束时轻震一下", Icons.Outlined.Vibration) {
                Toggle(haptics) { haptics = it; prefs.haptics = it }
            }
            Divider()
            SettingRow("恢复默认位置", null, Icons.Outlined.RestartAlt, onClick = {
                prefs.handleRight = true; prefs.handleY = 0.42f; right = true
                android.widget.Toast.makeText(activity, "已恢复到右侧中间", android.widget.Toast.LENGTH_SHORT).show()
            })
        }

        SectionLabel("OpenRouter")
        Group {
            SettingRow("API key", if (keySet) "已保存，加密存在这台手机上" else "还没有填写", Icons.Outlined.Key,
                iconTint = if (keySet) G.Muted else G.Warn, onClick = onOpenKey) { Chevron() }
            Divider()
            SettingRow("用量与余额", "花了多少钱、账户还剩多少", Icons.Outlined.PieChart, onClick = onOpenUsage) { Chevron() }
        }

        SectionLabel("历史记录")
        Group {
            SettingRow("保存多久", "只存在这台手机上", Icons.Outlined.History, onClick = { dialog = "keep" }) {
                Value(KEEP_OPTIONS.first { it.first == keep }.second)
            }
        }

        SectionLabel("权限与后台")
        Group {
            val mic = remember(resume) { Health.mic(activity) }
            val notify = remember(resume) { Health.notifications(activity) }
            val enabled = remember(resume, running) { Health.serviceEnabled(activity) }
            val battery = remember(resume) { Health.batteryUnrestricted(activity) }
            SettingRow("麦克风", "只在你说话时打开", Icons.Outlined.Mic, onClick = { if (!mic) fixIssue(activity, Health.Issue.MIC) {} }) { Status(mic) }
            Divider()
            SettingRow("通知", "录音时显示一条通知", Icons.Outlined.Notifications,
                onClick = { if (!notify) fixIssue(activity, Health.Issue.NOTIFICATIONS) {} else Health.openNotificationSettings(activity) }) { Status(notify) }
            Divider()
            SettingRow(
                "无障碍服务",
                when {
                    !enabled -> "没有开启"
                    !running -> "被系统停掉了：关掉再打开一次"
                    else -> "正在运行"
                },
                Icons.Outlined.Accessibility,
                iconTint = if (enabled && !running) G.Warn else G.Muted,
                onClick = { Health.openAccessibility(activity) },
            ) { Status(enabled && running) }
            Divider()
            SettingRow("省电策略", if (battery) "不受限制" else "可能被系统在后台关掉", Icons.Outlined.BatteryChargingFull,
                onClick = { Health.requestBattery(activity) }) { Status(battery) }
            if (Health.isXiaomi) {
                Divider()
                SettingRow("自启动", "改完后系统会关掉无障碍服务，需要再打开一次", Icons.Outlined.RocketLaunch,
                    onClick = { Health.openAutostart(activity) }) { Chevron() }
            }
        }

        SectionLabel("关于")
        Group {
            SettingRow("隐私", "说的话和数据去了哪里", Icons.Outlined.Shield, onClick = { dialog = "privacy" }) { Chevron() }
            Divider()
            SettingRow("重新看一遍引导", null, Icons.Outlined.PlayCircleOutline, onClick = onRestartGuide) { Chevron() }
            Divider()
            SettingRow("版本", null, Icons.Outlined.Info) { Value(BuildConfig.VERSION_NAME) }
        }

        if (BuildConfig.DEBUG) {
            SectionLabel("开发者")
            Group {
                SettingRow("用测试音频代替麦克风", "files/test-audio.ogg", Icons.Outlined.DeveloperMode) {
                    Toggle(testAudio) { testAudio = it; prefs.useTestAudio = it }
                }
            }
        }
    }

    pendingKeep?.let { choice ->
        val doomed = activity.app.store.countDeleted(if (choice == "never") 0 else choice.toIntOrNull())
        AlertDialog(
            onDismissRequest = { pendingKeep = null },
            containerColor = Color(0xFF15161F),
            title = { Text("删除 $doomed 条历史？", color = G.Ink) },
            text = { Text(if (choice == "never") "不保存历史后，已有的记录也会被删除，无法恢复。用量统计会保留。"
                else "早于 ${KEEP_OPTIONS.first { it.first == choice }.second} 的记录会被删除，无法恢复。", color = G.Muted) },
            confirmButton = { TextButton({
                keep = choice; prefs.keep = choice
                if (choice == "never") activity.app.store.clear() else activity.app.store.prune(prefs.keepDays)
                pendingKeep = null
            }) { Text("删除", color = G.Bad) } },
            dismissButton = { TextButton({ pendingKeep = null }) { Text("取消", color = G.Muted) } },
        )
    }

    when (dialog) {
        "lang" -> ChoiceDialog("翻译成", LANGUAGES, target, { target = it; prefs.translateTarget = it }) { dialog = null }
        "keep" -> ChoiceDialog("历史保存多久", KEEP_OPTIONS, keep, { choice ->
            val days = choice.toIntOrNull()
            val doomed = activity.app.store.countDeleted(if (choice == "never") 0 else days)
            if (doomed > 0) pendingKeep = choice else { keep = choice; prefs.keep = choice }
        }) { dialog = null }
        "privacy" -> AlertDialog(
            onDismissRequest = { dialog = null },
            containerColor = Color(0xFF15161F),
            title = { Text("隐私", color = G.Ink) },
            text = { Text(PRIVACY, color = G.Muted, fontSize = 14.sp, lineHeight = 21.sp) },
            confirmButton = { TextButton({ dialog = null }) { Text("知道了", color = G.Ink) } },
        )
    }
}

private const val PRIVACY = """• 录音只在你点细线之后开始，点 ✓ 或 ✕ 就停止，不在手机上保存。
• 录音发给语音识别模型，识别出的文字发给整理模型，都经过 OpenRouter。请求使用隐私路由，筛选不收集用户数据用于训练的服务商；这不等于零数据保留，具体保留政策以服务商为准。
• 发给模型的上下文只有：当前应用的名字、你设的词典，以及用 Ask 时选中的文字。
• 无障碍服务只用来知道哪里有输入框、把结果放进去。它不读取屏幕上的其他内容，也不上传屏幕。
• 历史记录只存在这台手机上，可以设置保存多久，也可以设成不保存。
• 没有账号，不做任何统计上报。"""

@Composable
private fun Value(text: String) {
    Text(text, color = G.Muted, fontSize = 14.sp)
}

@Composable
private fun Chevron() {
    Icon(Icons.AutoMirrored.Outlined.ArrowForwardIos, null, tint = G.Faint, modifier = Modifier.size(14.dp))
}

@Composable
private fun Status(ok: Boolean) {
    if (ok) Icon(Icons.Outlined.Check, "已完成", tint = G.Good, modifier = Modifier.size(20.dp))
    else Text("去设置", color = G.Warn, fontSize = 13.sp)
}

@Composable
fun ChoiceDialog(title: String, options: List<Pair<String, String>>, selected: String, onPick: (String) -> Unit, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = Color(0xFF15161F),
        title = { Text(title, color = G.Ink) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                options.forEach { (value, label) ->
                    Row(
                        Modifier.fillMaxWidth().heightIn(min = 48.dp).clip(RoundedCornerShape(12.dp))
                            .background(if (value == selected) Color(0x1AFFFFFF) else Color.Transparent)
                            .clickable { onPick(value); onDismiss() }.padding(horizontal = 14.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(label, color = G.Ink, fontSize = 15.sp, modifier = Modifier.weight(1f))
                        if (value == selected) Icon(Icons.Outlined.Check, null, tint = G.Violet, modifier = Modifier.size(18.dp))
                    }
                }
            }
        },
        confirmButton = {},
        dismissButton = { TextButton(onDismiss) { Text("取消", color = G.Muted) } },
    )
}

@Composable
fun KeyScreen(activity: MainActivity, onBack: () -> Unit) {
    val prefs = activity.app.prefs
    var saved by remember { mutableStateOf(prefs.apiKey != null) }
    var balance by remember { mutableStateOf<Double?>(null) }
    var justSaved by remember { mutableStateOf(false) }
    var confirm by remember { mutableStateOf(false) }
    if (confirm) AlertDialog(
        onDismissRequest = { confirm = false },
        containerColor = Color(0xFF15161F),
        title = { Text("删除这个 key？", color = G.Ink) },
        text = { Text("删除后就不能说话了，直到填入新的 key。", color = G.Muted) },
        confirmButton = { TextButton({ prefs.apiKey = null; saved = false; justSaved = false; confirm = false }) { Text("删除", color = G.Bad) } },
        dismissButton = { TextButton({ confirm = false }) { Text("取消", color = G.Muted) } },
    )
    Screen("OpenRouter key", onBack = onBack) {
        Card {
            Row(verticalAlignment = Alignment.CenterVertically) {
                StatusDot(if (saved) G.Good else G.Warn)
                Spacer(Modifier.width(10.dp))
                Text(
                    when {
                        justSaved -> "已保存" + (balance?.let { " · 余额 ${formatUsd(it)}" } ?: "")
                        saved -> "已保存一个 key"
                        else -> "还没有 key"
                    },
                    color = G.Ink, fontSize = 15.sp,
                )
            }
            if (saved) {
                Spacer(Modifier.padding(top = 6.dp))
                Body("要换 key，直接在下面粘贴新的；旧的会被替换。", size = 13)
            }
        }
        Card { KeyEditor(activity) { b -> saved = true; justSaved = true; balance = b } }
        if (saved) Button("删除这个 key", style = ButtonStyle.Quiet) { confirm = true }
    }
}
