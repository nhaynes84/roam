package com.roam.touch.channels.ui

import com.roam.touch.channels.Fx
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * ★ The one rule the headset toggle and the rail's TALK door both obey.
 *
 * ⚠️ These cases are the reason the rule is a pure function at all: when the same
 * decision lived inside `ControlSurface.pushToTalkToggle` and inside a PTT bar at the
 * root of the channel list, only one of them could be checked without a phone — and the
 * one at the root was the one that turned out to be wrong.
 */
class VoiceEntryTest {

    @Test
    fun `a live channel wins over a more recent dead one`() {
        val dead = Fx.channel(pane = "%1", label = "dead first", live = false)
        val live = Fx.channel(pane = "%2", label = "live second", live = true)
        assertEquals("%2", VoiceEntry.target(listOf(dead, live))?.paneId)
    }

    @Test
    fun `the first live one wins, in queue order`() {
        val a = Fx.channel(pane = "%1", live = true)
        val b = Fx.channel(pane = "%2", live = true)
        assertEquals("%1", VoiceEntry.target(listOf(a, b))?.paneId)
    }

    /**
     * All dead is still somewhere to *go*: the thread has his history in it, and the
     * composer will say the pane is gone before he can lose a sentence to it.
     */
    @Test
    fun `with nothing live it still lands on a channel rather than nowhere`() {
        val dead = Fx.channel(pane = "%9", live = false)
        assertEquals("%9", VoiceEntry.target(listOf(dead))?.paneId)
    }

    /** ⚠️ Null means *say so*. It must never be turned into "open something". */
    @Test
    fun `no channels resolves to nothing, not to a guess`() {
        assertNull(VoiceEntry.target(emptyList()))
    }
}
