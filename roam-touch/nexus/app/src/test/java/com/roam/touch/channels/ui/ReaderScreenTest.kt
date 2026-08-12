package com.roam.touch.channels.ui

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertTextContains
import com.roam.touch.channels.ChannelsState
import com.roam.touch.channels.Fx
import com.roam.touch.channels.model.Event
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * ★★ Where a long message actually becomes readable.
 *
 * The owner's report — *"any message over 6 lines doesn't scroll or have expandability,
 * i just can't read it on the phone"* — had two causes, and this file covers the display
 * half: the body has to arrive here **whole**, and when it has not arrived whole yet
 * that must be stated rather than implied by prose that simply stops.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [29])
class ReaderScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val channel = Fx.channel(pane = "%0", label = "◑ Roam Touch rebuild")

    private val body = """
        Done — Andy resolves now. But the pre-flight caught something that would have
        sunk the demo, and the detail runs on well past the point a summary stops.
    """.trimIndent()

    private fun render(event: Event, state: ChannelsState = ChannelsState()) {
        compose.setContent {
            RoamTheme {
                ReaderScreen(
                    state = state,
                    channel = channel,
                    event = event,
                    speaking = false,
                    onBack = {},
                    onPlay = {},
                    onStopPlaying = {},
                )
            }
        }
    }

    /** The whole point: the body, not the summary the list already showed him. */
    @Test
    fun `it shows the full body, not the summary`() {
        render(Fx.event(id = 1, kind = "outcome", body = body, summary = "Done — Andy…"))
        compose.onNodeWithTag(BODY_TAG)
            .assertTextContains("runs on well past the point a summary stops.", substring = true)
    }

    /**
     * ⚠️ A payload trimmed to 4 KiB in transit must never be presented as the answer.
     * `API.md` gives `GET /events/{id}` for exactly this, and until it lands the screen
     * says so — showing a truncated tail silently is the original bug in miniature.
     */
    @Test
    fun `a body still in transit says so instead of pretending to be whole`() {
        val trimmed = Fx.event(
            id = 2, kind = "outcome", body = body, summary = "Done…",
            chars = 6_501, truncated = true,
        )
        render(trimmed)
        compose.onNodeWithText("fetching the rest — 6.5k chars in full").assertIsDisplayed()
    }

    /** Once the untrimmed body has landed, the caveat goes and the real text is there. */
    @Test
    fun `when the rest arrives the caveat goes with it`() {
        val trimmed = Fx.event(
            id = 3, kind = "outcome", body = "the first four kibibytes", summary = "Done…",
            chars = 6_501, truncated = true,
        )
        val whole = ChannelsState(fullBodies = mapOf(3L to "$body\nAnd the true ending."))
        render(trimmed, whole)

        compose.onAllNodesWithText("fetching the rest", substring = true).assertCountEquals(0)
        compose.onNodeWithTag(BODY_TAG)
            .assertTextContains("And the true ending.", substring = true)
    }

    /** He is often listening rather than reading. The control travels with the message. */
    @Test
    fun `the message can be played from here`() {
        render(Fx.event(id = 4, kind = "outcome", body = body, summary = "Done…"))
        compose.onNodeWithContentDescriptionCompat("read this aloud").assertIsDisplayed()
    }

    /** One obvious way out, to the conversation he came from. */
    @Test
    fun `there is a way back to the thread`() {
        render(Fx.event(id = 5, kind = "outcome", body = body, summary = "Done…"))
        compose.onNodeWithText("THREAD").assertIsDisplayed()
    }
}

private fun androidx.compose.ui.test.junit4.ComposeContentTestRule
    .onNodeWithContentDescriptionCompat(label: String) =
    onNode(androidx.compose.ui.test.hasContentDescription(label))
