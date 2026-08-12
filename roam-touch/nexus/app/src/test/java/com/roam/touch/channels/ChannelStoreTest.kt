package com.roam.touch.channels

import com.roam.touch.channels.model.HubFrame
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The reducer carries every awkward case this device actually hits: a socket that died
 * mid-doze, a backlog replayed on top of a fresh snapshot, an `activity` frame for a
 * pane the list has not heard of. All of them are cheap here and expensive on a wrist.
 */
class ChannelStoreTest {

    private val base = Fx.stateWith(Fx.channel())

    // -- appending ----------------------------------------------------------

    @Test
    fun `event is appended and becomes the cursor`() {
        val s = ChannelReducer.applyEvent(base, Fx.event(id = 10))
        assertEquals(1, s.thread("%0").size)
        assertEquals(10L, s.cursor)
    }

    @Test
    fun `re-delivering the same event changes nothing`() {
        // A backlog replay racing a history fetch delivers the same id twice. If that
        // duplicated rows, every reconnect would visibly corrupt the thread.
        val once = ChannelReducer.applyEvent(base, Fx.event(id = 10))
        val twice = ChannelReducer.applyEvent(once, Fx.event(id = 10))
        assertEquals(1, twice.thread("%0").size)
        assertEquals(10L, twice.cursor)
    }

    @Test
    fun `events out of order are sorted by id`() {
        var s = ChannelReducer.applyEvent(base, Fx.event(id = 12))
        s = ChannelReducer.applyEvent(s, Fx.event(id = 11))
        assertEquals(listOf(11L, 12L), s.thread("%0").map { it.id })
        assertEquals(12L, s.cursor)
    }

    @Test
    fun `replayed old event does not drag last_event backwards`() {
        // The snapshot already knows about id 20. A catch-up sweep re-delivering id 5
        // must not make the list show a five-events-ago answer as the newest thing.
        val snapshot = Fx.stateWith(
            Fx.channel(lastEvent = Fx.event(id = 20, body = "newest"), eventCount = 20)
        )
        val s = ChannelReducer.applyEvent(snapshot, Fx.event(id = 5, body = "ancient"))
        assertEquals(20L, s.channel("%0")!!.lastEvent!!.id)
        assertEquals("stale event must not inflate the count", 20, s.channel("%0")!!.eventCount)
    }

    @Test
    fun `genuinely new event advances last_event and the count`() {
        val snapshot = Fx.stateWith(
            Fx.channel(lastEvent = Fx.event(id = 20), eventCount = 20)
        )
        val s = ChannelReducer.applyEvent(snapshot, Fx.event(id = 21, body = "fresh"))
        assertEquals(21L, s.channel("%0")!!.lastEvent!!.id)
        assertEquals(21, s.channel("%0")!!.eventCount)
    }

    // -- frames -------------------------------------------------------------

    @Test
    fun `hello replaces the channel list but leaves an established cursor alone`() {
        // backlog arrives right after hello. Advancing the cursor to the hub's latest
        // here would skip everything the backlog is about to replay if the socket dies
        // in between.
        val started = base.copy(cursor = 40L)
        val s = ChannelReducer.applyFrame(
            started,
            HubFrame.Hello(1, "1.0.0", Fx.T0, latestEventId = 99, channels = listOf(
                Fx.channel(pane = "%9", label = "new pane")
            ), presence = null),
            Fx.NOW_MS,
        )
        assertEquals(listOf("%9"), s.channels.map { it.paneId })
        assertEquals(40L, s.cursor)
    }

    @Test
    fun `hello seeds the cursor only on a cold start`() {
        val s = ChannelReducer.applyFrame(
            ChannelsState(),
            HubFrame.Hello(1, "1.0.0", Fx.T0, 99, listOf(Fx.channel()), null),
            Fx.NOW_MS,
        )
        assertEquals(99L, s.cursor)
    }

    @Test
    fun `backlog applies every event in order`() {
        val s = ChannelReducer.applyFrame(
            base.copy(cursor = 5L),
            HubFrame.Backlog(5, listOf(Fx.event(id = 6), Fx.event(id = 7))),
            Fx.NOW_MS,
        )
        assertEquals(listOf(6L, 7L), s.thread("%0").map { it.id })
        assertEquals(7L, s.cursor)
    }

    @Test
    fun `activity frame moves last_output_at and clears idle`() {
        val stale = Fx.stateWith(Fx.channel(status = "working", lastOutputAt = Fx.T0 - 300))
        val s = ChannelReducer.applyFrame(
            stale,
            HubFrame.Activity(mapOf("%0" to Fx.T0), Fx.T0),
            Fx.NOW_MS,
        )
        assertEquals(Fx.T0, s.channel("%0")!!.lastOutputAt!!, 0.001)
        assertEquals(0L, s.idleMs("%0", Fx.NOW_MS))
    }

    @Test
    fun `activity for an unknown pane is ignored rather than fatal`() {
        val s = ChannelReducer.applyFrame(
            base, HubFrame.Activity(mapOf("%42" to Fx.T0), Fx.T0), Fx.NOW_MS
        )
        assertEquals(1, s.channels.size)
    }

    @Test
    fun `history_cleared drops the thread and un-hydrates it`() {
        var s = ChannelReducer.applyHistory(base, "%0", listOf(Fx.event(id = 1)), 1)
        assertTrue(s.hydrated.contains("%0"))
        s = ChannelReducer.applyFrame(s, HubFrame.HistoryCleared("%0", 12), Fx.NOW_MS)
        assertTrue(s.thread("%0").isEmpty())
        assertFalse(s.hydrated.contains("%0"))
    }

    @Test
    fun `catch-up history does not mark a thread hydrated`() {
        val s = ChannelReducer.applyHistory(
            base, "%0", listOf(Fx.event(id = 9)), 0, hydrate = false
        )
        assertEquals(1, s.thread("%0").size)
        assertFalse(
            "opening the thread must still fetch its real history",
            s.hydrated.contains("%0")
        )
    }

    // -- unread -------------------------------------------------------------

    @Test
    fun `unread counts what the agent said and ignores what he typed`() {
        var s = base
        s = ChannelReducer.applyEvent(s, Fx.event(id = 1, kind = "sent", body = "go"))
        s = ChannelReducer.applyEvent(s, Fx.event(id = 2, kind = "receipt", body = "go"))
        s = ChannelReducer.applyEvent(s, Fx.event(id = 3, kind = "outcome"))
        s = ChannelReducer.applyEvent(s, Fx.event(id = 4, kind = "error", body = "boom"))
        s = ChannelReducer.applyEvent(s, Fx.event(id = 5, kind = "note", body = "fyi"))
        s = ChannelReducer.applyEvent(s, Fx.event(id = 6, kind = "opened", body = "x"))
        assertEquals(3, s.unreadCount("%0"))
    }

    @Test
    fun `marking read clears the badge and survives further reads`() {
        var s = ChannelReducer.applyEvent(base, Fx.event(id = 7))
        s = ChannelReducer.markRead(s, "%0")
        assertEquals(0, s.unreadCount("%0"))
        // Idempotent: re-marking must not rewind the cursor.
        s = ChannelReducer.markRead(s, "%0")
        assertEquals(7L, s.readCursors["%0"])
    }

    @Test
    fun `an event arriving after a read is unread again`() {
        var s = ChannelReducer.applyEvent(base, Fx.event(id = 7))
        s = ChannelReducer.markRead(s, "%0")
        s = ChannelReducer.applyEvent(s, Fx.event(id = 8))
        assertEquals(1, s.unreadCount("%0"))
    }

    @Test
    fun `first launch marks the whole snapshot read`() {
        val snapshot = Fx.stateWith(
            Fx.channel(pane = "%0", lastEvent = Fx.event(id = 71, pane = "%0")),
            Fx.channel(pane = "%1", lastEvent = Fx.event(id = 40, pane = "%1")),
        )
        val s = ChannelReducer.seedReadFromSnapshot(snapshot)
        assertEquals(mapOf("%0" to 71L, "%1" to 40L), s.readCursors)
    }

    // -- liveness arithmetic ------------------------------------------------

    @Test
    fun `idle is null when the hub has never sampled the pane`() {
        // API.md is explicit: null is not zero. Rendering "active now" for a pane the
        // hub has not looked at would be a lie in the one place lies are expensive.
        val s = Fx.stateWith(Fx.channel(lastOutputAt = null))
        assertNull(s.idleMs("%0", Fx.NOW_MS))
    }

    @Test
    fun `idle ages locally between frames using server skew`() {
        // The phone's clock is 60 s ahead of talos. Ageing must use the server's clock.
        val local = Fx.NOW_MS + 60_000
        val s = ChannelReducer.applyChannels(
            ChannelsState(), listOf(Fx.channel(lastOutputAt = Fx.T0)), 0, Fx.T0, local
        )
        assertEquals(0L, s.idleMs("%0", local))
        assertEquals(5_000L, s.idleMs("%0", local + 5_000))
    }

    @Test
    fun `full body from an expand is preferred over the trimmed one`() {
        val trimmed = Fx.event(id = 3, body = "start...", chars = 9000, truncated = true)
        var s = ChannelReducer.applyEvent(base, trimmed)
        assertTrue(s.needsExpansion(trimmed))
        s = ChannelReducer.applyFullBody(s, 3, "the whole thing")
        assertEquals("the whole thing", s.bodyOf(trimmed))
        assertFalse(s.needsExpansion(trimmed))
    }
}
