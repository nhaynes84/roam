package com.roam.touch.channels.ui

import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import com.roam.touch.channels.ChannelReducer
import com.roam.touch.channels.ChannelsState
import com.roam.touch.channels.Fx
import com.roam.touch.channels.model.Event
import com.roam.touch.channels.stt.PttState
import kotlinx.coroutines.flow.MutableStateFlow
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * ★★ What the thread actually puts on the glass, for the one thing he says.
 *
 * ⚠️ This substitutes for the test nobody may run: pressing the mic records his living
 * room. So the states after a successful send are driven straight from ledger shapes
 * captured off the hub on 2026-08-12 — the very events that produced the double render.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [29])
class ThreadScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val channel = Fx.channel(pane = "%0", label = "◑ Roam Touch rebuild")

    private val spoken = "Not done yet. Ba-ba-ba-ba-ba-ba-wee-wee."

    private fun render(vararg events: Event) {
        val state = events.fold(ChannelsState(channels = listOf(channel))) { acc, e ->
            ChannelReducer.applyEvent(acc, e)
        }
        compose.setContent {
            RoamTheme {
                ThreadScreen(
                    state = state,
                    channel = channel,
                    nowMs = Fx.NOW_MS,
                    speakingEventId = null,
                    pttState = PttState.Idle,
                    pttLevel = MutableStateFlow(-120.0),
                    onBack = {},
                    onExpand = {},
                    onPlay = {},
                    onStopPlaying = {},
                    onSend = {},
                    onInterrupt = {},
                    onKill = {},
                    onPttPress = {},
                    onPttRelease = {},
                    onPttSend = {},
                    onPttCancel = {},
                    onPttDismiss = {},
                )
            }
        }
    }

    /** The bug, as the owner saw it: ledger 340 `sent` + 341 `receipt`, one utterance. */
    @Test
    fun `a message he sent from ROAM is drawn once, not twice`() {
        render(
            Fx.event(id = 340, kind = "sent", body = spoken),
            Fx.event(id = 341, kind = "receipt", body = spoken, echoOf = 340),
        )
        compose.onAllNodesWithText(spoken).assertCountEquals(1)
    }

    /** ★ "Same message, multiple states." */
    @Test
    fun `its status advances from YOU to PROMPT when the agent takes it`() {
        render(Fx.event(id = 340, kind = "sent", body = spoken))
        compose.onNodeWithText("YOU").assertIsDisplayed()
        compose.onAllNodesWithText("PROMPT").assertCountEquals(0)
    }

    @Test
    fun `the echo turns that same entry into PROMPT`() {
        render(
            Fx.event(id = 340, kind = "sent", body = spoken),
            Fx.event(id = 341, kind = "receipt", body = spoken, echoOf = 340),
        )
        compose.onNodeWithText("PROMPT").assertIsDisplayed()
        compose.onAllNodesWithText("YOU").assertCountEquals(0)
    }

    /**
     * ⚠️ The regression that would make the fix worse than the bug: a prompt typed at
     * the keyboard arrives as a receipt with nothing before it, and that receipt is the
     * only record the message exists.
     */
    @Test
    fun `a prompt he typed at the keyboard still shows, exactly once`() {
        render(Fx.event(id = 341, kind = "receipt", body = "run the tests"))
        compose.onAllNodesWithText("run the tests").assertCountEquals(1)
        compose.onNodeWithText("PROMPT").assertIsDisplayed()
    }

    @Test
    fun `the answer is still its own message`() {
        render(
            Fx.event(id = 340, kind = "sent", body = spoken),
            Fx.event(id = 341, kind = "receipt", body = spoken, echoOf = 340),
            Fx.event(id = 342, kind = "outcome", body = "the suite is green"),
        )
        compose.onAllNodesWithText(spoken).assertCountEquals(1)
        compose.onNodeWithText("the suite is green").assertIsDisplayed()
        compose.onNodeWithText("ANSWER").assertIsDisplayed()
    }
}
