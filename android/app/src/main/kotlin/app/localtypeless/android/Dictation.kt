package app.localtypeless.android

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.os.VibrationEffect
import android.os.Vibrator
import android.util.Log
import android.view.accessibility.AccessibilityNodeInfo
import app.localtypeless.core.AskAction
import app.localtypeless.core.Context as CoreContext
import app.localtypeless.core.HttpException
import app.localtypeless.core.MissingKeyException
import app.localtypeless.core.Mode
import app.localtypeless.core.NetworkException
import app.localtypeless.core.OpenRouterClient
import app.localtypeless.core.RequestSession
import app.localtypeless.core.Pipeline
import app.localtypeless.core.TimeoutException
import java.io.File
import java.util.concurrent.CancellationException
import java.util.concurrent.Executors

/**
 * The session state machine (the desktop's app.py, much smaller): idle -> listening -> processing -> idle.
 * Everything runs on the main thread except the network call.
 */
object Dictation {
    private const val TAG = "Dictation"
    private const val MAX_MS = 9 * 60 * 1000L // Typeless: 9-minute cap
    private const val SILENCE_PEAK = 1200 // below this nothing was said (room noise peaks ~300-800)

    enum class State { IDLE, LISTENING, PROCESSING }

    var state = State.IDLE
        private set
    private val main = Handler(Looper.getMainLooper())
    // Warm-ups and active work use separate tasks, so a slow warm-up cannot queue dictation.
    private val io = Executors.newCachedThreadPool()
    private var recorder: Recorder? = null
    private var mode = Mode.DICTATE
    private var target: AccessibilityNodeInfo? = null
    private var field: VoiceAccessibilityService.FieldRef? = null
    /** The application, for stopping things when the service is gone. Set by [App]. */
    lateinit var app: App
    private var targetApp: String? = null
    private var selection: String? = null
    private var seconds = 0.0
    private var fakeAudio: ByteArray? = null
    private var requests: RequestSession? = null
    private var warmup: RequestSession? = null
    private var session = 0
    private var service: VoiceAccessibilityService? = null
    private var client: OpenRouterClient? = null
    private var clientKey: String? = null

    private val levelTick = object : Runnable {
        override fun run() {
            val r = recorder
            val svc = service ?: return
            if (state != State.LISTENING) return
            val level = if (fakeAudio != null) (0.25f + 0.6f * Math.random().toFloat()) else r?.level() ?: 0f
            svc.overlay.pushLevel(level)
            if ((r?.elapsedMs ?: 0) > MAX_MS) finish() else main.postDelayed(this, 50)
        }
    }

    fun attach(svc: VoiceAccessibilityService?) {
        if (service !== svc) abort()
        service = svc
    }

    fun detach(svc: VoiceAccessibilityService) {
        if (service !== svc) return
        abort()
        service = null
    }

    /**
     * The service is going away (the system unbound it, or the user switched it off): stop recording and any
     * session now. Without this the microphone stayed on, the state stayed LISTENING, and the handle never came
     * back after the service reconnected.
     */
    fun abort() {
        cancelRequests()
        main.removeCallbacks(levelTick)
        recorder?.cancel()
        recorder = null
        micForegroundPending = false
        if (state != State.IDLE) MicService.stop(app)
        session++
        state = State.IDLE
    }

    private fun prefs(ctx: Context) = (ctx.applicationContext as App).prefs

    // --- entry points from the overlay ------------------------------------------------------------

    fun start(m: Mode) {
        val svc = service ?: return
        if (state != State.IDLE) return
        val p = prefs(svc)
        val useTestAudio = BuildConfig.DEBUG && p.useTestAudio
        // Say so before the user talks for nothing.
        if (p.apiKey == null) return fail(svc, "还没有 key，点这里填写", openApp(svc, "key"))
        if (!useTestAudio && !Health.mic(svc)) return fail(svc, "需要麦克风权限，点这里", openApp(svc, null))
        mode = m
        session++
        svc.dismissAnswer()
        target = svc.focusedEditable()
        field = svc.currentField()
        targetApp = svc.targetPackage(target)
        selection = svc.selectedText(target)
        if (m == Mode.ASK && selection == null) Log.i(TAG, "Ask without a selection: write or answer")
        cancelRequests()
        requests = RequestSession()
        warmUp(p)
        state = State.LISTENING
        svc.overlay.listening(m)
        val testAudio = File(svc.filesDir, "test-audio.ogg")
        fakeAudio = if (useTestAudio && testAudio.exists()) testAudio.readBytes() else null
        if (fakeAudio == null) {
            micForegroundPending = true
            MicService.start(svc)
            // If the service can't reach the foreground (or the ROM is slow), record anyway after a moment.
            val id = session
            main.postDelayed({ if (id == session && micForegroundPending) onMicForeground(false) }, 700)
        } else {
            buzz(svc)
            main.post(levelTick)
        }
    }

    private var micForegroundPending = false

    /** Called by [MicService] once it is (or failed to get) in the foreground. */
    fun onMicForeground(ok: Boolean) {
        val id = session
        main.post {
            if (id != session || !micForegroundPending || state != State.LISTENING) return@post
            micForegroundPending = false
            val svc = service ?: return@post
            if (!ok) Log.w(TAG, "recording without a microphone foreground service")
            try {
                recorder = Recorder(svc).also { it.start() }
                // The buzz and the timer mean "speak now": give them when the microphone is really open, so the
                // first words aren't lost to the foreground-service start-up.
                buzz(svc)
                svc.overlay.recordingStarted()
                main.post(levelTick)
            } catch (e: Exception) {
                Log.e(TAG, "microphone unavailable", e)
                fail(svc, "麦克风打不开，可能正被其他应用占用")
            }
        }
    }

    fun finish() {
        val svc = service ?: return
        if (state != State.LISTENING) return
        main.removeCallbacks(levelTick)
        val r = recorder
        recorder = null
        seconds = if (fakeAudio != null) 6.0 else (r?.elapsedMs ?: 0) / 1000.0
        val audio = fakeAudio ?: r?.stop()
        val peak = if (fakeAudio != null) Int.MAX_VALUE else r?.peak ?: 0
        MicService.stop(svc)
        buzz(svc)
        when {
            audio == null || audio.size < 1500 -> return fail(svc, "太短了，没录到声音")
            peak == 0 -> return fail(svc, "麦克风没有声音：可能被通话或其他应用占用")
            peak < SILENCE_PEAK -> return fail(svc, "没有听到说话")
        }
        process(svc, audio!!)
    }

    /** Also reachable from the recording notification, with or without the service. */
    fun cancel() {
        abort() // cancel transport and drop any already-posted result
        service?.overlay?.collapse()
    }

    // --- processing ---------------------------------------------------------------------------

    private fun process(svc: VoiceAccessibilityService, audio: ByteArray) {
        val p = prefs(svc)
        val key = p.apiKey ?: return fail(svc, "还没有 key，点这里填写", openApp(svc, "key"))
        warmup?.cancel()
        warmup = null
        val requestSession = requests ?: return
        val network = client(key, p.apiBase)
        val settings = p.settings()
        val duration = seconds
        state = State.PROCESSING
        svc.overlay.processing()
        val id = session
        val m = mode
        val node = target ?: svc.focusedEditable()
        val spokenFor = field
        val sel = selection
        val app = node?.packageName?.toString() ?: targetApp
        io.execute {
            val outcome = runCatching {
                Pipeline(network, settings, requestSession).run(m, audio, "ogg",
                    CoreContext(app = app, dictionary = settings.dictionary), sel)
            }
            main.post {
                val store = this.app.store
                val result = outcome.getOrNull()
                if (id != session || service !== svc) { // cancelled, or the service went away meanwhile
                    // It was still paid for: keep the numbers right, but don't show or insert anything.
                    if (result != null) store.add(System.currentTimeMillis(), m.name.lowercase(), app.orEmpty(),
                        result.text, result.raw, result.costUsd, duration, keepEntry = false)
                    return@post
                }
                cancelRequests()
                state = State.IDLE
                outcome.fold(
                    onSuccess = { result ->
                        val keep = p.keep != "never" && result.text.isNotBlank()
                        store.add(System.currentTimeMillis(), m.name.lowercase(), app.orEmpty(),
                            result.text, result.raw, result.costUsd, duration, keepEntry = keep)
                        store.prune(p.keepDays) // retention holds even when the process lives for weeks
                        if (result.text.isBlank()) return@fold fail(svc, "没有听到说话")
                        when {
                            m == Mode.ASK && result.action == AskAction.ANSWER -> {
                                svc.overlay.done()
                                svc.showAnswer("Ask", result.text, question = result.raw)
                            }
                            svc.insert(node, result.text, replace = result.action == AskAction.REPLACE, field = spokenFor) ->
                                svc.overlay.done()
                            else -> { // no field, or input moved elsewhere: offer the text instead of misplacing it
                                svc.overlay.done()
                                svc.showAnswer(if (spokenFor != null) "输入框已经换了，文字在这里" else "没找到输入框，文字在这里", result.text)
                            }
                        }
                    },
                    onFailure = { e ->
                        Log.w(TAG, "pipeline failed", e)
                        val keyProblem = e is HttpException && e.code in setOf(401, 402, 403)
                        fail(svc, message(e) + if (keyProblem) "，点这里" else "", if (keyProblem) openApp(svc, if (e is HttpException && e.code == 402) "usage" else "key") else null)
                    },
                )
            }
        }
    }

    private fun client(key: String, base: String): OpenRouterClient {
        if (client == null || key + base != clientKey) {
            client = OpenRouterClient(key, baseUrl = base)
            clientKey = key + base
        }
        return client!!
    }

    private fun warmUp(p: Prefs) {
        val key = p.apiKey ?: return
        val c = client(key, p.apiBase)
        val owner = RequestSession().also { warmup = it }
        io.execute {
            try { c.warmUp(owner) } catch (_: CancellationException) { /* Expected on finish/abort. */ }
        }
    }

    private fun cancelRequests() {
        requests?.cancel()
        requests = null
        warmup?.cancel()
        warmup = null
    }

    private fun fail(svc: VoiceAccessibilityService, text: String, action: (() -> Unit)? = null) {
        cancelRequests()
        state = State.IDLE
        svc.overlay.error(text, action)
    }

    /** Open the app, optionally at a page ("key", "usage"). */
    private fun openApp(ctx: Context, page: String?): () -> Unit = {
        ctx.startActivity(android.content.Intent(ctx, MainActivity::class.java)
            .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK or android.content.Intent.FLAG_ACTIVITY_CLEAR_TOP)
            .putExtra(MainActivity.EXTRA_PAGE, page))
    }

    private fun message(e: Throwable): String = when (e) {
        is MissingKeyException -> "还没有 key"
        is TimeoutException -> "服务响应太慢，请再试一次"
        is NetworkException -> "网络连不上，检查一下网络或代理"
        is HttpException -> when (e.code) {
            401, 403 -> "key 无效"
            402 -> "OpenRouter 余额用完了"
            429 -> "请求太频繁，稍等一下再试"
            else -> "服务出错（HTTP ${e.code}）"
        }
        else -> "出了点问题，请再试一次"
    }

    private fun buzz(ctx: Context) {
        if (!prefs(ctx).haptics) return
        ctx.getSystemService(Vibrator::class.java)?.vibrate(VibrationEffect.createPredefined(VibrationEffect.EFFECT_TICK))
    }
}
