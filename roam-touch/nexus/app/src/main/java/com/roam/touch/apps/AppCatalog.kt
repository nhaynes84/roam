package com.roam.touch.apps

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.drawable.Drawable
import android.util.Log

/** Same tag the rest of Nexus logs under, so `roam-emu logcat` catches it unchanged. */
private const val TAG = "RoamNexus"

/**
 * The Android half of the shelf: ask the system what is installed and how to start it.
 *
 * ⚠️ Launching is done with [PackageManager.getLaunchIntentForPackage] and never with a
 * hard-coded `ComponentName`. Termux, Tailscale and Settings all rename their launcher
 * activity between versions; a component name recorded here would rot silently and the
 * tile would fail with an ActivityNotFoundException on a device with no other way out.
 */
object AppCatalog {

    /**
     * Everything launchable, as the system sees it right now. [AppShelf.build] then
     * decides which few of these earn a tile.
     */
    fun installed(context: Context): List<InstalledApp> {
        val pm = context.packageManager
        val main = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        return pm.queryIntentActivities(main, 0).mapNotNull { info ->
            val activity = info.activityInfo ?: return@mapNotNull null
            InstalledApp(
                packageId = activity.packageName,
                label = info.loadLabel(pm).toString().ifBlank { activity.packageName },
            )
        }.distinctBy { it.packageId }
    }

    /** The shelf, resolved against this device. */
    fun shelf(context: Context): List<AppTile> = AppShelf.build(installed(context))

    fun icon(context: Context, packageId: String): Drawable? =
        runCatching { context.packageManager.getApplicationIcon(packageId) }.getOrNull()

    /**
     * Start an app.
     *
     * Returns false rather than throwing: the caller is the home screen, and a home
     * screen that crashes on a stale tile leaves a device-owner phone with no UI at all.
     */
    fun launch(context: Context, packageId: String): Boolean {
        val intent = context.packageManager.getLaunchIntentForPackage(packageId)
        if (intent == null) {
            Log.w(TAG, "no launch intent for $packageId")
            return false
        }
        // FLAG_ACTIVITY_NEW_TASK: the launched app gets its own task, so Back and Home
        // both return here instead of unwinding through the launcher's task.
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        return runCatching { context.startActivity(intent); true }
            .onFailure { Log.w(TAG, "launch failed: $packageId", it) }
            .getOrDefault(false)
    }
}
