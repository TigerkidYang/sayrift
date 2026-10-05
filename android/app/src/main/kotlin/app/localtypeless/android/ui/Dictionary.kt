package app.localtypeless.android.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.localtypeless.android.MainActivity

/** Names, products and jargon: sent to the recognizer as hints and to the cleanup model as the glossary. */
@Composable
fun DictionaryScreen(activity: MainActivity) {
    val prefs = activity.app.prefs
    var words by remember { mutableStateOf(prefs.dictionary) }
    var draft by remember { mutableStateOf("") }

    fun add() {
        val w = draft.trim()
        if (w.isEmpty()) return
        if (words.none { it.equals(w, ignoreCase = true) }) {
            words = listOf(w) + words
            prefs.dictionary = words
        }
        draft = ""
    }

    Screen("词典") {
        Body("人名、产品名、专业术语。识别时会优先认成这些写法，整理时也按这里的拼写来写。", Modifier.padding(horizontal = 4.dp))
        Field(
            draft, { draft = it }, "添加一个词，比如 Claude Code", singleLine = true,
            keyboard = KeyboardOptions(imeAction = ImeAction.Done),
            actions = KeyboardActions(onDone = { add() }),
        ) {
            if (draft.isNotBlank()) IconButton(Icons.Outlined.Add, "添加", tint = G.Ink) { add() }
        }

        if (words.isEmpty()) {
            Column(Modifier.fillMaxWidth().padding(vertical = 40.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Text("还没有词", color = G.Ink, fontSize = 16.sp, fontWeight = FontWeight.Medium)
                Spacer(Modifier.height(6.dp))
                Body("常被认错的词加进来，下次就对了。", size = 13)
            }
        } else {
            SectionLabel("${words.size} 个词")
            Group {
                words.forEachIndexed { i, w ->
                    if (i > 0) Divider(inset = 16.dp)
                    Row(Modifier.fillMaxWidth().padding(start = 16.dp, end = 4.dp, top = 4.dp, bottom = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(w, color = G.Ink, fontSize = 15.sp, modifier = Modifier.weight(1f))
                        Spacer(Modifier.width(8.dp))
                        IconButton(Icons.Outlined.Close, "删除 $w", tint = G.Faint) {
                            words = words - w
                            prefs.dictionary = words
                        }
                    }
                }
            }
        }
    }
}
