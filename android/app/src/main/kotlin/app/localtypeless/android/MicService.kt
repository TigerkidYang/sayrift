package app.localtypeless.android

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.IBinder
import android.util.Log

/**
 * Holds the "foreground, using the microphone" state Android requires before a backgrounded app may record
 * (while-in-use permission). It is started from the user's tap on our overlay and stopped as soon as the
 * recording ends; the recording itself is done by [Dictation].
 */
class MicService : Service() {
    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_CANCEL) { // "停止" on the notification: works even if the overlay is gone
            Dictation.cancel()
            return START_NOT_STICKY
        }
        if (intent?.action == ACTION_STOP) {
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
            return START_NOT_STICKY
        }
        try {
            startForeground(ID, notification(this), ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
            Dictation.onMicForeground(true)
        } catch (e: Exception) { // ForegroundServiceStartNotAllowedException / SecurityException on some ROMs
            Log.w(TAG, "could not enter the foreground for the microphone", e)
            Dictation.onMicForeground(false)
            stopSelf()
        }
        return START_NOT_STICKY
    }

    companion object {
        private const val TAG = "MicService"
        private const val ID = 7
        private const val CHANNEL = "dictation" // Stable across renames to retain notification preferences.
        private const val ACTION_STOP = "stop"
        private const val ACTION_CANCEL = "cancel"

        fun start(context: Context) {
            context.startForegroundService(Intent(context, MicService::class.java))
        }

        fun stop(context: Context) {
            runCatching { context.startService(Intent(context, MicService::class.java).setAction(ACTION_STOP)) }
        }

        private fun notification(context: Context): Notification {
            val nm = context.getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL, "正在听写", NotificationManager.IMPORTANCE_LOW).apply {
                    description = "说话时显示，说完即消失"
                    setShowBadge(false)
                }
            )
            return Notification.Builder(context, CHANNEL)
                .setSmallIcon(R.drawable.ic_mic)
                .setContentTitle("${context.getString(R.string.app_name)} · 正在听你说话")
                .setContentText("点屏幕边缘胶囊上的 ✓ 结束")
                .setOngoing(true)
                .addAction(Notification.Action.Builder(null, "停止",
                    android.app.PendingIntent.getService(context, 1, Intent(context, MicService::class.java).setAction(ACTION_CANCEL),
                        android.app.PendingIntent.FLAG_IMMUTABLE)).build())
                .build()
        }
    }
}
