package app.localtypeless.core

import okhttp3.Call
import java.util.concurrent.CancellationException

/** One operation owns its calls; cancellation is terminal and never touches another session. */
class RequestSession {
    private val lock = Any()
    private var cancelled = false
    private val calls = mutableSetOf<Call>()

    fun ensureActive() = synchronized(lock) {
        if (cancelled) throw CancellationException("Request session cancelled")
    }

    internal fun register(call: Call) = synchronized(lock) {
        if (cancelled) {
            call.cancel()
            throw CancellationException("Request session cancelled")
        }
        calls.add(call)
    }

    internal fun release(call: Call) = synchronized(lock) { calls.remove(call) }

    fun cancel() = synchronized(lock) {
        cancelled = true
        calls.forEach { it.cancel() }
        calls.clear()
    }
}
