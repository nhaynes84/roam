package com.roam.touch.channels.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.getUnclippedBoundsInRoot
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.unit.width
import com.roam.touch.channels.BatteryState
import com.roam.touch.channels.ChannelsState
import com.roam.touch.channels.Fx
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * ★★ How many tiles fit across, in the pane the shelf is actually drawn in.
 *
 * Owner, 2026-08-15: *"let's also make the apps 3 or 4 to a row instead of two, it's a real
 * scroll problem right now."* Two abreast turned a twelve-tile shelf into six rows in a
 * pane that shows two of them, and the shelf is the only route off the home screen.
 *
 * ⚠️ The rail is rendered here on purpose. [AppsScreen] never sees the window — it sees
 * what is left of it beside the rail — so a test that measured the shelf full-width would
 * be measuring a pane that does not exist, and would keep passing through any change to
 * [NavRail]'s width.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [29])
class AppsScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private var haOpens = 0

    /** The shelf, in the content pane, exactly as [ChannelsApp] places it. */
    private fun renderShelf(shell: Shell) {
        haOpens = 0
        compose.setContent {
            RoamTheme {
                Row(Modifier.fillMaxSize()) {
                    NavRail(
                        shell = shell,
                        state = ChannelsState(),
                        battery = BatteryState(percent = 72),
                        nowMs = Fx.NOW_MS,
                        screen = Screen.Apps,
                        openPane = null,
                        sending = false,
                        collapsed = false,
                        onToggleCollapse = {},
                        onNewSession = {},
                        onOpenChannel = {},
                        onHome = {},
                        onOpenApps = {},
                        onOpenSettings = {},
                        onVoice = {},
                        onQuickSend = {},
                    )
                    Box(Modifier.weight(1f).fillMaxSize()) {
                        AppsScreen(
                            onBack = {},
                            onOpenHomeAssistant = { haOpens++ },
                            onOpenHub = { _, _ -> },
                            onMessage = {},
                        )
                    }
                }
            }
        }
    }

    /**
     * Tiles in the top row, and how wide each one came out. The grid only composes what is
     * visible, so the first row is always there to measure.
     */
    private fun topRow(): Pair<Int, Float> {
        val tiles = compose.onAllNodesWithTag(APP_TILE).fetchSemanticsNodes()
        assertTrue("no tiles on the shelf at all", tiles.isNotEmpty())
        val bounds = tiles.indices.map { compose.onAllNodesWithTag(APP_TILE)[it].getUnclippedBoundsInRoot() }
        val top = bounds.minOf { it.top.value }
        val row = bounds.filter { it.top.value == top }
        return row.size to row.minOf { it.width.value }
    }

    /**
     * ★ Three, not two — and three is the answer `Adaptive(150.dp)` gives in the 523 dp the
     * shelf has beside a 184 dp rail. It is asserted as an exact number rather than a floor
     * because both directions are failures: two is the scroll he complained about, and four
     * would mean the minimum tile width has been cut below what a subtitle needs.
     */
    @Test
    @Config(qualifiers = "w731dp-h411dp-land")
    fun `the shelf is three abreast in landscape`() {
        renderShelf(Shell.Wide)
        val (columns, tileWidth) = topRow()
        println("SHELF landscape columns=$columns tile=${tileWidth}dp")
        assertEquals("the shelf is still two abreast", 3, columns)
        // ⚠️ Read at arm's length while walking. A tile narrower than this ellipsises the
        // subtitles ("internet stations", "network drive") that say what a tile opens.
        assertTrue("tiles shrank to ${tileWidth}dp", tileWidth >= 150f)
    }

    /**
     * ⚠️ The same `Adaptive` must not put three cramped tiles in the narrow pane. Portrait
     * keeps the two it always had — that is the whole reason this is a minimum width and
     * not `Fixed(3)`.
     */
    @Test
    @Config(qualifiers = "w411dp-h731dp-port")
    fun `portrait keeps two, because the pane is half the width`() {
        renderShelf(Shell.Narrow)
        val (columns, tileWidth) = topRow()
        println("SHELF portrait columns=$columns tile=${tileWidth}dp")
        assertEquals(2, columns)
        assertTrue("tiles shrank to ${tileWidth}dp", tileWidth >= 150f)
    }

    /**
     * ★★ **Home Assistant is an app, and this is where it lives now.** Owner, 2026-08-15:
     * *"no the main feature is channels, Home is channels, HA is an app, has no business
     * being a main tab."* It was the rail's first destination, behind a house glyph that
     * read as Home — and with `roam.ha.token` unset that destination is the token-setup
     * wizard, which is the screen he meant by *"home … telling me i need a token."*
     *
     * ⚠️ The tile is not optional. Taking HA off the rail is only acceptable because the
     * shelf still opens it in one tap; if this ever fails, the feature is unreachable.
     */
    @Test
    @Config(qualifiers = "w731dp-h411dp-land")
    fun `home assistant is reachable from the shelf, now that it is off the rail`() {
        renderShelf(Shell.Wide)
        compose.onNodeWithText("Home Assistant").assertIsDisplayed()
        compose.onNodeWithText("Home Assistant").performClick()
        assertEquals("the shelf's HA tile did not open it", 1, haOpens)
    }
}
