package app.localtypeless.android

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.InputMethod
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.text.method.ScrollingMovementMethod
import android.util.Log
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import android.view.inputmethod.EditorInfo
import androidx.annotation.RequiresApi
import android.widget.LinearLayout
import android.widget.TextView

/**
 * Watches which text field has focus (to show the handle only then), and inserts results into it.
 *
 * Insertion prefers the accessibility input method (Android 13+, flagInputMethodEditor): it commits text through
 * the field's InputConnection, the channel keyboards use, alongside whatever keyboard is active. That works where
 * the node tree doesn't: WeChat hides its whole tree from third-party services (one empty 0x0 node, measured
 * 2026-09-27) but still hands us its input connection. Below Android 13, or with no connection, fall back to
 * ACTION_SET_TEXT computed around the cursor, then a result card with an explicit copy action.
 */
class VoiceAccessibilityService : AccessibilityService() {
    lateinit var overlay: EdgeOverlay
        private set
    private var answerView: View? = null
    private val main = Handler(Looper.getMainLooper())

    /** The text field the system is currently feeding input to, as seen by the accessibility input method. */
    @Volatile private var editor: EditorInfo? = null

    @RequiresApi(33)
    override fun onCreateInputMethod(): InputMethod = object : InputMethod(this) {
        override fun onStartInput(attribute: EditorInfo, restarting: Boolean) {
            if (BuildConfig.DEBUG) Log.d(TAG, "input started: pkg=${attribute.packageName} type=${attribute.inputType} restarting=$restarting")
            editor = attribute
            // Every start counts, restarts too: Compose hosts all its fields in one view, so moving between them
            // arrives as a restart (seen in the emulator). A restart of the same field while we process only costs
            // showing the text in a card instead of typing it.
            inputSession++
            main.post { refreshHandle() }
        }

        override fun onFinishInput() {
            editor = null
            main.post { refreshHandle() }
        }
    }

    private fun connection(): InputMethod.AccessibilityInputConnection? {
        if (Build.VERSION.SDK_INT < 33) return null
        val im = inputMethod ?: return null
        return if (im.currentInputStarted) im.currentInputConnection else null
    }

    /** A field that takes text (and isn't a password) is being fed input. */
    private fun editorTakesText(): Boolean {
        val type = editor?.inputType ?: return false
        return type != InputType.TYPE_NULL && connection() != null && !isPassword(type)
    }

    private fun isPassword(type: Int): Boolean {
        val variation = type and InputType.TYPE_MASK_VARIATION
        return when (type and InputType.TYPE_MASK_CLASS) {
            InputType.TYPE_CLASS_TEXT -> variation == InputType.TYPE_TEXT_VARIATION_PASSWORD ||
                variation == InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD ||
                variation == InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD
            InputType.TYPE_CLASS_NUMBER -> variation == InputType.TYPE_NUMBER_VARIATION_PASSWORD
            else -> false
        }
    }

    /**
     * Which field input is going to, so a result can be checked against the field it was spoken for. The field id
     * alone can't tell fields apart (Compose fields, and all of WeChat's, report the same one), so the count of
     * input sessions is part of it: it moves whenever focus goes to another field.
     */
    data class FieldRef(val pkg: String?, val fieldId: Int, val session: Int)

    @Volatile private var inputSession = 0

    fun currentField(): FieldRef? =
        editor?.takeIf { connection() != null }?.let { FieldRef(it.packageName, it.fieldId, inputSession) }

    /** Package of the field being typed into, whichever way we can see it. */
    fun targetPackage(node: AccessibilityNodeInfo?): String? =
        node?.packageName?.toString() ?: editor?.packageName ?: activePackage()

    override fun onServiceConnected() {
        running.value = true
        val prefs = (application as App).prefs
        overlay = EdgeOverlay(this, prefs).apply {
            onTap = { mode -> Dictation.start(mode) }
            onFinish = { Dictation.finish() }
            onCancel = { Dictation.cancel() }
            onIdle = { refreshHandle() }
        }
        Dictation.attach(this)
        refreshHandle()
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent) {
        when (event.eventType) {
            AccessibilityEvent.TYPE_VIEW_FOCUSED -> {
                val src = event.source
                if (BuildConfig.DEBUG) Log.d(TAG, "focused event: ${src?.className} editable=${src?.isEditable} focused=${src?.isFocused}")
                if (src?.isEditable == true) lastEditable = src
                refreshHandle()
            }
            AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED -> {
                // Another app came to the front: an answer card belongs to where it was asked.
                val pkg = event.packageName?.toString()
                if (answerView != null && pkg != null && pkg != packageName && pkg != answerPackage) dismissAnswer()
                refreshHandle()
            }
            AccessibilityEvent.TYPE_WINDOWS_CHANGED,
            AccessibilityEvent.TYPE_VIEW_TEXT_SELECTION_CHANGED -> refreshHandle() // Compose: caret moves, no focus event
        }
    }

    private var lastEditable: AccessibilityNodeInfo? = null

    override fun onInterrupt() {}

    override fun onUnbind(intent: android.content.Intent?): Boolean {
        running.value = false
        Dictation.detach(this) // stop owned calls and microphone; ignore an obsolete service instance
        return super.onUnbind(intent)
    }

    override fun onConfigurationChanged(newConfig: android.content.res.Configuration) {
        super.onConfigurationChanged(newConfig)
        if (::overlay.isInitialized) overlay.relayout()
        dismissAnswer() // its width was the old screen's
    }

    override fun onDestroy() {
        running.value = false
        Dictation.detach(this)
        dismissAnswer()
        if (::overlay.isInitialized) overlay.detach()
        super.onDestroy()
    }

    /** Show the handle while an editable field has input focus; hide it otherwise (never mid-session). */
    private fun refreshHandle() {
        if (!::overlay.isInitialized || Dictation.state != Dictation.State.IDLE) return
        // Never offer dictation into a password field (the input method sees its type even when the tree doesn't).
        if (editor?.let { isPassword(it.inputType) } == true) return overlay.hideHandle()
        val viaInput = editorTakesText()
        val focused = if (viaInput) null else focusedEditable()
        if (BuildConfig.DEBUG) Log.d(TAG, "focus: input=$viaInput node=${focused?.className} pkg=${focused?.packageName}")
        if (viaInput || focused != null) overlay.showHandle() else overlay.hideHandle()
    }

    /** The soft keyboard is on screen. Stands in for "a text field has focus" in apps that hide their
     *  accessibility tree from third-party services: WeChat exposes one empty 0x0 node (measured 2026-09-27). */
    fun keyboardUp(): Boolean =
        runCatching { windows.any { it.type == AccessibilityWindowInfo.TYPE_INPUT_METHOD } }.getOrDefault(false)

    /** Package of the app in front, for the prompt's context when there's no field node to ask. */
    fun activePackage(): String? = runCatching { rootInActiveWindow?.packageName?.toString() }.getOrNull()

    /** Put text on the clipboard for the user to paste themselves. */
    fun copy(text: String) =
        SensitiveClipboard.copy(this, text)

    /** The editable field with input focus: asked of the service, then of the active window, then the last
     *  focused field an event told us about (still focused?). Which one works differs between toolkits. */
    fun focusedEditable(): AccessibilityNodeInfo? {
        val candidates = sequenceOf(
            { findFocus(AccessibilityNodeInfo.FOCUS_INPUT) },
            { rootInActiveWindow?.findFocus(AccessibilityNodeInfo.FOCUS_INPUT) },
            { lastEditable?.takeIf { it.refresh() && it.isFocused } },
            { rootInActiveWindow?.let(::findFocusedEditable) }, // Compose fields: no input-focus report
        )
        return candidates.mapNotNull { runCatching(it).getOrNull() }.firstOrNull { it.isEditable && !it.isPassword }
    }

    /** Breadth-first search for a focused editable node (bounded: this runs on every focus change). */
    private fun findFocusedEditable(root: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        val queue = ArrayDeque<AccessibilityNodeInfo>().apply { add(root) }
        var seen = 0
        while (queue.isNotEmpty() && seen++ < 400) {
            val n = queue.removeFirst()
            if (n.isEditable && n.isFocused) return n
            for (i in 0 until n.childCount) n.getChild(i)?.let(queue::add)
        }
        return null
    }

    /** The selected text, from the input connection if there is one, else from the node. */
    fun selectedText(node: AccessibilityNodeInfo?): String? {
        connection()?.let { ic ->
            val st = runCatching { ic.getSurroundingText(0, 0, 0) }.getOrNull()
            if (st != null) {
                val t = st.text?.toString().orEmpty()
                val s = st.selectionStart
                val e = st.selectionEnd
                return if (s in 0 until e && e <= t.length) t.substring(s, e) else null
            }
        }
        node ?: return null
        val text = currentText(node)
        val s = node.textSelectionStart
        val e = node.textSelectionEnd
        if (s < 0 || e <= s || e > text.length) return null
        return text.substring(s, e)
    }

    private fun currentText(node: AccessibilityNodeInfo): String =
        if (node.isShowingHintText) "" else node.text?.toString().orEmpty()

    /**
     * Insert at the cursor, replacing any selection. [field] is the field the text was spoken for (null: take the
     * one focused now). If input has moved to another field or app since, nothing is inserted and false comes
     * back, so the caller shows the text instead of typing it somewhere the user didn't mean (a search box, a
     * chat that sends on Enter).
     */
    fun insert(node: AccessibilityNodeInfo?, insertion: String, replace: Boolean, field: FieldRef? = currentField()): Boolean {
        val ic = connection()
        if (field != null) {
            if (ic == null || currentField() != field) return false
            ic.commitText(insertion, 1, null)
            return true
        }
        node ?: return false
        node.refresh()
        val text = currentText(node)
        var start = node.textSelectionStart
        var end = node.textSelectionEnd
        if (start < 0 || end < 0 || start > text.length || end > text.length) { start = text.length; end = text.length }
        if (!replace) end = maxOf(start, end).also { start = minOf(start, end) }
        val updated = text.substring(0, start) + insertion + text.substring(end)
        val setOk = node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, updated)
        })
        if (setOk) {
            node.refresh()
            if (currentText(node) == updated) {
                val caret = start + insertion.length
                node.performAction(AccessibilityNodeInfo.ACTION_SET_SELECTION, Bundle().apply {
                    putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT, caret)
                    putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT, caret)
                })
                return true
            }
        }
        // Android denies background clipboard reads and provides no atomic compare-and-restore.
        // A temporary clip cannot be restored without risking newer user data; offer explicit copy instead.
        return false
    }

    // --- answer card (Ask anything answers, or text that couldn't be inserted) ------------------------

    /**
     * A card at the top of the screen (clear of the keyboard) for an Ask answer, or for text that could not be
     * inserted. Opaque: the keyboard showed through the translucent first version.
     */
    fun showAnswer(heading: String, body: String, question: String? = null) {
        dismissAnswer()
        answerPackage = activePackage()
        val dp = resources.displayMetrics.density
        fun px(v: Float) = (v * dp).toInt()
        val ink = Color.parseColor("#F3F4F8")
        val muted = Color.parseColor("#A4A7B8")
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(px(20f), px(16f), px(12f), px(14f))
            background = GradientDrawable().apply {
                cornerRadius = 24 * dp
                setColor(Color.parseColor("#FF14151E"))
                setStroke(px(1f), Color.parseColor("#26FFFFFF"))
            }
            elevation = 16 * dp
        }
        val header = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL }
        header.addView(View(this).apply {
            background = GradientDrawable(GradientDrawable.Orientation.TL_BR,
                intArrayOf(Color.parseColor("#D9CEFF"), Color.parseColor("#9B82FF"), Color.parseColor("#2FD3E0"))).apply {
                shape = GradientDrawable.OVAL
            }
        }, LinearLayout.LayoutParams(px(16f), px(16f)))
        header.addView(TextView(this).apply {
            text = heading
            setTextColor(muted)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            setPadding(px(10f), 0, 0, 0)
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        header.addView(TextView(this).apply {
            text = "✕"
            setTextColor(muted)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 15f)
            gravity = Gravity.CENTER
            setOnClickListener { dismissAnswer() }
        }, LinearLayout.LayoutParams(px(40f), px(32f)))
        card.addView(header)
        if (!question.isNullOrBlank()) card.addView(TextView(this).apply {
            text = question
            setTextColor(muted)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)
            maxLines = 2
            ellipsize = android.text.TextUtils.TruncateAt.END
            setPadding(0, px(8f), px(8f), 0)
        })
        card.addView(TextView(this).apply {
            text = Markdown.render(body)
            setTextColor(ink)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
            setLineSpacing(0f, 1.3f)
            setPadding(0, px(10f), px(8f), px(14f))
            maxHeight = px(340f)
            isVerticalScrollBarEnabled = true
            movementMethod = ScrollingMovementMethod()
        })
        val row = LinearLayout(this).apply { gravity = Gravity.END }
        fun button(label: String, primary: Boolean, action: () -> Unit) = TextView(this).apply {
            text = label
            setTextColor(Color.parseColor(if (primary) "#0B0C12" else "#F3F4F8"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
            setPadding(px(18f), px(9f), px(18f), px(9f))
            background = GradientDrawable().apply {
                cornerRadius = 14 * dp
                setColor(Color.parseColor(if (primary) "#EEF0F6" else "#1CFFFFFF"))
            }
            setOnClickListener { action() }
        }
        row.addView(button("复制", !canInsert()) {
            copy(Markdown.plain(body))
            dismissAnswer()
        })
        if (canInsert()) {
            row.addView(View(this), LinearLayout.LayoutParams(px(10f), 1))
            row.addView(button("插入", true) {
                if (insert(focusedEditable(), Markdown.plain(body), replace = false)) dismissAnswer()
                else {
                    copy(Markdown.plain(body))
                    android.widget.Toast.makeText(this, "没能插入，已复制", android.widget.Toast.LENGTH_SHORT).show()
                }
            })
        }
        card.addView(row)
        val statusBar = resources.getIdentifier("status_bar_height", "dimen", "android")
            .let { if (it > 0) resources.getDimensionPixelSize(it) else px(24f) }
        val params = WindowManager.LayoutParams(
            resources.displayMetrics.widthPixels - px(24f),
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT,
        ).apply { gravity = Gravity.TOP or Gravity.CENTER_HORIZONTAL; y = statusBar + px(10f) }
        card.alpha = 0f
        card.translationY = -12 * dp
        getSystemService(WindowManager::class.java).addView(card, params)
        card.animate().alpha(1f).translationY(0f).setDuration(180).start()
        answerView = card
    }

    /** A field is ready to take text right now. */
    private fun canInsert() = connection() != null || focusedEditable() != null

    private var answerPackage: String? = null

    fun dismissAnswer() {
        answerView?.let { runCatching { getSystemService(WindowManager::class.java).removeView(it) } }
        answerView = null
    }

    companion object {
        private const val TAG = "VoiceA11y"

        /** Whether the service is bound right now (the Settings switch alone can say "on" while it isn't). */
        val running = kotlinx.coroutines.flow.MutableStateFlow(false)
    }
}
