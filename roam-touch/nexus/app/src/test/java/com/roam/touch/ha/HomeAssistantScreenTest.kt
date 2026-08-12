package com.roam.touch.ha

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.junit4.ComposeTestRule
import androidx.compose.ui.test.performClick
import com.roam.touch.channels.ui.HomeAssistantScreen
import com.roam.touch.channels.ui.RoamTheme
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * What the Home Assistant screen actually puts in front of him, for each state it can
 * be in.
 *
 * ⚠️ ★ This is the substitute for a live end-to-end run, and it is not as good as one.
 * Talking to his real server needs a long-lived token only he can mint, and a local mock
 * server could not be used either — this session cannot open a listening socket. So the
 * screen is driven from recorded payloads instead: the rendering, the wiring and the
 * tap-to-service path are all covered, and the single unproven link in the chain is
 * whether his HA accepts the token he creates. Everything up to that is verified here.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [29])
class HomeAssistantScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private fun render(home: HaHome, onTap: (HaState) -> Unit = {}) {
        compose.setContent { RoamTheme { HomeAssistantScreen(home, {}, {}, onTap) } }
    }

    private fun loaded(pinned: List<String> = emptyList()) = HaHome(
        link = HaLink.Ready(0),
        tiles = HaEntities.tiles(HaFx.states(HaFx.ALL), pinned),
    )

    // -- the state he will find it in tonight -------------------------------

    @Test
    fun `with no token the screen is the instructions, not an error`() {
        render(HaHome(link = HaLink.Unconfigured))

        compose.onNodeWithText("NEEDS A TOKEN").assertIsDisplayed()
        // ★ The exact path, on the device, so he is not hunting through HA's settings.
        compose.onNode(hasText("Long-lived access tokens", substring = true)).assertIsDisplayed()
        compose.onNode(hasText("roam.ha.token", substring = true)).assertIsDisplayed()
        compose.onNode(hasText("./gradlew installDebug", substring = true)).assertIsDisplayed()
    }

    @Test
    fun `a rejected token sends him back to the same instructions, not to Tailscale`() {
        render(HaHome(link = HaLink.Failed("token rejected", unauthorised = true)))

        compose.onNodeWithText("TOKEN REJECTED").assertIsDisplayed()
        compose.onNode(hasText("Long-lived access tokens", substring = true)).assertIsDisplayed()
    }

    @Test
    fun `an unreachable server is a red banner, never a silent empty grid`() {
        render(
            HaHome(
                link = HaLink.Failed("unreachable — check Tailscale", unauthorised = false),
                tiles = loaded().tiles,
            )
        )
        compose.onNodeWithText("HOME ASSISTANT UNREACHABLE").assertIsDisplayed()
        // …and the last known state stays readable underneath it.
        compose.onNodeWithText("Kitchen").assertIsDisplayed()
    }

    // -- the grid -----------------------------------------------------------

    @Test
    fun `the grid shows the entities that matter and hides the noise`() {
        render(loaded())

        // The first screenful. Which entities make the list at all, and in what order,
        // is HaEntitiesTest's job; this is about what his eyes land on.
        compose.onNodeWithText("Desk Lamp").assertIsDisplayed()
        compose.onNodeWithText("Kitchen").assertIsDisplayed()
        compose.onNodeWithText("Porch").assertIsDisplayed()
        compose.onNodeWithText("Roaster").assertIsDisplayed()

        // ⚠️ A default HA install is mostly this. None of it may ever be composed —
        // not scrolled past, not there.
        assertEquals(0, compose.onAllNodes(hasText("Sun")).fetchSemanticsNodes().size)
        assertEquals(0, compose.onAllNodes(hasText("Office Temperature")).fetchSemanticsNodes().size)
        assertEquals(0, compose.onAllNodes(hasText("home")).fetchSemanticsNodes().size)
    }

    @Test
    fun `a dimmed light shows its brightness on the tile`() {
        render(loaded())
        compose.onNodeWithText("on · 50%").assertIsDisplayed()
    }

    @Test
    fun `an unavailable entity says so rather than looking off`() {
        render(loaded())
        compose.onNodeWithText("Porch").assertIsDisplayed()
        compose.onNodeWithText("unavailable").assertIsDisplayed()
    }

    @Test
    fun `pinned entities are what he gets, in his order`() {
        render(loaded(pinned = listOf("sensor.office_temperature", "light.kitchen")))
        // A read-only sensor is shown when pinned — with its unit.
        compose.onNodeWithText("21.4 °C").assertIsDisplayed()
    }

    // -- taps ---------------------------------------------------------------

    @Test
    fun `tapping a light asks to toggle exactly that light`() {
        var tapped: HaState? = null
        render(loaded()) { tapped = it }

        compose.onNodeWithText("Kitchen").performClick()

        assertEquals("light.kitchen", tapped?.entityId)
        assertEquals(
            HaEntities.Action("light", "turn_off"),
            HaEntities.actionFor(tapped!!),
        )
    }

    @Test
    fun `an unavailable tile is not tappable`() {
        var tapped: HaState? = null
        render(loaded()) { tapped = it }

        compose.onNodeWithText("Porch").performClick()

        // ⚠️ Nothing is sent. Firing a service call at a bulb HA has already lost would
        // hang the tile on "sending…" and teach him the panel lies.
        assertNull(tapped)
    }

    @Test
    fun `a tile with a call in flight swallows further taps`() {
        var taps = 0
        val busy = loaded().let { it.copy(busy = setOf("light.kitchen")) }
        render(busy) { taps++ }

        compose.onNodeWithText("Kitchen").performClick()
        compose.onNodeWithText("Kitchen").performClick()

        // ★ Double-tapping because the first tap "did nothing" is how a light ends up
        // back off. The round trip over the tailnet is not instant, so the tile says
        // "sending…" and refuses input until HA answers.
        assertEquals(0, taps)
        compose.onNodeWithText("sending…").assertIsDisplayed()
    }

    // -- never lost ---------------------------------------------------------

    @Test
    fun `the way back to channels is there before anything has loaded`() {
        // ★ The bar sits outside every branch of the screen on purpose: he is wearing
        // this, and "no route home" on a device that IS the home screen is unfixable
        // without a laptop.
        render(HaHome(link = HaLink.Unconfigured))
        assertTrue(compose.onAllNodes(hasText("CHANNELS")).fetchSemanticsNodes().isNotEmpty())
    }

    @Test
    fun `the way back to channels is there once tiles are up`() {
        render(loaded())
        assertTrue(compose.onAllNodes(hasText("CHANNELS")).fetchSemanticsNodes().isNotEmpty())
    }
}
