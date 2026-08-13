package com.roam.touch.channels.ui

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.down
import androidx.compose.ui.test.up
import com.roam.touch.channels.stt.PttState
import com.roam.touch.channels.stt.PttTarget
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * ★★ One press must mean one recording, however hard the screen redraws underneath it.
 *
 * ⚠️⚠️ Push-to-talk shipped broken in 0.4 and the emulator said it was fine, because the
 * emulator suppressed both of the things that churn this screen on real hardware:
 * `roam-emu` sets `animator_duration_scale 0`, so the mic button's pulse never animated,
 * and a silent emulator microphone reported the *same* level every chunk, which
 * `StateFlow` conflated away instead of emitting eight times a second.
 *
 * The eventual cause was in the audio drain loop rather than the gesture — see
 * `MicRecorderTest` — but the diagnosis went through here first, and the hazard is
 * real: a `pointerInput` keyed on anything that changes mid-hold tears the gesture down
 * with the thumb still on the glass, which closes the microphone and reopens it. So the
 * property is pinned directly, and this test does not depend on an emulator's settings.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [29])
class PttHoldTest {

    @get:Rule
    val compose = createComposeRule()

    @Test(timeout = 60_000)
    fun `recomposition during a hold never restarts the recording`() {
        var presses = 0
        var releases = 0
        // Everything that genuinely changes while a thumb is down: the hub re-pushing a
        // pane label with a new status glyph, the state machine's own transitions, and
        // the 1 Hz ticker driving the elapsed count.
        val churn = mutableIntStateOf(0)
        var listening by mutableStateOf(false)

        // ⚠️ The button runs an infinite pulse animation, so the clock never goes idle.
        // Frames are driven by hand rather than waited on.
        compose.mainClock.autoAdvance = false

        compose.setContent {
            RoamTheme {
                val target = PttTarget("%0", "◑ working ${churn.intValue}")
                PttButton(
                    state = if (listening) PttState.Listening(target, churn.intValue.toLong())
                    else PttState.Idle,
                    target = target,
                    enabled = true,
                    onPress = { presses++; listening = true },
                    onRelease = { releases++; listening = false },
                    modifier = Modifier.testTag("ptt"),
                )
            }
        }
        compose.mainClock.advanceTimeByFrame()

        compose.onNodeWithTag("ptt").performTouchInput { down(center) }
        compose.mainClock.advanceTimeByFrame()
        assertEquals("the press must land once", 1, presses)

        // Five seconds of frames, with the tree changing on every one of them.
        repeat(120) {
            churn.intValue = it + 1
            compose.mainClock.advanceTimeByFrame()
        }

        assertEquals("one press per hold — the mic must not be reopened", 1, presses)
        assertEquals("the mic must stay open for the whole hold", 0, releases)

        compose.onNodeWithTag("ptt").performTouchInput { up() }
        compose.mainClock.advanceTimeByFrame()

        assertEquals("and exactly one release when the thumb lifts", 1, releases)
        assertEquals(1, presses)
    }

    /** The same guarantee for Redo, which is the second place a hold can start. */
    @Test(timeout = 60_000)
    fun `a hold on the confirm panel is equally immune to recomposition`() {
        var presses = 0
        var releases = 0
        val churn = mutableIntStateOf(0)

        compose.mainClock.autoAdvance = false
        compose.setContent {
            RoamTheme {
                val target = PttTarget("%0", "◑ working ${churn.intValue}")
                PttPanel(
                    state = PttState.Confirming(target, "run the tests ${churn.intValue}"),
                    level = kotlinx.coroutines.flow.MutableStateFlow(-20.0 - churn.intValue),
                    channelLabel = target.label,
                    targetLive = true,
                    nowMs = 1_000L + churn.intValue,
                    onPress = { presses++ },
                    // ⚠️ HOLD TO REDO fires onRedoPress now — it is the one press that
                    // discards the transcript rather than continuing it. This test is
                    // about that chip, so it counts here.
                    onRedoPress = { presses++ },
                    onRelease = { releases++ },
                    onSend = {},
                    onCancel = {},
                    onDismiss = {},
                )
            }
        }
        compose.mainClock.advanceTimeByFrame()

        compose.onNodeWithText("HOLD TO REDO").performTouchInput { down(center) }
        compose.mainClock.advanceTimeByFrame()
        assertEquals(1, presses)

        repeat(60) {
            churn.intValue = it + 1
            compose.mainClock.advanceTimeByFrame()
        }
        assertEquals(1, presses)
        assertEquals(0, releases)

        compose.onNodeWithText("HOLD TO REDO").performTouchInput { up() }
        compose.mainClock.advanceTimeByFrame()
        assertEquals(1, releases)
    }
}
