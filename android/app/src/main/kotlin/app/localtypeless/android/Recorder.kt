package app.localtypeless.android

import android.content.Context
import android.media.MediaRecorder
import android.os.Build
import java.io.File

/**
 * Microphone to OGG/Opus, 16 kHz mono 24 kbps — exactly what the desktop app uploads (docs/models.md: WAV costs
 * 0.7-0.9 s more per request). The encoder runs while you speak, so stopping is instant.
 */
class Recorder(private val context: Context) {
    private var recorder: MediaRecorder? = null
    private var file: File? = null
    private var startedAt = 0L
    var peak = 0 // loudest level seen, 0..32767: tells "nothing said" (or a muted mic) from speech
        private set

    fun start() {
        val out = File(context.cacheDir, "dictation.ogg").also { it.delete() }
        val r = (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            MediaRecorder(context)
        } else {
            // MediaRecorder(Context) was added in API 31; keep Android 10/11 recording supported.
            @Suppress("DEPRECATION")
            MediaRecorder()
        }).apply {
            setAudioSource(MediaRecorder.AudioSource.VOICE_RECOGNITION) // no AGC pumping, tuned for speech
            setOutputFormat(MediaRecorder.OutputFormat.OGG)
            setAudioEncoder(MediaRecorder.AudioEncoder.OPUS)
            setAudioSamplingRate(16_000)
            setAudioChannels(1)
            setAudioEncodingBitRate(24_000)
            setOutputFile(out)
            prepare()
            start()
        }
        recorder = r
        file = out
        peak = 0
        startedAt = System.currentTimeMillis()
    }

    /** Current level 0..1 for the waveform (MediaRecorder reports the max amplitude since the last call). */
    fun level(): Float {
        val amp = runCatching { recorder?.maxAmplitude ?: 0 }.getOrDefault(0)
        if (amp > peak) peak = amp
        return ((amp - 300f) / 9000f).coerceIn(0f, 1f).let { Math.pow(it.toDouble(), 0.6).toFloat() }
    }

    val elapsedMs: Long get() = if (recorder == null) 0 else System.currentTimeMillis() - startedAt

    /** Stop and return the encoded audio, or null when it was too short or silent. */
    fun stop(): ByteArray? {
        val r = recorder ?: return null
        recorder = null
        val ok = runCatching { r.stop() }.isSuccess // throws when stopped right after start (no data)
        r.release()
        val bytes = file?.takeIf { ok && it.exists() }?.readBytes()
        file?.delete()
        return bytes
    }

    fun cancel() {
        recorder?.let { runCatching { it.stop() }; it.release() }
        recorder = null
        file?.delete()
    }
}
