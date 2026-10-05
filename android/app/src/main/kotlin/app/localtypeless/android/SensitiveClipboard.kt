package app.localtypeless.android

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.os.PersistableBundle

/** Explicit copies persist for manual paste. Never schedule restoration or clearing over a later user copy. */
object SensitiveClipboard {
    fun copy(context: Context, text: String) {
        val clip = ClipData.newPlainText("dictation", text).apply {
            description.extras = PersistableBundle().apply {
                // Compatible with API 29+; the named EXTRA_IS_SENSITIVE constant was added in API 33.
                putBoolean("android.content.extra.IS_SENSITIVE", true)
            }
        }
        context.getSystemService(ClipboardManager::class.java).setPrimaryClip(clip)
    }
}
