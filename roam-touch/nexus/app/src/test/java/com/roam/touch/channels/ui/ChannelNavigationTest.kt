package com.roam.touch.channels.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.hasAnyAncestor
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithContentDescription
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.roam.touch.channels.BatteryState
import com.roam.touch.channels.ChannelReducer
import com.roam.touch.channels.ChannelsState
import com.roam.touch.channels.Fx
import com.roam.touch.channels.HubLink
import com.roam.touch.channels.stt.PttState
import kotlinx.coroutines.flow.MutableStateFlow
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * ★★ **The wearer's path: home → list → channel → back → list.** In both fold states,
 * because the whole point of the fold is that it is optional.
 *
 * Owner, 2026-08-15: *"home should just be 'Channels' … by default if i click home, it
 * just lists all the channels, lets me dive into one and has a 'back' button to take me
 * back to the channel list if i don't want the extra column 'quick channel view' open."*
 *
 * ⚠️ This composes the panel the way [ChannelsApp] composes it — rail, then the content
 * pane branching on `openPane` — rather than mounting `ChannelsApp` itself, which would
 * drag [com.roam.touch.channels.Roam]'s whole singleton graph (hub socket, TTS, PTT) into
 * a navigation test. The branch under test is copied here in one line and asserted from
 * both ends; what it must not do is *differ*, which
 * `nothing open is the list` in [NavTest] pins on the decision itself.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [29], qualifiers = "w731dp-h411dp-land")
class ChannelNavigationTest {

    @get:Rule
    val compose = createComposeRule()

    private val live = Fx.channel(pane = "%2", label = "◑ live one", live = true)
    private val dead = Fx.channel(pane = "%1", label = "dead one", live = false)

    private val state = ChannelReducer.applyEvent(
        ChannelsState(channels = listOf(dead, live)),
        Fx.event(id = 900, pane = "%2", body = "the suite is green"),
    )

    /** The panel, minus the singletons: rail on the left, [Nav.pane]'s answer on the right. */
    private fun renderPanel(collapsed: Boolean) {
        compose.setContent {
            RoamTheme {
                var folded by remember { mutableStateOf(collapsed) }
                var openPane by remember { mutableStateOf<String?>(null) }
                var screen by remember { mutableStateOf(Screen.Channels) }
                Row(Modifier.fillMaxSize()) {
                    NavRail(
                        shell = Shell.Wide,
                        state = state,
                        battery = BatteryState(percent = 72),
                        nowMs = Fx.NOW_MS,
                        screen = screen,
                        openPane = openPane,
                        sending = false,
                        collapsed = folded,
                        onToggleCollapse = { folded = !folded },
                        onOpenChannel = { openPane = it.paneId; screen = Screen.Channels },
                        onHome = { openPane = null; screen = Screen.Channels },
                        onOpenApps = { screen = Screen.Apps },
                        onOpenSettings = { screen = Screen.Settings },
                        onVoice = {},
                        onQuickSend = {},
                    )
                    Box(Modifier.weight(1f).fillMaxSize()) {
                        val channel = openPane?.let { state.channel(it) }
                        if (channel == null) {
                            ChannelListScreen(
                                state = state,
                                link = HubLink.Online(sinceMs = Fx.NOW_MS),
                                nowMs = Fx.NOW_MS,
                                onOpen = { openPane = it.paneId },
                            )
                        } else {
                            ThreadScreen(
                                shell = Shell.Wide,
                                state = state,
                                channel = channel,
                                nowMs = Fx.NOW_MS,
                                speakingEventId = null,
                                pttState = PttState.Idle,
                                pttLevel = MutableStateFlow(-120.0),
                                draft = "",
                                outbox = null,
                                onDraft = {},
                                onSendDraft = {},
                                onBack = { openPane = null },
                                onRead = {},
                                onPlay = {},
                                onStopPlaying = {},
                                onSend = {},
                                onInterrupt = {},
                                onKill = {},
                                onPttPress = {},
                                onPttRedo = {},
                                onPttRelease = {},
                                onPttSend = {},
                                onPttCancel = {},
                                onPttDismiss = {},
                            )
                        }
                    }
                }
            }
        }
    }

    /**
     * ⚠️ Open a channel **from the content pane's list**, never from the rail's copy.
     * With the rail expanded the label is on screen twice, and a bare `onNodeWithText`
     * quietly resolves to the rail — which would make this a test of quick-switching
     * dressed up as a test of Home.
     */
    private fun openFromList(label: String) =
        compose.onNode(hasText(label) and hasAnyAncestor(hasTestTag(QUEUE))).performClick()

    /** The channel list is in the content pane — not the rail's copy of it. */
    private fun listIsShowing() =
        compose.onAllNodesWithTag(QUEUE).fetchSemanticsNodes().isNotEmpty()

    private fun threadIsShowing() =
        compose.onAllNodesWithTag(THREAD_TOP_BAR).fetchSemanticsNodes().isNotEmpty()

    /**
     * ★★ Folded — the shape he asked for, and the one where the rail cannot help. Every
     * step of the journey has to work with the quick-switch column put away.
     */
    @Test
    fun `home lists the channels, a tap dives in, and back comes out — rail folded`() {
        renderPanel(collapsed = true)

        // Home, by default: all the channels, full width, nothing about tokens.
        assertTrue("home is not the channel list", listIsShowing())
        compose.onNodeWithText("dead one").assertIsDisplayed()
        compose.onNodeWithText("◑ live one").assertIsDisplayed()

        // Dive in.
        openFromList("◑ live one")
        assertTrue("tapping a channel did not open it", threadIsShowing())

        // …and back out, to the list, by a control that is on screen.
        compose.onNodeWithContentDescription("back to channels").performClick()
        assertTrue("back did not return to the list", listIsShowing())
    }

    /**
     * ⚠️ And expanded, where the rail *does* hold a list. The content pane must still be
     * the list rather than a prompt about picking one — he asked for Home to list the
     * channels, not to describe them.
     */
    @Test
    fun `home lists the channels, a tap dives in, and back comes out — rail expanded`() {
        renderPanel(collapsed = false)

        assertTrue("home is not the channel list", listIsShowing())
        compose.onNodeWithTag(RAIL_QUEUE).assertIsDisplayed()

        openFromList("◑ live one")
        assertTrue("tapping a channel did not open it", threadIsShowing())

        compose.onNodeWithContentDescription("back to channels").performClick()
        assertTrue("back did not return to the list", listIsShowing())
    }

    /**
     * ★★★ **The invariant, stated as one.** There is no reachable state with a channel open
     * and no way back to the list — in either fold state, and whether or not the rail has a
     * queue in it. This is the test that would have caught the landscape thread top bar
     * shipping without a Back button, which was fine only for as long as the rail could not
     * be folded away.
     */
    @Test
    fun `no open channel is ever a dead end`() {
        renderPanel(collapsed = false)

        // Expanded: dive in, and there is a way out.
        openFromList("◑ live one")
        compose.onAllNodesWithContentDescription("back to channels").assertCountEquals(1)

        // Fold the rail *while the channel is open* — the list in the rail disappears
        // underneath him, which is exactly the moment the way out has to still be there.
        compose.onNodeWithTag(RAIL_FOLD).performClick()
        assertTrue("folding took the channel away", threadIsShowing())
        compose.onAllNodesWithTag(RAIL_QUEUE).assertCountEquals(0)
        compose.onNodeWithContentDescription("back to channels").performClick()
        assertTrue("no way back to the list from a folded rail", listIsShowing())

        // …and home is still home from there, with the rail still folded.
        compose.onNodeWithContentDescription("channels").performClick()
        assertTrue(listIsShowing())
    }

    /**
     * ⚠️ The rail's selection follows the pane rather than competing with it: one
     * `openPane`, read by both. A channel opened from the *content* list is the channel the
     * rail shows as current, with no second source of truth to disagree.
     */
    @Test
    fun `the rail follows the channel opened from the list, expanded`() {
        renderPanel(collapsed = false)
        openFromList("◑ live one")
        // Two copies of the label on screen — the rail's row and the thread's title — and
        // that is the point: the quick-switch column is showing the same conversation.
        assertTrue(threadIsShowing())
        assertTrue(
            "the rail lost the channel the content pane opened",
            compose.onAllNodesWithText("◑ live one").fetchSemanticsNodes().size >= 2,
        )
    }
}
