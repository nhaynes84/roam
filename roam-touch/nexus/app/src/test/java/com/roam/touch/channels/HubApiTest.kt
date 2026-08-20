package com.roam.touch.channels

import com.roam.touch.channels.net.HubApi
import com.roam.touch.channels.net.HubConfig
import com.roam.touch.channels.net.HubHttpException
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test

/**
 * The REST surface against a real HTTP server — real sockets, real headers, real status
 * codes. A mocked client would let the URL-encoding bug this suite is here to prevent
 * pass unnoticed, because a mock would be written from the same misunderstanding as the
 * code.
 */
class HubApiTest {

    private lateinit var server: MockWebServer
    private lateinit var api: HubApi

    @Before
    fun setUp() {
        server = MockWebServer().also { it.start() }
        api = HubApi(
            HubConfig(
                host = server.hostName,
                port = server.port,
                token = "test-token",
            )
        )
    }

    @After
    fun tearDown() = server.shutdown()

    private fun json(body: String, code: Int = 200) =
        server.enqueue(MockResponse().setResponseCode(code).setBody(body))

    // -- pane ids in URLs ---------------------------------------------------

    @Test
    fun `a pane id loses its percent before it reaches the path`() = runBlocking {
        // `%` is the URL escape character. Left in, OkHttp encodes it to %25 and the hub
        // sees a different pane — the single worst failure for a device whose job is
        // "send this to exactly that".
        json("""{"pane_id":"%3","events":[],"latest_event_id":0}""")
        api.history("%3")
        assertEquals("/channels/3/history?limit=200", server.takeRequest().path)
    }

    @Test
    fun `a pane id already stripped is left alone`() = runBlocking {
        json("""{"pane_id":"%3","events":[],"latest_event_id":0}""")
        api.history("3")
        assertTrue(server.takeRequest().path!!.startsWith("/channels/3/history"))
    }

    // -- auth ---------------------------------------------------------------

    @Test
    fun `every authenticated call carries the bearer token`() = runBlocking {
        json("""{"channels":[],"latest_event_id":0,"server_time":1.0}""")
        api.channels()
        assertEquals("Bearer test-token", server.takeRequest().getHeader("Authorization"))
    }

    @Test
    fun `health carries no token because the hub does not want one`() = runBlocking {
        json("""{"ok":true}""")
        assertTrue(api.health())
        assertEquals(null, server.takeRequest().getHeader("Authorization"))
    }

    @Test
    fun `health returns false rather than throwing when nothing answers`() = runBlocking {
        server.shutdown()
        assertFalse(api.health())
    }

    // -- errors, in the hub's own terms ------------------------------------

    @Test
    fun `a dead pane reports as a dead pane, not as a generic failure`() = runBlocking {
        json("""{"detail":"channel %3 is not live; nothing was sent"}""", code = 404)
        try {
            api.send("%3", "continue")
            fail("expected 404")
        } catch (e: HubHttpException) {
            assertTrue(e.isNotLive)
            assertEquals("pane is gone", e.shortReason())
            assertTrue(e.detail.contains("nothing was sent"))
        }
    }

    @Test
    fun `a refused token is distinguishable from an unreachable hub`() = runBlocking {
        json("""{"detail":"missing bearer token"}""", code = 401)
        try {
            api.channels()
            fail("expected 401")
        } catch (e: HubHttpException) {
            assertTrue(e.isUnauthorised)
            assertEquals("token rejected", e.shortReason())
        }
    }

    @Test
    fun `every documented status maps to something a wearer can act on`() = runBlocking {
        val cases = mapOf(
            400 to "bad pane id", 404 to "pane is gone", 422 to "empty message",
            502 to "tmux refused", 503 to "tmux down", 418 to "hub error 418",
        )
        cases.forEach { (code, expected) ->
            json("""{"detail":"x"}""", code = code)
            try {
                api.channels()
                fail("expected $code")
            } catch (e: HubHttpException) {
                assertEquals(expected, e.shortReason())
            }
        }
    }

    @Test
    fun `an error with no detail body still produces a usable message`() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(502).setBody("<html>nope</html>"))
        try {
            api.channels()
            fail("expected 502")
        } catch (e: HubHttpException) {
            assertTrue(e.isTmuxRefusal)
        }
    }

    // -- sending ------------------------------------------------------------

    @Test
    fun `sending text submits it`() = runBlocking {
        json("""{"event":{"id":1,"pane_id":"%3","kind":"sent","body":"continue"}}""")
        api.send("%3", "continue")
        val req = server.takeRequest()
        assertEquals("/channels/3/send", req.path)
        val body = req.body.readUtf8()
        assertTrue(body.contains("\"text\":\"continue\""))
        assertTrue(body.contains("\"enter\":true"))
        assertTrue(body.contains("\"origin\":\"roam-app\""))
    }

    // -- interrupt and kill: endpoints, never control bytes through send -----

    /**
     * ⚠️ These used to be raw bytes through `/send` (`enter:false`), and the hub stored
     * them as `sent` events he "said". Since 1.5.0 `/send` REJECTS C0 control characters
     * with 400, and the real endpoints record a `control` event instead.
     */
    @Test
    fun `an interrupt is its own endpoint, not a control byte through send`() = runBlocking {
        json(
            """{"event":{"id":1,"pane_id":"%3","kind":"control","body":"escape"},
            "channel":{"pane_id":"%3","status":"idle","live":true}}"""
        )
        api.interrupt("%3")
        val req = server.takeRequest()
        assertEquals("/channels/3/interrupt", req.path)
        assertEquals("POST", req.method)
        val body = req.body.readUtf8()
        assertTrue(body, body.contains("\"action\":\"escape\""))
        assertTrue(body, body.contains("\"origin\":\"roam-app\""))
        assertFalse("no control byte anywhere near the wire", body.contains("\\u001b"))
    }

    @Test
    fun `the kill is the kill endpoint, and carries only its origin`() = runBlocking {
        json(
            """{"event":{"id":1,"pane_id":"%3","kind":"control","body":"kill"},
            "channel":{"pane_id":"%3","status":"dead","live":false}}"""
        )
        api.kill("%3")
        val req = server.takeRequest()
        assertEquals("/channels/3/kill", req.path)
        assertEquals("POST", req.method)
        val body = req.body.readUtf8()
        assertTrue(body, body.contains("\"origin\":\"roam-app\""))
        assertFalse("the two Ctrl-Cs are history, not a payload", body.contains("\\u0003"))
    }

    // -- new session ----------------------------------------------------------

    @Test
    fun `creating a session posts the command and label and decodes the 201 channel`() =
        runBlocking {
            json(
                """{"channel":{"pane_id":"%9","label":"refactor the parser",
                "status":"idle","live":true,"command":"claude"}}""",
                code = 201,
            )
            val ch = api.createChannel(command = "claude", label = "refactor the parser")
            val req = server.takeRequest()
            assertEquals("/channels", req.path)
            assertEquals("POST", req.method)
            val body = req.body.readUtf8()
            assertTrue(body, body.contains("\"command\":\"claude\""))
            assertTrue(body, body.contains("\"label\":\"refactor the parser\""))
            assertTrue(body, body.contains("\"origin\":\"roam-app\""))
            assertEquals("%9", ch.paneId)
            assertTrue(ch.live)
        }

    // -- catch-up and expansion --------------------------------------------

    @Test
    fun `catch-up asks for everything after the cursor, once`() = runBlocking {
        json("""{"events":[],"latest_event_id":80}""")
        api.events(since = 42, limit = 500)
        assertEquals("/events?since=42&limit=500", server.takeRequest().path)
    }

    @Test
    fun `expanding an event asks for it untrimmed by id`() = runBlocking {
        json("""{"event":{"id":412,"pane_id":"%0","kind":"outcome","body":"whole thing"}}""")
        val e = api.event(412)
        assertEquals("/events/412", server.takeRequest().path)
        assertEquals("whole thing", e.body)
    }

    // -- presence -----------------------------------------------------------

    /**
     * ★★ **Presence covers the open channel, not everything.** Claiming `covers_all` told
     * the hub he had eyes on every channel at once, so it correctly decided nothing was
     * worth interrupting him for and his arm went silent all evening. The buzz path was
     * never broken — it was never asked to run.
     */
    @Test
    fun `presence covers only the channel on screen`() = runBlocking {
        json("""{"source":"roam-app","presence":{"present":true}}""")
        api.registerPresence("%3")
        val req = server.takeRequest()
        assertEquals("/presence", req.path)
        val body = req.body.readUtf8()
        assertTrue(body.contains("\"source\":\"roam-app\""))
        assertTrue(body, body.contains("\"covers_all\":false"))
        assertTrue(body, body.contains("\"panes\":[\"%3\"]"))
        assertTrue(body.contains("\"ttl_s\":${HubApi.PRESENCE_TTL_S}"))
    }

    /** ⚠️ On the list, nothing is covered — a message on any channel should reach him. */
    @Test
    fun `presence with no thread open covers nothing`() = runBlocking {
        json("""{"source":"roam-app","presence":{"present":true}}""")
        api.registerPresence(null)
        val body = server.takeRequest().body.readUtf8()
        assertTrue(body, body.contains("\"covers_all\":false"))
        assertTrue(body, body.contains("\"panes\":[]"))
    }

    @Test
    fun `dropping presence uses the source id in the path`() = runBlocking {
        json("""{"removed":true}""")
        api.clearPresence()
        val req = server.takeRequest()
        assertEquals("/presence/roam-app", req.path)
        assertEquals("DELETE", req.method)
    }

    @Test
    fun `a failed presence drop is swallowed, never fatal`() = runBlocking {
        // Backgrounding must not be able to crash anything; the source expires anyway.
        server.shutdown()
        api.clearPresence()
    }
}
