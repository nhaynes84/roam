package com.roam.touch.channels.ui

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * ★★ The precedence bug, pinned. Owner, with the rail in front of him: *"the icons don't
 * seem to work."* They did — the tap landed, the icon highlighted, `screen` changed. The
 * content pane just never looked at it, because an open thread was answered first.
 */
class NavTest {

    // --- what the pane shows -------------------------------------------------

    /** ⚠️⚠️ The regression itself: a destination chosen from inside a thread must win. */
    @Test
    fun `a detour outranks an open thread`() {
        assertEquals(
            Pane.Detour,
            Nav.pane(reading = false, screen = Screen.HomeAssistant, hasChannel = true),
        )
    }

    /** …for every destination, not just the one that was reported. */
    @Test
    fun `every destination outranks an open thread`() {
        for (s in listOf(Screen.HomeAssistant, Screen.Apps, Screen.Controls)) {
            assertEquals(
                "$s should cover the thread",
                Pane.Detour,
                Nav.pane(reading = false, screen = s, hasChannel = true),
            )
        }
    }

    /** With no detour up, the thread is what he came for. */
    @Test
    fun `an open channel shows its thread`() {
        assertEquals(
            Pane.Thread,
            Nav.pane(reading = false, screen = Screen.Channels, hasChannel = true),
        )
    }

    @Test
    fun `nothing open is the list`() {
        assertEquals(
            Pane.List,
            Nav.pane(reading = false, screen = Screen.Channels, hasChannel = false),
        )
    }

    /** The reader is on top of everything — it was opened from whatever is under it. */
    @Test
    fun `the reader outranks a detour and a thread`() {
        assertEquals(
            Pane.Reader,
            Nav.pane(reading = true, screen = Screen.HomeAssistant, hasChannel = true),
        )
    }

    /** ⚠️ A detour with no channel behind it is still a detour, not the list. */
    @Test
    fun `a detour without a channel open is still the detour`() {
        assertEquals(
            Pane.Detour,
            Nav.pane(reading = false, screen = Screen.Apps, hasChannel = false),
        )
    }

    // --- and the way back out ------------------------------------------------

    /**
     * ★★ The other half. If a detour covers the thread on the way in, Back must lift the
     * detour *first* — otherwise the conversation closes silently underneath it and he is
     * left on Home Assistant wondering where it went.
     */
    @Test
    fun `back lifts the detour before it closes the thread`() {
        assertEquals(
            Back.CloseDetour,
            Nav.back(reading = false, screen = Screen.HomeAssistant, hasOpenPane = true),
        )
    }

    /**
     * ⚠️ Every branch of [Nav.back] must mirror [Nav.pane], in every state.
     *
     * ★ Exhaustive over `Screen.values()` rather than a hand-written list, so adding a
     * destination cannot quietly go untested — that is exactly how the hub browser would
     * have shipped with Back walking two steps out in one press.
     */
    @Test
    fun `back always closes whatever pane is on top`() {
        for (reading in listOf(false, true)) {
            for (screen in Screen.values()) {
                for (open in listOf(false, true)) {
                    val expected = when (Nav.pane(reading, screen, open)) {
                        Pane.Reader -> Back.CloseReader
                        // ⚠️ The one documented exception to the mirror, and it is about
                        // *how far* back rather than about what is on top: the browser is
                        // a detour opened from another detour, so it unwinds to the shelf
                        // rather than all the way to Channels. See Back.CloseHubBrowser.
                        Pane.Detour ->
                            if (screen == Screen.HubBrowser) Back.CloseHubBrowser
                            else Back.CloseDetour
                        Pane.Thread -> Back.CloseThread
                        Pane.List -> null
                    }
                    assertEquals(
                        "reading=$reading screen=$screen open=$open",
                        expected,
                        Nav.back(reading, screen, open),
                    )
                }
            }
        }
    }

    // ---- the hub browser -------------------------------------------------------------

    /**
     * ★★ He tapped Files on the shelf; Back has to put him back on the shelf.
     *
     * ⚠️ The general detour rule would send him to Channels, which is two steps out in one
     * press and leaves no sign the shelf was ever there — on a screen that is the only
     * route off the home screen, "where did the apps go" is a real way to be lost.
     */
    @Test
    fun `back out of the hub browser lands on the shelf, not on channels`() {
        assertEquals(
            Back.CloseHubBrowser,
            Nav.back(reading = false, screen = Screen.HubBrowser, hasOpenPane = false),
        )
        // …and an open conversation behind it does not change that. It is still there
        // afterwards; the shelf is simply what he was looking at a moment ago.
        assertEquals(
            Back.CloseHubBrowser,
            Nav.back(reading = false, screen = Screen.HubBrowser, hasOpenPane = true),
        )
    }

    /** The reader still outranks it, like everything else. */
    @Test
    fun `the reader outranks the hub browser`() {
        assertEquals(
            Back.CloseReader,
            Nav.back(reading = true, screen = Screen.HubBrowser, hasOpenPane = true),
        )
    }

    /**
     * ⚠️⚠️ Presence. Reading his own files is *not* being in a conversation, so nothing
     * is covered and any channel may still buzz his arm — the same rule that applies to
     * the other detours, and the one that silenced his arm all evening when it was wrong.
     */
    @Test
    fun `browsing the hub covers no channel`() {
        assertEquals(Pane.Detour, Nav.pane(reading = false, screen = Screen.HubBrowser, hasChannel = true))
        assertEquals(
            null,
            Nav.covered(
                reading = false,
                screen = Screen.HubBrowser,
                openPane = "%3",
                hasChannel = true,
            ),
        )
    }

    /** Nothing stacked: Back is the system's, not ours. */
    @Test
    fun `back does nothing at the root`() {
        assertEquals(
            null,
            Nav.back(reading = false, screen = Screen.Channels, hasOpenPane = false),
        )
    }

    // --- ★★ what presence covers, i.e. what is allowed to buzz -----------------

    /**
     * ★★ **The silent arm.** The app told the hub it covered every channel at once, so
     * the hub correctly decided nothing was worth interrupting him for and suppressed
     * every push — his log read `presence registered (covers_all)` and `roam-msg` said
     * `no push (covered by tmux-input, roam-app)` all evening. The buzz path was fine.
     *
     * Owner's rule, verbatim: *"haptic and buzz when I'm actually on that device, and
     * I'm not in the active channel at the time, that's it."*
     */
    @Test
    fun `an open thread covers itself and nothing else`() {
        assertEquals(
            "%3",
            Nav.covered(
                reading = false,
                screen = Screen.Channels,
                openPane = "%3",
                hasChannel = true,
            ),
        )
    }

    /** ⚠️ On the list nothing is covered — a message on ANY channel must reach him. */
    @Test
    fun `the channel list covers nothing`() {
        assertEquals(
            null,
            Nav.covered(
                reading = false,
                screen = Screen.Channels,
                openPane = null,
                hasChannel = false,
            ),
        )
    }

    /** Reading one message in full is still being in that conversation. */
    @Test
    fun `the reader still covers the thread it was opened from`() {
        assertEquals(
            "%3",
            Nav.covered(
                reading = true,
                screen = Screen.Channels,
                openPane = "%3",
                hasChannel = true,
            ),
        )
    }

    /**
     * ⚠️ A detour is drawn *over* the thread and `openPane` deliberately stays set so
     * Back returns to it — but he is looking at Home Assistant, not at the conversation,
     * so the conversation may buzz him. Claiming otherwise here is the same lie as
     * `covers_all`, just smaller.
     */
    @Test
    fun `a detour over an open thread covers nothing`() {
        for (s in listOf(Screen.HomeAssistant, Screen.Apps, Screen.Controls)) {
            assertEquals(
                "$s is not the conversation",
                null,
                Nav.covered(reading = false, screen = s, openPane = "%3", hasChannel = true),
            )
        }
    }

    /** ⚠️ A pane whose channel has gone away draws nothing, so it covers nothing. */
    @Test
    fun `a pane with no channel behind it covers nothing`() {
        assertEquals(
            null,
            Nav.covered(
                reading = false,
                screen = Screen.Channels,
                openPane = "%3",
                hasChannel = false,
            ),
        )
    }

    /**
     * ★ **Coverage never outlives what is drawn.** The rule that broke was maintained by
     * hand at each navigation site; this pins it to [Nav.pane] in every state instead, so
     * a new screen cannot quietly start suppressing his notifications.
     */
    @Test
    fun `only a visible thread is ever covered`() {
        val screens = listOf(Screen.Channels, Screen.HomeAssistant, Screen.Apps, Screen.Controls)
        for (reading in listOf(false, true)) {
            for (screen in screens) {
                for (has in listOf(false, true)) {
                    val covered = Nav.covered(reading, screen, "%3", has)
                    val visible = Nav.pane(reading, screen, has)
                    assertEquals(
                        "reading=$reading screen=$screen hasChannel=$has",
                        if (visible == Pane.Thread || visible == Pane.Reader) "%3" else null,
                        covered,
                    )
                }
            }
        }
    }
}
