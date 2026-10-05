package app.localtypeless.core

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject

/**
 * Prompt templates and message builders — a port of `src/local_typeless/prompts/__init__.py`.
 *
 * The .md files are the desktop app's own (copied in by the `copyPrompts` Gradle task), so both apps clean up
 * text the same way. Layout rule: the system message depends only on stable settings (provider prefix caching);
 * everything per-request (app, dictionary, selection, transcript) goes into the user message.
 */
object Prompts {
    const val CJK_SPACING_ON =
        "Put one space between Chinese characters and an adjacent Latin-letter word " +
            "(用 Python 写, 更新 README 文件); do not add spaces around numbers (下午4点, 3个)."
    const val CJK_SPACING_OFF =
        "Do not insert spaces between Chinese characters and English words or numbers " +
            "(this overrides the spacing shown in the examples)."

    private val cache = mutableMapOf<String, String>()

    fun load(name: String): String = synchronized(cache) {
        cache.getOrPut(name) {
            val stream = Prompts::class.java.getResourceAsStream("/app/localtypeless/core/prompts/$name.md")
                ?: error("prompt $name.md is missing from the build")
            stream.use { it.readBytes().toString(Charsets.UTF_8) }
        }
    }

    private fun contextBlock(ctx: Context): String {
        val lines = buildList {
            ctx.app?.let { add("App: $it") }
            ctx.windowTitle?.let { add("Window title: $it") }
            if (ctx.dictionary.isNotEmpty()) add("Personal dictionary: " + ctx.dictionary.joinToString(", "))
        }
        return if (lines.isEmpty()) "" else "<context>\n" + lines.joinToString("\n") + "\n</context>\n"
    }

    fun dictationSystem(cjkSpacing: Boolean = true): String =
        load("dictation").replace("{{cjk_spacing_rule}}", if (cjkSpacing) CJK_SPACING_ON else CJK_SPACING_OFF)

    fun dictation(transcript: String, ctx: Context, cjkSpacing: Boolean = true): List<Message> = listOf(
        Message("system", dictationSystem(cjkSpacing)),
        Message("user", contextBlock(ctx) + "<transcript>$transcript</transcript>"),
    )

    fun translate(transcript: String, ctx: Context, targetLanguage: String): List<Message> = listOf(
        Message("system", load("translate").replace("{{target_language}}", targetLanguage)),
        Message("user", contextBlock(ctx) + "<transcript>$transcript</transcript>"),
    )

    fun ask(spoken: String, ctx: Context, selection: String?): List<Message> {
        var user = contextBlock(ctx)
        if (!selection.isNullOrEmpty()) user += "<selection>\n$selection\n</selection>\n"
        user += "<spoken>$spoken</spoken>"
        return listOf(Message("system", load("ask")), Message("user", user))
    }

    val ASK_RESPONSE_FORMAT: JsonObject = buildJsonObject {
        put("type", "json_schema")
        putJsonObject("json_schema") {
            put("name", "ask_result")
            put("strict", true)
            putJsonObject("schema") {
                put("type", "object")
                putJsonObject("properties") {
                    putJsonObject("action") {
                        put("type", "string")
                        put("enum", JsonArray(listOf("replace", "insert", "answer").map(::JsonPrimitive)))
                    }
                    putJsonObject("text") { put("type", "string") }
                }
                putJsonArray("required") { add(JsonPrimitive("action")); add(JsonPrimitive("text")) }
                put("additionalProperties", false)
            }
        }
    }
}

data class Message(val role: String, val content: String)

/** Per-request context: the app the text goes into and the glossary for this request. */
data class Context(
    val app: String? = null, // Android package name, e.g. "com.tencent.mm"
    val windowTitle: String? = null,
    val dictionary: List<String> = emptyList(),
)
