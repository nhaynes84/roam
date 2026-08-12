package com.roam.touch.channels

import com.roam.touch.channels.model.Event
import com.roam.touch.channels.net.HubApi
import com.roam.touch.channels.net.HubConfig
import com.roam.touch.channels.net.HubSocket
import com.roam.touch.channels.stt.FakeHeadset
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
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.withTimeout
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.io.IOException
import java.net.ServerSocket
import java.net.SocketException
import java.util.concurrent.atomic.AtomicInteger
import kotlin.concurrent.thread

/**
 * ★★ **The hub that answers, slowly, forever.**
 *
 * The owner, 2026-08-12: *"app froze sending you a message."* Nothing had crashed, no
 * ANR was recorded and the process was still alive — and the UI thread turned out never
 * to have been blocked at all. What was actually wrong was simpler and worse: the send
 * had no end.
 *
 * ⚠️⚠️ **OkHttp's `readTimeout` bounds one read, not one call.** A hub that sends its
 * headers and then trickles the body resets that timer with every byte, so the call runs
 * for as long as the trickle lasts. Measured against [dribblingHub] before the fix: a
 * send was still outstanding after 105 seconds, with no error, no thread and nothing
 * whatsoever on screen. The tailnet hub answers in milliseconds, so this is precisely the
 * case nobody tested and the only one that matters when it happens.
 *
 * These tests are wall-clock deliberately. The bug is *duration*, and a virtual clock
 * would have let it through: the old code was not slow, it was unbounded.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class SlowHubTest {

    private lateinit var hub: ServerSocket
    private lateinit var api: HubApi
    private lateinit var repo: HubRepository
    private lateinit var scope: CoroutineScope

    /** How many requests the wedged hub has accepted, so cancellation can be observed. */
    private val accepted = AtomicInteger()

    @Before
    fun setUp() {
        Dispatchers.setMain(Dispatchers.Unconfined)
        hub = dribblingHub()
        val config = HubConfig("127.0.0.1", hub.localPort, "test-token")
        api = HubApi(config)
        repo = HubRepository(api, HubSocket(config), FakeCursorStore())
        scope = CoroutineScope(SupervisorJob())
    }

    @After
    fun tearDown() {
        scope.cancel()
        runCatching { hub.close() }
        Dispatchers.resetMain()
    }

    /**
     * A hub that is *up*: it accepts, it answers, it even promises a content length. It
     * just never finishes — one byte of body every second, forever.
     *
     * ⚠️ One second is well inside the 20 s read timeout, on purpose. That is the whole
     * point: every individual read succeeds, so nothing at the socket layer ever fires.
     */
    private fun dribblingHub(): ServerSocket {
        val server = ServerSocket(0)
        thread(isDaemon = true) {
            while (!server.isClosed) {
                val socket = try {
                    server.accept()
                } catch (e: IOException) {
                    return@thread
                }
                accepted.incrementAndGet()
                thread(isDaemon = true) {
                    runCatching {
                        val out = socket.getOutputStream()
                        out.write(
                            ("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n" +
                                    "Content-Length: 9000\r\n\r\n").toByteArray()
                        )
                        out.flush()
                        while (true) {
                            out.write(' '.code)
                            out.flush()
                            Thread.sleep(1_000)
                        }
                    }
                    runCatching { socket.close() }
                }
            }
        }
        return server
    }

    /** Milliseconds [block] took, and whatever it produced. */
    private fun <T> timed(block: () -> T): Pair<Long, T> {
        val t0 = System.currentTimeMillis()
        val result = block()
        return (System.currentTimeMillis() - t0) to result
    }

    // -- ★★ the deadline ------------------------------------------------------

    /**
     * ★★ The regression. Before the deadline existed this call simply never returned.
     */
    @Test
    fun `a hub that never finishes answering does not hold a send open forever`() {
        val (ms, result) = timed { runBlocking { repo.send("%0", "continue") } }

        assertTrue(
            "the send ran for $ms ms — a send must end, one way or the other",
            ms < HubApi.SEND_DEADLINE_MS + SLACK_MS
        )
        assertEquals(
            SendResult.Failed(HubRepository.TIMED_OUT, fatal = false),
            result
        )
    }

    /**
     * ★ "Timed out" and "unreachable" are different sentences because they send him to
     * different places: this one means the tailnet is fine and something on talos is
     * wedged, and it is the only one where trying again in ten seconds is sensible.
     */
    @Test
    fun `a wedged hub does not report itself as unreachable`() {
        val result = runBlocking { repo.send("%0", "continue") } as SendResult.Failed
        assertEquals(HubRepository.TIMED_OUT, result.message)
        assertTrue("a timeout says nothing about the pane — retrying is allowed", !result.fatal)
    }

    /** Reads are bounded too. A screen that never fills in is the same bug, quieter. */
    @Test
    fun `a read against a wedged hub also ends`() {
        val (ms, _) = timed { runBlocking { repo.loadHistory("%0") } }
        assertTrue(
            "history ran for $ms ms",
            ms < HubApi.READ_DEADLINE_MS + SLACK_MS
        )
    }

    /**
     * ⚠️ `execute()` is a blocking socket read: cancelling the coroutine cannot interrupt
     * it, so the call is cancelled explicitly. Without that, walking out of a thread left
     * the request running on an IO thread until its deadline expired — invisible, but it
     * is how you end up with a handful of wedged sockets and a phone that will not sleep.
     */
    @Test
    fun `walking away cancels the request instead of leaving it running`() = runBlocking {
        val job = scope.launch { repo.send("%0", "continue") }
        withTimeout(5_000) { while (accepted.get() == 0) delay(10) }

        val (ms, _) = timed {
            runBlocking {
                job.cancel()
                withTimeout(3_000) { job.join() }
            }
        }
        assertTrue("cancelling took $ms ms", ms < 3_000)
    }

    // -- ★★ what the wearer is left looking at --------------------------------

    /**
     * ★★ **The freeze itself.**
     *
     * The panel goes to [PttState.Sending] on the confirmed send, and [Ptt.press] ignores
     * every press while it is there — so for as long as that state lasts the microphone,
     * the mic button and the confirm card are all inert. Unbounded, that is an app that
     * has frozen. It must end on its own, and it must end with his words still in hand.
     */
    @Test
    fun `a wedged hub does not leave the voice panel stuck in SENDING`() = runBlocking {
        val ptt = confirmedPtt()
        val vm = viewModel(ptt)

        val (ms, _) = timed {
            runBlocking {
                vm.pttConfirm()
                withTimeout(HubApi.SEND_DEADLINE_MS + SLACK_MS) {
                    while (ptt.state.value is PttState.Sending) delay(20)
                }
            }
        }

        val state = ptt.state.value
        assertTrue("still $state after $ms ms", state is PttState.Confirming)
        state as PttState.Confirming
        // ★ His words come back. He said a sentence out loud; a hub that stopped
        // answering is not a reason to make him say it again.
        assertEquals(SPOKEN, state.transcript)
        assertEquals(HubRepository.TIMED_OUT, state.error)
    }

    /**
     * ★ And he never has to wait it out. STOP WAITING is on the panel from the first
     * frame, and pressing it hands the words straight back — honestly labelled, because
     * the hub may well have typed them already.
     */
    @Test
    fun `he can stop waiting, and keeps the sentence when he does`() = runBlocking {
        val ptt = confirmedPtt()
        val vm = viewModel(ptt)

        vm.pttConfirm()
        withTimeout(5_000) { while (ptt.state.value !is PttState.Sending) delay(10) }

        vm.pttCancel()

        val state = ptt.state.value
        assertTrue("stopping the wait left it in $state", state is PttState.Confirming)
        state as PttState.Confirming
        assertEquals(SPOKEN, state.transcript)
        assertEquals(Ptt.STOPPED_WAITING, state.error)
    }

    // -- ★★ the typed and canned half ----------------------------------------

    /**
     * ★★ The other half of the same freeze, and the one he actually tapped.
     *
     * A canned chip used to call the hub and show **nothing at all**: the word vanished
     * out of the composer, no pending state appeared, and the toast only came once the
     * hub answered — which, against a wedged hub, was never. Reproduced on the emulator
     * on 2026-08-12: CONTINUE tapped, blank screen, still blank 105 seconds later.
     */
    @Test
    fun `a send in flight is visible while it is in flight`() = runBlocking {
        val vm = viewModel(confirmedPtt())
        assertNull(vm.outbox.value)

        vm.send("%0", "continue")
        withTimeout(5_000) { while (vm.outbox.value == null) delay(10) }

        assertEquals("continue", vm.outbox.value?.text)

        // …and it clears itself when the call ends, rather than becoming a permanent
        // spinner. That is the difference between "slow" and "broken".
        withTimeout(HubApi.SEND_DEADLINE_MS + SLACK_MS) {
            while (vm.outbox.value != null) delay(20)
        }
    }

    /**
     * ★★ **His words are not the price of a failed send.**
     *
     * The composer used to clear on tap and keep its text in a `remember` inside the
     * composable, so a refused or timed-out send deleted a sentence he had one-handedly
     * typed while walking, and said so in a toast that was gone in three seconds.
     */
    @Test
    fun `a failed send leaves the typed words in the composer`() = runBlocking {
        val vm = viewModel(confirmedPtt())
        vm.draft("check the roaster temperature")

        vm.sendDraft("%0")
        withTimeout(HubApi.SEND_DEADLINE_MS + SLACK_MS) {
            while (vm.outbox.value != null) delay(20)
        }

        assertEquals("check the roaster temperature", vm.draft.value)
        val toast = withTimeout(2_000) { vm.messages.first() }
        assertTrue("the failure has to be said out loud: $toast", toast.bad)
        assertTrue(toast.text.contains(HubRepository.TIMED_OUT))
    }

    // -- harness --------------------------------------------------------------

    /** A [Ptt] carried all the way to the confirm card, ready for a Send. */
    private fun confirmedPtt(): Ptt {
        val ptt = Ptt(
            recorder = FakeRecorder(),
            stt = object : SttClient {
                override suspend fun transcribe(recording: Recording) = SPOKEN
            },
            scope = scope,
            headset = FakeHeadset().also { it.setupMs = 0 },
        )
        ptt.press(PttTarget("%0", "pane 0"))
        runBlocking {
            withTimeout(5_000) { while (ptt.state.value !is PttState.Listening) delay(10) }
            ptt.release()
            withTimeout(5_000) { while (ptt.state.value !is PttState.Confirming) delay(10) }
        }
        return ptt
    }

    private fun viewModel(ptt: Ptt) = ChannelsViewModel(
        repo = repo,
        speaker = SilentSpeaker,
        pttProvider = { ptt },
    )

    private object SilentSpeaker : Speaker {
        override val speakingEventId: StateFlow<Long?> = MutableStateFlow(null)
        override fun play(event: Event, channelLabel: String, body: String) = Unit
        override fun stop() = Unit
    }

    private companion object {
        const val SPOKEN = "run the test suite and tell me if it is green"

        /**
         * Room for a socket, a thread hop and a slow CI box — but nowhere near enough to
         * let an unbounded call pass. The bug this suite pins ran for 105 seconds.
         */
        const val SLACK_MS = 6_000L
    }
}
