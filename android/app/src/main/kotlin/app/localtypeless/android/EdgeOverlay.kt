package app.localtypeless.android

import android.animation.ValueAnimator
import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.PixelFormat
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.Typeface
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.view.WindowManager
import android.view.animation.DecelerateInterpolator
import app.localtypeless.core.Mode
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin

/**
 * The edge handle and the voice capsule, in the Glass language of the desktop app.
 *
 * Idle, it is a 5 dp violet-to-cyan line hugging the screen edge, shown only while a text field has focus — most
 * of the time you don't see it at all. Its touch area is far larger than what is drawn. Tap: it slides out into
 * a dark frosted capsule (× · mode · waveform · timer · ✓). Long-press: pick Translate or Ask. Drag: move it up
 * and down, or across to the other edge. It lives in an accessibility overlay window: no "draw over other apps"
 * permission, and it never takes the focus from the field you are typing in.
 */
@SuppressLint("ViewConstructor")
class EdgeOverlay(private val context: Context, private val prefs: Prefs) {
    enum class State { HIDDEN, HANDLE, MENU, LISTENING, PROCESSING, DONE, ERROR }

    private val wm = context.getSystemService(WindowManager::class.java)
    private val dp = context.resources.displayMetrics.density
    private val view = OverlayView()
    private val params = WindowManager.LayoutParams(
        WindowManager.LayoutParams.WRAP_CONTENT,
        WindowManager.LayoutParams.WRAP_CONTENT,
        WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
        WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS or
            WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or WindowManager.LayoutParams.FLAG_WATCH_OUTSIDE_TOUCH,
        PixelFormat.TRANSLUCENT,
    ).apply { gravity = Gravity.TOP or Gravity.START }
    private var attached = false

    var state = State.HIDDEN
        private set
    var mode = Mode.DICTATE
    var repoLabel = "" // not used on the phone yet; kept for parity with the desktop chip
    var message = ""
    private var levels = FloatArray(BARS)
    private var shown = FloatArray(BARS)
    private var startedAt = 0L
    private var expand = 0f // 0 = handle, 1 = capsule / menu fully out
    private var animator: ValueAnimator? = null

    /** Callbacks into the controller. */
    var onTap: (Mode) -> Unit = {}
    var onFinish: () -> Unit = {}
    var onCancel: () -> Unit = {}
    /** Back to the plain handle: the controller re-checks whether a field still has focus. */
    var onIdle: () -> Unit = {}

    /**
     * Bumped on every state change. Delayed work (auto-dismiss timers, animation end blocks) captures it and does
     * nothing if the state moved on meanwhile: a stale "collapse" used to shrink the capsule of the *next* session
     * to the handle while it was still recording.
     */
    private var gen = 0
    private var listeningSince = 0L

    // --- geometry ------------------------------------------------------------------------------

    private fun px(v: Float) = v * dp
    private val screenW get() = context.resources.displayMetrics.widthPixels
    private val screenH get() = context.resources.displayMetrics.heightPixels
    private val onRight get() = prefs.handleRight

    private val handleWin get() = Pair(px(26f).toInt(), px(88f).toInt())
    private val capsuleW get() = px(if (state == State.ERROR) 288f else if (mode == Mode.DICTATE) 232f else 262f)
    private val capsuleH get() = px(52f)
    private val margin get() = px(14f) // room for the soft shadow
    // The window is only as big as what is drawn: every pixel of it swallows touches meant for the app below.
    private val capsuleWin get() = Pair((capsuleW + 2 * margin + px(10f)).toInt(), (capsuleH + 2 * margin).toInt())
    private val menuWin get() = Pair((px(132f) + px(34f) + margin).toInt(), px(172f).toInt())

    private fun centerY(): Int = (prefs.handleY * screenH).toInt()

    private fun place(width: Int, height: Int) {
        params.width = width
        params.height = height
        params.x = if (onRight) screenW - width else 0
        params.y = (centerY() - height / 2).coerceIn(0, max(0, screenH - height))
        if (attached) wm.updateViewLayout(view, params) else {
            wm.addView(view, params)
            attached = true
        }
    }

    // --- state changes (main thread) ------------------------------------------------------------

    fun showHandle() {
        if (state == State.HIDDEN) {
            gen++
            state = State.HANDLE
            expand = 0f
            handleWin.let { place(it.first, it.second) }
            view.alpha = 0f
            view.animate().alpha(1f).setDuration(160).start()
        }
    }

    fun hideHandle() {
        if (state == State.HANDLE || state == State.MENU) {
            gen++
            state = State.HIDDEN
            view.animate().alpha(0f).setDuration(120).withEndAction { detach() }.start()
        }
    }

    fun listening(m: Mode) {
        mode = m
        levels = FloatArray(BARS)
        shown = FloatArray(BARS)
        startedAt = System.currentTimeMillis()
        listeningSince = startedAt
        gen++
        state = State.LISTENING
        view.alpha = 1f
        capsuleWin.let { place(it.first, it.second) }
        animateExpand(1f)
        view.startTicking()
    }

    /** The microphone is actually recording now: the timer starts here, not at the tap. */
    fun recordingStarted() {
        startedAt = System.currentTimeMillis()
    }

    fun pushLevel(level: Float) {
        System.arraycopy(levels, 1, levels, 0, BARS - 1)
        levels[BARS - 1] = level
    }

    fun processing() {
        gen++
        state = State.PROCESSING
        view.invalidate()
    }

    fun done() {
        message = ""
        state = State.DONE
        later(420) { collapse() }
    }

    /** Run [block] after [ms] unless the state changed in between. */
    private fun later(ms: Long, block: () -> Unit) {
        val g = ++gen
        view.postDelayed({ if (g == gen) block() }, ms)
    }

    /** Done, with a line of text held long enough to read (e.g. "copied, paste it"). */
    fun notice(text: String) {
        message = text
        state = State.DONE
        view.invalidate()
        later(2600) { collapse() }
    }

    /** What tapping the current error does (e.g. open the app at the key page); null = just dismiss. */
    private var errorAction: (() -> Unit)? = null

    fun error(text: String, action: (() -> Unit)? = null) {
        errorAction = action
        message = text
        state = State.ERROR
        capsuleWin.let { place(it.first, it.second) }
        animateExpand(1f)
        view.startTicking()
        // An error you can act on stays longer: there is something to tap.
        later(if (action != null) 5000 else 2800) { collapse() }
    }

    fun collapse(stayVisible: Boolean = true) {
        val g = ++gen
        animateExpand(0f) {
            if (g != gen) return@animateExpand // a new session started while collapsing
            view.stopTicking()
            state = if (stayVisible) State.HANDLE else State.HIDDEN
            if (stayVisible) {
                handleWin.let { place(it.first, it.second) }
                onIdle()
            } else detach()
        }
    }

    private fun showMenu() {
        gen++
        state = State.MENU
        menuWin.let { place(it.first, it.second) }
        animateExpand(1f)
    }

    /** Screen size changed (rotation): put the window back against the edge. */
    fun relayout() {
        if (!attached) return
        when (state) {
            State.HANDLE -> handleWin
            State.MENU -> menuWin
            State.HIDDEN -> return
            else -> capsuleWin
        }.let { place(it.first, it.second) }
        view.invalidate()
    }

    fun detach() {
        view.stopTicking()
        if (attached) runCatching { wm.removeView(view) }
        attached = false
        if (state == State.HANDLE || state == State.MENU) state = State.HIDDEN
    }

    private fun animateExpand(to: Float, end: () -> Unit = {}) {
        animator?.cancel()
        animator = ValueAnimator.ofFloat(expand, to).apply {
            duration = if (to > expand) 220 else 180
            interpolator = DecelerateInterpolator(2f)
            addUpdateListener { expand = it.animatedValue as Float; view.invalidate() }
            addListener(object : android.animation.AnimatorListenerAdapter() {
                private var cancelled = false
                override fun onAnimationCancel(a: android.animation.Animator) { cancelled = true }
                override fun onAnimationEnd(a: android.animation.Animator) { if (!cancelled) end() }
            })
            start()
        }
    }

    // --- the view -------------------------------------------------------------------------------

    private inner class OverlayView : View(context) {
        private val violet = Color.parseColor("#9B82FF")
        private val cyan = Color.parseColor("#2FD3E0")
        private val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#EE101119") }
        private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = px(1f) }
        private val shadow = Paint(Paint.ANTI_ALIAS_FLAG)
        private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
        private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.parseColor("#F3F4F8"); textSize = px(13.5f); typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
        }
        private val muted = Paint(text).apply { color = Color.parseColor("#A4A7B8"); typeface = Typeface.MONOSPACE; textSize = px(12.5f) }
        private val ticker = object : Runnable {
            override fun run() {
                for (i in 0 until BARS) shown[i] += (levels[i] - shown[i]) * 0.35f
                invalidate()
                postOnAnimation(this)
            }
        }
        private var ticking = false

        fun startTicking() { if (!ticking) { ticking = true; postOnAnimation(ticker) } }
        fun stopTicking() { ticking = false; removeCallbacks(ticker) }

        // hit targets in the capsule, set while drawing
        private val cancelRect = RectF()
        private val finishRect = RectF()
        private val menuRects = Array(3) { RectF() }
        private val menuHint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#8A8DA0"); textSize = px(11.5f) }

        override fun onDraw(c: Canvas) {
            when (state) {
                State.HANDLE -> drawHandle(c)
                State.MENU -> { drawHandle(c); drawMenu(c) }
                State.LISTENING, State.PROCESSING, State.DONE, State.ERROR -> drawCapsule(c)
                State.HIDDEN -> {}
            }
        }

        private fun drawHandle(c: Canvas) {
            val w = px(5f)
            val h = px(52f)
            val x = if (onRight) width - w - px(2f) else px(2f)
            val y = (height - h) / 2f
            val r = RectF(x, y, x + w, y + h)
            paint.shader = null
            paint.color = Color.parseColor("#66101119") // dark rim: visible on white backgrounds too
            c.drawRoundRect(RectF(r.left - px(1.2f), r.top - px(1.2f), r.right + px(1.2f), r.bottom + px(1.2f)), w, w, paint)
            paint.shader = LinearGradient(0f, r.top, 0f, r.bottom, violet, cyan, Shader.TileMode.CLAMP)
            paint.alpha = 230
            c.drawRoundRect(r, w / 2, w / 2, paint)
            paint.shader = null
            paint.alpha = 255
        }

        private fun capsuleRect(): RectF {
            val w = capsuleW * (0.35f + 0.65f * expand)
            val top = (height - capsuleH) / 2f
            return if (onRight) RectF(width - margin - w, top, width - margin, top + capsuleH)
            else RectF(margin, top, margin + w, top + capsuleH)
        }

        private fun glass(c: Canvas, r: RectF, radius: Float) {
            for (i in 6 downTo 1) { // soft shadow
                shadow.color = Color.argb((10 * (7 - i) / 3), 0, 0, 0)
                val s = px(i * 2f)
                c.drawRoundRect(RectF(r.left - s, r.top - s + px(4f), r.right + s, r.bottom + s + px(4f)), radius + s, radius + s, shadow)
            }
            c.drawRoundRect(r, radius, radius, fill)
            stroke.shader = LinearGradient(0f, r.top, 0f, r.bottom, Color.argb(80, 255, 255, 255), Color.argb(22, 255, 255, 255), Shader.TileMode.CLAMP)
            c.drawRoundRect(RectF(r.left + 0.5f, r.top + 0.5f, r.right - 0.5f, r.bottom - 0.5f), radius, radius, stroke)
        }

        private fun drawCapsule(c: Canvas) {
            val r = capsuleRect()
            val radius = r.height() / 2
            glass(c, r, radius)
            if (expand < 0.85f) return
            c.save()
            c.clipRect(r)
            val cy = r.centerY()
            val btn = px(34f)
            val pad = px(9f)
            when (state) {
                State.ERROR -> {
                    paint.color = Color.parseColor("#FF7A8A"); paint.style = Paint.Style.STROKE; paint.strokeWidth = px(1.6f)
                    c.drawCircle(r.left + px(26f), cy, px(8f), paint)
                    paint.style = Paint.Style.FILL
                    c.drawRect(r.left + px(25.2f), cy - px(4.5f), r.left + px(26.8f), cy + px(1f), paint)
                    c.drawCircle(r.left + px(26f), cy + px(4f), px(1f), paint)
                    val shownText = TextUtilsEllipsize.fit(message, text, r.width() - px(56f))
                    c.drawText(shownText, r.left + px(44f), cy + px(5f), text)
                }
                State.DONE -> if (message.isNotEmpty()) {
                    paint.shader = LinearGradient(r.left + px(12f), 0f, r.left + px(40f), 0f, violet, cyan, Shader.TileMode.CLAMP)
                    c.drawCircle(r.left + px(26f), cy, px(12f), paint)
                    paint.shader = null
                    check(c, r.left + px(26f), cy, Color.WHITE, 0.9f)
                    val shownText = TextUtilsEllipsize.fit(message, text, r.width() - px(60f))
                    c.drawText(shownText, r.left + px(46f), cy + px(5f), text)
                } else {
                    paint.shader = LinearGradient(r.centerX() - px(15f), 0f, r.centerX() + px(15f), 0f, violet, cyan, Shader.TileMode.CLAMP)
                    c.drawCircle(r.centerX(), cy, px(15f), paint)
                    paint.shader = null
                    check(c, r.centerX(), cy, Color.WHITE, 1.15f)
                }
                else -> {
                    // × on the left
                    cancelRect.set(r.left + pad, cy - btn / 2, r.left + pad + btn, cy + btn / 2)
                    paint.color = Color.argb(28, 255, 255, 255)
                    c.drawCircle(cancelRect.centerX(), cy, btn / 2, paint)
                    paint.color = Color.parseColor("#A4A7B8"); paint.strokeWidth = px(1.7f); paint.strokeCap = Paint.Cap.ROUND
                    val d = px(5.5f)
                    c.drawLine(cancelRect.centerX() - d, cy - d, cancelRect.centerX() + d, cy + d, paint)
                    c.drawLine(cancelRect.centerX() - d, cy + d, cancelRect.centerX() + d, cy - d, paint)
                    var left = cancelRect.right + px(10f)
                    // mode tag for Translate / Ask
                    if (mode != Mode.DICTATE) {
                        val tag = if (mode == Mode.TRANSLATE) "译" else "Ask"
                        val tw = text.measureText(tag) + px(16f)
                        paint.color = Color.argb(30, 255, 255, 255)
                        c.drawRoundRect(RectF(left, cy - px(12f), left + tw, cy + px(12f)), px(12f), px(12f), paint)
                        c.drawText(tag, left + px(8f), cy + px(5f), text)
                        left += tw + px(10f)
                    }
                    // ✓ on the right (listening only)
                    finishRect.set(r.right - pad - btn, cy - btn / 2, r.right - pad, cy + btn / 2)
                    var barsRight = r.right - px(16f)
                    if (state == State.LISTENING) {
                        paint.color = Color.parseColor("#F3F4F8")
                        c.drawCircle(finishRect.centerX(), cy, btn / 2, paint)
                        check(c, finishRect.centerX(), cy, Color.parseColor("#0B0C12"), 1f)
                        val secs = ((System.currentTimeMillis() - startedAt) / 1000).toInt()
                        val remaining = MAX_SECONDS - secs
                        // The desktop's Voice bar: the last minute counts down in red before the cap sends it.
                        val red = remaining <= 60
                        val clock = if (red) "-0:%02d".format(maxOf(0, remaining)) else "%d:%02d".format(secs / 60, secs % 60)
                        val cw = muted.measureText("0:00")
                        muted.color = Color.parseColor(if (red) "#FF7A8A" else "#A4A7B8")
                        c.drawText(clock, finishRect.left - px(10f) - cw, cy + px(4.5f), muted)
                        barsRight = finishRect.left - px(18f) - cw
                    }
                    drawBars(c, RectF(left, cy - px(12f), barsRight, cy + px(12f)))
                }
            }
            c.restore()
        }

        private fun drawBars(c: Canvas, area: RectF) {
            if (area.width() <= 0) return
            val step = area.width() / BARS
            val bw = max(px(2.2f), step * 0.5f)
            paint.shader = LinearGradient(area.left, 0f, area.right, 0f, violet, cyan, Shader.TileMode.CLAMP)
            val t = System.currentTimeMillis() / 1000.0
            for (i in 0 until BARS) {
                val v = if (state == State.PROCESSING) (0.18 + 0.5 * max(0.0, sin(t * 5.0 - i * 0.45)).let { it * it }).toFloat() else shown[i]
                val h = max(px(3f), v * area.height())
                val cx = area.left + step * (i + 0.5f)
                c.drawRoundRect(RectF(cx - bw / 2, area.centerY() - h / 2, cx + bw / 2, area.centerY() + h / 2), bw / 2, bw / 2, paint)
            }
            paint.shader = null
        }

        private fun check(c: Canvas, cx: Float, cy: Float, color: Int, s: Float) {
            paint.color = color; paint.strokeWidth = px(2.1f); paint.strokeCap = Paint.Cap.ROUND; paint.style = Paint.Style.STROKE
            val p = android.graphics.Path().apply {
                moveTo(cx - px(5.5f) * s, cy + px(0.3f) * s)
                lineTo(cx - px(1.8f) * s, cy + px(4f) * s)
                lineTo(cx + px(5.5f) * s, cy - px(4.2f) * s)
            }
            c.drawPath(p, paint)
            paint.style = Paint.Style.FILL
        }

        private fun drawMenu(c: Canvas) {
            val labels = listOf("听写", "翻译", "Ask")
            val target = app.localtypeless.android.ui.languageLabel(prefs.translateTarget)
            val w = px(132f); val h = px(42f); val gap = px(8f)
            val total = 3 * h + 2 * gap
            val top = (height - total) / 2f
            for (i in 0..2) {
                val offset = (1 - expand) * px(24f)
                val l = if (onRight) width - px(34f) - w + offset else px(34f) - offset
                val r = RectF(l, top + i * (h + gap), l + w, top + i * (h + gap) + h)
                menuRects[i].set(r)
                glass(c, r, h / 2)
                paint.shader = LinearGradient(r.left + px(12f), 0f, r.left + px(20f), 0f, violet, cyan, Shader.TileMode.CLAMP)
                c.drawCircle(r.left + px(16f), r.centerY(), px(3.5f), paint)
                paint.shader = null
                c.drawText(labels[i], r.left + px(28f), r.centerY() + px(5f), text)
                val hint = when (i) { 1 -> "→ $target"; 2 -> "问或改写"; else -> "" }
                if (hint.isNotEmpty()) {
                    val hw = menuHint.measureText(hint)
                    c.drawText(hint, r.right - px(16f) - hw, r.centerY() + px(4.5f), menuHint)
                }
            }
        }

        // --- touch ---------------------------------------------------------------------------

        private val slop = ViewConfiguration.get(context).scaledTouchSlop
        private var downX = 0f
        private var downY = 0f
        private var downWinY = 0
        private var dragging = false
        private var menuFromThisGesture = false
        private val longPress = Runnable {
            if (state == State.HANDLE && !dragging) {
                performHapticFeedback(android.view.HapticFeedbackConstants.LONG_PRESS)
                menuFromThisGesture = true
                showMenu()
            }
        }

        @SuppressLint("ClickableViewAccessibility")
        override fun onTouchEvent(e: MotionEvent): Boolean {
            if (e.actionMasked == MotionEvent.ACTION_OUTSIDE) { // a tap elsewhere closes the menu
                if (state == State.MENU) collapse()
                return false
            }
            when (state) {
                State.HANDLE -> handleTouch(e)
                State.MENU -> if (e.actionMasked == MotionEvent.ACTION_UP) {
                    // Long-press, slide onto an option, release: picks it. Releasing elsewhere right after the
                    // long-press keeps the menu open for a tap; a later tap outside closes it.
                    val hit = menuRects.indexOfFirst { it.contains(e.x, e.y) }
                    when {
                        hit >= 0 -> onTap(listOf(Mode.DICTATE, Mode.TRANSLATE, Mode.ASK)[hit])
                        menuFromThisGesture -> {}
                        else -> collapse()
                    }
                    menuFromThisGesture = false
                }
                State.LISTENING, State.PROCESSING -> if (e.action == MotionEvent.ACTION_UP &&
                    // The second tap of a double tap on the handle lands where the check mark is about to be.
                    System.currentTimeMillis() - listeningSince > 350
                ) {
                    when {
                        cancelRect.contains(e.x, e.y) -> onCancel()
                        state == State.LISTENING && finishRect.contains(e.x, e.y) -> onFinish()
                    }
                }
                State.ERROR, State.DONE -> if (e.action == MotionEvent.ACTION_UP && capsuleRect().contains(e.x, e.y)) {
                    if (state == State.ERROR) errorAction?.invoke()
                    errorAction = null
                    collapse()
                }
                else -> {}
            }
            return true
        }

        private fun handleTouch(e: MotionEvent) {
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    downX = e.rawX; downY = e.rawY; downWinY = params.y; dragging = false
                    postDelayed(longPress, ViewConfiguration.getLongPressTimeout().toLong())
                }
                MotionEvent.ACTION_MOVE -> {
                    if (!dragging && (abs(e.rawY - downY) > slop || abs(e.rawX - downX) > slop)) {
                        dragging = true
                        removeCallbacks(longPress)
                    }
                    if (dragging) {
                        params.y = (downWinY + (e.rawY - downY)).toInt().coerceIn(0, screenH - params.height)
                        params.x = (e.rawX - params.width / 2).toInt().coerceIn(0, screenW - params.width)
                        wm.updateViewLayout(this, params)
                    }
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    removeCallbacks(longPress)
                    if (dragging) { // snap to the nearer edge and remember the spot
                        prefs.handleRight = e.rawX > screenW / 2
                        prefs.handleY = (params.y + params.height / 2f) / screenH
                        handleWin.let { place(it.first, it.second) }
                        invalidate()
                    } else if (e.actionMasked == MotionEvent.ACTION_UP) {
                        onTap(Mode.DICTATE)
                    }
                }
            }
        }
    }

    companion object {
        const val BARS = 18
        const val MAX_SECONDS = 9 * 60 // Dictation.MAX_MS
    }
}

/** Shorten a line to fit a width, with an ellipsis. */
internal object TextUtilsEllipsize {
    fun fit(s: String, paint: Paint, width: Float): String {
        if (paint.measureText(s) <= width) return s
        var end = s.length
        while (end > 0 && paint.measureText(s, 0, end) + paint.measureText("…") > width) end--
        return s.substring(0, end) + "…"
    }
}
