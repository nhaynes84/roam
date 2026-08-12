package com.roam.touch.channels

import com.roam.touch.channels.model.Event
import com.roam.touch.channels.net.HubApi
import com.roam.touch.channels.net.HubConfig
import com.roam.touch.channels.net.HubSocket
import com.roam.touch.channels.tts.Speaker
import com.roam.touch.channels.tts.Speech
import com.roam.touch.channels.tts.Utterance
import com.roam.touch.channels.ui.ChannelsViewModel
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.util.concurrent.LinkedBlockingQueue

/** Records what it was asked to say, and by whom. */
private class FakeSpeaker : Speaker {
    val spoken = mutableListOf<Pair<Long, String>>()
    private val _id = MutableStateFlow<Long?>(null)
    override val speakingEventId: StateFlow<Long?> = _id
    var stopped = 0

    override fun play(event: Event, channelLabel: String, body: String) {
        spoken += event.id to Utterance.of(channelLabel, event, body)
        _id.value = event.id
    }

    override fun stop() {
        stopped++
        _id.value = null
    }
}

/**
 * ★★ Regression, reported live on the device: *"channels is reading these messages out
 * loud"* — the owner was at his laptop, not touching the phone, and the app was speaking
 * outcomes at him. His ruling: *"I should have the option to just 'play' a message, I
 * don't want it non stop blabbering at me."*
 *
 * So the rule this file enforces is absolute and has no exceptions to configure:
 * **audio happens if and only if he pressed play on a specific message.** The previous
 * behaviour — decide for him based on screen state, foreground state and hub presence —
 * is deleted, not defaulted off, and this test fails the moment any of it comes back.
 */
class SpeechPolicyTest {

    private lateinit var server: MockWebServer
    private lateinit var repo: HubRepository
    private lateinit var speaker: FakeSpeaker
    private lateinit var vm: ChannelsViewModel
    private lateinit var scope: CoroutineScope
    private var job: Job? = null
    private val sockets = LinkedBlockingQueue<WebSocket>()

    @Before
    fun setUp() {
        server = MockWebServer().also { it.start() }
        val config = HubConfig(server.hostName, server.port, "t")
        repo = HubRepository(HubApi(config), HubSocket(config), FakeCursorStore())
        speaker = FakeSpeaker()
        vm = ChannelsViewModel(repo, speaker)
        scope = CoroutineScope(SupervisorJob())
    }

    @After
    fun tearDown() {
        job?.cancel()
        scope.cancel()
        server.shutdown()
    }

    private fun seed(latest: Long = 40) = MockResponse().setBody(
        """{"channels":[{"pane_id":"%0","label":"✳ Augment things","status":"working",
        "live":true,"last_output_at":1786511500.0,"idle_s":0.4,"event_count":1}],
        "latest_event_id":$latest,"server_time":1786511500.0}"""
    )

    private fun socketUpgrade() =
        MockResponse().withWebSocketUpgrade(object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: okhttp3.Response) {
                sockets.put(webSocket)
            }
        })

    private suspend fun online() = withTimeout(10_000) {
        while (!repo.link.value.isOnline) delay(10)
    }

    private suspend fun await(what: String, check: () -> Boolean) = withTimeout(10_000) {
        while (!check()) delay(10)
    }.also { assertTrue(what, true) }

    private fun eventFrame(id: Long, kind: String, body: String) =
        """{"type":"event","event":{"id":$id,"pane_id":"%0","kind":"$kind",
        "body":"$body","summary":"$body","body_chars":${body.length},
        "body_truncated":false,"meta":{},"ts":1786511510.0,"archived":false}}"""

    // -----------------------------------------------------------------------

    /**
     * The exact reported scenario: he is elsewhere, messages land, the app is running.
     * Every kind, including the outcomes the old gate treated as speakable.
     */
    @Test
    fun `messages arriving never speak`() = runBlocking {
        server.enqueue(seed())
        server.enqueue(socketUpgrade())
        job = scope.launch { repo.run(this) }
        online()

        // ⚠️ Subscribing here keeps this test honest. `arrivals` is the exact flow the
        // deleted auto-speak collected from, so proving events land on it proves the
        // silence below is a policy and not an accident of nothing being delivered —
        // this assertion is what makes the test fail against the old build.
        val arrived = mutableListOf<ArrivedEvent>()
        val watcher = scope.launch { repo.arrivals.collect { arrived += it } }
        delay(50)

        val socket = sockets.take()
        socket.send(eventFrame(41, "outcome", "the suite is green"))
        socket.send(eventFrame(42, "error", "tmux refused the send"))
        socket.send(eventFrame(43, "note", "heads up"))
        socket.send(eventFrame(44, "receipt", "run the tests"))
        socket.send(eventFrame(45, "sent", "continue"))
        await("all events applied") { repo.state.value.thread("%0").size == 5 }
        // Give any stray subscriber every chance to fire before we declare silence.
        delay(300)

        assertEquals("the events really were delivered", 5, arrived.size)
        assertEquals("nothing may be spoken unasked", emptyList<Pair<Long, String>>(), speaker.spoken)
        assertNull(vm.speakingEventId.value)
        watcher.cancel()
    }

    @Test
    fun `a replayed backlog never speaks either`() = runBlocking {
        server.enqueue(seed())
        server.enqueue(socketUpgrade())
        job = scope.launch { repo.run(this) }
        online()

        sockets.take().send(
            """{"type":"backlog","since":40,"events":[
            {"id":41,"pane_id":"%0","kind":"outcome","body":"one","summary":"one","meta":{},"ts":1.0},
            {"id":42,"pane_id":"%0","kind":"outcome","body":"two","summary":"two","meta":{},"ts":2.0}]}"""
        )
        await("backlog applied") { repo.state.value.thread("%0").size == 2 }
        delay(300)
        assertTrue(speaker.spoken.isEmpty())
    }

    @Test
    fun `pressing play speaks that message and only that message`() = runBlocking {
        server.enqueue(seed())
        server.enqueue(socketUpgrade())
        job = scope.launch { repo.run(this) }
        online()

        sockets.take().send(eventFrame(41, "outcome", "the suite is green"))
        await("event applied") { repo.state.value.thread("%0").size == 1 }

        val event = repo.state.value.thread("%0").single()
        vm.play(event)

        assertEquals(1, speaker.spoken.size)
        assertEquals(41L, speaker.spoken.single().first)
        // The channel label rides along so he knows who is talking without looking.
        assertEquals("Augment things. the suite is green", speaker.spoken.single().second)
        assertEquals(41L, vm.speakingEventId.value)
    }

    @Test
    fun `stop is available while a message is playing`() = runBlocking {
        server.enqueue(seed())
        server.enqueue(socketUpgrade())
        job = scope.launch { repo.run(this) }
        online()
        sockets.take().send(eventFrame(41, "outcome", "a long answer"))
        await("event applied") { repo.state.value.thread("%0").size == 1 }

        vm.play(repo.state.value.thread("%0").single())
        assertEquals(41L, vm.speakingEventId.value)
        vm.stopSpeaking()
        assertEquals(1, speaker.stopped)
        assertNull(vm.speakingEventId.value)
    }

    /**
     * No kind is privileged. The old gate had a SPEAKABLE_KINDS set; there is no such
     * concept now, because he chose the message.
     */
    @Test
    fun `play works on any kind he taps`() {
        listOf("outcome", "error", "note", "receipt", "sent", "opened", "future_kind")
            .forEachIndexed { i, kind ->
                speaker.play(Fx.event(id = i.toLong(), kind = kind, body = "text"), "chan")
            }
        assertEquals(7, speaker.spoken.size)
    }
}

/** What Piper is handed, once he has chosen a message. */
class UtteranceTest {

    @Test
    fun `the label comes first, then the message itself`() {
        val e = Fx.event(id = 1, kind = "outcome", body = "The suite is green.",
            summary = "The suite is green.")
        assertEquals("Augment things. The suite is green.", Utterance.of("✳ Augment things", e))
    }

    /**
     * ★★ The regression that matters most here: the summary is the *glance*, and play is
     * not a glance. Speaking `summary` is what made the voice stop in the same place the
     * screen did — *"the TTS also cuts off there."*
     */
    @Test
    fun `play speaks the body, not the shorter summary the hub sent alongside it`() {
        val e = Fx.event(
            id = 1, kind = "outcome",
            body = "First sentence. Second sentence, which the summary never carried.",
            summary = "First sentence.…",
        )
        assertTrue(Utterance.of("x", e).endsWith("which the summary never carried."))
    }

    @Test
    fun `status glyphs are stripped so Piper does not stumble on them`() {
        assertEquals("Roam Touch rebuild discussion",
            Utterance.speakableLabel("◑ Roam Touch rebuild discussion"))
        assertEquals("Pose model export", Utterance.speakableLabel("◑ Pose model export"))
    }

    @Test
    fun `an error announces itself as one`() {
        val e = Fx.event(id = 2, kind = "error", body = "tmux refused the send")
        assertTrue(Utterance.of("✳ Augment things", e).startsWith("Error in Augment things"))
    }

    /**
     * ⚠️ The API.md rule survives in the form that actually matters: **nothing is
     * summarised client-side.** Markdown scaffolding is removed so Piper does not read
     * hashes and backticks aloud, but every word is still there — this strips, it never
     * chooses. Dropping content client-side is the bug, wearing a different hat.
     */
    @Test
    fun `nothing is summarised client-side — only the markdown is taken out`() {
        val e = Fx.event(
            id = 3, kind = "outcome",
            body = "# Heading\n\n**Every** word `survives` the [strip](http://x/y).",
            summary = "hub says this",
        )
        val spoken = Utterance.of("x", e)
        assertTrue(spoken.contains("Heading"))
        assertTrue(spoken.contains("Every word survives the strip."))
        assertFalse("markdown syntax must not be read aloud", spoken.contains("**"))
        assertFalse("a spoken URL is noise", spoken.contains("http"))
    }

    /** A code block is content he asked to hear, not decoration to be dropped. */
    @Test
    fun `a fenced code block keeps its code and loses its fences`() {
        val e = Fx.event(
            id = 7, kind = "outcome",
            body = "Here:\n```bash\nmake p2-flash\n```\nthat is all.",
            summary = "Here: [code, 1 line] that is all.",
        )
        val spoken = Utterance.of("", e)
        assertTrue(spoken.contains("make p2-flash"))
        assertFalse(spoken.contains("```"))
    }

    @Test
    fun `an empty message produces nothing to say`() {
        assertEquals("", Utterance.of("chan", Fx.event(id = 4, body = "", summary = "")))
    }

    @Test
    fun `a label of pure glyphs degrades to just the message`() {
        val e = Fx.event(id = 5, kind = "outcome", body = "done", summary = "done")
        assertEquals("done", Utterance.of("◑✳", e))
    }

    /**
     * ⚠️ The bound is a guard against a pathological payload, not a message cap — so it
     * has to be well clear of a real answer. A 6000-character outcome is ordinary on
     * `%0` and must arrive whole; only something absurd gets cut.
     */
    @Test
    fun `a real answer is spoken whole, and only an absurd one is bounded`() {
        val real = Fx.event(id = 6, kind = "outcome", body = "word ".repeat(1_200), summary = "s")
        assertEquals(Speech.plain("word ".repeat(1_200)), Utterance.of("", real))

        val absurd = Fx.event(id = 7, kind = "outcome", body = "x".repeat(80_000), summary = "")
        assertTrue(Utterance.of("", absurd).length <= Utterance.MAX_CHARS)
    }
}
