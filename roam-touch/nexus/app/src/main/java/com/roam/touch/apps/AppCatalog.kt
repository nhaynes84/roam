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

    /**
     * The shelf, resolved against this device — what is installed, and what the hardware
     * can actually do. Both questions are asked of the system; neither is assumed.
     */
    fun shelf(context: Context): List<AppTile> =
        AppShelf.build(installed(context), hasTorch = Torch.available(context))

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

    /**
     * Fire a tile. The one place that knows how each [TileKind] is opened — and by now it
     * knows about exactly one of them.
     *
     * ⚠️⚠️ **There is deliberately no "open a URL" function here any more.** It fired
     * `ACTION_VIEW` and let the system hand the URL to Chrome, which is how the Files tile
     * came back *"bearer token required"*: the hub wants a bearer token and the only way
     * to give an external browser one is to write it into the URL, where it lands in
     * history, in the omnibox and in logs — and that token opens every endpoint on the
     * hub. [TileKind.HUB] tiles are now drawn by this app, which can put the token in a
     * header. Removing the function rather than leaving it unused is the point: an
     * ACTION_VIEW that does not exist cannot be reached for by the next tile.
     *
     * [TileKind.INTERNAL] and [TileKind.HUB] are both events inside this app rather than
     * intents, so the caller owns them. Returning false for them would read as a failure;
     * it is simply not this object's job.
     */
    fun open(context: Context, tile: AppTile): Boolean = when (tile.kind) {
        TileKind.PACKAGE -> launch(context, tile.id)
        TileKind.INTERNAL, TileKind.HUB -> false
    }
}
