package app.localtypeless.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class PipelineTest {
    private lateinit var server: MockWebServer
    private val requests = mutableListOf<Pair<String, String>>()

    @BeforeTest
    fun setUp() {
        server = MockWebServer()
        server.start()
    }

    @AfterTest
    fun tearDown() = server.shutdown()

    private fun respond(handler: (path: String, body: String) -> MockResponse) {
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                val body = request.body.readUtf8()
                synchronized(requests) { requests += request.path!! to body }
                return handler(request.path!!, body)
            }
        }
    }

    private fun json(s: String) = MockResponse().setBody(s).setHeader("Content-Type", "application/json")

    private fun pipeline(settings: Settings = Settings()) =
        Pipeline(OpenRouterClient("test-key", baseUrl = server.url("/api/v1").toString().trimEnd('/')), settings)

    @Test
    fun prompts_come_from_the_desktop_files() {
        assertTrue(Prompts.load("dictation").contains("You are the text-cleanup stage"))
        assertTrue(!Prompts.dictationSystem().contains("{{cjk_spacing_rule}}"))
    }

    @Test
    fun dictation_sends_hints_in_the_vendor_block_and_cleans_up() {
        respond { path, _ ->
            if (path.endsWith("/audio/transcriptions")) json("""{"text":"嗯 帮我跑一下 ptest","usage":{"cost":0.001}}""")
            else json("""{"model":"deepseek/deepseek-v4.1-flash","choices":[{"message":{"content":"帮我跑一下 pytest。  "}}],"usage":{"cost":0.0002}}""")
        }
        val r = pipeline(Settings(dictionary = listOf("pytest"))).run(Mode.DICTATE, byteArrayOf(1, 2), "ogg", Context(app = "com.termux"))
        assertEquals("帮我跑一下 pytest。", r.text)
        assertEquals(0.0012, r.costUsd, 1e-9)
        val stt = Json.parseToJsonElement(requests.first { it.first.endsWith("transcriptions") }.second).jsonObject
        val openai = stt["provider"]!!.jsonObject["options"]!!.jsonObject["openai"]!!.jsonObject
        assertEquals("pytest", openai["keywords"].toString().trim('[', ']', '"'))
        val chat = requests.first { it.first.endsWith("completions") }.second
        assertTrue(chat.contains("Personal dictionary: pytest") && chat.contains("App: com.termux"))
        assertTrue(chat.contains("\"data_collection\":\"deny\""))
    }

    @Test
    fun a_failing_model_falls_back_to_the_next_one() {
        respond { path, body ->
            when {
                path.endsWith("/audio/transcriptions") -> json("""{"text":"hello there"}""")
                body.contains("deepseek") -> MockResponse().setResponseCode(502).setBody("""{"error":"down"}""")
                else -> json("""{"model":"openai/gpt-6-luna","choices":[{"message":{"content":"Hello there."}}]}""")
            }
        }
        val r = pipeline().run(Mode.DICTATE, byteArrayOf(1), "ogg", Context())
        assertEquals("Hello there.", r.text)
    }

    @Test
    fun guard_replaces_answers_and_placeholders() {
        assertEquals("", Pipeline.guard("嗯", "（空）"))
        val raw = "法国首都是哪里"
        assertEquals(raw, Pipeline.guard(raw, "法国的首都是巴黎。".repeat(20)))
    }

    @Test
    fun ask_parsing_tolerates_prose_and_never_replaces_without_a_selection() {
        assertEquals(AskAction.INSERT to "Hi", Pipeline.parseAsk("""```json {"action":"replace","text":"Hi"} ```""", false))
        assertEquals(AskAction.ANSWER to "just text", Pipeline.parseAsk("just text", true))
    }
}
