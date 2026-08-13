package com.roam.touch.channels.ui

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipeDown
import com.roam.touch.channels.ChannelReducer
import com.roam.touch.channels.ChannelsState
import com.roam.touch.channels.Fx
import com.roam.touch.channels.stt.PttState
import kotlinx.coroutines.flow.MutableStateFlow
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * ★★ **Where the reader puts him back.**
 *
 * He scrolls up the thread, opens one message in full, and comes back — and the panel
 * used to hand him the newest message instead of the place he left. The reader is drawn
 * *instead of* the thread, not over it, so the thread is disposed: its scroll position
 * went with it, and so did `settled`, which made the thread call itself freshly opened on
 * the way back and jump to the bottom by design.
 *
 * ⚠️ The other half of the rule has to survive intact — a channel he *opens* still opens
 * at the newest message, which is his own complaint from the other direction: *"when i
 * enter and receive messages, it doesn't autoscroll to the latest message, bad
 * experience."* So this pins both: covered keeps the place, closed forgets it.
 *
 * ⚠️ Rendered at sailfish's real landscape window. A viewport tall enough to hold a whole
 * answer cannot reproduce any of it — see [ThreadAutoScrollTest].
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [29], qualifiers = "w731dp-h411dp-land")
class ReaderReturnTest {

    @get:Rule
    val compose = createComposeRule()

    private val channel = Fx.channel(pane = "%0", label = "◑ Roam Touch rebuild", live = true)

    private fun answer(n: Long) = Fx.event(
        id = n,
        kind = "outcome",
        body = "answer $n. " + "the send simply had no end, and the read timer kept " +
                "resetting with every byte the hub trickled out. ".repeat(6),
        summary = "answer $n",
    )

    private val state = (1L..12L).fold(ChannelsState(channels = listOf(channel))) { acc, i ->
        ChannelReducer.applyEvent(acc, answer(i))
    }

    /** True while the reader is up — the content pane swaps, exactly as `ChannelsApp` does. */
    private var reading by mutableStateOf(false)

    /** The channel that is open, so closing and re-opening can be exercised. */
    private var openPane by mutableStateOf<String?>("%0")

    /**
     * The content pane, wired the way [ChannelsApp] wires it: one
     * `SaveableStateHolder`, keyed on the pane, with the thread inside it and the reader
     * drawn in its place.
     */
    private fun render() {
        compose.setContent {
            RoamTheme {
                // ⚠️ The real rule, not a copy of it — see [rememberThreadPlaces].
                val places = rememberThreadPlaces(openPane)
                val pane = openPane
                if (reading) {
                    ReaderScreen(
                        state = state,
                        channel = channel,
                        event = state.thread("%0").first(),
                        speaking = false,
                        onBack = { reading = false },
                        onPlay = {},
                        onStopPlaying = {},
                    )
                } else if (pane != null) {
                    places.SaveableStateProvider(pane) {
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
        compose.waitForIdle()
    }

    private fun onScreen(summary: String) =
        compose.onAllNodesWithText(summary, substring = true).fetchSemanticsNodes().isNotEmpty()

    private fun scrollUp() {
        compose.onNodeWithTag(MESSAGES).performTouchInput { swipeDown() }
        compose.onNodeWithTag(MESSAGES).performTouchInput { swipeDown() }
        compose.waitForIdle()
    }

    /**
     * ★★ **The bug.** Scroll back through the conversation, read one message in full,
     * come back — and be exactly where you were, not dragged to the bottom.
     */
    @Test
    fun `coming back from the reader lands where he left, not on the newest message`() {
        render()
        scrollUp()
        assertTrue("the swipe did not move him off the newest answer", !onScreen("answer 12"))
        val whereHeWas = compose.onAllNodesWithText("answer", substring = true)
            .fetchSemanticsNodes().size

        reading = true
        compose.waitForIdle()
        reading = false
        compose.waitForIdle()

        assertTrue(
            "the reader returned him to the newest message instead of his place",
            !onScreen("answer 12"),
        )
        assertTrue("the thread came back empty", whereHeWas > 0)
    }

    /** ⚠️ And it must not greet him with NEW BELOW over a thread nothing arrived in. */
    @Test
    fun `coming back from the reader announces nothing, because nothing arrived`() {
        render()
        scrollUp()
        reading = true
        compose.waitForIdle()
        reading = false
        compose.waitForIdle()

        compose.onAllNodesWithText("NEW BELOW ↓").assertCountEquals(0)
    }

    /**
     * ⚠️⚠️ **The half that must not break.** Leaving the conversation releases the place,
     * so opening the channel again opens it at the end — his original complaint, and the
     * reason the thread jumps on open in the first place.
     */
    @Test
    fun `leaving the channel and opening it again lands on the newest message`() {
        render()
        scrollUp()
        assertTrue(!onScreen("answer 12"))

        // Closing the pane is what releases the saved place — see `ChannelsApp`.
        openPane = null
        compose.waitForIdle()
        openPane = "%0"
        compose.waitForIdle()

        assertTrue("re-opening the channel did not land on the newest answer", onScreen("answer 12"))
    }
}
