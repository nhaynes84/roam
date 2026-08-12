package com.roam.touch.channels

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * ★ The list is a queue: *which session needs me first*. These tests are the definition
 * of "needs me" — if the order here is wrong, the device is a feed reader on a forearm.
 */
class QueueTest {

    private val now = Fx.NOW_MS

    private fun idle(pane: String, secondsAgo: Int) = Fx.channel(
        pane = pane, status = "idle",
        lastOutputAt = Fx.T0 - secondsAgo, lastSeen = Fx.T0 - secondsAgo,
    )

    private fun working(pane: String, quietSeconds: Int) = Fx.channel(
        pane = pane, status = "working",
        lastOutputAt = Fx.T0 - quietSeconds, lastSeen = Fx.T0,
    )

    private fun dead(pane: String) = Fx.channel(
        pane = pane, status = "dead", live = false, lastOutputAt = Fx.T0 - 600,
    )

    private fun withUnread(state: ChannelsState, pane: String, id: Long) =
        ChannelReducer.applyEvent(state, Fx.event(id = id, pane = pane, kind = "outcome"))

    @Test
    fun `unread outranks everything else`() {
        var s = Fx.stateWith(working("%1", 1), idle("%2", 5), dead("%3"))
        s = withUnread(s, "%2", 50)
        assertEquals("%2", Queue.order(s, now).first().paneId)
    }

    @Test
    fun `a dead channel with unread still comes first`() {
        // API.md: the outcome you were waiting for may be the last thing that pane ever
        // said. Sorting death below "nothing to see" would bury exactly that.
        var s = Fx.stateWith(idle("%1", 2), dead("%9"))
        s = withUnread(s, "%9", 50)
        assertEquals("%9", Queue.order(s, now).first().paneId)
    }

    @Test
    fun `a session that has gone quiet mid-work outranks one still producing output`() {
        // This is the kill decision. It is the second most urgent thing on the screen.
        val s = Fx.stateWith(working("%1", 1), working("%2", 300))
        assertEquals(listOf("%2", "%1"), Queue.order(s, now).map { it.paneId })
    }

    @Test
    fun `working outranks idle and idle outranks dead`() {
        val s = Fx.stateWith(dead("%3"), idle("%2", 3), working("%1", 1))
        assertEquals(listOf("%1", "%2", "%3"), Queue.order(s, now).map { it.paneId })
    }

    @Test
    fun `within a rank the most recent wins`() {
        val s = Fx.stateWith(idle("%1", 600), idle("%2", 5), idle("%3", 60))
        assertEquals(listOf("%2", "%3", "%1"), Queue.order(s, now).map { it.paneId })
    }

    @Test
    fun `ordering is stable for identical channels`() {
        val a = Fx.channel(pane = "%1", lastOutputAt = Fx.T0, lastSeen = Fx.T0)
        val b = Fx.channel(pane = "%2", lastOutputAt = Fx.T0, lastSeen = Fx.T0)
        val s = Fx.stateWith(b, a)
        assertEquals(listOf("%1", "%2"), Queue.order(s, now).map { it.paneId })
    }

    @Test
    fun `reading a channel demotes it out of the top slot`() {
        var s = Fx.stateWith(working("%1", 1), idle("%2", 5))
        s = withUnread(s, "%2", 50)
        assertEquals("%2", Queue.order(s, now).first().paneId)
        s = ChannelReducer.markRead(s, "%2")
        assertEquals("%1", Queue.order(s, now).first().paneId)
    }

    @Test
    fun `every channel keeps a place in the list`() {
        val s = Fx.stateWith(dead("%3"), idle("%2", 3), working("%1", 1))
        assertEquals(3, Queue.order(s, now).size)
        assertTrue(Queue.order(s, now).map { it.paneId }.containsAll(listOf("%1", "%2", "%3")))
    }
}

/** The three states the wearer must be able to tell apart at a glance. */
class LivenessTest {

    @Test
    fun `producing output reads as working`() {
        val s = Fx.stateWith(Fx.channel(status = "working", lastOutputAt = Fx.T0 - 2))
        val l = Liveliness.of(s, s.channels.first(), Fx.NOW_MS)
        assertTrue(l is Liveness.Working)
        assertEquals(2_000L, (l as Liveness.Working).idleMs)
    }

    @Test
    fun `working with nothing coming out reads as quiet, with the number`() {
        val s = Fx.stateWith(Fx.channel(status = "working", lastOutputAt = Fx.T0 - 240))
        val l = Liveliness.of(s, s.channels.first(), Fx.NOW_MS)
        assertTrue(l is Liveness.Quiet)
        assertEquals(240_000L, (l as Liveness.Quiet).idleMs)
    }

    @Test
    fun `the quiet threshold is ten samples of silence, not one`() {
        val justUnder = Fx.channel(status = "working", lastOutputAt = Fx.T0 - 19)
        val justOver = Fx.channel(status = "working", lastOutputAt = Fx.T0 - 21)
        assertTrue(
            Liveliness.of(Fx.stateWith(justUnder), justUnder, Fx.NOW_MS) is Liveness.Working
        )
        assertTrue(
            Liveliness.of(Fx.stateWith(justOver), justOver, Fx.NOW_MS) is Liveness.Quiet
        )
    }

    @Test
    fun `a pane that is gone is dead even if the snapshot still says live`() {
        val ch = Fx.channel(status = "dead", live = true)
        assertEquals(Liveness.Dead, Liveliness.of(Fx.stateWith(ch), ch, Fx.NOW_MS))
    }

    @Test
    fun `an unsampled working pane is working with an unknown age, never zero`() {
        val ch = Fx.channel(status = "working", lastOutputAt = null)
        val l = Liveliness.of(Fx.stateWith(ch), ch, Fx.NOW_MS)
        assertEquals(Liveness.Working(null), l)
    }

    @Test
    fun `an unknown status degrades to unknown rather than a wrong claim`() {
        val ch = Fx.channel(status = "hibernating")
        assertEquals(Liveness.Unknown, Liveliness.of(Fx.stateWith(ch), ch, Fx.NOW_MS))
    }
}
