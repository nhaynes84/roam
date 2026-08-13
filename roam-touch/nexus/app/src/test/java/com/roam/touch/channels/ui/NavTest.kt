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

    /** ⚠️ Every branch of [Nav.back] must mirror [Nav.pane], in every state. */
    @Test
    fun `back always closes whatever pane is on top`() {
        val screens = listOf(Screen.Channels, Screen.HomeAssistant, Screen.Apps, Screen.Controls)
        for (reading in listOf(false, true)) {
            for (screen in screens) {
                for (open in listOf(false, true)) {
                    val expected = when (Nav.pane(reading, screen, open)) {
                        Pane.Reader -> Back.CloseReader
                        Pane.Detour -> Back.CloseDetour
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

    /** Nothing stacked: Back is the system's, not ours. */
    @Test
    fun `back does nothing at the root`() {
        assertEquals(
            null,
            Nav.back(reading = false, screen = Screen.Channels, hasOpenPane = false),
        )
    }
}
