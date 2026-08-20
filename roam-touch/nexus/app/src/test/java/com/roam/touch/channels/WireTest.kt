package com.roam.touch.channels

import com.roam.touch.channels.model.ChannelStatus
import com.roam.touch.channels.model.ChannelsResponse
import com.roam.touch.channels.model.ControlKeys
import com.roam.touch.channels.model.Event
import com.roam.touch.channels.model.EventKind
import com.roam.touch.channels.model.FrameParser
import com.roam.touch.channels.model.HubFrame
import com.roam.touch.channels.model.HubJson
import com.roam.touch.channels.net.Backoff
import com.roam.touch.channels.ui.Format
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Decoding, against payloads copied verbatim off the running hub. The lesson from the
 * hook work is written into this file: capture the real payload, do not guess the schema.
 */
class WireTest {

    /** Captured from `GET /channels` on talos, 2026-08-12. */
    private val realChannels = """
    {"channels":[{"pane_id":"%0","label":"◑ Roam Touch rebuild discussion","session":"main",
    "window":1,"index":1,"command":"claude.exe","live":true,"status":"idle","archived":false,
    "first_seen":1786511692.204854,"last_seen":1786516980.192878,
    "last_output_at":1786516979.278782,"idle_s":0.9,"event_count":47,
    "last_event":{"id":75,"pane_id":"%0","kind":"outcome","body":"Running. Scoped to the app.",
    "summary":"Running. Scoped to the app.","body_chars":685,"body_truncated":false,
    "meta":{"source":"claude-hook","answer_source":"hook_payload"},"ts":1786516961.840132,
    "archived":false}},
    {"pane_id":"%3","label":"roamprobe:1.1","session":"roamprobe","window":null,"index":null,
    "command":null,"live":false,"status":"dead","archived":false,"first_seen":1786515094.2,
    "last_seen":1786515325.7,"last_output_at":1786515107.0,"idle_s":null,"event_count":3,
    "last_event":null}],
    "latest_event_id":75,"server_time":1786516980.193595}
    """.trimIndent()

    @Test
    fun `a real channels payload decodes with its nulls intact`() {
        val r = HubJson.decodeFromString<ChannelsResponse>(realChannels)
        assertEquals(2, r.channels.size)
        assertEquals(75L, r.latestEventId)

        val live = r.channels[0]
        assertEquals(ChannelStatus.IDLE, live.statusEnum)
        assertEquals("◑ Roam Touch rebuild discussion", live.displayLabel)
        assertEquals("0", live.urlKey)
        assertEquals(EventKind.OUTCOME, live.lastEvent!!.kindEnum)

        val dead = r.channels[1]
        assertEquals(ChannelStatus.DEAD, dead.statusEnum)
        assertFalse(dead.live)
        assertNull("idle_s must stay null, never coerce to 0", dead.idleS)
        assertNull(dead.window)
    }

    @Test
    fun `a hub that grows new fields does not break the client`() {
        // The hub gained `coverage` and `last_input_source` mid-build. An old client
        // must keep working; a new field must not empty the panel.
        val withExtras = """{"channels":[{"pane_id":"%0","status":"idle","live":true,
        "last_input_source":"app","last_input_at":1786511490.0,"future_field":{"a":1},
        "event_count":1}],"latest_event_id":9,"server_time":1.0}""".trimIndent()
        val r = HubJson.decodeFromString<ChannelsResponse>(withExtras)
        assertEquals("app", r.channels.first().lastInputSource)
    }

    @Test
    fun `an echo receipt names the send it duplicates`() {
        // Captured from the live hub, 2026-08-12. `echo_of` is a JSON number.
        val e = HubJson.decodeFromString<Event>(
            """{"id":341,"pane_id":"%0","kind":"receipt","body":"Not done yet.",
            "summary":"Not done yet.","meta":{"source":"claude-hook","echo_of":340},
            "ts":1786516984.1}""".trimIndent()
        )
        assertEquals(340L, e.echoOf)
    }

    @Test
    fun `a keyboard prompt has no echo reference`() {
        val e = HubJson.decodeFromString<Event>(
            """{"id":341,"pane_id":"%0","kind":"receipt","body":"run the tests",
            "meta":{"source":"claude-hook"},"ts":1786516984.1}"""
        )
        assertNull(e.echoOf)
    }

    @Test
    fun `an unknown event kind is kept, not dropped`() {
        val e = Fx.event(id = 1, kind = "deployment")
        assertEquals(EventKind.OTHER, e.kindEnum)
        assertEquals("deployment", e.kind)
    }

    // -- frames -------------------------------------------------------------

    @Test
    fun `hello carries the channel list and the cursor`() {
        val f = FrameParser.parse(
            """{"type":"hello","protocol":1,"version":"1.0.0","server_time":1786516980.1,
            "latest_event_id":75,"channels":[{"pane_id":"%0","status":"idle"}],
            "presence":{"present":true,"covers_all":false,"covered_panes":["%0"],
            "sources":[],"server_time":1786516980.1}}"""
        )
        assertTrue(f is HubFrame.Hello)
        f as HubFrame.Hello
        assertEquals(75L, f.latestEventId)
        assertEquals(1, f.channels.size)
        assertEquals(listOf("%0"), f.presence!!.coveredPanes)
    }

    @Test
    fun `activity decodes the pane to timestamp map`() {
        val f = FrameParser.parse(
            """{"type":"activity","panes":{"%0":1786511500.3,"%1":1786511499.0},
            "server_time":1786511500.4}"""
        ) as HubFrame.Activity
        assertEquals(2, f.panes.size)
        assertEquals(1786511500.3, f.panes["%0"]!!, 0.001)
    }

    @Test
    fun `presence arrives inline, not nested`() {
        val f = FrameParser.parse(
            """{"type":"presence","present":true,"covers_all":true,"covered_panes":[],
            "sources":[{"id":"roam-app","kind":"app","covers_all":true}],
            "server_time":1.0}"""
        ) as HubFrame.PresenceChanged
        assertTrue(f.presence.coversAll)
        assertEquals("roam-app", f.presence.sources.first().id)
    }

    @Test
    fun `desync and error frames are recognised`() {
        assertEquals(
            HubFrame.Desync(412),
            FrameParser.parse("""{"type":"desync","latest_event_id":412}""")
        )
        assertEquals(
            HubFrame.Error("unauthorised"),
            FrameParser.parse("""{"type":"error","detail":"unauthorised"}""")
        )
    }

    @Test
    fun `an unknown frame type is surfaced, not fatal`() {
        val f = FrameParser.parse("""{"type":"weather","temp":21}""")
        assertEquals(HubFrame.Unknown("weather"), f)
    }

    @Test
    fun `garbage on the socket returns null instead of throwing`() {
        // A frame that kills the parser would kill the connection, and a wearer who
        // sees nothing arriving cannot tell that from a quiet afternoon.
        assertNull(FrameParser.parse("not json at all"))
        assertNull(FrameParser.parse("""{"no_type":true}"""))
        assertNull(FrameParser.parse(""))
    }

    // -- display rules ------------------------------------------------------

    @Test
    fun `expansion is not offered for something with nothing behind it`() {
        // Seen on the device: an `opened` event offered "full text · 16 chars", which is
        // clutter that teaches him to ignore the affordance everywhere else.
        val opened = Fx.event(id = 1, kind = "opened", body = "✳ Augment things",
            summary = "Augment things", chars = 16)
        assertFalse(opened.hasMore())
    }

    @Test
    fun `expansion is offered when the payload was trimmed`() {
        val trimmed = Fx.event(id = 2, body = "first 4096 chars...", chars = 9000,
            truncated = true)
        assertTrue(trimmed.hasMore())
    }

    @Test
    fun `expansion is offered when the summary stands in for a block`() {
        val elided = Fx.event(
            id = 3,
            body = "Here it is:\n```\nrsync -a\nexit 23\n```\nthat is the failure",
            summary = "Here it is: [code, 2 lines] that is the failure",
        )
        assertTrue(elided.hasMore())
        val table = Fx.event(id = 4, body = "x".repeat(60), summary = "[table, 4 rows] done")
        assertTrue(table.hasMore())
    }

    @Test
    fun `expansion is offered when the body is materially longer`() {
        val long = Fx.event(id = 5, body = "a".repeat(500), summary = "a".repeat(200))
        assertTrue(long.hasMore())
        val barely = Fx.event(id = 6, body = "a".repeat(210), summary = "a".repeat(200))
        assertFalse(barely.hasMore())
    }

    @Test
    fun `a control byte renders as an action, never as text he said`() {
        val esc = Fx.event(id = 7, kind = "sent", body = ControlKeys.INTERRUPT.bytes,
            summary = ControlKeys.INTERRUPT.bytes)
        assertEquals(ControlKeys.Key.ESC, esc.controlKey)
        assertEquals("INTERRUPT", esc.displaySummary())
        assertFalse(esc.hasMore())

        val kill = Fx.event(id = 8, kind = "sent", body = ControlKeys.KILL.bytes.repeat(2))
        assertEquals(ControlKeys.Key.CTRL_C, kill.controlKey)
        assertEquals("STOP", kill.displaySummary())
    }

    /** Since hub 1.5.0 an interrupt/kill is a `control` event whose body names it. */
    @Test
    fun `a control event renders as the action it records`() {
        val esc = Fx.event(id = 10, kind = "control", body = "escape", summary = "escape")
        assertEquals(ControlKeys.Key.ESC, esc.controlKey)
        assertEquals("INTERRUPT", esc.displaySummary())

        val kill = Fx.event(id = 11, kind = "control", body = "kill", summary = "kill")
        assertEquals(ControlKeys.Key.KILL_PANE, kill.controlKey)
        assertEquals("KILL", kill.displaySummary())
    }

    @Test
    fun `ordinary text is never mistaken for a control key`() {
        assertNull(Fx.event(id = 9, kind = "sent", body = "continue").controlKey)
        assertNull(Fx.event(id = 10, kind = "outcome",
            body = ControlKeys.INTERRUPT.bytes).controlKey)
    }

    @Test
    fun `a summary-less event still shows something`() {
        val e = Fx.event(id = 11, body = "line one\nline two", summary = "")
        assertEquals("line one", e.displaySummary())
        val nothing = Fx.event(id = 12, kind = "closed", body = "", summary = "")
        assertEquals("closed", nothing.displaySummary())
    }
}

/** The reconnect schedule `API.md` §4 step 8 asks for, exactly. */
class BackoffTest {

    @Test
    fun `backoff doubles then caps at thirty seconds`() {
        assertEquals(0L, Backoff.delayMs(0))
        assertEquals(1_000L, Backoff.delayMs(1))
        assertEquals(2_000L, Backoff.delayMs(2))
        assertEquals(4_000L, Backoff.delayMs(3))
        assertEquals(8_000L, Backoff.delayMs(4))
        assertEquals(16_000L, Backoff.delayMs(5))
        assertEquals(30_000L, Backoff.delayMs(6))
    }

    @Test
    fun `a long outage never exceeds the cap or overflows`() {
        (7..64).forEach { assertEquals("attempt $it", Backoff.MAX_MS, Backoff.delayMs(it)) }
    }
}

/** Durations for a glance; the boundaries are where these go wrong unnoticed. */
class FormatTest {

    @Test
    fun `durations stay short at every boundary`() {
        assertEquals("0s", Format.duration(0))
        assertEquals("59s", Format.duration(59_999))
        assertEquals("1m", Format.duration(60_000))
        assertEquals("59m", Format.duration(59 * 60_000L))
        assertEquals("1h", Format.duration(3_600_000))
        assertEquals("1h12m", Format.duration(72 * 60_000L))
        assertEquals("23h59m", Format.duration(86_340_000))
        assertEquals("1d", Format.duration(86_400_000))
        assertEquals("3d", Format.duration(3 * 86_400_000L))
    }

    @Test
    fun `a negative duration cannot render as garbage`() {
        // Clock skew between phone and hub can make "now minus then" go negative.
        assertEquals("0s", Format.duration(-5_000))
    }

    @Test
    fun `character counts are readable at a glance`() {
        assertEquals("999 chars", Format.chars(999))
        assertEquals("4.1k chars", Format.chars(4096))
    }

    @Test
    fun `read cursors survive a round trip through storage`() {
        val cursors = mapOf("%0" to 71L, "%11" to 3L)
        assertEquals(cursors, Settings.decode(Settings.encode(cursors)))
        assertEquals(emptyMap<String, Long>(), Settings.decode(null))
        assertEquals(emptyMap<String, Long>(), Settings.decode(""))
        assertEquals(emptyMap<String, Long>(), Settings.decode("garbage;=;x=y"))
    }
}
