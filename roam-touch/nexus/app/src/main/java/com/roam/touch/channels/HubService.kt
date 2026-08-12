package com.roam.touch.channels

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.annotation.RequiresApi
import com.roam.touch.MainActivity
import com.roam.touch.R
import android.util.Log
import kotlinx.coroutines.CoroutineExceptionHandler
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.plus

/**
 * Keeps the hub connection and the voice alive when the panel is not on screen.
 *
 * ★ This is the piece that makes the device a device rather than an app. The two things
 * the wearer asked for — hear the outcome while the screen is off, and never mistake a
 * dead link for a quiet one — both require the socket to survive backgrounding. On
 * Android 10 a foreground service is the only honest way to get that; anything else is
 * doze roulette. The notification it is obliged to post is not a cost, it is the
 * always-visible link indicator.
 */
class HubService : Service() {

    /**
     * ⚠️ The handler is load-bearing, not defensive decoration. An uncaught throw in any
     * child coroutine reaches Android's default handler and kills the process — and the
     * process is the link. A worn device must degrade to a red HUB UNREACHABLE bar, never
     * to nothing at all.
     */
    private val crashGuard = CoroutineExceptionHandler { _, t ->
        Log.e(TAG, "unhandled in service scope", t)
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default + crashGuard)
    private var connection: Job? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        Roam.init(this)
        Roam.device.start()
        startForeground(NOTIFICATION_ID, buildNotification(HubLink.Connecting, 0))

        connection = scope.launch {
            Roam.repository.restore()
            Roam.repository.run(this)
        }

        // Presence: "I am looking at the panel." Registered on foreground, dropped on
        // background, exactly as API.md asks — the bridge reads suppression out of the
        // hub, so none of that logic is duplicated on this side.
        //
        // ⚠️ The heartbeat is launched into the SERVICE scope, not into this collector's,
        // so a state change cannot cancel it half-registered.
        scope.launch {
            Roam.device.appForeground.collect { foreground ->
                Log.i(TAG, "foreground=$foreground screenOn=${Roam.device.screenOn.value}")
                if (foreground) {
                    Roam.repository.startPresence(scope)
                } else {
                    Roam.repository.stopPresence()
                }
            }
        }

        scope.launch { updateNotification() }
    }

    /**
     * ★★ There is deliberately no code here that turns an arriving event into speech.
     *
     * The owner, with the app on the phone while he worked at the laptop: *"channels is
     * reading these messages out loud … I don't want it non stop blabbering at me."*
     * Speech is opt-in per message, from a play control in the thread. If you are adding
     * an automatic path back, you are re-introducing a bug he has already reported.
     */
    private suspend fun updateNotification() {
        Roam.repository.link.collect { link ->
            val unread = Roam.repository.state.value.totalUnread()
            notificationManager().notify(NOTIFICATION_ID, buildNotification(link, unread))
        }
    }

    private fun notificationManager() =
        getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

    private fun buildNotification(link: HubLink, unread: Int): Notification {
        ensureChannel()
        val title = when (link) {
            is HubLink.Online -> if (unread > 0) "ROAM · $unread waiting" else "ROAM · connected"
            is HubLink.Connecting -> "ROAM · connecting"
            is HubLink.Offline -> when (link.reason) {
                OfflineReason.UNAUTHORISED -> "ROAM · HUB REFUSED TOKEN"
                else -> "ROAM · HUB UNREACHABLE"
            }
        }
        val tap = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_ID)
        } else {
            @Suppress("DEPRECATION") Notification.Builder(this)
        }
        return builder
            .setContentTitle(title)
            .setContentText(
                when (link) {
                    is HubLink.Offline -> "nothing is arriving — this is not silence"
                    else -> "channels"
                }
            )
            .setSmallIcon(R.drawable.ic_roam_status)
            .setOngoing(true)
            .setContentIntent(tap)
            .build()
    }

    @RequiresApi(Build.VERSION_CODES.O)
    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val existing = notificationManager().getNotificationChannel(CHANNEL_ID)
        if (existing != null) return
        notificationManager().createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "ROAM link", NotificationManager.IMPORTANCE_LOW)
                .apply { setShowBadge(false) }
        )
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

    override fun onDestroy() {
        connection?.cancel()
        scope.cancel()
        Roam.speaker.stop()
        Roam.device.stop()
        super.onDestroy()
    }

    companion object {
        private const val TAG = "RoamChannels"
        private const val CHANNEL_ID = "roam-link"
        private const val NOTIFICATION_ID = 42

        fun start(context: Context) {
            val intent = Intent(context, HubService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }
    }
}
