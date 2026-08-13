package com.roam.touch.channels.ui

import android.app.Activity
import android.view.View
import androidx.activity.ComponentActivity
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * ★★ The system status bar comes off, and stays off.
 *
 * Owner: *"i don't need to see the battery charge unless you're going to hide the
 * notification bar that's always on, which i'm not opposed to."* Two readouts of one
 * number was the complaint; this is the half of the fix that gives something back —
 * 24 dp of a 411 dp landscape window, permanently.
 *
 * ⚠️ On API 29 all of this is one `systemUiVisibility` word, which is exactly why it is
 * worth asserting rather than eyeballing: the three flags are set by three different
 * calls into the same integer, and a plausible-looking reordering can drop one silently.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [29])
class SystemBarsTest {

    private fun flags(activity: Activity): Int = activity.window.decorView.systemUiVisibility

    private fun launched(): Activity =
        Robolectric.buildActivity(ComponentActivity::class.java).setup().get()

    @Test
    fun `the status bar is hidden`() {
        val activity = launched()
        SystemBars.hideStatusBar(activity)
        assertTrue(
            "SYSTEM_UI_FLAG_FULLSCREEN is not set",
            flags(activity) and View.SYSTEM_UI_FLAG_FULLSCREEN != 0,
        )
    }

    /**
     * ⚠️⚠️ The escape hatch. `MainActivity`'s standing rule is **not a kiosk**: the shade,
     * Settings and recents stay reachable, because Settings is the "we broke something,
     * unfuck it" path on a device-owner phone that cannot be force-stopped.
     *
     * `IMMERSIVE_STICKY` is what keeps that true with the bar hidden — a swipe from the
     * top edge brings it back transiently, and the shade with it. Hiding the bar *without*
     * it would be the same pixels and a sealed device.
     */
    @Test
    fun `a swipe can still bring the bar and the shade back`() {
        val activity = launched()
        SystemBars.hideStatusBar(activity)
        assertTrue(
            "the bar is hidden without a way to reveal it — that is a kiosk",
            flags(activity) and View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY != 0,
        )
    }

    /**
     * ⚠️ The navigation bar stays. Back / home / recents outrank another 24 dp on a phone
     * this app is the persistent home activity of.
     */
    @Test
    fun `the navigation bar is left alone`() {
        val activity = launched()
        SystemBars.hideStatusBar(activity)
        assertEquals(
            "the navigation bar was hidden too",
            0,
            flags(activity) and View.SYSTEM_UI_FLAG_HIDE_NAVIGATION,
        )
    }

    /**
     * ⚠️ It is called again on every focus gain — the shade, a permission dialog and
     * Settings all hand focus back with the flags cleared — so it has to be idempotent
     * rather than toggling anything.
     */
    @Test
    fun `calling it again after focus comes back changes nothing`() {
        val activity = launched()
        SystemBars.hideStatusBar(activity)
        val once = flags(activity)
        activity.window.decorView.systemUiVisibility = 0
        SystemBars.hideStatusBar(activity)
        assertEquals(once, flags(activity))
    }
}
