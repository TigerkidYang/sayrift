package app.localtypeless.android.ui

import android.content.ClipboardManager
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ContentPaste
import androidx.compose.material.icons.outlined.Key
import androidx.compose.material.icons.outlined.OpenInNew
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.localtypeless.android.Health
import app.localtypeless.android.MainActivity
import app.localtypeless.core.HttpException
import app.localtypeless.core.NetworkException
import app.localtypeless.core.OpenRouterClient
import app.localtypeless.core.TimeoutException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Paste, check and save an OpenRouter key. The key is checked against OpenRouter (GET /key, free) before it is
 * stored, so a typo shows up here and not as a failed dictation later.
 */
@Composable
fun KeyEditor(activity: MainActivity, onSaved: (balance: Double?) -> Unit) {
    val prefs = activity.app.prefs
    var key by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    val focus = androidx.compose.ui.platform.LocalFocusManager.current

    fun check() {
        val candidate = key.trim()
        if (candidate.isEmpty()) return
        busy = true
        error = null
        scope.launch {
            val outcome = withContext(Dispatchers.IO) {
                runCatching { OpenRouterClient(candidate, baseUrl = prefs.apiBase).account() }
            }
            busy = false
            outcome.fold(
                onSuccess = { account -> prefs.apiKey = candidate; key = ""; focus.clearFocus(); onSaved(account.balance) },
                onFailure = { e ->
                    error = when {
                        e is HttpException && e.code in setOf(401, 403) -> "OpenRouter 不认这个 key，检查一下有没有复制完整。"
                        e is NetworkException || e is TimeoutException -> "连不上 OpenRouter，检查一下网络。"
                        else -> "验证失败：${e.message?.take(60)}"
                    }
                },
            )
        }
    }

    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Field(
            key, { key = it; error = null }, "sk-or-v1-…",
            secret = true, singleLine = true, leading = Icons.Outlined.Key,
            keyboard = KeyboardOptions(keyboardType = KeyboardType.Password),
        ) {
            Spacer(Modifier.width(8.dp))
            IconButton(Icons.Outlined.ContentPaste, "粘贴") {
                val clip = activity.getSystemService(ClipboardManager::class.java).primaryClip
                val text = clip?.takeIf { it.itemCount > 0 }?.getItemAt(0)?.coerceToText(activity)?.toString()?.trim()
                if (!text.isNullOrEmpty()) { key = text; error = null }
            }
        }
        if (error != null) Text(error!!, color = G.Bad, fontSize = 13.sp)
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
            Button(if (busy) "验证中…" else "验证并保存", style = ButtonStyle.Primary, enabled = key.isNotBlank() && !busy) { check() }
            Button("创建 key", icon = Icons.Outlined.OpenInNew) { Health.openUrl(activity, "https://openrouter.ai/keys") }
        }
        Spacer(Modifier.height(2.dp))
        Body("在 OpenRouter 网站登录后点 Create Key，复制下来回到这里粘贴。建议给它设一个额度上限，比如 \$2。" +
            "key 加密保存在这台手机上，只用来调用模型。", size = 13)
    }
}
