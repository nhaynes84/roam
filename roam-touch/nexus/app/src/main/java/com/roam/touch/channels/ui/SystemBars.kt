package com.roam.touch.channels.ui

import android.app.Activity
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat

/**
 * ★★ The stock status bar comes off, because this is an appliance and not a phone.
 *
 * The owner, on the battery chip in the nav rail: *"i don't need to see the battery charge
 * unless you're going to hide the notification bar that's always on, which i'm not opposed
 * to."* Two readouts of one number is the complaint; hiding the bar is the version of the
 * fix that also gives something back.
 *
 * ★ **Measured on the API 29 target, 1080 × 1920 at 420 dpi — the same panel as sailfish:**
 * the bar is 63 px = **24 dp**, and the landscape window is 411 dp tall. So it was spending
 * **5.8 % of the window, permanently**, on a carrier label, other apps' notification icons
 * and a second copy of the battery. The app's own content went from 387 dp to 411 dp —
 * **6.2 % more of the axis he reads on**, which is the axis the whole nav-rail layout
 * exists to buy.
 *
 * ⚠️ **What this deliberately does not do.**
 * - It does not hide the navigation bar. Back / home / recents are the escape hatch on a
 *   device-owner phone, and `MainActivity`'s "not a kiosk" rule outranks another 24 dp.
 * - It does not call `setDecorFitsSystemWindows(false)`. Going edge-to-edge would put the
 *   content *under* where the bar was and hand this app an insets problem in exchange for
 *   the same pixels. Hiding the bar without it resizes the window instead, which is the
 *   whole point: the 24 dp arrives as usable height, not as padding.
 * - It does not take the notification shade away. [BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE]
 *   means a swipe from the top edge still brings the bar back, transiently, and the shade
 *   with it. Nothing about notifications, Settings or the "unfuck it" path changes.
 *
 * ⚠️ **Sticky, and re-applied on focus, on purpose.** Anything that takes the window's
 * focus — the shade, a permission dialog, Settings — hands it back with the flags cleared,
 * and a status bar that reappeared once and stayed is exactly the state the owner is
 * objecting to. `MainActivity.onWindowFocusChanged` calls this again every time.
 *
 * ⚠️ The two things the bar was carrying that actually matter on a worn device — the
 * charge and **the clock** — are the app's job now. See `RailStatus`. Deleting this call
 * without deleting that row is fine; the reverse is not.
 */
object SystemBars {

    /**
     * Hide the status bar for [activity], and keep it hidden.
     *
     * Safe to call repeatedly and safe to call before the first composition.
     */
    @JvmStatic
    fun hideStatusBar(activity: Activity) {
        val window = activity.window ?: return
        val controller = WindowCompat.getInsetsController(window, window.decorView)
        // Order matters on API < 30: the behaviour flag is folded into the same
        // systemUiVisibility word that `hide` writes, so setting it afterwards would
        // read a stale value on some vendor builds.
        controller.systemBarsBehavior =
            WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        controller.hide(WindowInsetsCompat.Type.statusBars())
    }
}
