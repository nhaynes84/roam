package com.roam.touch.channels.ui

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.getUnclippedBoundsInRoot
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithContentDescription
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.roam.touch.channels.BatteryState
import com.roam.touch.channels.ChannelReducer
import com.roam.touch.channels.ChannelsState
import com.roam.touch.channels.Fx
import com.roam.touch.channels.model.Channel
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * ★★ The rail: what it carries, and — more important — what it must not.
 *
 * The bug this replaces was not cosmetic. A `PttBar` sat at the root of the channel list
 * saying **PUSH TO TALK** on a screen where pushing it could not record anything; it only
 * opened a channel. This suite pins both halves of the fix: no microphone outside a
 * thread, and the door that replaced it obeying [VoiceEntry] rather than guessing.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [29])
class NavRailTest {

    @get:Rule
    val compose = createComposeRule()

    private val live = Fx.channel(pane = "%2", label = "◑ live one", live = true)
    private val dead = Fx.channel(pane = "%1", label = "dead one", live = false)

    private var opened: Channel? = null
    private var voicePresses = 0
    private var quickSent: String? = null
    private var wentTo: Screen? = null
    private var folds = 0

    private fun render(
        shell: Shell,
        state: ChannelsState = ChannelsState(channels = listOf(dead, live)),
        openPane: String? = null,
        screen: Screen = Screen.Channels,
        sending: Boolean = false,
        battery: BatteryState = BatteryState(percent = 72),
        collapsed: Boolean = false,
    ) {
        opened = null; voicePresses = 0; quickSent = null; wentTo = null; folds = 0
        compose.setContent {
            RoamTheme {
                // ⚠️ The fold is state the rail's own control drives, not a fixed flag:
                // Compose allows one `setContent` per test, so pinning "the control works
                // in both states" needs a rail that can actually change state under it.
                var folded by remember { mutableStateOf(collapsed) }
                Row(Modifier.fillMaxSize()) {
                    NavRail(
                        shell = shell,
                        state = state,
                        battery = battery,
                        nowMs = Fx.NOW_MS,
                        screen = screen,
                        openPane = openPane,
                        sending = sending,
                        collapsed = folded,
                        onToggleCollapse = { folds++; folded = !folded },
                        onOpenChannel = { opened = it },
                        onHome = {},
                        onOpenApps = { wentTo = Screen.Apps },
                        onOpenSettings = { wentTo = Screen.Settings },
                        onVoice = { voicePresses++ },
                        onQuickSend = { quickSent = it },
                    )
                }
            }
        }
    }

    /**
     * The destinations the rail offers, by the names they used to shout.
     *
     * ⚠️⚠️ **Both of these changed on 2026-08-15, and neither was a rename.** "home
     * assistant" was a house glyph in the first slot — pressing it opened the HA token
     * wizard, which is the screen behind owner's *"home … telling me i need a token"*; HA
     * is an app now and lives on the shelf. "headset buttons" became one widget inside
     * [SettingsScreen]: *"the headphones setup is a Setting."* Home itself is not in this
     * list because it is the CHANNELS header while the rail is open — see
     * `the folded rail is his column, in his order` for where it appears when it is not.
     */
    private val DESTINATIONS = listOf("apps", "settings")

    // --- the correctness fix -------------------------------------------------

    /**
     * ⚠️⚠️ The load-bearing assertion in this file. [PttButton]'s recording control
     * announces itself as "push to talk, hold to record"; nothing outside a thread may
     * ever carry it again, in either shape.
     */
    @Test
    fun `there is no recording control in the Wide rail`() {
        render(Shell.Wide)
        compose.onAllNodesWithContentDescription("push to talk, hold to record")
            .assertCountEquals(0)
    }

    /** ⚠️ And none in portrait either — the deleted bar was a bug in both orientations. */
    @Test
    fun `there is no recording control in the Narrow rail`() {
        render(Shell.Narrow)
        compose.onAllNodesWithContentDescription("push to talk, hold to record")
            .assertCountEquals(0)
    }

    /** The door is a door, and it says so — it opens something, it does not "hold". */
    @Test
    fun `TALK announces itself as navigation, not as a microphone`() {
        render(Shell.Wide)
        compose.onAllNodesWithContentDescription("talk, opens ◑ live one")
            .assertCountEquals(1)
        compose.onNodeWithTag(RAIL_TALK).performClick()
        assertEquals(1, voicePresses)
    }

    /**
     * ★★ The owner's question was *"what does 'TALK' do in that side nav"* — asked with
     * the button in front of him, which means the answer was not on it. It is now: the
     * destination is printed under the word, and it is the destination [VoiceEntry] will
     * actually pick, not a re-derivation that can drift out of step with the press.
     */
    @Test
    fun `TALK prints the channel it will open`() {
        render(Shell.Wide)
        compose.onNodeWithText("→ ◑ live one").assertIsDisplayed()
    }

    /**
     * ⚠️ The default state lists the dead pane first, so the label above is also the
     * assertion that the printed name is [VoiceEntry]'s pick — live first — and not
     * simply `channels.first()`. This is the other branch: with nothing live, it falls
     * back rather than claiming a target it does not have.
     */
    @Test
    fun `TALK falls back to the only channel there is when none are live`() {
        render(Shell.Wide, state = ChannelsState(channels = listOf(dead)))
        compose.onNodeWithText("→ dead one").assertIsDisplayed()
    }

    /**
     * ⚠️ With a thread open the real microphone is on screen in the composer. A second
     * voice control that only navigates, next to one that records, is the confusion the
     * root PTT bar used to cause — so the door is not drawn.
     */
    @Test
    fun `the TALK door disappears once a channel is open`() {
        render(Shell.Wide, openPane = "%2")
        compose.onAllNodesWithTag(RAIL_TALK).assertCountEquals(0)
    }

    @Test
    fun `with nothing to talk to the door is disabled rather than lying about a target`() {
        render(Shell.Wide, state = ChannelsState())
        compose.onAllNodesWithContentDescription("talk, no channels to talk to yet")
            .assertCountEquals(1)
        compose.onNodeWithTag(RAIL_TALK).performClick()
        assertEquals(0, voicePresses)
    }

    // --- the two shapes ------------------------------------------------------

    /** Landscape: the list is chrome, and chrome lives left. */
    @Test
    fun `Wide carries the channel list in the rail`() {
        render(Shell.Wide)
        compose.onNodeWithTag(RAIL_QUEUE).assertIsDisplayed()
        compose.onNodeWithText("◑ live one").performClick()
        assertEquals("%2", opened?.paneId)
    }

    /**
     * Portrait: the rail collapses instead of the tree forking. The list keeps the
     * content pane to itself, and the destinations stay reachable.
     */
    @Test
    fun `Narrow collapses the rail and leaves the list to the content pane`() {
        render(Shell.Narrow)
        assertTrue(compose.onAllNodesWithText("HOME ASSISTANT").fetchSemanticsNodes().isEmpty())
        assertTrue(compose.onAllNodesWithTag(RAIL_QUEUE).fetchSemanticsNodes().isEmpty())
        compose.onNodeWithContentDescription("apps").assertIsDisplayed()
        compose.onNodeWithText("CH").assertIsDisplayed()
    }

    // --- the destinations are glyphs now -------------------------------------

    /**
     * ★★ Owner, 2026-08-12: *"HA / BUDS / APPS, let's do icons instead, looks
     * amateurish."* All three, in both shapes, reachable by the name they used to shout.
     */
    @Test
    fun `every destination in Wide is an icon carrying its name`() {
        render(Shell.Wide)
        DESTINATIONS.forEach { compose.onNodeWithContentDescription(it).assertIsDisplayed() }
    }

    /** ⚠️ Both shapes. The words were in both, so the glyphs have to be in both. */
    @Test
    fun `every destination in Narrow is an icon carrying its name`() {
        render(Shell.Narrow)
        DESTINATIONS.forEach { compose.onNodeWithContentDescription(it).assertIsDisplayed() }
    }

    /**
     * ⚠️ The half of that instruction that is easy to leave undone: the words have to
     * actually go. A glyph with `HA` still printed beside it is the amateurish version
     * with an icon added to it.
     */
    @Test
    fun `the shouted abbreviations are gone from the Wide rail`() {
        render(Shell.Wide)
        assertNoWords()
    }

    @Test
    fun `the shouted abbreviations are gone from the Narrow rail`() {
        render(Shell.Narrow)
        assertNoWords()
    }

    private fun assertNoWords() = listOf("HA", "APPS", "BUDS").forEach { word ->
        assertTrue(
            "the rail still prints $word",
            compose.onAllNodesWithText(word).fetchSemanticsNodes().isEmpty(),
        )
    }

    /** The doors still open. A glyph that is decoration is worse than a word. */
    @Test
    fun `the icons are the buttons, not decoration on them`() {
        render(Shell.Wide)
        compose.onNodeWithContentDescription("apps").performClick()
        assertEquals(Screen.Apps, wentTo)
        compose.onNodeWithContentDescription("settings").performClick()
        assertEquals(Screen.Settings, wentTo)
    }

    // --- what the hidden status bar handed over ------------------------------

    /**
     * ★★ The system status bar is hidden (see `SystemBars`), so the app owns both of the
     * things on it that a worn device cannot do without.
     *
     * ⚠️ The clock is here for the same reason the charge is. He asked why the battery
     * chip existed *next to a bar showing the battery*; the answer was to remove the bar —
     * and the bar was also the only clock on a device he wears on his arm. Losing that
     * silently would be a worse bug than the duplication that started this.
     */
    @Test
    fun `the Wide rail carries the time and the charge`() {
        render(Shell.Wide)
        compose.onNodeWithTag(RAIL_STATUS).assertIsDisplayed()
        compose.onNodeWithText("72%").assertIsDisplayed()
        compose.onNodeWithText(Format.clock(Fx.NOW_MS)).assertIsDisplayed()
    }

    @Test
    fun `the Narrow rail carries the time and the charge`() {
        render(Shell.Narrow)
        compose.onNodeWithTag(RAIL_STATUS).assertIsDisplayed()
        compose.onNodeWithText("72%").assertIsDisplayed()
        compose.onNodeWithText(Format.clock(Fx.NOW_MS)).assertIsDisplayed()
    }

    /** ⚠️ Charging is a different fact from charge, and it survives the move. */
    @Test
    fun `the status line says when it is on the charger`() {
        render(Shell.Wide, battery = BatteryState(percent = 88, charging = true))
        compose.onNodeWithText("88% CHG").assertIsDisplayed()
    }

    /** The rail is on screen on every screen — that is what makes it the way back. */
    @Test
    fun `the rail is present on a detour, not just on Channels`() {
        render(Shell.Wide, screen = Screen.HomeAssistant)
        compose.onNodeWithTag(RAIL).assertIsDisplayed()
        compose.onNodeWithText("CHANNELS").assertIsDisplayed()
    }

    // --- what came left with the list ----------------------------------------

    /**
     * ★ The canned replies moved into the rail in Wide so the composer is one row. They
     * are relocated, not deleted: these five words are what he actually sends from a
     * corridor.
     */
    @Test
    fun `Wide puts the canned replies in the rail`() {
        render(Shell.Wide, openPane = "%2")
        compose.onNodeWithText("CONTINUE").performClick()
        assertEquals("continue", quickSent)
    }

    /** They act on the open channel, so like the mic they exist only while there is one. */
    @Test
    fun `the canned replies are absent with no channel open`() {
        render(Shell.Wide, openPane = null)
        assertTrue(compose.onAllNodesWithText("CONTINUE").fetchSemanticsNodes().isEmpty())
    }

    /** ⚠️ A dead pane cannot be typed into, and the rail must not pretend otherwise. */
    @Test
    fun `a canned reply into a dead pane does nothing`() {
        render(Shell.Wide, openPane = "%1")
        compose.onNodeWithText("CONTINUE").performClick()
        assertNull(quickSent)
    }

    /**
     * ⚠️⚠️ The rail's canned chips are a second copy of the composer's, so they inherit the
     * composer's rule: **dead while a send is outstanding.** A live chip during an 8 s wait
     * is a duplicate prompt one tap away — the same double-send the composer was fixed for.
     *
     * This test exists because of *where* the two changes came from: the deadlines landed on
     * `main` and the rail on a branch, and neither one could see the other's half. A merge
     * that compiles is not a merge that kept the rule.
     */
    @Test
    fun `a canned reply in the rail does nothing while a send is in flight`() {
        render(Shell.Wide, openPane = "%2", sending = true)
        compose.onNodeWithText("CONTINUE").performClick()
        assertNull(quickSent)
    }

    /**
     * The unread count follows the chrome left. It is the one number that has to be
     * legible from a screen that is not Channels at all.
     */
    @Test
    fun `the unread badge is on the Narrow rail even with no list in it`() {
        render(Shell.Narrow, state = withOneUnread())
        compose.onAllNodesWithContentDescription("1 unread").assertCountEquals(1)
    }

    /** In Wide it is on the rail header *and* on the row that owns it. */
    @Test
    fun `the unread badge is on the Wide rail header and on its channel`() {
        render(Shell.Wide, state = withOneUnread())
        compose.onAllNodesWithContentDescription("1 unread").assertCountEquals(2)
    }

    // --- folded: the icon column ---------------------------------------------

    /** The top of a node, in dp, for asserting what is above what. */
    private fun topOf(tag: String) =
        compose.onNodeWithTag(tag).getUnclippedBoundsInRoot().top.value

    private fun topOfName(name: String) =
        compose.onNodeWithContentDescription(name).getUnclippedBoundsInRoot().top.value

    /**
     * ★★ **The spec, in his order.** Owner: *"show me the home / apps / headphones
     * stacked, with the expand icon at the top of the column, and just unread notification
     * count bubble under that."*
     *
     * ⚠️ Asserted as an *order*, not as a set. Every one of these could be present and the
     * column still be wrong — the expand control below the destinations is a different
     * control from the one he asked for, because on a rail he finds by feel while walking,
     * position is the label.
     */
    @Test
    fun `the folded rail is his column, in his order`() {
        render(Shell.Wide, state = withOneUnread(), collapsed = true)

        val order = listOf(
            "expand" to topOf(RAIL_FOLD),
            "count" to topOf(RAIL_COUNT),
            "channels" to topOfName("channels"),
            "apps" to topOfName("apps"),
            "settings" to topOfName("settings"),
        )
        println("FOLDED " + order.joinToString { "${it.first}=${it.second}dp" })
        order.zipWithNext { (aName, a), (bName, b) ->
            assertTrue("$bName is not below $aName ($b vs $a)", b > a)
        }
    }

    /**
     * ⚠️⚠️ Folding must *remove* the list, not squeeze it. A queue clipped to a 56 dp
     * column would still be composed, still be scrollable, and still be reported as
     * present by everything except the eye — which is exactly how the rail once shipped
     * with a 0 dp channel list nobody could see.
     */
    @Test
    fun `folding puts the channel list away rather than clipping it`() {
        render(Shell.Wide, collapsed = true)
        assertTrue(compose.onAllNodesWithTag(RAIL_QUEUE).fetchSemanticsNodes().isEmpty())
        assertTrue(compose.onAllNodesWithText("◑ live one").fetchSemanticsNodes().isEmpty())
        // ★ And the door to voice goes with it: it is a full-width control with a channel
        // name printed on it, and there is no width to print one in.
        assertTrue(compose.onAllNodesWithTag(RAIL_TALK).fetchSemanticsNodes().isEmpty())
    }

    /**
     * ★★ One badge, not two. Expanded, the count sits on the CHANNELS row (and again on
     * the channel that owns it, which is a different fact about a different thing). Folded,
     * there is no CHANNELS row, so the bubble *is* that badge in the shape that has room
     * for it — never an addition to it.
     */
    @Test
    fun `the folded rail counts once, and does not repeat itself`() {
        render(Shell.Wide, state = withOneUnread(), collapsed = true)
        compose.onAllNodesWithContentDescription("1 unread").assertCountEquals(1)
    }

    /** Nothing waiting means no bubble — the count is a signal, not a permanent zero. */
    @Test
    fun `a quiet folded rail shows no bubble at all`() {
        render(Shell.Wide, collapsed = true)
        assertTrue(compose.onAllNodesWithTag(RAIL_COUNT).fetchSemanticsNodes().isEmpty())
    }

    /**
     * ⚠️ The control is at the top in *both* states, and it works in both. A toggle that
     * moves when it is used is a toggle he has to look for after every press.
     */
    @Test
    fun `the fold control is the top of the column in both states`() {
        render(Shell.Wide, collapsed = true)
        compose.onNodeWithContentDescription("expand the channel rail").assertIsDisplayed()

        // ★ One press, and the same control is still under the finger that pressed it —
        // now saying the opposite thing, above the list it just brought back.
        compose.onNodeWithTag(RAIL_FOLD).performClick()
        assertEquals(1, folds)
        compose.onNodeWithContentDescription("collapse the channel rail").assertIsDisplayed()
        assertTrue("the fold control moved off the top row", topOf(RAIL_FOLD) < topOf(RAIL_QUEUE))

        compose.onNodeWithTag(RAIL_FOLD).performClick()
        assertEquals(2, folds)
        compose.onNodeWithContentDescription("expand the channel rail").assertIsDisplayed()
    }

    /** ⚠️ Narrow is already the icon column. A fold control there folds nothing. */
    @Test
    fun `Narrow has nothing to fold, so it offers no control`() {
        render(Shell.Narrow, collapsed = true)
        assertTrue(compose.onAllNodesWithTag(RAIL_FOLD).fetchSemanticsNodes().isEmpty())
        // …and it stays the rail it always was, list or no list.
        compose.onNodeWithText("CH").assertIsDisplayed()
    }

    /**
     * The three destinations are the *same three*, reached the same way. Folding must not
     * fork the nav targets — see the `destinations` lambda they both draw from.
     */
    @Test
    fun `the folded destinations are the same doors and still open`() {
        render(Shell.Wide, collapsed = true)
        DESTINATIONS.forEach { compose.onNodeWithContentDescription(it).assertIsDisplayed() }
        compose.onNodeWithContentDescription("apps").performClick()
        assertEquals(Screen.Apps, wentTo)
        compose.onNodeWithContentDescription("settings").performClick()
        assertEquals(Screen.Settings, wentTo)
    }

    /**
     * ⚠️ The clock survives the fold. He did not ask for it in the column — but the system
     * status bar is hidden app-wide, so this rail is the only clock the device has, in
     * whatever shape it is in. See `the Wide rail carries the time and the charge`.
     */
    @Test
    fun `the folded rail still tells the time`() {
        render(Shell.Wide, collapsed = true)
        compose.onNodeWithTag(RAIL_STATUS).assertIsDisplayed()
        compose.onNodeWithText(Format.clock(Fx.NOW_MS)).assertIsDisplayed()
    }

    private fun withOneUnread() = ChannelReducer.applyEvent(
        ChannelsState(channels = listOf(dead, live)),
        Fx.event(id = 900, pane = "%2", kind = "outcome"),
    )
}
