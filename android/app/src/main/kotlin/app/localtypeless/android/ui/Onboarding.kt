package app.localtypeless.android.ui

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Check
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.localtypeless.android.Health
import app.localtypeless.android.LocalResume
import app.localtypeless.android.MainActivity
import app.localtypeless.android.VoiceAccessibilityService

// Background limits come before the accessibility step: on HyperOS, changing autostart makes the Security app
// force-stop us, which also switches our accessibility service off (seen on a Xiaomi 15, 2026-09-28).
private enum class Step { WELCOME, KEY, MIC, BACKGROUND, SERVICE, TRY }

@Composable
fun Onboarding(activity: MainActivity, canLeave: Boolean = false, onDone: () -> Unit) {
    val prefs = activity.app.prefs
    var step by remember {
        mutableStateOf(prefs.guideStep?.let { saved -> Step.entries.firstOrNull { it.name == saved } } ?: Step.WELCOME)
    }
    LaunchedEffect(step) { prefs.guideStep = step.name }
    val steps = Step.entries
    fun finish() { prefs.guideStep = null; onDone() }
    fun next() {
        val i = steps.indexOf(step)
        if (i == steps.lastIndex) finish() else step = steps[i + 1]
    }
    BackHandler(enabled = step != Step.WELCOME || canLeave) {
        if (step == Step.WELCOME) finish() else step = steps[steps.indexOf(step) - 1]
    }

    Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().imePadding()) {
        if (step != Step.WELCOME) Progress(steps.indexOf(step), steps.size - 1, onSkip = ::finish)
        AnimatedContent(
            step,
            transitionSpec = {
                val forward = targetState.ordinal > initialState.ordinal
                (slideInHorizontally { if (forward) it / 4 else -it / 4 } + fadeIn()) togetherWith
                    (slideOutHorizontally { if (forward) -it / 4 else it / 4 } + fadeOut())
            },
            label = "step",
            modifier = Modifier.weight(1f),
        ) { s ->
            when (s) {
                Step.WELCOME -> Welcome(::next)
                Step.KEY -> KeyStep(activity, ::next)
                Step.MIC -> MicStep(activity, ::next)
                Step.SERVICE -> ServiceStep(activity, ::next)
                Step.BACKGROUND -> BackgroundStep(activity, ::next)
                Step.TRY -> TryStep(activity, ::finish)
            }
        }
    }
}

@Composable
private fun Progress(index: Int, count: Int, onSkip: () -> Unit) {
    Row(Modifier.fillMaxWidth().padding(start = 24.dp, end = 12.dp, top = 12.dp), verticalAlignment = Alignment.CenterVertically) {
        Row(Modifier.weight(1f), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            for (i in 1..count) Box(
                Modifier.weight(1f).height(3.dp).clip(RoundedCornerShape(2.dp))
                    .background(if (i <= index) G.Violet else Color(0x1FFFFFFF))
            )
        }
        Spacer(Modifier.width(12.dp))
        Button("跳过", style = ButtonStyle.Quiet, onClick = onSkip)
    }
}

/** One step: big title, explanation, content, and the buttons pinned at the bottom. */
@Composable
private fun StepPage(
    title: String,
    body: String,
    primary: String?,
    primaryEnabled: Boolean = true,
    onPrimary: () -> Unit = {},
    secondary: String? = null,
    onSecondary: () -> Unit = {},
    content: @Composable ColumnScope.() -> Unit = {},
) {
    Column(Modifier.fillMaxSize().padding(horizontal = 24.dp)) {
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
            Spacer(Modifier.height(28.dp))
            Text(title, color = G.Ink, fontSize = 28.sp, fontWeight = FontWeight.SemiBold, lineHeight = 36.sp, letterSpacing = (-0.4).sp)
            Spacer(Modifier.height(10.dp))
            Body(body, size = 15)
            Spacer(Modifier.height(24.dp))
            content()
            Spacer(Modifier.height(16.dp))
        }
        Column(Modifier.padding(bottom = 16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            if (primary != null) Button(primary, Modifier.fillMaxWidth(), ButtonStyle.Primary, enabled = primaryEnabled, onClick = onPrimary)
            if (secondary != null) Button(secondary, Modifier.fillMaxWidth(), ButtonStyle.Quiet, onClick = onSecondary)
        }
    }
}

@Composable
private fun Welcome(next: () -> Unit) {
    val pulse = rememberInfiniteTransition(label = "orb")
    val scale by pulse.animateFloat(0.94f, 1.04f, infiniteRepeatable(tween(2600), RepeatMode.Reverse), label = "scale")
    Column(Modifier.fillMaxSize().padding(horizontal = 28.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Spacer(Modifier.weight(1f))
        Orb(112.dp, Modifier.scale(scale))
        Spacer(Modifier.height(40.dp))
        Text("开口，就是打字", color = G.Ink, fontSize = 32.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-0.5).sp)
        Spacer(Modifier.height(14.dp))
        Text(
            "在任何应用的输入框里，点一下屏幕边缘说话。\n嗯啊、口误和重复会被去掉，整理好的文字直接出现在光标处。",
            color = G.Muted, fontSize = 15.sp, lineHeight = 24.sp, textAlign = TextAlign.Center,
        )
        Spacer(Modifier.weight(1.2f))
        Button("开始设置", Modifier.fillMaxWidth(), ButtonStyle.Primary, onClick = next)
        Spacer(Modifier.height(10.dp))
        Text("大约需要 2 分钟", color = G.Faint, fontSize = 12.sp)
        Spacer(Modifier.height(20.dp))
    }
}

@Composable
private fun KeyStep(activity: MainActivity, next: () -> Unit) {
    var saved by remember { mutableStateOf(activity.app.prefs.apiKey != null) }
    var balance by remember { mutableStateOf<Double?>(null) }
    StepPage(
        "连接 OpenRouter",
        "语音识别和整理用的模型都通过 OpenRouter 调用，费用从你自己的账户里扣。日常使用，一个月通常不到 1 美元。",
        primary = if (saved) "继续" else null, onPrimary = next,
        secondary = if (saved) null else "稍后再填", onSecondary = next,
    ) {
        if (saved) Done("已连接" + (balance?.let { " · 账户余额 ${formatUsd(it)}" } ?: ""))
        else KeyEditor(activity) { b -> balance = b; saved = true }
    }
}

@Composable
private fun MicStep(activity: MainActivity, next: () -> Unit) {
    val resume = LocalResume.current
    val mic = remember(resume) { Health.mic(activity) }
    val notify = remember(resume) { Health.notifications(activity) }
    val doneOnArrival = remember { Health.mic(activity) && Health.notifications(activity) }
    // Move on by itself only when the user just granted them here: arriving with Back must not bounce forward.
    LaunchedEffect(mic, notify) { if (mic && notify && !doneOnArrival) { kotlinx.coroutines.delay(500); next() } }
    StepPage(
        "允许使用麦克风",
        "只在你点细线之后开始录音，说完就停。录音时系统要求显示一条通知，所以也需要通知权限。",
        primary = if (mic) "继续" else "允许",
        onPrimary = { if (mic) next() else fixIssue(activity, Health.Issue.MIC) {} },
    ) {
        Check("麦克风", mic)
        Check("通知", notify)
    }
}

@Composable
private fun ServiceStep(activity: MainActivity, next: () -> Unit) {
    val resume = LocalResume.current
    val running by VoiceAccessibilityService.running.collectAsState()
    val enabled = remember(resume, running) { Health.serviceEnabled(activity) }
    var opened by remember { mutableIntStateOf(0) }
    val runningOnArrival = remember { Health.serviceRunning() }
    LaunchedEffect(running) { if (running && !runningOnArrival) { kotlinx.coroutines.delay(600); next() } }
    StepPage(
        "打开无障碍服务",
        "边缘细线要靠它才能在别的应用里出现，识别好的文字也靠它放进输入框。",
        primary = if (running) "继续" else "打开无障碍设置",
        onPrimary = { if (running) next() else { opened++; Health.openAccessibility(activity) } },
    ) {
        if (running) Done("已开启") else {
            Card {
                Numbered(1, "在列表里找到“已下载的应用”或“已安装的服务”")
                Numbered(2, "点“Sayrift 语音输入”")
                Numbered(3, "打开开关，确认")
            }
            Spacer(Modifier.height(14.dp))
            Card {
                Text("它能看到什么", color = G.Ink, fontSize = 14.sp, fontWeight = FontWeight.Medium)
                Spacer(Modifier.height(6.dp))
                Body("只用来知道哪里有输入框、把结果放进去。不读取屏幕上的其他内容，不上传屏幕，没有账号，也不做统计。", size = 13)
            }
            if (opened > 0 && !enabled) {
                Spacer(Modifier.height(14.dp))
                Card {
                    Text("开关是灰的、打不开？", color = G.Warn, fontSize = 14.sp, fontWeight = FontWeight.Medium)
                    Spacer(Modifier.height(6.dp))
                    Body("安卓会限制自己下载安装的应用。打开“应用信息”，点右上角 ⋮，选“允许受限制的设置”，再回来打开开关。", size = 13)
                    Spacer(Modifier.height(10.dp))
                    Button("打开应用信息") { Health.openAppInfo(activity) }
                }
            }
            if (enabled && !running) {
                Spacer(Modifier.height(14.dp))
                Body("开关已经打开，但服务还没运行。关掉再打开一次试试。", color = G.Warn, size = 13)
            }
        }
    }
}

@Composable
private fun BackgroundStep(activity: MainActivity, next: () -> Unit) {
    val resume = LocalResume.current
    val battery = remember(resume) { Health.batteryUnrestricted(activity) }
    StepPage(
        "别让系统把它关掉",
        if (Health.isXiaomi) "小米手机会在后台停掉服务，细线就不见了。把这两项设好，就能一直用。"
        else "有些手机会在后台停掉服务，细线就不见了。关掉电池优化就能一直用。",
        primary = "继续", onPrimary = next,
    ) {
        Card {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("省电策略：无限制", color = G.Ink, fontSize = 15.sp)
                    Body("在弹出的对话框里选“允许”", size = 12)
                }
                if (battery) CheckMark() else Button("设置") { Health.requestBattery(activity) }
            }
            if (Health.isXiaomi) {
                Spacer(Modifier.height(16.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("自启动", color = G.Ink, fontSize = 15.sp)
                        Body("在列表里打开 Sayrift 的开关。系统会顺手关掉应用，没关系，回来继续就行", size = 12)
                    }
                    Button("设置") { Health.openAutostart(activity) }
                }
            }
        }
    }
}

@Composable
private fun TryStep(activity: MainActivity, onDone: () -> Unit) {
    var text by rememberSaveable { mutableStateOf("") }
    val rev = storeRevision(activity)
    val start = remember { rev }
    val succeeded = rev > start
    val running by VoiceAccessibilityService.running.collectAsState()
    StepPage(
        if (succeeded) "成了！" else "试一试",
        if (succeeded) "以后在任何应用里都是这样：点输入框，点细线，说话。长按细线可以选翻译或 Ask。"
        else "点下面的框，屏幕${if (activity.app.prefs.handleRight) "右" else "左"}边缘会出现一条细线。点它，随便说一句话，再点 ✓。",
        primary = if (succeeded) "开始使用" else "完成",
        onPrimary = onDone,
    ) {
        if (!running && !succeeded) {
            Card {
                Text("细线不会出现：无障碍服务没在运行", color = G.Warn, fontSize = 14.sp, fontWeight = FontWeight.Medium)
                Spacer(Modifier.height(6.dp))
                Body("可能是刚才改设置时被系统关掉了。打开无障碍设置，把 Sayrift 语音输入重新打开。", size = 13)
                Spacer(Modifier.height(10.dp))
                Button("打开无障碍设置") { Health.openAccessibility(activity) }
            }
            Spacer(Modifier.height(14.dp))
        }
        Field(text, { text = it }, "点这里…", minLines = 4)
        Spacer(Modifier.height(16.dp))
        if (!succeeded) Tips()
    }
}

@Composable
private fun Tips() {
    Card {
        Numbered(1, "点细线：开始说话")
        Numbered(2, "点 ✓：结束，文字出现在光标处")
        Numbered(3, "点 ✕：不要这段")
        Numbered(4, "长按细线：选翻译或 Ask；拖动：换位置")
    }
}

@Composable
private fun Numbered(n: Int, text: String) {
    Row(Modifier.padding(vertical = 5.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(22.dp).clip(CircleShape).background(Color(0x1FFFFFFF)), contentAlignment = Alignment.Center) {
            Text(n.toString(), color = G.Ink, fontSize = 12.sp, fontWeight = FontWeight.Medium)
        }
        Spacer(Modifier.width(12.dp))
        Text(text, color = G.Ink, fontSize = 14.sp, lineHeight = 20.sp)
    }
}

@Composable
private fun Check(label: String, ok: Boolean) {
    Row(Modifier.padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        if (ok) CheckMark() else Box(Modifier.size(22.dp).clip(CircleShape).background(Color(0x14FFFFFF)))
        Spacer(Modifier.width(12.dp))
        Text(label, color = if (ok) G.Ink else G.Muted, fontSize = 15.sp)
    }
}

@Composable
private fun CheckMark() {
    Box(Modifier.size(22.dp).clip(CircleShape).background(G.Good.copy(alpha = 0.18f)), contentAlignment = Alignment.Center) {
        Icon(Icons.Outlined.Check, null, tint = G.Good, modifier = Modifier.size(15.dp))
    }
}

@Composable
private fun Done(text: String) {
    Card {
        Row(verticalAlignment = Alignment.CenterVertically) {
            CheckMark()
            Spacer(Modifier.width(12.dp))
            Text(text, color = G.Ink, fontSize = 15.sp)
        }
    }
}
