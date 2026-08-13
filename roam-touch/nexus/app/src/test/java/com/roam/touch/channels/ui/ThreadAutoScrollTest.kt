package com.roam.touch.channels.ui

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipeDown
import com.roam.touch.channels.ChannelReducer
import com.roam.touch.channels.ChannelsState
import com.roam.touch.channels.Fx
import com.roam.touch.channels.model.Event
import com.roam.touch.channels.stt.PttState
import kotlinx.coroutines.flow.MutableStateFlow
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * ★★ Where the thread is looking, which is the thing he actually complained about.
 *
 * Owner, 2026-08-12: *"when i enter and receive messages, it doesn't autoscroll to the
 * latest message, bad experience."*
 *
 * [ThreadFollowTest] pins the rule; this pins the **wiring**, because the rule was never
 * the part that was wrong. The old code asked the layout "is the bottom of the last card
 * on screen", and on this device the last card is an answer several windows tall — so on
 * a freshly opened thread the answer was *no*, the panel concluded he had scrolled away,
 * and every message after that queued up behind NEW BELOW. Nothing about that is visible
 * in a pure test of the rule, and nothing about it is visible in the shape of the code.
 *
 * ⚠️ Rendered at sailfish's real landscape window. A test viewport tall enough to hold a
 * whole answer cannot reproduce any of this.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [29], qualifiers = "w731dp-h411dp-land")
class ThreadAutoScrollTest {

    @get:Rule
    val compose = createComposeRule()

    private val channel = Fx.channel(pane = "%0", label = "◑ Roam Touch rebuild", live = true)

    /**
     * Answers the size the hub actually delivers — several windows of text each. That is
     * what makes "the last card is fully on screen" false on arrival, and it is the whole
     * bug.
     */
    private fun answer(n: Long) = Fx.event(
        id = n,
        kind = "outcome",
        body = "answer $n. " + "the send simply had no end, and the read timer kept " +
            "resetting with every byte the hub trickled out. ".repeat(6),
        summary = "answer $n",
    )

    private var state by mutableStateOf(ChannelsState(channels = listOf(channel)))

    private fun deliver(vararg events: Event) {
        state = events.fold(state) { acc, e -> ChannelReducer.applyEvent(acc, e) }
        compose.waitForIdle()
    }

    /** Opens the thread with [count] answers already in it, exactly as [ChannelsApp] does. */
    private fun open(count: Int = 12) {
        state = (1L..count).fold(ChannelsState(channels = listOf(channel))) { acc, i ->
            ChannelReducer.applyEvent(acc, answer(i))
        }
        compose.setContent {
            RoamTheme {
                ThreadScreen(
                    shell = Shell.Wide,
                    state = state,
                    channel = channel,
                    nowMs = Fx.NOW_MS,
                    speakingEventId = null,
                    pttState = PttState.Idle,
                    pttLevel = MutableStateFlow(-120.0),
                    onBack = {},
                    onRead = {},
                    onPlay = {},
                    onStopPlaying = {},
                    draft = "",
                    outbox = null,
                    onDraft = {},
                    onSend = {},
                    onSendDraft = {},
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
        compose.waitForIdle()
    }

    private fun onScreen(summary: String) =
        compose.onAllNodesWithText(summary, substring = true).fetchSemanticsNodes().isNotEmpty()

    private fun assertNoNewBelow() =
        compose.onAllNodesWithText("NEW BELOW ↓").assertCountEquals(0)

    // --- moment one: entering ------------------------------------------------

    /** ★ *"when i enter … it doesn't autoscroll to the latest message."* Now it does. */
    @Test
    fun `opening a thread lands on the newest message`() {
        open(count = 12)
        assertTrue("the newest answer is not on screen", onScreen("answer 12"))
        assertTrue("it opened on the top of the history", !onScreen("answer 1."))
    }

    /**
     * ⚠️⚠️ The regression that made the whole thing look broken: arriving at the top of an
     * answer taller than the window is *not* "he scrolled away", and the panel must not
     * greet him with NEW BELOW over the message it just took him to.
     */
    @Test
    fun `opening a tall thread does not announce the message it is already showing`() {
        open(count = 12)
        assertNoNewBelow()
    }

    // --- moment two: receiving -----------------------------------------------

    /** ★ *"…and receive messages."* He has touched nothing, so the answer comes to him. */
    @Test
    fun `an answer arriving while he has not touched the list comes into view`() {
        open(count = 12)
        deliver(answer(13))
        assertTrue("the answer that just landed is not on screen", onScreen("answer 13"))
        assertNoNewBelow()
    }

    /**
     * ⚠️⚠️ The opposite bug, and the worse one: he scrolled up on purpose, so the arrival
     * must not move the text he is mid-sentence on. It announces itself instead.
     */
    @Test
    fun `an answer arriving after he scrolls up does not move him`() {
        open(count = 12)
        compose.onNodeWithTag(MESSAGES).performTouchInput { swipeDown() }
        compose.waitForIdle()
        deliver(answer(13))
        compose.onNodeWithText("NEW BELOW ↓").assertIsDisplayed()
        assertTrue("it pulled him to the new answer anyway", !onScreen("answer 13"))
    }

    /**
     * ⚠️ Pressing the chip hands control back — and the chip has to *go*. It used to
     * survive its own press, because a long answer is not "at its own end" the moment you
     * arrive at the top of it.
     */
    @Test
    fun `pressing NEW BELOW takes him there and the chip goes with him`() {
        open(count = 12)
        compose.onNodeWithTag(MESSAGES).performTouchInput { swipeDown() }
        compose.waitForIdle()
        deliver(answer(13))
        compose.onNodeWithText("NEW BELOW ↓").performClick()
        compose.waitForIdle()
        assertTrue("the newest answer is still not on screen", onScreen("answer 13"))
        assertNoNewBelow()
    }

    /**
     * ⚠️⚠️ History hydrating **underneath** him. The socket delivers the tail and
     * `GET /thread` delivers the backlog, so a busy channel opens on two events and then
     * grows by thirty rows *above* them: the last id never changes, and the index that
     * meant "the bottom" quietly starts meaning "near the top". He is left stranded in
     * the middle of a thread he just opened, which is what *"doesn't autoscroll to the
     * latest message"* looks like on the channels he actually uses.
     */
    @Test
    fun `history arriving underneath keeps him pinned to the newest message`() {
        open(count = 2)
        // ⚠️ Prepending, not appending: these ids sort *before* everything on screen, so
        // the newest entry is unchanged and only the list's length moves.
        deliver(*(-30L..-1L).map { answer(it) }.toTypedArray())
        assertTrue("history pushed him off the newest message", onScreen("answer 2"))
        assertNoNewBelow()
    }
}
