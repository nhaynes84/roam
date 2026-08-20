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
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.getUnclippedBoundsInRoot
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.unit.height
import androidx.compose.ui.unit.width
import com.roam.touch.channels.BatteryState
import com.roam.touch.channels.ChannelsState
import com.roam.touch.channels.Fx
import com.roam.touch.channels.controls.ControlAction
import com.roam.touch.channels.controls.HeadsetGesture
import com.roam.touch.channels.controls.HeadsetProfile
import com.roam.touch.settings.SettingsShelf
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * ★★ Settings, and the one setting in it.
 *
 * Owner, 2026-08-15: *"honestly the headphones setup is a Setting, we'll need our own
 * settings so might as well just start making widgets there, of which headphones is one
 * setting."*
 *
 * ⚠️⚠️ **The headset screen is load-bearing and this move must not have broken it.** This
 * handset's microphone is dead at the HAL, so push-to-talk records through a Bluetooth
 * headset and that screen is where its buttons are bound. It was a top-level destination;
 * it is now two taps in, and the second tap has to land.
 *
 * ⚠️ Nothing here opens a microphone. The headset screen is rendered with a fake profile
 * and its callbacks counted — the same way `ControlsScreenTest` has always done it.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [29], qualifiers = "w731dp-h411dp-land")
class SettingsScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val buds = HeadsetProfile(
        address = "AA:BB:CC:DD:EE:FF",
        name = "Pixel Buds",
        bindings = mapOf(HeadsetGesture(85) to ControlAction.PUSH_TO_TALK),
    )

    private var learned: ControlAction? = null

    /**
     * Rail plus content, wired the way [ChannelsApp] wires them: the settings shelf opens
     * the headset screen, and the headset screen comes back to the shelf.
     */
    private fun renderPanel(collapsed: Boolean = false) {
        learned = null
        compose.setContent {
            RoamTheme {
                var screen by remember { mutableStateOf(Screen.Channels) }
                var folded by remember { mutableStateOf(collapsed) }
                Row(Modifier.fillMaxSize()) {
                    NavRail(
                        shell = Shell.Wide,
                        state = ChannelsState(),
                        battery = BatteryState(percent = 72),
                        nowMs = Fx.NOW_MS,
                        screen = screen,
                        openPane = null,
                        sending = false,
                        collapsed = folded,
                        onToggleCollapse = { folded = !folded },
                        onNewSession = {},
                        onOpenChannel = {},
                        onHome = { screen = Screen.Channels },
                        onOpenApps = { screen = Screen.Apps },
                        onOpenSettings = { screen = Screen.Settings },
                        onVoice = {},
                        onQuickSend = {},
                    )
                    Box(Modifier.weight(1f).fillMaxSize()) {
                        when (screen) {
                            Screen.Settings -> SettingsScreen(
                                onBack = { screen = Screen.Channels },
                                onOpen = { id ->
                                    if (id == SettingsShelf.HEADSET) screen = Screen.Controls
                                },
                            )

                            Screen.Controls -> ControlsScreen(
                                profile = buds,
                                seen = emptyList(),
                                learningFor = null,
                                onBack = { screen = Screen.Settings },
                                onLearn = { learned = it },
                                onCancelLearn = {},
                                onUnbind = {},
                                shell = Shell.Wide,
                                backLabel = "SETTINGS",
                            )

                            else -> Unit
                        }
                    }
                }
            }
        }
    }

    /** ★ The path, from the rail: settings → the headset widget → the headset screen. */
    @Test
    fun `the headset setup is reachable from settings, expanded`() {
        renderPanel()
        compose.onNodeWithContentDescription("settings").performClick()
        compose.onNodeWithText("Headset buttons").assertIsDisplayed()

        compose.onNodeWithText("Headset buttons").performClick()
        compose.onNodeWithText("HEADSET CONTROLS").assertIsDisplayed()
        // ★ Still the same screen it always was: the bindings are here and they still act.
        compose.onNodeWithText("Pixel Buds").assertIsDisplayed()
    }

    /** ⚠️ And with the rail folded, which is the shape he asked to be able to live in. */
    @Test
    fun `the headset setup is reachable from settings, folded`() {
        renderPanel(collapsed = true)
        compose.onNodeWithContentDescription("settings").performClick()
        compose.onNodeWithText("Headset buttons").performClick()
        compose.onNodeWithText("HEADSET CONTROLS").assertIsDisplayed()
    }

    /**
     * ⚠️⚠️ Back out of the headset screen lands on **Settings**, not on Channels. It is a
     * screen reached from another screen now — see [Nav.parentOf] — and a Back that walks
     * two steps in one press leaves no sign the settings shelf was ever there.
     */
    @Test
    fun `back out of the headset screen lands on settings`() {
        renderPanel()
        compose.onNodeWithContentDescription("settings").performClick()
        compose.onNodeWithText("Headset buttons").performClick()

        compose.onNodeWithText("SETTINGS").assertIsDisplayed()
        compose.onNodeWithText("SETTINGS").performClick()
        // …and he is on the shelf he tapped the widget on.
        compose.onNodeWithText("Headset buttons").assertIsDisplayed()
    }

    /** The learning flow the screen exists for still works from its new home. */
    @Test
    fun `binding a button still works two taps in`() {
        renderPanel()
        compose.onNodeWithContentDescription("settings").performClick()
        compose.onNodeWithText("Headset buttons").performClick()
        compose.onAllNodesWithTag(BINDINGS).assertCountEquals(1)
        // ⚠️ The bound gesture's own control, by the word the screen actually prints —
        // the same one `ControlsScreenTest` presses. Re-capturing PTT is the flow that
        // matters most here: it is how the dead handset mic is worked around.
        compose.onNodeWithText("CHANGE").performClick()
        assertEquals(ControlAction.PUSH_TO_TALK, learned)
    }

    /**
     * ★ Same shelf idiom as the apps: [ShelfGrid], so a settings widget is the same size
     * as an app tile at the same reading distance. One widget today, so the assertion that
     * matters is the *tile*, not the column count — see `AppsScreenTest` for the columns.
     */
    @Test
    fun `a settings widget is a shelf tile, not a preference row`() {
        renderPanel()
        compose.onNodeWithContentDescription("settings").performClick()

        val tiles = compose.onAllNodesWithTag(SETTING_TILE).fetchSemanticsNodes()
        assertEquals(SettingsShelf.WIDGETS.size, tiles.size)
        val tile = compose.onAllNodesWithTag(SETTING_TILE)[0].getUnclippedBoundsInRoot()
        println("SETTING tile=${tile.width.value}x${tile.height.value}dp")
        assertTrue("a widget is ${tile.width.value}dp wide", tile.width.value >= 150f)
        assertTrue("a widget is ${tile.height.value}dp tall", tile.height.value >= 132f)
    }
}
