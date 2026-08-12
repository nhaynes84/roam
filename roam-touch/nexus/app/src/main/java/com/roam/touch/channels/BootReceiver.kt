package com.roam.touch.channels

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Bring the link back after a reboot, without anyone tapping anything.
 *
 * A worn device that needs its launcher opened before it starts listening is a device
 * that silently misses everything between the reboot and the next time he happens to
 * look at it — which is precisely the failure the visible-offline-state work exists to
 * prevent.
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        HubService.start(context)
    }
}
