package com.roam.touch.channels

import com.roam.touch.channels.model.Event
import com.roam.touch.channels.net.HubApi
import com.roam.touch.channels.net.HubConfig
import com.roam.touch.channels.net.HubSocket
import com.roam.touch.channels.stt.FakeRecorder
import com.roam.touch.channels.stt.Ptt
import com.roam.touch.channels.stt.PttState
import com.roam.touch.channels.stt.PttTarget
import com.roam.touch.channels.stt.Recording
import com.roam.touch.channels.stt.SttClient
import com.roam.touch.channels.tts.Speaker
import com.roam.touch.channels.ui.ChannelsViewModel
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.withTimeout
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit

private class MuteSpeaker : Speaker {
    override val speakingEventId: StateFlow<Long?> = MutableStateFlow(null)
    override fun play(event: Event, channelLabel: String) = Unit
    override fun stop() = Unit
}

private class CannedStt(private val text: String) : SttClient {
    var calls = 0
        private set

    override suspend fun transcribe(recording: Recording): String {
        calls++
        return text
    }
}

/**
 * ★★ The two rules that make voice input safe on a device worn all day.
 *
 * **1. Nothing records unless he presses the button.** The owner had automatic *speech*
 * deleted for being presumptuous — *"I don't want it non stop blabbering at me"* — and a
 * microphone that opens on its own is the same mistake pointed the other way, with far
 * worse consequences. So: no wake word, no VAD, no "listen while the thread is open",
 * no mic that survives leaving the screen. `SpeechPolicyTest` is this file's sibling.
 *
 * **2. The hub only ever sees a confirmed send.** The confirmation covers the words
 * *and* the routing, in one gesture, client-side. Nothing spoken reaches a live agent
 * without passing it — a good command landing in the wrong session is the worst failure
 * this device has.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class PttPolicyTest {

    private lateinit var server: MockWebServer
    private lateinit var repo: HubRepository
    private lateinit var recorder: FakeRecorder
    private lateinit var stt: CannedStt
    private lateinit var ptt: Ptt
    private lateinit var vm: ChannelsViewModel
    private lateinit var scope: CoroutineScope
    private var job: Job? = null
    private val sockets = LinkedBlockingQueue<WebSocket>()

    private val target = PttTarget("%0", "✳ Augment things")

    @Before
    fun setUp() {
        // The view model launches on `viewModelScope`, which is Main. These tests run
        // against a real MockWebServer on real time, so Main is simply made immediate
        // rather than virtual.
        Dispatchers.setMain(Dispatchers.Unconfined)
        server = MockWebServer().also { it.start() }
        val config = HubConfig(server.hostName, server.port, "t")
        repo = HubRepository(HubApi(config), HubSocket(config), FakeCursorStore())
        scope = CoroutineScope(SupervisorJob())
        recorder = FakeRecorder()
        stt = CannedStt("run the test suite")
        ptt = Ptt(recorder, stt, scope)
        vm = ChannelsViewModel(repo, MuteSpeaker(), pttProvider = { ptt })
    }

    @After
    fun tearDown() {
        job?.cancel()
        scope.cancel()
        server.shutdown()
        Dispatchers.resetMain()
    }

    private fun seed() = MockResponse().setBody(
        """{"channels":[{"pane_id":"%0","label":"✳ Augment things","status":"working",
        "live":true,"last_output_at":1786511500.0,"idle_s":0.4,"event_count":1}],
        "latest_event_id":40,"server_time":1786511500.0}"""
    )

    private fun socketUpgrade() =
        MockResponse().withWebSocketUpgrade(object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: okhttp3.Response) {
                sockets.put(webSocket)
            }
        })

    private fun sendAccepted() = MockResponse().setBody(
        """{"event":{"id":41,"pane_id":"%0","kind":"sent","body":"run the test suite",
        "summary":"run the test suite","body_chars":18,"body_truncated":false,
        "meta":{"origin":"roam-app"},"ts":1786511510.0,"archived":false}}"""
    )

    private suspend fun connect() {
        server.enqueue(seed())
        server.enqueue(socketUpgrade())
        job = scope.launch { repo.run(this) }
        withTimeout(10_000) { while (!repo.link.value.isOnline) delay(10) }
        server.takeRequest()   // GET /channels
        server.takeRequest()   // WebSocket upgrade
    }

    private suspend fun await(check: () -> Boolean) =
        withTimeout(10_000) { while (!check()) delay(10) }

    // --- 1. nothing records unless he presses --------------------------------

    /**
     * The app doing everything it does on its own: connecting, receiving a backlog,
     * receiving outcomes, having a thread opened and read. No microphone anywhere.
     */
    @Test
    fun `running the app never opens the microphone`() = runBlocking {
        connect()
        val socket = sockets.take()
        socket.send(
            """{"type":"event","event":{"id":41,"pane_id":"%0","kind":"outcome",
            "body":"the suite is green","summary":"the suite is green","meta":{},
            "ts":1786511510.0}}"""
        )
        await { repo.state.value.thread("%0").isNotEmpty() }
        vm.openThread("%0")
        vm.markRead("%0")
        delay(300)

        assertEquals("the mic was never opened", 0, recorder.starts)
        assertEquals("and nothing was transcribed", 0, stt.calls)
        assertEquals(PttState.Idle, vm.pttState.value)
    }

    @Test
    fun `only a press opens it, and a release closes it again`() = runBlocking {
        vm.pttPress(target)
        assertEquals(1, recorder.starts)
        assertTrue(recorder.recording)

        vm.pttRelease()
        assertTrue("the mic is shut the moment the thumb lifts", !recorder.recording)
        assertEquals(1, recorder.stops)
    }

    /** ★ Leaving the thread must not leave a microphone running behind it. */
    @Test
    fun `cancelling — as leaving the thread does — closes the mic`() = runBlocking {
        vm.pttPress(target)
        vm.pttCancel()
        assertTrue(!recorder.recording)
        assertEquals(1, recorder.discards)
        assertEquals(PttState.Idle, vm.pttState.value)
    }

    // --- 2. the hub only sees confirmed sends --------------------------------

    /**
     * ★★ The safety rail, end to end. Speaking produces a *confirmation*, not a send —
     * the hub sees nothing at all until Send is pressed.
     */
    @Test
    fun `speaking sends nothing to the hub until Send is pressed`() = runBlocking {
        connect()
        vm.pttPress(target)
        vm.pttRelease()
        await { vm.pttState.value is PttState.Confirming }
        delay(200)

        assertNull(
            "not one request may reach the hub before the confirmation",
            server.takeRequest(300, TimeUnit.MILLISECONDS),
        )
        assertEquals(
            PttState.Confirming(target, "run the test suite"),
            vm.pttState.value,
        )
    }

    @Test
    fun `Send posts the confirmed words to the confirmed pane, as the app`() = runBlocking {
        connect()
        server.enqueue(sendAccepted())

        vm.pttPress(target)
        vm.pttRelease()
        await { vm.pttState.value is PttState.Confirming }
        vm.pttConfirm()
        await { vm.pttState.value == PttState.Idle }

        val request = server.takeRequest(5, TimeUnit.SECONDS)!!
        // The pane comes from the press, not from whatever is on screen now.
        assertEquals("/channels/0/send", request.path)
        val body = request.body.readUtf8()
        assertTrue(body.contains("\"text\":\"run the test suite\""))
        assertTrue(body.contains("\"enter\":true"))
        // ★ Posting through the app's own send is what moves the hub's last-input rule
        // to `app`, so the outcome comes back here instead of being left in tmux, and
        // `origin` names who did it in the stored event. API.md §2, coverage.
        assertTrue(body.contains("\"origin\":\"roam-app\""))
    }

    /** Cancel is a real cancel: nothing is queued, nothing arrives later. */
    @Test
    fun `Cancel reaches the hub as nothing at all`() = runBlocking {
        connect()
        vm.pttPress(target)
        vm.pttRelease()
        await { vm.pttState.value is PttState.Confirming }
        vm.pttCancel()
        delay(300)

        assertEquals(PttState.Idle, vm.pttState.value)
        assertNull(server.takeRequest(300, TimeUnit.MILLISECONDS))
    }

    /**
     * ⚠️ A pane that died while he was talking. The send is refused, and the words come
     * back to the confirm step rather than evaporating into a toast.
     */
    @Test
    fun `a refused send returns the transcript instead of losing it`() = runBlocking {
        connect()
        server.enqueue(
            MockResponse().setResponseCode(404)
                .setBody("""{"detail":"channel %0 is not live; nothing was sent"}""")
        )

        vm.pttPress(target)
        vm.pttRelease()
        await { vm.pttState.value is PttState.Confirming }
        vm.pttConfirm()
        await { (vm.pttState.value as? PttState.Confirming)?.error != null }

        val state = vm.pttState.value as PttState.Confirming
        assertEquals("run the test suite", state.transcript)
        assertEquals("pane is gone", state.error)
    }
}
