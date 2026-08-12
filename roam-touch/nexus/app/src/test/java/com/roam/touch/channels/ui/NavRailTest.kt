package com.roam.touch.channels.ui

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithContentDescription
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.roam.touch.channels.BatteryState
import com.roam.touch.channels.ChannelReducer
import com.roam.touch.channels.ChannelsState
import com.roam.touch.channels.Fx
import com.roam.touch.channels.model.Channel
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * ★★ The rail: what it carries, and — more important — what it must not.
 *
 * The bug this replaces was not cosmetic. A `PttBar` sat at the root of the channel list
 * saying **PUSH TO TALK** on a screen where pushing it could not record anything; it only
 * opened a channel. This suite pins both halves of the fix: no microphone outside a
 * thread, and the door that replaced it obeying [VoiceEntry] rather than guessing.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [29])
class NavRailTest {

    @get:Rule
    val compose = createComposeRule()

    private val live = Fx.channel(pane = "%2", label = "◑ live one", live = true)
    private val dead = Fx.channel(pane = "%1", label = "dead one", live = false)

    private var opened: Channel? = null
    private var voicePresses = 0
    private var quickSent: String? = null

    private fun render(
        shell: Shell,
        state: ChannelsState = ChannelsState(channels = listOf(dead, live)),
        openPane: String? = null,
        screen: Screen = Screen.Channels,
    ) {
        opened = null; voicePresses = 0; quickSent = null
        compose.setContent {
            RoamTheme {
                Row(Modifier.fillMaxSize()) {
                    NavRail(
                        shell = shell,
                        state = state,
                        battery = BatteryState(percent = 72),
                        nowMs = Fx.NOW_MS,
                        screen = screen,
                        openPane = openPane,
                        onOpenChannel = { opened = it },
                        onHome = {},
                        onOpenApps = {},
                        onOpenHomeAssistant = {},
                        onOpenControls = {},
                        onVoice = { voicePresses++ },
                        onQuickSend = { quickSent = it },
                    )
                }
            }
        }
    }

    // --- the correctness fix -------------------------------------------------

    /**
     * ⚠️⚠️ The load-bearing assertion in this file. [PttButton]'s recording control
     * announces itself as "push to talk, hold to record"; nothing outside a thread may
     * ever carry it again, in either shape.
     */
    @Test
    fun `there is no recording control in the Wide rail`() {
        render(Shell.Wide)
        compose.onAllNodesWithContentDescription("push to talk, hold to record")
            .assertCountEquals(0)
    }

    /** ⚠️ And none in portrait either — the deleted bar was a bug in both orientations. */
    @Test
    fun `there is no recording control in the Narrow rail`() {
        render(Shell.Narrow)
        compose.onAllNodesWithContentDescription("push to talk, hold to record")
            .assertCountEquals(0)
    }

    /** The door is a door, and it says so — "opens the top live channel", not "hold". */
    @Test
    fun `TALK announces itself as navigation, not as a microphone`() {
        render(Shell.Wide)
        compose.onAllNodesWithContentDescription("talk, opens the top live channel")
            .assertCountEquals(1)
        compose.onNodeWithTag(RAIL_TALK).performClick()
        assertEquals(1, voicePresses)
    }

    /**
     * ⚠️ With a thread open the real microphone is on screen in the composer. A second
     * voice control that only navigates, next to one that records, is the confusion the
     * root PTT bar used to cause — so the door is not drawn.
     */
    @Test
    fun `the TALK door disappears once a channel is open`() {
        render(Shell.Wide, openPane = "%2")
        compose.onAllNodesWithContentDescription("talk, opens the top live channel")
            .assertCountEquals(0)
    }

    @Test
    fun `with nothing to talk to the door is disabled rather than lying about a target`() {
        render(Shell.Wide, state = ChannelsState())
        compose.onAllNodesWithContentDescription("talk, no channels to talk to yet")
            .assertCountEquals(1)
        compose.onNodeWithTag(RAIL_TALK).performClick()
        assertEquals(0, voicePresses)
    }

    // --- the two shapes ------------------------------------------------------

    /** Landscape: the list is chrome, and chrome lives left. */
    @Test
    fun `Wide carries the channel list in the rail`() {
        render(Shell.Wide)
        compose.onNodeWithTag(RAIL_QUEUE).assertIsDisplayed()
        compose.onNodeWithText("◑ live one").performClick()
        assertEquals("%2", opened?.paneId)
    }

    /**
     * Portrait: the rail collapses instead of the tree forking. The list keeps the
     * content pane to itself, and the destinations stay reachable as short words.
     */
    @Test
    fun `Narrow collapses the rail and leaves the list to the content pane`() {
        render(Shell.Narrow)
        assertTrue(compose.onAllNodesWithText("HOME ASSISTANT").fetchSemanticsNodes().isEmpty())
        assertTrue(compose.onAllNodesWithTag(RAIL_QUEUE).fetchSemanticsNodes().isEmpty())
        compose.onNodeWithText("HA").assertIsDisplayed()
        compose.onNodeWithText("CH").assertIsDisplayed()
    }

    /** The rail is on screen on every screen — that is what makes it the way back. */
    @Test
    fun `the rail is present on a detour, not just on Channels`() {
        render(Shell.Wide, screen = Screen.HomeAssistant)
        compose.onNodeWithTag(RAIL).assertIsDisplayed()
        compose.onNodeWithText("CHANNELS").assertIsDisplayed()
    }

    // --- what came left with the list ----------------------------------------

    /**
     * ★ The canned replies moved into the rail in Wide so the composer is one row. They
     * are relocated, not deleted: these five words are what he actually sends from a
     * corridor.
     */
    @Test
    fun `Wide puts the canned replies in the rail`() {
        render(Shell.Wide, openPane = "%2")
        compose.onNodeWithText("CONTINUE").performClick()
        assertEquals("continue", quickSent)
    }

    /** They act on the open channel, so like the mic they exist only while there is one. */
    @Test
    fun `the canned replies are absent with no channel open`() {
        render(Shell.Wide, openPane = null)
        assertTrue(compose.onAllNodesWithText("CONTINUE").fetchSemanticsNodes().isEmpty())
    }

    /** ⚠️ A dead pane cannot be typed into, and the rail must not pretend otherwise. */
    @Test
    fun `a canned reply into a dead pane does nothing`() {
        render(Shell.Wide, openPane = "%1")
        compose.onNodeWithText("CONTINUE").performClick()
        assertNull(quickSent)
    }

    /**
     * The unread count follows the chrome left. It is the one number that has to be
     * legible from a screen that is not Channels at all.
     */
    @Test
    fun `the unread badge is on the Narrow rail even with no list in it`() {
        render(Shell.Narrow, state = withOneUnread())
        compose.onAllNodesWithContentDescription("1 unread").assertCountEquals(1)
    }

    /** In Wide it is on the rail header *and* on the row that owns it. */
    @Test
    fun `the unread badge is on the Wide rail header and on its channel`() {
        render(Shell.Wide, state = withOneUnread())
        compose.onAllNodesWithContentDescription("1 unread").assertCountEquals(2)
    }

    private fun withOneUnread() = ChannelReducer.applyEvent(
        ChannelsState(channels = listOf(dead, live)),
        Fx.event(id = 900, pane = "%2", kind = "outcome"),
    )
}
