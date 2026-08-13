package com.roam.touch.channels.ui

import android.view.KeyEvent
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.getUnclippedBoundsInRoot
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.unit.height
import com.roam.touch.channels.controls.ControlAction
import com.roam.touch.channels.controls.HeadsetGesture
import com.roam.touch.channels.controls.HeadsetProfile
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
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

    /** Breathing room the last binding row must keep below it. */
    private val MARGIN_DP = 24f

    private val tap = HeadsetGesture(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE)
    private val volumeUp = HeadsetGesture(KeyEvent.KEYCODE_VOLUME_UP)

    private var learned: ControlAction? = null
    private var unbound: HeadsetGesture? = null
    private var backs = 0

    private fun render(
        profile: HeadsetProfile?,
        seen: List<String> = emptyList(),
        learningFor: ControlAction? = null,
        shell: Shell = Shell.Narrow,
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
                    shell = shell,
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
        compose.onNodeWithText("send").assertExists()
        compose.onNodeWithText("next channel").assertExists()
        compose.onNodeWithText("previous channel").assertExists()
        compose.onNodeWithText("cancel").assertExists()
        // Four of the five actions are unbound, and each says so.
        assertEquals(4, compose.onAllNodes(hasText("not bound")).fetchSemanticsNodes().size)
    }

    // --- ★★ it must not need scrolling on a forearm --------------------------

    /**
     * ★★ **All five actions on screen at once, in the orientation the housing is going
     * to.** SEND made a fifth action and the list ran past the bottom of sailfish's
     * 411 dp-tall landscape window. It scrolled, and he never complained — but a
     * settings screen you have to scroll is a minor annoyance at a desk and a real one
     * on a wrist you are reading at arm's length with one hand full.
     *
     * ⚠️ Measured against the window, not eyeballed, and against the *unclipped* bounds
     * so a block that overflows is caught rather than silently cropped.
     */
    @Test
    @Config(qualifiers = "w731dp-h411dp-land")
    fun `every binding fits a landscape window without scrolling`() {
        render(buds(tap to ControlAction.PUSH_TO_TALK), shell = Shell.Wide)

        val root = compose.onRoot().getUnclippedBoundsInRoot()
        val bindings = compose.onNodeWithTag(BINDINGS).getUnclippedBoundsInRoot()
        println(
            "BINDINGS top=${bindings.top.value}dp bottom=${bindings.bottom.value}dp " +
                "of window ${root.height.value}dp"
        )
        // ⚠️ A margin, not merely "does not overflow". Landing exactly on the bottom
        // edge is a layout one padding tweak away from scrolling again, and the last row
        // would read as cut off even while it technically fitted.
        val room = root.height.value - MARGIN_DP
        assertTrue(
            "the bindings reach ${bindings.bottom.value}dp of a ${root.height.value}dp " +
                    "window, leaving no room below the last row",
            bindings.bottom.value <= room,
        )
        for (action in ControlAction.entries) {
            compose.onNodeWithText(action.label).assertIsDisplayed()
        }
    }

    /**
     * ⚠️ Portrait keeps the single column. There is height to spare there and width to
     * spare in landscape; the fold is per shape, not a new layout everywhere.
     */
    @Test
    @Config(qualifiers = "w411dp-h731dp-port")
    fun `portrait keeps one binding per row`() {
        render(buds(tap to ControlAction.PUSH_TO_TALK), shell = Shell.Narrow)

        val rows = ControlAction.entries.map {
            compose.onNodeWithText(it.label).getUnclippedBoundsInRoot().top.value
        }
        assertEquals("every row must be at a different height", rows.size, rows.toSet().size)
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
