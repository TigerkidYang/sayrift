package app.localtypeless.android.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.localtypeless.android.Health
import app.localtypeless.android.Health.Issue
import app.localtypeless.android.MainActivity

data class IssueText(val title: String, val body: String, val action: String)

fun issueText(issue: Issue): IssueText = when (issue) {
    Issue.KEY -> IssueText("还没连接 OpenRouter", "填入 API key 后才能识别语音。", "填写 key")
    Issue.MIC -> IssueText("需要麦克风权限", "只在你说话时打开。", "允许")
    Issue.SERVICE_OFF -> IssueText("无障碍服务没有开启", "边缘细线和把文字放进输入框，都靠它。", "去开启")
    Issue.SERVICE_STOPPED -> IssueText(
        "服务被系统停掉了",
        "在无障碍设置里把 Sayrift 关掉再打开。再到下面把自启动、省电策略设好，就不会再被停。",
        "去重新打开",
    )
    Issue.NOTIFICATIONS -> IssueText("允许通知", "录音时系统要求显示一条通知；不允许的话，有些手机会在后台拦截麦克风。", "允许")
    Issue.BATTERY -> IssueText(
        "别让系统在后台关掉它",
        if (Health.isXiaomi) "省电策略选“无限制”，并打开“自启动”。" else "把电池优化设为“不优化”。",
        "去设置",
    )
}

fun fixIssue(activity: MainActivity, issue: Issue, onKey: () -> Unit) {
    when (issue) {
        Issue.KEY -> onKey()
        Issue.MIC, Issue.NOTIFICATIONS -> {
            val asked = activity.getSharedPreferences("ui", 0)
            // After a second refusal Android stops showing the dialog: send the user to App info instead.
            if (asked.getInt("asked_" + issue.name, 0) >= 2) {
                if (issue == Issue.NOTIFICATIONS) Health.openNotificationSettings(activity) else Health.openAppInfo(activity)
            } else {
                asked.edit().putInt("asked_" + issue.name, asked.getInt("asked_" + issue.name, 0) + 1).apply()
                activity.requestMicAndNotifications()
            }
        }
        Issue.SERVICE_OFF, Issue.SERVICE_STOPPED -> Health.openAccessibility(activity)
        Issue.BATTERY -> Health.requestBattery(activity)
    }
}

/** The one thing to fix next, as a card with a button. */
@Composable
fun IssueCard(activity: MainActivity, issue: Issue, more: Int, onKey: () -> Unit) {
    val t = issueText(issue)
    val blocking = issue in setOf(Issue.KEY, Issue.MIC, Issue.SERVICE_OFF, Issue.SERVICE_STOPPED)
    Card {
        Row(verticalAlignment = Alignment.CenterVertically) {
            StatusDot(if (blocking) G.Warn else G.Muted)
            Spacer(Modifier.width(10.dp))
            Text(t.title, color = G.Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            if (more > 0) Tag("还有 $more 项")
        }
        Spacer(Modifier.height(6.dp))
        Body(t.body, Modifier.padding(start = 18.dp))
        Spacer(Modifier.height(14.dp))
        Row(Modifier.padding(start = 18.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Button(t.action, style = ButtonStyle.Primary) { fixIssue(activity, issue, onKey) }
            if (issue == Issue.BATTERY && Health.isXiaomi) Button("自启动") { Health.openAutostart(activity) }
        }
    }
}
