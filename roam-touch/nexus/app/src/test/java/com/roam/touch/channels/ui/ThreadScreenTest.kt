package com.roam.touch.channels.ui

import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.roam.touch.channels.ChannelReducer
import com.roam.touch.channels.ChannelsState
import com.roam.touch.channels.Fx
import com.roam.touch.channels.model.Event
import com.roam.touch.channels.stt.PttState
import kotlinx.coroutines.flow.MutableStateFlow
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
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

    /** What the card asked to be opened in the reader, if anything. */
    private var readRequest: Event? = null

    /** What the composer's field was last told to hold. */
    private var draft = ""

    /** Canned words the composer asked to send. */
    private val sent = mutableListOf<String>()

    private var draftSends = 0

    private fun render(vararg events: Event, outbox: Outbox? = null) {
        readRequest = null
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
                    onRead = { readRequest = it },
                    onPlay = {},
                    onStopPlaying = {},
                    draft = draft,
                    outbox = outbox,
                    onDraft = { draft = it },
                    onSend = { sent += it },
                    onSendDraft = { draftSends++ },
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

    // -----------------------------------------------------------------------
    // ★★ Long messages. The owner: *"any message over 6 lines doesn't scroll or
    // have expandability, i just can't read it on the phone."*
    // -----------------------------------------------------------------------

    private val longBody = "Done — Andy resolves now. " + "There is a great deal more. ".repeat(80)
    private val cutSummary = longBody.take(279) + "…"

    private fun longAnswer(id: Long = 350) = Fx.event(
        id = id, kind = "outcome", body = longBody, summary = cutSummary,
        chars = longBody.length,
    )

    /**
     * ⚠️ The card must never grow into the wall of text it used to. The list is the
     * glanceable thing; if the body leaks into it, summary-first is dead.
     */
    @Test
    fun `a long answer shows only its summary in the list`() {
        render(longAnswer())
        compose.onAllNodesWithText(longBody, substring = true).assertCountEquals(0)
        compose.onNodeWithText(cutSummary).assertIsDisplayed()
    }

    /** It has to be obvious there is more, and how much. A silent stop is the bug. */
    @Test
    fun `it says how much more there is to read`() {
        render(longAnswer())
        compose.onNodeWithText("READ ALL · ${Format.chars(longBody.length)}").assertIsDisplayed()
    }

    /**
     * ★ Tapping the affordance opens the reader rather than expanding in place — the
     * distinction that keeps the read from being destroyed by the list scrolling.
     */
    @Test
    fun `pressing it asks for the whole message`() {
        render(longAnswer())
        compose.onNodeWithText("READ ALL · ${Format.chars(longBody.length)}").performClick()
        assertEquals(350L, readRequest?.id)
    }

    /** A short message has nothing behind it and must not offer a door to nowhere. */
    @Test
    fun `a short message offers nothing to open`() {
        render(Fx.event(id = 351, kind = "outcome", body = "the suite is green"))
        compose.onAllNodesWithText("READ ALL", substring = true).assertCountEquals(0)
        compose.onNodeWithText("the suite is green").performClick()
        assertNull("a card with nothing behind it must not navigate", readRequest)
    }

    // -- ★★ the composer, while the hub has his words -------------------------

    /**
     * ★★ The typed half of the freeze the owner reported.
     *
     * Tapping a canned chip used to produce **nothing visible at all** — the word left
     * the composer and the only feedback was a toast that arrived when the hub answered.
     * Against a hub that never answered, that was a blank screen for as long as he cared
     * to look at it. Reproduced on the emulator, 105 seconds, 2026-08-12.
     */
    @Test
    fun `a send in flight is on screen, with a clock on it`() {
        render(outbox = Outbox("continue", startedAtMs = Fx.NOW_MS - 4_000))
        compose.onNodeWithText("SENDING · 4s").assertIsDisplayed()
        compose.onNodeWithText("continue").assertIsDisplayed()
    }

    /** Nothing is in flight, so nothing claims to be. */
    @Test
    fun `an idle composer says nothing about sending`() {
        render()
        compose.onAllNodesWithText("SENDING", substring = true).assertCountEquals(0)
    }

    /**
     * ⚠️ One at a time. A second tap on a send that has not come back is a man wondering
     * whether the first worked, and turning that into two prompts in a live agent is a
     * far more expensive mistake than making him wait.
     */
    @Test
    fun `the canned replies are dead while a send is in flight`() {
        render(outbox = Outbox("continue", startedAtMs = Fx.NOW_MS))
        compose.onNodeWithText("YES").performClick()
        assertEquals("a send was already in flight", emptyList<String>(), sent)
    }

    /**
     * ★★ **His words are not the price of a failed send.** The field is fed from above
     * and cleared only when the hub has actually taken them — see
     * [ChannelsViewModel.sendDraft].
     */
    @Test
    fun `the composer shows the words it was given rather than owning them`() {
        draft = "check the roaster temperature"
        render()
        compose.onNodeWithText("check the roaster temperature").assertIsDisplayed()
    }
}
