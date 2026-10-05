package app.localtypeless.android

import android.Manifest
import android.content.ActivityNotFoundException
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import android.text.TextUtils

/** Everything the app needs from the system, checked the same way by the guide, Today and Settings. */
object Health {
    enum class Issue { KEY, MIC, SERVICE_OFF, SERVICE_STOPPED, NOTIFICATIONS, BATTERY }

    fun mic(ctx: Context) = ctx.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    fun notifications(ctx: Context) = Build.VERSION.SDK_INT < 33 ||
        ctx.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    /**
     * Switched on in Settings -> Accessibility (or running, which settles it). The setting may hold the short form
     * "pkg/.Service" (the Settings UI) or the full one "pkg/pkg.Service" (adb), so entries are compared as
     * components, not strings: the string compare said "off" on a Xiaomi where the service was working.
     */
    fun serviceEnabled(ctx: Context): Boolean {
        if (serviceRunning()) return true
        val me = ComponentName(ctx, VoiceAccessibilityService::class.java)
        val enabled = Settings.Secure.getString(ctx.contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES) ?: return false
        return TextUtils.SimpleStringSplitter(':').apply { setString(enabled) }
            .any { ComponentName.unflattenFromString(it.trim()) == me }
    }

    /** Actually running. HyperOS can unbind a switched-on service in the background: the switch still says on. */
    fun serviceRunning() = VoiceAccessibilityService.running.value

    fun batteryUnrestricted(ctx: Context) =
        ctx.getSystemService(PowerManager::class.java).isIgnoringBatteryOptimizations(ctx.packageName)

    val isXiaomi: Boolean get() = Build.MANUFACTURER.equals("Xiaomi", ignoreCase = true) ||
        Build.BRAND.lowercase() in setOf("xiaomi", "redmi", "poco")

    /** What stands between the user and dictating, most blocking first. */
    fun issues(ctx: Context, prefs: Prefs): List<Issue> = buildList {
        if (prefs.apiKey == null) add(Issue.KEY)
        if (!mic(ctx)) add(Issue.MIC)
        if (!serviceEnabled(ctx)) add(Issue.SERVICE_OFF)
        else if (!serviceRunning()) add(Issue.SERVICE_STOPPED)
        if (!notifications(ctx)) add(Issue.NOTIFICATIONS)
        if (!batteryUnrestricted(ctx)) add(Issue.BATTERY)
    }

    // --- places in system settings --------------------------------------------------------------

    fun openAccessibility(ctx: Context) = start(ctx, Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))

    /** App info: where "Allow restricted settings" lives for sideloaded apps (Android 13+). */
    fun openAppInfo(ctx: Context) =
        start(ctx, Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${ctx.packageName}")))

    fun requestBattery(ctx: Context) {
        if (!start(ctx, Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:${ctx.packageName}")))) {
            start(ctx, Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
        }
    }

    fun openAutostart(ctx: Context) {
        val miui = Intent().setComponent(ComponentName("com.miui.securitycenter", "com.miui.permcenter.autostart.AutoStartManagementActivity"))
        if (!start(ctx, miui)) openAppInfo(ctx)
    }

    fun openNotificationSettings(ctx: Context) =
        start(ctx, Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, ctx.packageName))

    fun openUrl(ctx: Context, url: String) = start(ctx, Intent(Intent.ACTION_VIEW, Uri.parse(url)))

    private fun start(ctx: Context, intent: Intent): Boolean = try {
        if (ctx !is android.app.Activity) intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        ctx.startActivity(intent)
        true
    } catch (e: ActivityNotFoundException) {
        false
    } catch (e: SecurityException) {
        false
    }
}
