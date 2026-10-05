package app.localtypeless.android

import android.graphics.Typeface
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.style.RelativeSizeSpan
import android.text.style.StyleSpan
import android.text.style.TypefaceSpan

/**
 * Just enough Markdown for Ask answers (prompts/ask.md tells the model the card renders Markdown): headings, bold,
 * inline code and bullets. Anything else stays as written, which reads fine.
 */
object Markdown {
    private val BOLD = Regex("\\*\\*(.+?)\\*\\*")
    private val CODE = Regex("`([^`]+)`")
    private val HEADING = Regex("^#{1,6}\\s+")
    private val BULLET = Regex("^(\\s*)[-*+]\\s+")

    fun render(md: String): CharSequence {
        val out = SpannableStringBuilder()
        md.trim().lines().forEachIndexed { i, raw ->
            if (i > 0) out.append('\n')
            var line = raw
            val heading = HEADING.containsMatchIn(line)
            if (heading) line = line.replaceFirst(HEADING, "")
            line = line.replaceFirst(BULLET, "\$1• ")
            val start = out.length
            appendInline(out, line)
            if (heading) {
                out.setSpan(StyleSpan(Typeface.BOLD), start, out.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                out.setSpan(RelativeSizeSpan(1.08f), start, out.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            }
        }
        return out
    }

    /** The text without markers, for copying and inserting into other apps. */
    fun plain(md: String): String = md.trim().lines().joinToString("\n") { raw ->
        raw.replaceFirst(HEADING, "").replaceFirst(BULLET, "\$1• ")
            .replace(BOLD) { it.groupValues[1] }.replace(CODE) { it.groupValues[1] }
    }

    private fun appendInline(out: SpannableStringBuilder, line: String) {
        var rest = line
        while (rest.isNotEmpty()) {
            val bold = BOLD.find(rest)
            val code = CODE.find(rest)
            val next = listOfNotNull(bold, code).minByOrNull { it.range.first } ?: run { out.append(rest); return }
            out.append(rest.substring(0, next.range.first))
            val start = out.length
            out.append(next.groupValues[1])
            val span: Any = if (next === bold) StyleSpan(Typeface.BOLD) else TypefaceSpan("monospace")
            out.setSpan(span, start, out.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            rest = rest.substring(next.range.last + 1)
        }
    }
}
