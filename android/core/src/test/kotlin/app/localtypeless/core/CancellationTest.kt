package app.localtypeless.core

import okhttp3.Call
import okhttp3.EventListener
import okhttp3.OkHttpClient
import okhttp3.ResponseBody.Companion.toResponseBody
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import java.io.IOException
import java.io.InterruptedIOException
import java.util.concurrent.CancellationException
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

class CancellationTest {
    private fun client(server: MockWebServer, http: OkHttpClient = OpenRouterClient.defaultHttp()) =
        OpenRouterClient("offline-test-key", http, server.url("/api/v1").toString().trimEnd('/'))

    @Test
    fun cancelled_before_registration_never_sends_a_request() {
        MockWebServer().use { server ->
            val owner = RequestSession().apply { cancel() }
            val c = client(server)
            assertFailsWith<CancellationException> {
                Pipeline(c, Settings(), owner).run(Mode.DICTATE, byteArrayOf(1), "ogg", Context())
            }
            assertFailsWith<CancellationException> { c.warmUp(owner) }
            val call = OpenRouterClient.defaultHttp().newCall(okhttp3.Request.Builder().url(server.url("/")).build())
            assertFailsWith<CancellationException> { owner.register(call) }
            assertTrue(call.isCanceled())
            assertEquals(0, server.requestCount)
        }
    }

    private fun cancelInFlight(chat: Boolean, bodyRead: Boolean = false) {
        MockWebServer().use { server ->
            if (chat) server.enqueue(MockResponse().setBody("""{"text":"test"}"""))
            server.enqueue(if (bodyRead) MockResponse().setBody("""{"text":"test"}""")
                .setHeader("Content-Length", "10000") else MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
            val cancelled = CountDownLatch(1)
            val bodyStarted = CountDownLatch(1)
            val http = OpenRouterClient.defaultHttp().newBuilder().eventListener(object : EventListener() {
                override fun canceled(call: Call) { cancelled.countDown() }
                override fun responseBodyStart(call: Call) { bodyStarted.countDown() }
            }).build()
            val owner = RequestSession()
            val worker = Executors.newSingleThreadExecutor()
            try {
                val result = worker.submit<Throwable?> {
                    runCatching {
                        Pipeline(client(server, http), Settings(), owner)
                            .run(Mode.DICTATE, byteArrayOf(1), "ogg", Context())
                    }.exceptionOrNull()
                }
                assertNotNull(server.takeRequest(3, TimeUnit.SECONDS))
                if (chat) assertNotNull(server.takeRequest(3, TimeUnit.SECONDS))
                if (bodyRead) assertTrue(bodyStarted.await(3, TimeUnit.SECONDS))
                owner.cancel()
                assertTrue(cancelled.await(1, TimeUnit.SECONDS), "the actual OkHttp Call must be cancelled")
                assertTrue(result.get(3, TimeUnit.SECONDS) is CancellationException)
                assertEquals(if (chat) 2 else 1, server.requestCount, "no retry, fallback or next stage")
            } finally {
                owner.cancel()
                worker.shutdownNow()
            }
        }
    }

    @Test fun cancel_asr_stops_socket_and_fallback() = cancelInFlight(chat = false)
    @Test fun cancel_chat_stops_socket_and_fallback() = cancelInFlight(chat = true)
    @Test fun cancellation_still_owns_call_while_reading_body() = cancelInFlight(chat = false, bodyRead = true)

    @Test
    fun cancelled_io_timeout_and_http_errors_never_retry_or_fallback() {
        for (kind in listOf("io", "timeout", "http")) {
            val owner = RequestSession()
            val attempts = AtomicInteger()
            val http = OkHttpClient.Builder().addInterceptor { chain ->
                attempts.incrementAndGet()
                owner.cancel()
                when (kind) {
                    "io" -> throw IOException("synthetic failure")
                    "timeout" -> throw InterruptedIOException("synthetic timeout")
                    else -> okhttp3.Response.Builder().request(chain.request()).protocol(okhttp3.Protocol.HTTP_1_1)
                        .code(503).message("unavailable").body("".toResponseBody()).build()
                }
            }.build()
            val c = OpenRouterClient("test", http, "http://127.0.0.1:1")
            assertFailsWith<CancellationException> {
                Pipeline(c, Settings(), owner).run(Mode.DICTATE, byteArrayOf(1), "ogg", Context())
            }
            assertEquals(1, attempts.get())
        }
    }

    @Test
    fun cancellation_between_asr_and_chat_suppresses_next_stage() {
        val owner = RequestSession()
        val attempts = AtomicInteger()
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setBody("""{"text":"test"}"""))
            val http = OpenRouterClient.defaultHttp().newBuilder().eventListener(object : EventListener() {
                override fun callEnd(call: Call) { owner.cancel() }
                override fun callStart(call: Call) { attempts.incrementAndGet() }
            }).build()
            assertFailsWith<CancellationException> {
                Pipeline(client(server, http), Settings(), owner).run(Mode.DICTATE, byteArrayOf(1), "ogg", Context())
            }
            assertEquals(1, attempts.get())
        }
    }

    @Test
    fun cancelling_old_session_leaves_new_inflight_call_alive() {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
            server.enqueue(MockResponse().setBody("""{"text":"new session"}""").setBodyDelay(300, TimeUnit.MILLISECONDS))
            val old = RequestSession()
            val newer = RequestSession()
            val c = client(server)
            val worker = Executors.newFixedThreadPool(2)
            try {
                val first = worker.submit<Throwable?> {
                    runCatching { c.transcribe(byteArrayOf(1), "ogg", "old", session = old) }.exceptionOrNull()
                }
                assertNotNull(server.takeRequest(3, TimeUnit.SECONDS))
                val second = worker.submit<Transcript> { c.transcribe(byteArrayOf(1), "ogg", "new", session = newer) }
                assertNotNull(server.takeRequest(3, TimeUnit.SECONDS))
                old.cancel()
                old.cancel() // stale repeated teardown is harmless
                assertTrue(first.get(3, TimeUnit.SECONDS) is CancellationException)
                assertEquals("new session", second.get(3, TimeUnit.SECONDS).text)
                assertEquals(2, server.requestCount)
            } finally {
                old.cancel()
                newer.cancel()
                worker.shutdownNow()
            }
        }
    }

    @Test
    fun stalled_warmup_does_not_queue_active_request() {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
            server.enqueue(MockResponse().setBody("""{"text":"ready"}"""))
            val warm = RequestSession()
            val active = RequestSession()
            val c = client(server)
            val workers = Executors.newFixedThreadPool(2)
            try {
                val warming = workers.submit<Throwable?> { runCatching { c.warmUp(warm) }.exceptionOrNull() }
                assertNotNull(server.takeRequest(3, TimeUnit.SECONDS))
                val result = workers.submit<Transcript> { c.transcribe(byteArrayOf(1), "ogg", "test", session = active) }
                assertEquals("ready", result.get(3, TimeUnit.SECONDS).text)
                warm.cancel()
                assertTrue(warming.get(3, TimeUnit.SECONDS) is CancellationException)
                active.ensureActive()
            } finally {
                warm.cancel()
                active.cancel()
                workers.shutdownNow()
            }
        }
    }

    @Test
    fun ordinary_network_error_keeps_single_retry() {
        val attempts = AtomicInteger()
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setBody("""{"text":"retried"}"""))
            val http = OpenRouterClient.defaultHttp().newBuilder().addInterceptor { chain ->
                if (attempts.incrementAndGet() == 1) throw IOException("synthetic stale connection")
                chain.proceed(chain.request())
            }.build()
            assertEquals("retried", client(server, http).transcribe(byteArrayOf(1), "ogg", "test").text)
            assertEquals(2, attempts.get())
            assertEquals(1, server.requestCount)
        }
    }
}
