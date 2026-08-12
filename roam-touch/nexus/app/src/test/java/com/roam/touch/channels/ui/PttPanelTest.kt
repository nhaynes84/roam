package com.roam.touch.channels.ui

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.roam.touch.channels.stt.Ptt
import com.roam.touch.channels.stt.PttState
import com.roam.touch.channels.stt.PttTarget
import kotlinx.coroutines.flow.MutableStateFlow
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * ★★ What the panel actually puts in front of him, state by state.
 *
 * ⚠️ This substitutes for one thing an emulator cannot do: an emulator's microphone
 * returns digital silence, so the gate correctly rejects every recording and the
 * confirm step is unreachable there — verified on the AVD, `rejected at -120.0 dBFS`.
 * The states downstream of a *successful* transcription are therefore driven directly
 * here. The confirm step is the safety rail of the whole feature, so it does not get to
 * be the untested part.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [29])
class PttPanelTest {

    @get:Rule
    val compose = createComposeRule()

    private val target = PttTarget("%3", "◑ Roam Touch rebuild")

    private var sends = 0
    private var cancels = 0
    private var dismisses = 0

    private fun render(state: PttState, live: Boolean = true) {
        compose.setContent {
            RoamTheme {
                PttPanel(
                    state = state,
                    level = MutableStateFlow(-24.0),
                    channelLabel = target.label,
                    targetLive = live,
                    nowMs = 12_000L,
                    onPress = {},
                    onRelease = {},
                    onSend = { sends++ },
                    onCancel = { cancels++ },
                    onDismiss = { dismisses++ },
                )
            }
        }
    }

    // -- ★ the confirm step ---------------------------------------------------

    /**
     * ★★ The architecture's rule, on screen: **one confirmation covers the words and
     * the routing.** Both must be visible at once, above one Send — a transcript with
     * no destination is half a confirmation and would let a good command reach the
     * wrong session.
     */
    @Test
    fun `the confirmation shows the words and the destination together`() {
        render(PttState.Confirming(target, "run the test suite and tell me if it is green"))

        compose.onNodeWithText("run the test suite and tell me if it is green")
            .assertIsDisplayed()
        compose.onNodeWithText("◑ Roam Touch rebuild").assertIsDisplayed()
        compose.onNode(hasText("to")).assertIsDisplayed()
        compose.onNodeWithText("SEND").assertIsDisplayed()
        compose.onNodeWithText("HOLD TO REDO").assertIsDisplayed()
        compose.onNodeWithText("CANCEL").assertIsDisplayed()
    }

    @Test
    fun `Send and Cancel are wired to different things`() {
        render(PttState.Confirming(target, "continue"))

        compose.onNodeWithText("SEND").performClick()
        assertEquals(1, sends)
        assertEquals(0, cancels)

        compose.onNodeWithText("CANCEL").performClick()
        assertEquals(1, cancels)
        assertEquals("Cancel must never send", 1, sends)
    }

    /**
     * ⚠️ A pane that died while he was talking. It says so *before* the press, and Send
     * does nothing — stale state surfaced up front, not after the tap.
     */
    @Test
    fun `a dead pane is called out and Send is inert`() {
        render(PttState.Confirming(target, "deploy it"), live = false)

        compose.onNode(hasText("that pane is gone", substring = true)).assertIsDisplayed()
        compose.onNodeWithText("SEND").performClick()
        assertEquals("a dead pane cannot be sent to", 0, sends)
    }

    @Test
    fun `a refused send keeps the words on screen with the reason`() {
        render(PttState.Confirming(target, "run the tests", error = "hub unreachable"))

        compose.onNodeWithText("run the tests").assertIsDisplayed()
        compose.onNodeWithText("hub unreachable").assertIsDisplayed()
        // Still sendable: he can press it again once the tailnet comes back.
        compose.onNodeWithText("SEND").performClick()
        assertEquals(1, sends)
    }

    // -- ★ every state is distinguishable ------------------------------------

    /**
     * The whole reason the panel exists. On a forearm there is no other feedback, and
     * "listening", "waiting on the network" and "broken" must never look alike.
     */
    @Test
    fun `listening says so, with an elapsed count and where it is going`() {
        render(PttState.Listening(target, startedAtMs = 9_000L))

        compose.onNodeWithText("LISTENING · 3s").assertIsDisplayed()
        compose.onNodeWithText("release to send").assertIsDisplayed()
        compose.onNodeWithText("◑ Roam Touch rebuild").assertIsDisplayed()
    }

    @Test
    fun `transcribing is its own state, and is cancellable`() {
        render(PttState.Transcribing(target))

        compose.onNodeWithText("TRANSCRIBING").assertIsDisplayed()
        compose.onNodeWithText("CANCEL").performClick()
        assertEquals(1, cancels)
    }

    @Test
    fun `sending is distinct from transcribing`() {
        render(PttState.Sending(target, "continue"))
        compose.onNodeWithText("SENDING").assertIsDisplayed()
        compose.onNodeWithText("continue").assertIsDisplayed()
    }

    /**
     * ⚠️ Each failure says which failure it was. "The mic is dead" and "Whisper is
     * unreachable" call for completely different things from a man in a corridor.
     */
    @Test
    fun `a failure names itself and clears on acknowledgement`() {
        render(PttState.Failed(Ptt.TOO_QUIET))

        compose.onNodeWithText(Ptt.TOO_QUIET).assertIsDisplayed()
        compose.onNodeWithText("OK").performClick()
        assertEquals(1, dismisses)
    }

    @Test
    fun `the failure reasons are distinct sentences, not one generic message`() {
        val reasons = listOf(
            Ptt.NO_MIC, Ptt.TOO_SHORT, Ptt.TOO_QUIET, Ptt.NOTHING_HEARD,
            Ptt.WHISPER_UNREACHABLE, Ptt.WHISPER_FAILED, Ptt.micDropout(240, 5_000),
            Ptt.MIC_NOT_DELIVERING,
        )
        assertEquals("no two failures may read alike", reasons.size, reasons.toSet().size)
    }

    /**
     * ⚠️ The message that would have diagnosed the 0.4 bug on sight. He held it for five
     * seconds; the panel must say the mic dropped out and show both numbers, not tell
     * him to hold it longer.
     */
    @Test
    fun `a capture fault names the mic and both durations`() {
        render(PttState.Failed(Ptt.micDropout(240, 5_000)))

        compose.onNode(hasText("mic dropped out", substring = true)).assertIsDisplayed()
        compose.onNode(hasText("0.2s", substring = true)).assertIsDisplayed()
        compose.onNode(hasText("5.0s", substring = true)).assertIsDisplayed()
    }

    /**
     * ⚠️ A dead audio input has to be readable at arm's length as *not his fault*. The
     * panel is the only place this device ever says anything.
     */
    @Test
    fun `a dead audio input says so on the panel`() {
        render(PttState.Failed(Ptt.MIC_NOT_DELIVERING))

        compose.onNode(hasText("never started", substring = true)).assertIsDisplayed()
        compose.onNode(hasText("not your press", substring = true)).assertIsDisplayed()
    }

    /** ★ Idle is silent: no panel, no leftover chrome above the composer. */
    @Test
    fun `idle renders nothing at all`() {
        render(PttState.Idle)
        compose.onAllNodesWithTextCount("SEND", 0)
        compose.onAllNodesWithTextCount("CANCEL", 0)
        compose.onAllNodesWithTextCount("LISTENING · 0s", 0)
    }

    private fun androidx.compose.ui.test.junit4.ComposeContentTestRule.onAllNodesWithTextCount(
        text: String,
        expected: Int,
    ) {
        assertEquals(
            "\"$text\" should not be on screen when idle",
            expected,
            onAllNodes(hasText(text)).fetchSemanticsNodes().size,
        )
    }
}
