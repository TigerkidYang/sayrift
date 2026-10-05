package app.localtypeless.core

import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import java.io.IOException
import java.io.InterruptedIOException
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class OpenRouterPrivacyTest {
    private lateinit var server: MockWebServer
    private val keyMarker = "synthetic-private-key-marker"
    private val textMarker = "synthetic-dictation-text-marker"

    @BeforeTest
    fun setUp() {
        server = MockWebServer()
        server.start()
    }

    @AfterTest
    fun tearDown() = server.shutdown()

    private fun client(http: OkHttpClient = OpenRouterClient.defaultHttp()) =
        OpenRouterClient(keyMarker, http, server.url("/api/v1").toString().trimEnd('/'))

    private fun assertSafe(error: Throwable) {
        // Android Log.w(tag, message, throwable) includes the entire cause chain.
        val logged = error.stackTraceToString()
        assertFalse(logged.contains(keyMarker))
        assertFalse(logged.contains(textMarker))
        assertNull(error.cause)
    }

    @Test
    fun http_errors_preserve_status_without_response_bodies() {
        for (body in listOf("""{"error":"$keyMarker $textMarker"}""", "<html>$keyMarker $textMarker</html>")) {
            server.enqueue(MockResponse().setResponseCode(403).setBody(body))
            val error = assertFailsWith<HttpException> { client().check() }
            assertEquals(403, error.code)
            assertSafe(error)
        }
    }

    @Test
    fun unreadable_responses_do_not_retain_parser_causes() {
        for (body in listOf("<html>$keyMarker $textMarker</html>", """{"$keyMarker":"$textMarker"""", """["$keyMarker", "$textMarker"]""")) {
            server.enqueue(MockResponse().setBody(body))
            val error = assertFailsWith<OpenRouterException> { client().check() }
            assertTrue(error.message.orEmpty().contains("invalid response"))
            assertSafe(error)
        }
    }

    @Test
    fun provider_errors_and_chat_shape_errors_are_safe_to_log() {
        val bodies = listOf(
            """{"error":{"message":"$keyMarker $textMarker"}}""",
            """{"choices":"$keyMarker $textMarker"}""",
            """{"choices":[{"message":{"content":{"secret":"$keyMarker $textMarker"}}}]}""",
        )
        for (body in bodies) {
            server.enqueue(MockResponse().setBody(body))
            val error = assertFailsWith<OpenRouterException> {
                client().chat(listOf(Message("user", textMarker)), "test-model", 20)
            }
            assertSafe(error)
        }
    }

    @Test
    fun transcription_and_account_shape_errors_are_safe_to_log() {
        server.enqueue(MockResponse().setBody("""{"text":{"secret":"$keyMarker $textMarker"}}"""))
        assertSafe(assertFailsWith<OpenRouterException> {
            client().transcribe(byteArrayOf(1), "ogg", "test-model")
        })
        server.enqueue(MockResponse().setBody("""{"data":"$keyMarker $textMarker"}"""))
        assertSafe(assertFailsWith<OpenRouterException> { client().account() })
    }

    @Test
    fun transport_failures_keep_categories_without_private_causes() {
        for (timeout in listOf(false, true)) {
            val http = OkHttpClient.Builder().addInterceptor {
                val failure = if (timeout) InterruptedIOException("$keyMarker $textMarker")
                    else IOException("$keyMarker $textMarker")
                failure.initCause(IllegalArgumentException(textMarker))
                throw failure
            }.build()
            val error = assertFailsWith<OpenRouterException> { client(http).check() }
            if (timeout) assertTrue(error is TimeoutException) else assertTrue(error is NetworkException)
            assertSafe(error)
        }
    }
}
