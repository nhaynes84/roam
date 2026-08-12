package com.roam.touch.channels.ui

import android.view.KeyEvent
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.roam.touch.channels.controls.ControlAction
import com.roam.touch.channels.controls.HeadsetGesture
import com.roam.touch.channels.controls.HeadsetProfile
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * ★★ The bindings screen, which exists because the owner's two headsets disagree.
 *
 * The Pixel Buds bind long-press to Assistant, the Jabras bind it to volume, and the
 * Jabras fire a different action set per ear — so this screen has to make the mapping
 * *visible and changeable*, not merely settable once. His words: **"but make it
 * 'editable'"**.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [29])
class ControlsScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val tap = HeadsetGesture(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE)
    private val volumeUp = HeadsetGesture(KeyEvent.KEYCODE_VOLUME_UP)

    private var learned: ControlAction? = null
    private var unbound: HeadsetGesture? = null
    private var backs = 0

    private fun render(
        profile: HeadsetProfile?,
        seen: List<String> = emptyList(),
        learningFor: ControlAction? = null,
    ) {
        compose.setContent {
            RoamTheme {
                ControlsScreen(
                    profile = profile,
                    seen = seen,
                    learningFor = learningFor,
                    onBack = { backs++ },
                    onLearn = { learned = it },
                    onCancelLearn = {},
                    onUnbind = { unbound = it },
                )
            }
        }
    }

    private fun buds(vararg bindings: Pair<HeadsetGesture, ControlAction>) =
        HeadsetProfile("11:22:33:44:55:66", "Pixel Buds Pro", bindings.toMap(), introduced = true)

    /**
     * ★ Every action is listed, bound or not. An unbound control that is simply absent
     * from the screen is one he will conclude is broken.
     */
    @Test
    fun `every action is shown, and an unbound one says so`() {
        render(buds(tap to ControlAction.PUSH_TO_TALK))

        compose.onNodeWithText("push to talk").assertIsDisplayed()
        compose.onNodeWithText("tap").assertIsDisplayed()
        compose.onNodeWithText("next channel").assertIsDisplayed()
        compose.onNodeWithText("previous channel").assertIsDisplayed()
        compose.onNodeWithText("cancel").assertIsDisplayed()
        // Three of the four actions are unbound, and each says so.
        assertEquals(3, compose.onAllNodes(hasText("not bound")).fetchSemanticsNodes().size)
    }

    /** ★★ One binding, changed in place — no wizard to walk. */
    @Test
    fun `a single binding can be re-captured without touching the others`() {
        render(buds(tap to ControlAction.PUSH_TO_TALK))

        compose.onNodeWithText("CHANGE").performClick()
        assertEquals(ControlAction.PUSH_TO_TALK, learned)
    }

    @Test
    fun `an unbound action offers to capture a gesture for it`() {
        render(buds(tap to ControlAction.PUSH_TO_TALK))
        // Three actions are unbound, so SET appears three times; any of them is the seam.
        compose.onAllNodes(hasText("SET"))[0].assertIsDisplayed()
    }

    /**
     * ⚠️ Unbinding hands the key back to the headset and the system. A gesture he stops
     * wanting intercepted must be releasable, or binding volume once would cost him
     * volume forever.
     */
    @Test
    fun `a bound gesture can be released`() {
        render(buds(tap to ControlAction.PUSH_TO_TALK))

        compose.onNodeWithText("UNBIND").performClick()
        assertEquals(tap, unbound)
    }

    /**
     * ⚠️⚠️ Capturing volume takes the rocker from the system, so it is called out on the
     * screen. He must never have to work out for himself why volume stopped working.
     */
    @Test
    fun `binding a volume gesture says out loud that volume is being taken`() {
        render(buds(volumeUp to ControlAction.NEXT_CHANNEL))

        // ⚠️ assertExists, not assertIsDisplayed: the notes sit below the fold on a
        // short screen and this is about the words being on the screen at all.
        compose.onNode(hasText("volume keys go to this app", substring = true)).assertExists()
        compose.onNode(hasText("Unbind it to give them back", substring = true)).assertExists()
    }

    /**
     * ⚠️⚠️ A gesture may never open a microphone he does not know about. The screen
     * states plainly that a tap is a toggle and that the mic announces itself.
     */
    @Test
    fun `the screen says a tap opens the microphone and how he will know`() {
        render(buds(tap to ControlAction.PUSH_TO_TALK))

        compose.onNode(hasText("toggle, not a hold", substring = true)).assertExists()
        compose.onNode(hasText("LISTENING", substring = true)).assertExists()
        compose.onNode(hasText("buzzes", substring = true)).assertExists()
    }

    /** ★ Discovery, on screen: what this headset actually sent, in his own hands. */
    @Test
    fun `the raw key log is shown so an unknown headset can still be mapped`() {
        render(
            buds(),
            seen = listOf("KEYCODE_MEDIA_PLAY_PAUSE DOWN repeat=0 flags=0x0 source=Pixel Buds"),
        )
        compose.onNode(hasText("KEYCODE_MEDIA_PLAY_PAUSE", substring = true)).assertExists()
    }

    @Test
    fun `learn mode asks for the gesture by name`() {
        render(buds(), learningFor = ControlAction.NEXT_CHANNEL)
        // ⚠️ The learn card names the action, and so does its own row — the card is the
        // one that must be on screen, so it is matched by its own words.
        compose.onNode(hasText("press the button you want for “next channel”"))
            .assertIsDisplayed()
        compose.onNodeWithText("PRESS IT").assertIsDisplayed()
    }

    /** ⚠️ No headset is an honest state, not a blank screen. */
    @Test
    fun `with nothing connected it says so instead of showing an empty list`() {
        render(null)
        compose.onNode(hasText("no headset connected", substring = true)).assertIsDisplayed()
    }

    // --- ★ the first-connect prompt ------------------------------------------

    /**
     * ⚠️⚠️ **A prompt, never a gate.** The owner: *"we just map it on first connect"* —
     * and dismissing it must leave the headset fully usable as a microphone. It also has
     * to say that a tap is already wired to the mic, because a default he was not told
     * about is the same surprise as a hot mic.
     */
    @Test
    fun `the first-connect card offers mapping and is dismissible without losing the mic`() {
        var mapped = 0
        var dismissed = 0
        compose.setContent {
            RoamTheme {
                HeadsetIntroCard(
                    profile = HeadsetProfile.forNewHeadset("11:22", "Jabra Elite 8"),
                    onMap = { mapped++ },
                    onDismiss = { dismissed++ },
                )
            }
        }

        compose.onNode(hasText("Jabra Elite 8", substring = true)).assertIsDisplayed()
        compose.onNode(hasText("single tap is set to push-to-talk", substring = true))
            .assertIsDisplayed()
        compose.onNode(hasText("mic button on screen works either way", substring = true))
            .assertIsDisplayed()

        compose.onNodeWithText("NOT NOW").performClick()
        assertEquals(1, dismissed)
        assertEquals(0, mapped)
    }
}
