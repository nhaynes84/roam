package com.roam.touch.channels

import com.roam.touch.channels.model.ControlKeys
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

    @Test
    fun `an interrupt is a literal control byte with no Enter behind it`() = runBlocking {
        // ⚠️ The hub has no interrupt endpoint. This works precisely because /send types
        // literally: a lone 0x1B reaches the pane's tty. An Enter after it would submit
        // a stray empty prompt into the session he was trying to quieten.
        json("""{"event":{"id":1,"pane_id":"%3","kind":"sent","body":""}}""")
        api.send("%3", ControlKeys.INTERRUPT.bytes, enter = false)
        val body = server.takeRequest().body.readUtf8()
        assertTrue("escaped as \\u001b on the wire", body.contains("\\u001b"))
        assertTrue(body.contains("\"enter\":false"))
    }

    @Test
    fun `the kill is two Ctrl-Cs in one payload`() = runBlocking {
        // One payload, so a reconnect cannot separate them into two half-kills.
        json("""{"event":{"id":1,"pane_id":"%3","kind":"sent","body":"x"}}""")
        api.send("%3", ControlKeys.KILL.bytes.repeat(2), enter = false)
        val body = server.takeRequest().body.readUtf8()
        assertEquals(2, Regex("\\\\u0003").findAll(body).count())
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

    @Test
    fun `presence registers as a covers-all app source with a TTL`() = runBlocking {
        json("""{"source":"roam-app","presence":{"present":true}}""")
        api.registerPresence()
        val req = server.takeRequest()
        assertEquals("/presence", req.path)
        val body = req.body.readUtf8()
        assertTrue(body.contains("\"source\":\"roam-app\""))
        assertTrue(body.contains("\"covers_all\":true"))
        assertTrue(body.contains("\"ttl_s\":${HubApi.PRESENCE_TTL_S}"))
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
