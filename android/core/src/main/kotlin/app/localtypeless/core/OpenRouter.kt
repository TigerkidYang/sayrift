package app.localtypeless.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.io.InterruptedIOException
import java.util.Base64
import java.util.concurrent.TimeUnit

open class OpenRouterException(message: String, cause: Throwable? = null) : Exception(message, cause)
class NetworkException(message: String, cause: Throwable? = null) : OpenRouterException(message, cause)
class TimeoutException(message: String, cause: Throwable? = null) : OpenRouterException(message, cause)
class HttpException(val code: Int, message: String) : OpenRouterException(message)
class MissingKeyException : OpenRouterException("OPENROUTER_API_KEY is not set")

data class Transcript(val text: String, val model: String, val latencyMs: Long, val costUsd: Double? = null)
data class ChatResult(val text: String, val model: String, val latencyMs: Long, val costUsd: Double? = null)

/** What OpenRouter says about the account and this key (both endpoints are free). */
data class Account(
    val balance: Double?, // credits bought minus used; null when the key can't read account credits
    val keyToday: Double,
    val keyMonth: Double,
    val keyLimitRemaining: Double?,
)

/**
 * OpenRouter client — the requests of `src/local_typeless/openrouter.py`, without streaming: on a phone the
 * simple form is enough, and a whole-call timeout stands in for the desktop's first-token timeout.
 */
class OpenRouterClient(
    private val apiKey: String,
    private val http: OkHttpClient = defaultHttp(),
    private val baseUrl: String = "https://openrouter.ai/api/v1",
) {
    companion object {
        private val JSON = Json { ignoreUnknownKeys = true }
        private val JSON_TYPE = "application/json".toMediaType()

        fun defaultHttp(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            // A warm connection saves ~0.7 s per request through a proxy (desktop measurement).
            .connectionPool(okhttp3.ConnectionPool(2, 2, TimeUnit.MINUTES))
            .build()
    }

    /** Open the TLS connection ahead of time (hotkey-down on the desktop, button-down here). */
    fun warmUp(session: RequestSession = RequestSession()) {
        try {
            get("/key", 5_000, session)
        } catch (_: OpenRouterException) {
            // Best effort; cancellation remains terminal.
        }
    }

    /** Throws unless the key is accepted (first-run check). */
    fun check() {
        get("/key", 10_000)
    }

    fun account(): Account = decodeResponse {
        val key = get("/key", 10_000)["data"]?.jsonObject
        val credits = runCatching { get("/credits", 10_000)["data"]?.jsonObject }.getOrNull()
        fun JsonObject?.num(name: String) = this?.get(name)?.jsonPrimitive?.doubleOrNull
        val bought = credits.num("total_credits")
        val used = credits.num("total_usage")
        Account(
            balance = if (bought != null && used != null) bought - used else null,
            keyToday = key.num("usage_daily") ?: 0.0,
            keyMonth = key.num("usage_monthly") ?: 0.0,
            keyLimitRemaining = key.num("limit_remaining"),
        )
    }

    fun transcribe(
        audio: ByteArray,
        format: String,
        model: String,
        keywords: List<String> = emptyList(),
        languages: List<String> = emptyList(),
        provider: JsonObject = Models.providerPrefs(lowLatency = false),
        timeoutMs: Long = 20_000,
        session: RequestSession = RequestSession(),
    ): Transcript {
        session.ensureActive()
        val prefs = provider.toMutableMap()
        val options = Models.sttHints(model, keywords, languages)
        if (options.isNotEmpty()) prefs["options"] = JsonObject(options)
        val body = buildJsonObject {
            put("model", model)
            putJsonObject("input_audio") {
                put("data", Base64.getEncoder().encodeToString(audio))
                put("format", format)
            }
            if (prefs.isNotEmpty()) put("provider", JsonObject(prefs))
        }
        val t0 = System.nanoTime()
        val data = try {
            post("/audio/transcriptions", body, timeoutMs, session)
        } catch (e: NetworkException) {
            session.ensureActive()
            post("/audio/transcriptions", body, timeoutMs, session) // a reused connection may have died: once more, fresh
        }
        return decodeResponse {
            val usage = data["usage"]?.jsonObject
            Transcript(
                text = data["text"]?.jsonPrimitive?.contentOrNull?.trim().orEmpty(),
                model = model,
                latencyMs = (System.nanoTime() - t0) / 1_000_000,
                costUsd = usage?.get("cost")?.jsonPrimitive?.doubleOrNull,
            )
        }
    }

    fun chat(
        messages: List<Message>,
        model: String,
        maxTokens: Int,
        extra: Map<String, JsonElement> = emptyMap(),
        timeoutMs: Long = 12_000,
        session: RequestSession = RequestSession(),
    ): ChatResult {
        session.ensureActive()
        val body = buildJsonObject {
            put("model", model)
            put("temperature", 0.0)
            put("max_tokens", maxTokens)
            putJsonArray("messages") {
                messages.forEach { m -> add(buildJsonObject { put("role", m.role); put("content", m.content) }) }
            }
            putJsonObject("usage") { put("include", true) }
            extra.forEach { (k, v) -> put(k, v) }
        }
        val t0 = System.nanoTime()
        val data = try {
            post("/chat/completions", body, timeoutMs, session)
        } catch (e: NetworkException) {
            session.ensureActive()
            post("/chat/completions", body, timeoutMs, session)
        }
        return decodeResponse {
            data["error"]?.let { throw OpenRouterException("OpenRouter returned a provider error") }
            val choice = data["choices"]?.jsonArray?.firstOrNull()?.jsonObject
                ?: throw OpenRouterException("OpenRouter returned no choices")
            val text = choice["message"]?.jsonObject?.get("content")?.jsonPrimitive?.contentOrNull.orEmpty()
            ChatResult(
                text = text,
                model = data["model"]?.jsonPrimitive?.contentOrNull ?: model,
                latencyMs = (System.nanoTime() - t0) / 1_000_000,
                costUsd = data["usage"]?.jsonObject?.get("cost")?.jsonPrimitive?.doubleOrNull,
            )
        }
    }

    // JSON parser/type errors can echo response contents. Never retain them as a logged cause.
    private inline fun <T> decodeResponse(block: () -> T): T = try {
        block()
    } catch (_: IllegalArgumentException) {
        throw OpenRouterException("OpenRouter returned an invalid response")
    }

    private fun post(path: String, body: JsonObject, timeoutMs: Long, session: RequestSession): JsonObject =
        call(Request.Builder().url(baseUrl + path).post(body.toString().toRequestBody(JSON_TYPE)), timeoutMs, session)

    private fun get(path: String, timeoutMs: Long, session: RequestSession = RequestSession()): JsonObject =
        call(Request.Builder().url(baseUrl + path), timeoutMs, session)

    private fun call(builder: Request.Builder, timeoutMs: Long, session: RequestSession): JsonObject {
        session.ensureActive()
        val request = builder
            .header("Authorization", "Bearer $apiKey")
            .header("X-Title", "Sayrift")
            .build()
        val client = http.newBuilder().callTimeout(timeoutMs, TimeUnit.MILLISECONDS).build()
        val call = client.newCall(request)
        session.register(call)
        try {
            call.execute().use { resp ->
                session.ensureActive()
                if (!resp.isSuccessful) throw HttpException(resp.code, "OpenRouter HTTP ${resp.code}")
                val text = resp.body?.string().orEmpty()
                session.ensureActive()
                // A proxy or captive portal can answer 200 with HTML: treat it like any failed call, so the
                // fallback model gets its turn.
                return decodeResponse { JSON.parseToJsonElement(text).jsonObject }
            }
        } catch (_: InterruptedIOException) {
            session.ensureActive()
            throw TimeoutException("OpenRouter request timed out")
        } catch (_: IOException) {
            session.ensureActive()
            throw NetworkException("OpenRouter network request failed")
        } finally {
            session.release(call)
        }
    }
}

/** Per-model request presets and provider routing — `src/local_typeless/models.py`. */
object Models {
    private val REASONING_OFF = buildJsonObject { put("enabled", false) }
    private val EFFORT_NONE = buildJsonObject { put("effort", "none") }

    fun chatPreset(model: String): Map<String, JsonElement> = when (model) {
        "deepseek/deepseek-v4.1-flash", "qwen/qwen3.8-flash" -> mapOf("reasoning" to REASONING_OFF)
        "openai/gpt-6-luna" -> mapOf("reasoning" to EFFORT_NONE)
        else -> emptyMap()
    }

    /** sort=latency picks the endpoint with the lowest recent TTFT; data_collection=deny applies OpenRouter's
     *  data-collection policy filter, not Zero Data Retention. Sent with both speech and chat requests. */
    fun providerPrefs(lowLatency: Boolean = true, denyDataCollection: Boolean = true): JsonObject = buildJsonObject {
        if (lowLatency) put("sort", "latency")
        if (denyDataCollection) put("data_collection", "deny")
    }

    fun chatExtra(model: String, denyDataCollection: Boolean = true): Map<String, JsonElement> =
        chatPreset(model) + ("provider" to providerPrefs(lowLatency = true, denyDataCollection = denyDataCollection))

    /**
     * Speech-model hints in the only shape each model honours (desktop experiment 12): inside
     * `provider.options.<vendor>`; the same fields at the top level are silently ignored.
     */
    fun sttHints(model: String, keywords: List<String>, languages: List<String>): Map<String, JsonElement> =
        when (model) {
            "openai/gpt-transcribe" -> {
                val hints = buildJsonObject {
                    if (keywords.isNotEmpty()) putJsonArray("keywords") { keywords.forEach { add(JsonPrimitive(it)) } }
                    if (languages.isNotEmpty()) putJsonArray("languages") { languages.forEach { add(JsonPrimitive(it)) } }
                }
                if (hints.isEmpty()) emptyMap() else mapOf("openai" to hints)
            }
            "microsoft/mai-transcribe-2" ->
                if (keywords.isEmpty()) emptyMap()
                else mapOf("azure" to buildJsonObject {
                    putJsonObject("phraseList") { putJsonArray("phrases") { keywords.take(100).forEach { add(JsonPrimitive(it)) } } }
                })
            else -> emptyMap()
        }
}
