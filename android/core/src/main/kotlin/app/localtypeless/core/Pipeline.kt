package app.localtypeless.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive

/** The models and switches the pipeline needs — defaults match the desktop app's config.py. */
data class Settings(
    val asrModel: String = "openai/gpt-transcribe",
    val asrFallback: String? = "microsoft/mai-transcribe-2",
    val languages: List<String> = listOf("zh-cn", "en"),
    val polishModel: String = "deepseek/deepseek-v4.1-flash",
    val polishFallback: String? = "openai/gpt-6-luna",
    val askModel: String = "deepseek/deepseek-v4.1-flash",
    val askFallback: String? = "openai/gpt-6-luna",
    val cjkSpacing: Boolean = true,
    val translateTargets: List<String> = listOf("English"),
    val dictionary: List<String> = emptyList(),
    val denyDataCollection: Boolean = true,
    // Whole-call deadlines standing in for the desktop's first-token timeouts (6 s / 8 s) plus generation time.
    val polishTimeoutMs: Long = 10_000,
    val askTimeoutMs: Long = 20_000,
)

enum class Mode { DICTATE, TRANSLATE, ASK }

enum class AskAction { REPLACE, INSERT, ANSWER, NOTHING }

data class Result(
    val mode: Mode,
    val raw: String, // what the recognizer heard
    val text: String, // what goes into the app (or the answer)
    val action: AskAction = AskAction.INSERT,
    val costUsd: Double = 0.0,
    val asrMs: Long = 0,
    val llmMs: Long = 0,
)

/** `src/local_typeless/pipeline.py`: speech -> recognizer (with fallback) -> cleanup / translation / Ask. */
class Pipeline(
    private val client: OpenRouterClient,
    private val settings: Settings,
    private val session: RequestSession = RequestSession(),
) {

    fun run(mode: Mode, audio: ByteArray, format: String, ctx: Context, selection: String? = null): Result {
        session.ensureActive()
        val context = if (ctx.dictionary.isEmpty() && settings.dictionary.isNotEmpty()) {
            ctx.copy(dictionary = settings.dictionary)
        } else ctx
        val asr = transcribe(audio, format, context.dictionary)
        session.ensureActive()
        if (asr.text.isBlank()) return Result(mode, "", "", AskAction.NOTHING, asr.costUsd ?: 0.0, asr.latencyMs)
        val result = when (mode) {
            Mode.DICTATE -> {
                val res = chat(Prompts.dictation(asr.text, context, settings.cjkSpacing), asr.text, checkLength = true)
                Result(mode, asr.text, res.text, AskAction.INSERT, cost(asr, res), asr.latencyMs, res.latencyMs)
            }
            Mode.TRANSLATE -> {
                val target = settings.translateTargets.firstOrNull() ?: "English"
                val res = chat(Prompts.translate(asr.text, context, target), asr.text, checkLength = false)
                Result(mode, asr.text, res.text, AskAction.INSERT, cost(asr, res), asr.latencyMs, res.latencyMs)
            }
            Mode.ASK -> {
                val res = withFallback(
                    Prompts.ask(asr.text, context, selection),
                    listOf(settings.askModel, settings.askFallback),
                    maxTokens = 4000,
                    timeoutMs = settings.askTimeoutMs,
                    body = mapOf("response_format" to Prompts.ASK_RESPONSE_FORMAT),
                )
                val (action, text) = parseAsk(res.text, hasSelection = !selection.isNullOrEmpty())
                Result(mode, asr.text, text, if (text.isEmpty()) AskAction.NOTHING else action, cost(asr, res),
                    asr.latencyMs, res.latencyMs)
            }
        }
        session.ensureActive()
        return result
    }

    fun transcribe(audio: ByteArray, format: String, keywords: List<String>): Transcript {
        val models = listOfNotNull(settings.asrModel, settings.asrFallback)
        var last: OpenRouterException? = null
        for (model in models) {
            session.ensureActive()
            try {
                // Opus at 24 kbps is ~3 KB/s: a generous deadline for long clips, a short one for typical ones.
                val timeout = maxOf(15_000L, 10_000L + audio.size / 10)
                return client.transcribe(audio, format, model, keywords, settings.languages,
                    Models.providerPrefs(lowLatency = false, denyDataCollection = settings.denyDataCollection), timeout, session)
            } catch (e: OpenRouterException) {
                session.ensureActive()
                last = e
            }
        }
        throw last ?: OpenRouterException("no speech model configured")
    }

    private fun chat(messages: List<Message>, raw: String, checkLength: Boolean): ChatResult {
        val res = withFallback(messages, listOf(settings.polishModel, settings.polishFallback),
            maxTokens = maxOf(256, 4 * raw.length), timeoutMs = settings.polishTimeoutMs)
        return res.copy(text = guard(raw, tidy(res.text), checkLength))
    }

    private fun withFallback(
        messages: List<Message>,
        models: List<String?>,
        maxTokens: Int,
        timeoutMs: Long,
        body: Map<String, kotlinx.serialization.json.JsonElement> = emptyMap(),
    ): ChatResult {
        var last: OpenRouterException? = null
        for (model in models.filterNotNull()) {
            session.ensureActive()
            try {
                val extra = Models.chatExtra(model, settings.denyDataCollection) + body
                return client.chat(messages, model, maxTokens, extra, timeoutMs, session)
            } catch (e: OpenRouterException) {
                session.ensureActive()
                last = e // errors and timeouts move on to the next model; never retry the same one
            }
        }
        throw last ?: OpenRouterException("no text model configured")
    }

    private fun cost(asr: Transcript, llm: ChatResult) = (asr.costUsd ?: 0.0) + (llm.costUsd ?: 0.0)

    companion object {
        /** Placeholders some models emit instead of an empty answer (seen with kimi-k2.6, qwen3.8-flash). */
        private val EMPTY_PLACEHOLDERS = setOf("（空）", "(空)", "(empty)", "(empty output)", "<empty>", "[empty]")

        fun tidy(text: String): String = text.trim().lines().joinToString("\n") { it.trimEnd() }

        /**
         * Catch cleanup failures the prompt alone does not prevent: a placeholder instead of empty output -> "";
         * output far longer than the transcript (the model answered or drafted instead of cleaning) -> the raw
         * transcript, because inserting the user's own words is the safe failure. Not for translation.
         */
        fun guard(raw: String, cleaned: String, checkLength: Boolean = true): String {
            if (cleaned.trim().lowercase() in EMPTY_PLACEHOLDERS) return ""
            if (checkLength && cleaned.length > maxOf(2 * raw.length, raw.length + 60)) return raw
            return cleaned
        }

        /** Model output -> (action, text); anything unparseable is shown as an answer, never typed into a document. */
        fun parseAsk(output: String, hasSelection: Boolean): Pair<AskAction, String> {
            val raw = output.trim()
            val start = raw.indexOf('{')
            val end = raw.lastIndexOf('}')
            val data = if (start != -1 && end > start) {
                runCatching { Json.parseToJsonElement(raw.substring(start, end + 1)) as? JsonObject }.getOrNull()
            } else null
            val text = data?.get("text")?.jsonPrimitive?.contentOrNull ?: return AskAction.ANSWER to raw
            var action = when (data["action"]?.jsonPrimitive?.contentOrNull) {
                "replace" -> AskAction.REPLACE
                "insert" -> AskAction.INSERT
                else -> AskAction.ANSWER
            }
            if (action == AskAction.REPLACE && !hasSelection) action = AskAction.INSERT // nothing to replace
            return action to tidy(text)
        }
    }
}
