package com.roam.touch.apps

import android.content.Context
import android.content.pm.PackageManager
import android.hardware.camera2.CameraAccessException
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.os.Handler
import android.os.Looper
import android.util.Log

/** Same tag the rest of Nexus logs under, so `roam-emu logcat` catches it unchanged. */
private const val TAG = "RoamNexus"

/**
 * ★ The flashlight, which is not an app.
 *
 * Android has never shipped a torch *package* to launch. On this phone it is a
 * quick-settings tile — `settings get secure sysui_qs_tiles` lists `flashlight` — and a
 * SystemUI tile is not something a launcher can start with an intent. So the shelf owns
 * the switch itself: `CameraManager.setTorchMode`, which needs no `CAMERA` permission and
 * no open camera session, only API 23+.
 *
 * ⚠️ Everything here returns a value rather than throwing. `setTorchMode` throws
 * [CameraAccessException] when the camera is in use by something else or the flash is
 * unavailable, and `IllegalArgumentException` if the id it was given has gone away. The
 * caller is the app shelf, which is the only route off a device-owner home screen — the
 * same rule that keeps [AppCatalog.launch] from throwing applies here with more force,
 * because a torch is the sort of thing that gets pressed while the camera app is open.
 */
object Torch {

    /** The tile id. A `roam:` id, so nothing can mistake it for a package or a URL. */
    const val TILE_ID = "roam:torch"

    /**
     * ★ Which camera's flash to drive, asked of the device rather than assumed.
     *
     * ⚠️ **Not `"0"`.** The back camera is usually id 0 and usually the one with the
     * flash, and "usually" is exactly the assumption [AppCatalog] refuses to make about
     * launcher activities: a device where it is not true fails at the tap with nothing to
     * read. Kept as a pure function over the ids so the choice is covered by a plain JVM
     * test instead of needing a camera.
     */
    fun pick(ids: List<String>, hasFlash: (String) -> Boolean): String? =
        ids.firstOrNull { runCatching { hasFlash(it) }.getOrDefault(false) }

    /** Whether this device has a flash at all. Decides whether the tile exists. */
    fun available(context: Context): Boolean =
        context.packageManager.hasSystemFeature(PackageManager.FEATURE_CAMERA_FLASH)

    private fun manager(context: Context): CameraManager? =
        context.getSystemService(Context.CAMERA_SERVICE) as? CameraManager

    /** The first camera id whose characteristics report a flash, or null. */
    fun cameraId(context: Context): String? {
        val cm = manager(context) ?: return null
        return runCatching {
            pick(cm.cameraIdList.toList()) { id ->
                cm.getCameraCharacteristics(id)[CameraCharacteristics.FLASH_INFO_AVAILABLE] == true
            }
        }.onFailure { Log.w(TAG, "could not enumerate cameras", it) }.getOrNull()
    }

    /**
     * Turn the torch on or off. Returns false if it could not be done, having said why in
     * the log — never throws.
     */
    fun set(context: Context, on: Boolean): Boolean {
        val cm = manager(context) ?: return false
        val id = cameraId(context)
        if (id == null) {
            Log.w(TAG, "no camera with a flash")
            return false
        }
        return runCatching { cm.setTorchMode(id, on); true }
            .onFailure { Log.w(TAG, "setTorchMode($on) failed", it) }
            .getOrDefault(false)
    }

    /**
     * ★★ Watch the torch, rather than remembering what we last asked for.
     *
     * ⚠️ The tile has to show the truth, and our own last write is not it: the
     * quick-settings tile, the camera app and any other process can change the torch
     * underneath us, and `setTorchMode` can also be refused *after* returning — the
     * callback is the only thing that knows. A tile that says OFF while the phone is lit
     * up on a worn device is how a battery gets flattened without anyone noticing.
     *
     * Returns a handle to unregister with, or null if there is nothing to watch.
     */
    fun watch(context: Context, onChange: (Boolean) -> Unit): AutoCloseable? {
        val cm = manager(context) ?: return null
        val id = cameraId(context) ?: return null
        val callback = object : CameraManager.TorchCallback() {
            override fun onTorchModeChanged(cameraId: String, enabled: Boolean) {
                if (cameraId == id) onChange(enabled)
            }

            /** The flash went away — treat that as off, because it is not lighting anything. */
            override fun onTorchModeUnavailable(cameraId: String) {
                if (cameraId == id) onChange(false)
            }
        }
        return runCatching {
            cm.registerTorchCallback(callback, Handler(Looper.getMainLooper()))
            AutoCloseable { runCatching { cm.unregisterTorchCallback(callback) } }
        }.onFailure { Log.w(TAG, "could not watch the torch", it) }.getOrNull()
    }
}
