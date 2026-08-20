package com.roam.touch.channels

import com.roam.touch.channels.net.HubApi
import com.roam.touch.channels.net.HubConfig
import com.roam.touch.channels.net.HubSocket
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.util.concurrent.LinkedBlockingQueue

/**
 * The connection, end to end, over real sockets.
 *
 * These are the cases the device actually lives in: backgrounded and killed, doze,
 * Tailscale down, a hub that restarts under it. Per the fidelity ladder, the highest rung
 * available off-device is a real HTTP + WebSocket server, so that is what this uses —
 * MockWebServer speaks the actual protocol, including the upgrade handshake.
 */
class HubRepositoryTest {

    private companion object {
        const val PRESENCE_OK = """{"source":"roam-app","presence":{"present":true}}"""
    }

    private lateinit var server: MockWebServer
    private lateinit var repo: HubRepository
    private lateinit var cursors: FakeCursorStore
    private lateinit var scope: CoroutineScope
    private var job: Job? = null

    /** Sockets the server handed out, in order, so a test can close one deliberately. */
    private val sockets = LinkedBlockingQueue<WebSocket>()

    @Before
    fun setUp() {
        server = MockWebServer().also { it.start() }
        val config = HubConfig(server.hostName, server.port, "test-token")
        cursors = FakeCursorStore()
        repo = HubRepository(HubApi(config), HubSocket(config), cursors)
        scope = CoroutineScope(SupervisorJob())
    }

    @After
    fun tearDown() {
        job?.cancel()
        scope.cancel()
        server.shutdown()
    }

    // -- helpers ------------------------------------------------------------

    private fun channelsResponse(
        vararg panes: Pair<String, String>,
        latest: Long = 0,
    ) = MockResponse().setBody(
        """{"channels":[${
            panes.joinToString(",") { (pane, status) ->
                """{"pane_id":"$pane","label":"pane $pane","status":"$status","live":true,
                   "last_output_at":1786511500.0,"idle_s":0.4,"event_count":1}"""
            }
        }],"latest_event_id":$latest,"server_time":1786511500.0}"""
    )

    /** A WebSocket upgrade whose socket is captured so the test can drive/close it. */
    private fun socketUpgrade(onOpen: (WebSocket) -> Unit = {}) =
        MockResponse().withWebSocketUpgrade(object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: okhttp3.Response) {
                sockets.put(webSocket)
                onOpen(webSocket)
            }
        })

    private fun start() {
        job = scope.launch { repo.run(this) }
    }

    private suspend fun awaitOnline() = withTimeout(10_000) {
        while (!repo.link.value.isOnline) delay(10)
    }

    private suspend fun await(what: String = "condition", check: () -> Boolean) =
        withTimeout(10_000) {
            while (!check()) delay(10)
            true
        }.also { assertTrue(what, it) }

    /** Skip HTTP requests until the [nth] one matching [predicate] shows up. */
    private fun takeUntil(nth: Int = 1, predicate: (RecordedRequest) -> Boolean): RecordedRequest {
        var seen = 0
        repeat(12) {
            val r = server.takeRequest(10, java.util.concurrent.TimeUnit.SECONDS)
                ?: throw AssertionError("timed out waiting for request $nth")
            if (predicate(r) && ++seen == nth) return r
        }
        throw AssertionError("no matching request")
    }

    // -- the happy path -----------------------------------------------------

    @Test
    fun `seeds from channels then holds the socket`() = runBlocking {
        server.enqueue(channelsResponse("%0" to "idle", latest = 40))
        server.enqueue(socketUpgrade())
        start()
        awaitOnline()

        assertEquals(1, repo.state.value.channels.size)
        assertEquals(40L, repo.state.value.cursor)
        assertEquals("/channels?include_archived=false", takeUntil { it.path!!.startsWith("/channels") }.path)
    }

    @Test
    fun `a live event lands in the thread and moves the cursor`() = runBlocking {
        server.enqueue(channelsResponse("%0" to "idle", latest = 40))
        server.enqueue(socketUpgrade())
        start()
        awaitOnline()

        sockets.take().send(
            """{"type":"event","event":{"id":41,"pane_id":"%0","kind":"outcome",
            "body":"the suite is green","summary":"the suite is green","body_chars":18,
            "body_truncated":false,"meta":{},"ts":1786511510.0,"archived":false}}"""
        )
        await("event applied") { repo.state.value.cursor == 41L }
        assertEquals(1, repo.state.value.thread("%0").size)
        assertEquals(1, repo.state.value.unreadCount("%0"))
    }

    @Test
    fun `first ever launch does not open with a wall of unread badges`() = runBlocking {
        server.enqueue(
            MockResponse().setBody(
                """{"channels":[{"pane_id":"%0","status":"idle","live":true,"event_count":71,
                "last_event":{"id":71,"pane_id":"%0","kind":"outcome","body":"old news",
                "summary":"old news","meta":{},"ts":1.0}}],
                "latest_event_id":71,"server_time":1786511500.0}"""
            )
        )
        server.enqueue(socketUpgrade())
        start()
        awaitOnline()
        await("cursors seeded") { cursors.saved.isNotEmpty() }

        assertEquals(0, repo.state.value.unreadCount("%0"))
        assertEquals(mapOf("%0" to 71L), cursors.saved)
    }

    @Test
    fun `a returning client catches up so the badges are true`() = runBlocking {
        // He read up to 40 yesterday; three answers landed while the process was dead.
        cursors = FakeCursorStore(mapOf("%0" to 40L))
        val config = HubConfig(server.hostName, server.port, "t")
        repo = HubRepository(HubApi(config), HubSocket(config), cursors)

        server.enqueue(channelsResponse("%0" to "idle", latest = 43))
        server.enqueue(
            MockResponse().setBody(
                """{"events":[
                {"id":41,"pane_id":"%0","kind":"outcome","body":"one","summary":"one","meta":{},"ts":1.0},
                {"id":42,"pane_id":"%0","kind":"receipt","body":"two","summary":"two","meta":{},"ts":2.0},
                {"id":43,"pane_id":"%0","kind":"outcome","body":"three","summary":"three","meta":{},"ts":3.0}
                ],"latest_event_id":43}"""
            )
        )
        server.enqueue(socketUpgrade())
        repo.restore()
        start()
        awaitOnline()
        await("catch-up applied") { repo.state.value.thread("%0").size == 3 }

        assertEquals("receipts do not count as news", 2, repo.state.value.unreadCount("%0"))
        assertTrue(
            "a catch-up slice is not a loaded thread",
            "%0" !in repo.state.value.hydrated
        )
    }

    // -- losing the link ----------------------------------------------------

    @Test
    fun `a dropped socket reconnects with the cursor and loses nothing`() = runBlocking {
        server.enqueue(channelsResponse("%0" to "idle", latest = 40))
        server.enqueue(socketUpgrade())
        start()
        awaitOnline()

        val first = sockets.take()
        first.send(
            """{"type":"event","event":{"id":41,"pane_id":"%0","kind":"outcome",
            "body":"before the drop","summary":"before the drop","meta":{},"ts":1.0}}"""
        )
        await("first event applied") { repo.state.value.cursor == 41L }

        // Queue the second round before killing the first socket.
        server.enqueue(channelsResponse("%0" to "idle", latest = 41))
        server.enqueue(socketUpgrade())
        first.close(1001, "going away")

        // The SECOND /ws is the reconnect; the first carried the seeded cursor (40).
        val reconnect = takeUntil(nth = 2) { it.path!!.startsWith("/ws") }
        assertTrue(
            "reconnect must resume from the applied cursor, not the hub's latest: " +
                reconnect.path,
            reconnect.path!!.contains("since=41")
        )
        // Nothing already applied was lost while offline.
        assertEquals(1, repo.state.value.thread("%0").size)
    }

    @Test
    fun `a backlog replay after a gap is applied and marked as catch-up`() = runBlocking {
        server.enqueue(channelsResponse("%0" to "idle", latest = 40))
        server.enqueue(socketUpgrade())
        start()
        awaitOnline()

        val arrivals = mutableListOf<ArrivedEvent>()
        val collector = scope.launch { repo.arrivals.collect { arrivals.add(it) } }
        delay(50)

        sockets.take().send(
            """{"type":"backlog","since":40,"events":[
            {"id":41,"pane_id":"%0","kind":"outcome","body":"missed one","summary":"missed one","meta":{},"ts":1.0},
            {"id":42,"pane_id":"%0","kind":"outcome","body":"missed two","summary":"missed two","meta":{},"ts":2.0}]}"""
        )
        await("backlog applied") { repo.state.value.thread("%0").size == 2 }
        await("arrivals seen") { arrivals.size == 2 }

        // ★ Everything replayed is flagged fromBacklog so the voice stays quiet — the
        // bridge already buzzed his arm for these while the app was dead.
        assertTrue(arrivals.all { it.fromBacklog })
        collector.cancel()
    }

    @Test
    fun `an unreachable hub becomes a visible offline state, not silence`() = runBlocking {
        server.shutdown()
        start()
        await("went offline") { repo.link.value is HubLink.Offline }

        val off = repo.link.value as HubLink.Offline
        assertEquals(OfflineReason.UNREACHABLE, off.reason)
        assertTrue("a retry must be scheduled", off.nextRetryAtMs > off.sinceMs)
    }

    @Test
    fun `offline remembers when the hub was last heard from`() = runBlocking {
        server.enqueue(channelsResponse("%0" to "idle", latest = 40))
        server.enqueue(socketUpgrade())
        start()
        awaitOnline()
        val onlineAt = System.currentTimeMillis()

        server.shutdown()
        sockets.take().close(1001, "gone")
        await("offline after shutdown") { repo.link.value is HubLink.Offline }

        val off = repo.link.value as HubLink.Offline
        // "nothing since 4m ago" is the difference between a quiet afternoon and a
        // dead device; without a last-contact stamp the banner cannot say it.
        assertNotNull(off.lastContactMs)
        assertTrue(off.lastContactMs!! <= onlineAt + 1_000)
    }

    @Test
    fun `a refused token is reported as refused, not as unreachable`() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(401).setBody("""{"detail":"bad token"}"""))
        start()
        await("offline") { repo.link.value is HubLink.Offline }
        assertEquals(
            OfflineReason.UNAUTHORISED,
            (repo.link.value as HubLink.Offline).reason,
        )
    }

    @Test
    fun `channels frames replace the list wholesale`() = runBlocking {
        server.enqueue(channelsResponse("%0" to "idle", latest = 1))
        server.enqueue(socketUpgrade())
        start()
        awaitOnline()

        sockets.take().send(
            """{"type":"channels","channels":[
            {"pane_id":"%0","status":"working","live":true,"label":"renamed"},
            {"pane_id":"%7","status":"idle","live":true,"label":"new pane"}],
            "server_time":1786511600.0}"""
        )
        await("list replaced") { repo.state.value.channels.size == 2 }
        assertEquals("renamed", repo.state.value.channel("%0")!!.label)
    }

    // -- writing ------------------------------------------------------------

    @Test
    fun `a send shows up in the thread immediately, without waiting for the socket`() =
        runBlocking {
            server.enqueue(channelsResponse("%0" to "idle", latest = 1))
            server.enqueue(socketUpgrade())
            start()
            awaitOnline()

            server.enqueue(
                MockResponse().setBody(
                    """{"event":{"id":2,"pane_id":"%0","kind":"sent","body":"continue",
                    "summary":"continue","meta":{},"ts":9.0}}"""
                )
            )
            assertEquals(SendResult.Ok, repo.send("%0", "continue"))
            assertEquals(1, repo.state.value.thread("%0").size)
        }

    @Test
    fun `a send to a dead pane says the pane is dead`() = runBlocking {
        server.enqueue(channelsResponse("%0" to "dead", latest = 1))
        server.enqueue(socketUpgrade())
        start()
        awaitOnline()

        server.enqueue(
            MockResponse().setResponseCode(404)
                .setBody("""{"detail":"channel %0 is not live; nothing was sent"}""")
        )
        val result = repo.send("%0", "continue")
        assertTrue(result is SendResult.Failed)
        assertEquals("not sent — pane is gone", "not sent — ${(result as SendResult.Failed).message}")
        assertTrue("a dead pane is not going to recover on a retry", result.fatal)
    }

    /**
     * ⚠️ Interrupt and kill go over their own endpoints since hub 1.5.0 — `/send` now
     * answers 400 to a control byte, which is exactly what these used to type. The
     * hub's `control` event is applied on the response, same as a send's `sent`.
     */
    @Test
    fun `a kill hits the kill endpoint and its control event lands in the thread`() =
        runBlocking {
            server.enqueue(channelsResponse("%0" to "working", latest = 1))
            server.enqueue(socketUpgrade())
            start()
            awaitOnline()

            server.enqueue(
                MockResponse().setBody(
                    """{"event":{"id":2,"pane_id":"%0","kind":"control","body":"kill",
                    "summary":"kill","meta":{},"ts":9.0},
                    "channel":{"pane_id":"%0","status":"working","live":true}}"""
                )
            )
            assertEquals(SendResult.Ok, repo.kill("%0"))

            val req = takeUntil { it.path == "/channels/0/kill" }
            assertEquals("POST", req.method)
            val body = req.body.readUtf8()
            assertTrue(body, body.contains("\"origin\":\"roam-app\""))
            assertFalse("never a control byte through send", body.contains("\\u0003"))

            val event = repo.state.value.thread("%0").single()
            assertEquals("control", event.kind)
            assertEquals("kill", event.body)
        }

    @Test
    fun `an interrupt hits the interrupt endpoint with the escape action`() = runBlocking {
        server.enqueue(channelsResponse("%0" to "working", latest = 1))
        server.enqueue(socketUpgrade())
        start()
        awaitOnline()

        server.enqueue(
            MockResponse().setBody(
                """{"event":{"id":2,"pane_id":"%0","kind":"control","body":"escape",
                "summary":"escape","meta":{},"ts":9.0},
                "channel":{"pane_id":"%0","status":"working","live":true}}"""
            )
        )
        assertEquals(SendResult.Ok, repo.interrupt("%0"))

        val req = takeUntil { it.path == "/channels/0/interrupt" }
        val body = req.body.readUtf8()
        assertTrue(body, body.contains("\"action\":\"escape\""))
        assertFalse("never a control byte through send", body.contains("\\u001b"))
        assertEquals(1, repo.state.value.thread("%0").size)
    }

    /** The 404 mapping survives the move off /send: a gone pane is fatal, not a retry. */
    @Test
    fun `a kill on a pane that is already gone says so and is fatal`() = runBlocking {
        server.enqueue(channelsResponse("%0" to "dead", latest = 1))
        server.enqueue(socketUpgrade())
        start()
        awaitOnline()

        server.enqueue(
            MockResponse().setResponseCode(404)
                .setBody("""{"detail":"channel %0 is not live; nothing to kill"}""")
        )
        val result = repo.kill("%0")
        assertTrue(result is SendResult.Failed)
        assertEquals("pane is gone", (result as SendResult.Failed).message)
        assertTrue("a dead pane cannot be killed deader on a retry", result.fatal)
    }

    // -- new session ----------------------------------------------------------

    /** The 201 channel is upserted at once — the thread must be openable on the spot. */
    @Test
    fun `a created session is in the channel list before any socket frame mentions it`() =
        runBlocking {
            server.enqueue(channelsResponse("%0" to "idle", latest = 1))
            server.enqueue(socketUpgrade())
            start()
            awaitOnline()

            server.enqueue(
                MockResponse().setResponseCode(201).setBody(
                    """{"channel":{"pane_id":"%9","label":"TEST android probe",
                    "status":"idle","live":true,"command":"claude"}}"""
                )
            )
            val result = repo.createSession("TEST android probe")

            assertTrue(result is CreateResult.Created)
            assertEquals("%9", (result as CreateResult.Created).channel.paneId)
            assertNotNull(repo.state.value.channel("%9"))

            val req = takeUntil { it.path == "/channels" && it.method == "POST" }
            val body = req.body.readUtf8()
            assertTrue(body, body.contains("\"command\":\"claude\""))
            assertTrue(body, body.contains("\"label\":\"TEST android probe\""))
        }

    @Test
    fun `a session that cannot spawn reports why instead of pretending`() = runBlocking {
        server.enqueue(channelsResponse("%0" to "idle", latest = 1))
        server.enqueue(socketUpgrade())
        start()
        awaitOnline()

        server.enqueue(
            MockResponse().setResponseCode(502).setBody("""{"detail":"tmux refused"}""")
        )
        val result = repo.createSession("TEST doomed")
        assertTrue(result is CreateResult.Failed)
        assertEquals("tmux refused", (result as CreateResult.Failed).message)
    }

    @Test
    fun `a send with the hub unreachable fails softly and says so`() = runBlocking {
        server.enqueue(channelsResponse("%0" to "idle", latest = 1))
        server.enqueue(socketUpgrade())
        start()
        awaitOnline()
        server.shutdown()

        val result = repo.send("%0", "continue")
        assertTrue(result is SendResult.Failed)
        assertEquals("hub unreachable", (result as SendResult.Failed).message)
        assertTrue("worth retrying once the link comes back", !result.fatal)
    }

    @Test
    fun `reading a thread persists the read cursor across a process death`() = runBlocking {
        server.enqueue(channelsResponse("%0" to "idle", latest = 40))
        server.enqueue(socketUpgrade())
        start()
        awaitOnline()

        sockets.take().send(
            """{"type":"event","event":{"id":41,"pane_id":"%0","kind":"outcome",
            "body":"read me","summary":"read me","meta":{},"ts":1.0}}"""
        )
        await("event applied") { repo.state.value.unreadCount("%0") == 1 }
        repo.markRead("%0")

        assertEquals(0, repo.state.value.unreadCount("%0"))
        assertEquals(mapOf("%0" to 41L), cursors.saved)
    }

    // -----------------------------------------------------------------------
    // ★ "If a body was trimmed in transit, fetch the rest — never show a
    //   truncated tail as if it were the whole thing."
    // -----------------------------------------------------------------------

    /**
     * `API.md`: a bulk payload trims `body` to 4096 characters and flags it, and
     * `GET /events/{id}` returns the event whole. Verified against the live hub on
     * 2026-08-12 — event 331 arrives as 4096 of 5147 over the socket and comes back
     * complete from the single-event route.
     */
    @Test
    fun `a trimmed body is fetched whole before it can be read`() = runBlocking {
        server.enqueue(channelsResponse("%0" to "idle", latest = 40))
        server.enqueue(socketUpgrade())
        start()
        awaitOnline()

        val trimmed = "the first four kibibytes"
        sockets.take().send(
            """{"type":"event","event":{"id":41,"pane_id":"%0","kind":"outcome",
            "body":"$trimmed","summary":"the first…","body_chars":5147,
            "body_truncated":true,"meta":{},"ts":1.0}}"""
        )
        await("event applied") { repo.state.value.thread("%0").size == 1 }
        val event = repo.state.value.thread("%0").single()

        // Before the fetch the client knows it is holding a fragment, and says so.
        assertTrue("a trimmed body must advertise that it is trimmed",
            repo.state.value.needsExpansion(event))
        assertEquals(trimmed, repo.state.value.bodyOf(event))

        server.enqueue(
            MockResponse().setBody(
                """{"event":{"id":41,"pane_id":"%0","kind":"outcome",
                "body":"$trimmed and the 1051 characters that were cut.",
                "summary":"the first…","body_chars":5147,"body_truncated":false,
                "meta":{},"ts":1.0}}"""
            )
        )
        repo.expand(event)

        assertTrue("the fetch must clear the caveat", !repo.state.value.needsExpansion(event))
        assertTrue(
            "the whole body must replace the fragment",
            repo.state.value.bodyOf(event).endsWith("characters that were cut."),
        )
    }

    // -- ★★ presence, i.e. what is allowed to buzz his arm --------------------

    /**
     * ★★ **The channel he is looking at is reported the moment he opens it.**
     *
     * The heartbeat is every 30 s, and a coverage change that waits for it is a coverage
     * change that is wrong for half a minute — either buzzing him about the conversation
     * on his screen, or silently swallowing the one that is not. He switches channel and
     * expects the next message to behave accordingly, so the setter posts immediately.
     *
     * ⚠️ The heartbeat here is real (30 s), so the second POST cannot come from it.
     */
    @Test
    fun `changing the open channel re-posts presence without waiting for the heartbeat`() =
        runBlocking {
            repeat(4) { server.enqueue(MockResponse().setBody(PRESENCE_OK)) }
            repo.startPresence(scope)

            val first = takeUntil { it.path == "/presence" }.body.readUtf8()
            assertTrue(first, first.contains("\"covers_all\":false"))
            assertTrue("nothing open covers nothing: $first", first.contains("\"panes\":[]"))

            repo.openPane = "%3"
            val second = takeUntil { it.path == "/presence" }.body.readUtf8()
            assertTrue(second, second.contains("\"panes\":[\"%3\"]"))

            // ⚠️ And leaving the thread must be just as prompt — an arm that stays silent
            // after he walks away is exactly the failure this whole path exists to fix.
            repo.openPane = null
            val third = takeUntil { it.path == "/presence" }.body.readUtf8()
            assertTrue(third, third.contains("\"panes\":[]"))
        }

    /** ⚠️ Re-selecting the same channel is not a change, and must not chatter at the hub. */
    @Test
    fun `re-opening the channel already open posts nothing extra`() = runBlocking {
        repeat(3) { server.enqueue(MockResponse().setBody(PRESENCE_OK)) }
        repo.startPresence(scope)
        takeUntil { it.path == "/presence" }

        repo.openPane = "%3"
        takeUntil { it.path == "/presence" }

        val before = server.requestCount
        repo.openPane = "%3"
        delay(200)
        assertEquals("an unchanged pane is not news", before, server.requestCount)
    }

    /** ⚠️ A body that arrived whole must not cost a round trip every time he opens it. */
    @Test
    fun `a body that was never trimmed is not re-fetched`() = runBlocking {
        server.enqueue(channelsResponse("%0" to "idle", latest = 40))
        server.enqueue(socketUpgrade())
        start()
        awaitOnline()

        sockets.take().send(
            """{"type":"event","event":{"id":41,"pane_id":"%0","kind":"outcome",
            "body":"short and complete","summary":"short and complete","body_chars":18,
            "body_truncated":false,"meta":{},"ts":1.0}}"""
        )
        await("event applied") { repo.state.value.thread("%0").size == 1 }

        val before = server.requestCount
        repo.expand(repo.state.value.thread("%0").single())
        assertEquals("no request should have been made", before, server.requestCount)
    }
}
