package app.localtypeless.android

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import app.localtypeless.core.Settings
import org.json.JSONArray
import org.json.JSONObject
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Settings and history in private storage. The OpenRouter key is encrypted with a key that never leaves the
 * Android Keystore, so a copy of the app's files is not enough to read it.
 */
class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("settings", Context.MODE_PRIVATE)

    /**
     * Debug builds only: files/dev.json can point the app at a mock OpenRouter with a test key, so the emulator
     * runs the whole flow without anyone's real key (tools/android_mock_openrouter.py). Written with `run-as`.
     */
    private val dev: JSONObject? = if (BuildConfig.DEBUG) {
        runCatching { JSONObject(java.io.File(context.filesDir, "dev.json").readText()) }.getOrNull()
    } else null

    val apiBase: String get() = dev?.optString("api_base")?.takeIf { it.isNotBlank() } ?: "https://openrouter.ai/api/v1"

    var apiKey: String?
        get() = dev?.optString("api_key")?.takeIf { it.isNotBlank() } ?: sp.getString("api_key", null)?.let(::decrypt)
        set(value) = sp.edit().apply { if (value.isNullOrBlank()) remove("api_key") else putString("api_key", encrypt(value.trim())) }.apply()

    var translateTarget: String
        get() = sp.getString("translate_target", "English")!!
        set(value) = sp.edit().putString("translate_target", value).apply()

    var dictionary: List<String>
        get() = sp.getString("dictionary", "")!!.split('\n').filter { it.isNotBlank() }
        set(value) = sp.edit().putString("dictionary", value.joinToString("\n")).apply()

    /** Which screen edge the handle sits on, and how far down (0..1 of the usable height). */
    var handleRight: Boolean
        get() = sp.getBoolean("handle_right", true)
        set(value) = sp.edit().putBoolean("handle_right", value).apply()

    // Kept in the upper ~60 %: the handle shows while a keyboard is usually up, and the accessibility overlay
    // draws above the keyboard, so a low handle would sit on its keys.
    var handleY: Float
        get() = sp.getFloat("handle_y", 0.42f).coerceIn(0.08f, 0.6f)
        set(value) = sp.edit().putFloat("handle_y", value.coerceIn(0.08f, 0.6f)).apply()

    /** Developer switch: use files/test-audio.ogg instead of the microphone (emulator and automated tests). */
    var useTestAudio: Boolean
        get() = BuildConfig.DEBUG && (dev?.optBoolean("use_test_audio") == true || sp.getBoolean("use_test_audio", false))
        set(value) = sp.edit().putBoolean("use_test_audio", value).apply()

    var haptics: Boolean
        get() = sp.getBoolean("haptics", true)
        set(value) = sp.edit().putBoolean("haptics", value).apply()

    fun settings() = Settings(translateTargets = listOf(translateTarget), dictionary = dictionary)

    /** History retention: "forever", "30", "7", "1" (days) or "never" (Typeless offers the same kind of choice). */
    var keep: String
        get() = sp.getString("keep", "forever")!!
        set(value) = sp.edit().putString("keep", value).apply()

    val keepDays: Int? get() = keep.toIntOrNull()

    /** The first-run guide was finished (or skipped). */
    var onboarded: Boolean
        get() = sp.getBoolean("onboarded", false)
        set(value) = sp.edit().putBoolean("onboarded", value).apply()

    /** Where the first-run guide was, so it survives the process being killed mid-guide (HyperOS force-stops
     *  the app when autostart is changed). */
    var guideStep: String?
        get() = sp.getString("guide_step", null)
        set(value) = sp.edit().apply { if (value == null) remove("guide_step") else putString("guide_step", value) }.apply()

    /** Version 0.1 kept history as JSON in these preferences; hand it to [Store] once. */
    fun migrateHistory(store: Store) {
        val json = sp.getString("history", null) ?: return
        runCatching {
            val arr = JSONArray(json)
            for (i in arr.length() - 1 downTo 0) {
                val o = arr.getJSONObject(i)
                store.add(o.getLong("t"), o.getString("m"), o.optString("a"), o.getString("x"), o.optString("r"),
                    o.optDouble("c", 0.0), 0.0, keepEntry = true)
            }
        }
        sp.edit().remove("history").apply()
    }

    // --- Keystore encryption --------------------------------------------------------------------

    private fun secretKey(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getEntry(ALIAS, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build()
        )
        return generator.generateKey()
    }

    private fun encrypt(plain: String): String {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, secretKey()) }
        val out = cipher.iv + cipher.doFinal(plain.toByteArray())
        return Base64.encodeToString(out, Base64.NO_WRAP)
    }

    private fun decrypt(stored: String): String? = runCatching {
        val raw = Base64.decode(stored, Base64.NO_WRAP)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, secretKey(), GCMParameterSpec(128, raw, 0, 12))
        String(cipher.doFinal(raw, 12, raw.size - 12))
    }.getOrNull()

    companion object {
        private const val ALIAS = "openrouter_key"
    }
}
