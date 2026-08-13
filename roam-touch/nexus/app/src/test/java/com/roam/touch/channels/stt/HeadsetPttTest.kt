package com.roam.touch.channels.stt

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * A headset that is exactly as present, as fast and as cooperative as a test says.
 *
 * Every call is written into a shared [trace] alongside the recorder's, because the
 * property that matters most here is an *ordering* one: the microphone must not open
 * until the link is up.
 */
class FakeHeadset(
    private val trace: MutableList<String> = mutableListOf(),
    override var connected: Boolean = true,
) : HeadsetLink {

    /** How long the SCO link takes to come up. The XM6 measures about 600 ms. */
    var setupMs: Long = 600L

    /** False makes the link fail to come up, as a headset going flat mid-press would. */
    var linkComesUp = true

    var opens = 0
        private set
    var closes = 0
        private set

    override suspend fun open(): Boolean {
        opens++
        trace += "link.open"
        delay(setupMs)
        trace += if (linkComesUp) "link.up" else "link.failed"
        return linkComesUp
    }

    override fun close() {
        closes++
        trace += "link.close"
    }
}

/** A recorder that writes into the same trace, so ordering can be asserted across both. */
private class TracingRecorder(
    private val trace: MutableList<String>,
    private var next: Recording = FakeRecorder.speech(),
) : Recorder {
    var starts = 0
        private set

    override var recording: Boolean = false
        private set

    override fun start(): Boolean {
        starts++
        trace += "mic.start"
        recording = true
        return true
    }

    override fun stop(): Recording {
        trace += "mic.stop"
        recording = false
        return next
    }

    override fun discard() {
        trace += "mic.discard"
        recording = false
    }

    fun willCapture(recording: Recording) {
        next = recording
    }
}

/**
 * ★★ Push to talk through a **Bluetooth headset microphone**, which on this device is the
 * only microphone there is.
 *
 * ⚠️⚠️ **The fact this file is built on.** sailfish's built-in analog capture delivers
 * nothing — the HAL fails `pcm_prepare` for every audio source, every sample rate and
 * every buffer size, and hands back zero-filled buffers at 3 % of real time. A Bluetooth
 * headset carries its own microphone, its own codec and its own link, and lands in
 * `bt-sco-mic-wb` past all of it. Measured in one four-minute run, 2026-08-12:
 *
 * | route | frames / muted | level |
 * |---|---|---|
 * | SCO + `VOICE_RECOGNITION` → `bt-sco-mic-wb` | **48640 / 0**, 0 errors | peak −6.2 dBFS |
 * | built-in, any source | 2560 / **2560 muted** | −inf |
 *
 * So the headset is **the normal path, not a fallback**, and the two things this file
 * pins are the two ways the old code failed him every single time he pressed the button:
 *
 * 1. **It opened a microphone that could not work**, then reported a capture fault — true
 *    and useless. Now a press with no headset opens nothing and says the handset mic is
 *    dead, which is the one thing he can act on.
 * 2. **It captured from the first millisecond**, so the ~600 ms of SCO setup would have
 *    eaten the front of every sentence. Now that wait is a visible held state and capture
 *    begins after it.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class HeadsetPttTest {

    private val augment = PttTarget("%1", "✳ Augment things")

    private val dispatcher = StandardTestDispatcher()
    private val scope = CoroutineScope(dispatcher)

    @After
    fun tearDown() = scope.cancel()

    private val trace = mutableListOf<String>()
    private val headset = FakeHeadset(trace)
    private val mic = TracingRecorder(trace)
    private val stt = FakeStt2("run the test suite")

    private fun ptt(clock: () -> Long = System::currentTimeMillis) =
        Ptt(mic, stt, scope, headset, clock)

    // --- ⚠️⚠️ 1. no headset is an answer, not a mystery -----------------------

    /**
     * ⚠️⚠️ **The regression this whole change exists for.**
     *
     * Every press he made opened the built-in microphone, which on this handset returns
     * zero-filled buffers, and the app then told him the capture had failed. The message
     * was accurate about the audio and led him nowhere: the fault is a dead analog front
     * end, and the fix is a headset. So the check happens *before* anything opens, and
     * the message names the handset mic as dead rather than reporting an absence.
     */
    @Test
    fun `a press with no headset opens no microphone and says the handset mic is dead`() =
        runTest(dispatcher) {
            headset.connected = false
            val ptt = ptt()

            ptt.press(augment)
            advanceUntilIdle()

            assertEquals("nothing may be opened without a headset", 0, mic.starts)
            assertEquals("and no link may be requested", 0, headset.opens)
            assertEquals(PttState.Failed(Ptt.NO_HEADSET), ptt.state.value)
            assertEquals(emptyList<String>(), trace)
        }

    /** ★ It has to point him at the fix, and not read as "capture went wrong". */
    @Test
    fun `the no-headset message names the dead handset mic and an earbud`() {
        val reason = Ptt.NO_HEADSET
        assertTrue("it must say the phone's own mic is the dead part",
            reason.contains("mic is dead"))
        assertTrue("it must say what to do", reason.contains("earbud"))
        assertTrue("it must not read as a capture fault he can retry",
            !reason.contains("dropped out") && !reason.contains("hold the button"))
        assertTrue("and it must not be confusable with the zero-samples fault",
            reason != Ptt.MIC_NOT_DELIVERING)
    }

    /** Nothing was transcribed, so nothing reached Whisper either. */
    @Test
    fun `a headset-less press never reaches whisper`() = runTest(dispatcher) {
        headset.connected = false
        val ptt = ptt()
        ptt.press(augment)
        ptt.release()
        advanceUntilIdle()
        assertEquals(0, stt.calls)
    }

    // --- ⚠️⚠️ 2. the 600 ms is held, never swallowed --------------------------

    /**
     * ⚠️⚠️ **The mic opens after the link is up, never before.**
     *
     * SCO takes about 600 ms on the XM6. Opening `AudioRecord` first would have produced
     * a recording whose first half-second is whatever the HAL felt like handing over —
     * which, on this handset, is zeroes — with no indication that the front of the
     * sentence was gone. The order below is the contract.
     */
    @Test
    fun `the microphone is not opened until the headset link is up`() = runTest(dispatcher) {
        val ptt = ptt()

        ptt.press(augment)
        assertEquals("capture must not have started", 0, mic.starts)
        assertTrue("and he must be told to keep holding",
            ptt.state.value is PttState.Connecting)

        // ⚠️ Only as far as the link — not `advanceUntilIdle`, which would run the
        // sixty-second cap out and finish the press before anything could be read.
        advanceTimeBy(headset.setupMs + 1)
        assertEquals(listOf("link.open", "link.up", "mic.start"), trace)
        assertTrue(ptt.state.value is PttState.Listening)
    }

    /** The wait is a state he can see, with the target he chose already on it. */
    @Test
    fun `the connecting state carries the press time and the destination`() =
        runTest(dispatcher) {
            var now = 1_000L
            val ptt = ptt { now }
            ptt.press(augment)

            assertEquals(PttState.Connecting(augment, 1_000L), ptt.state.value)

            now += 600L
            advanceTimeBy(headset.setupMs + 1)
            assertEquals(PttState.Listening(augment, 1_600L), ptt.state.value)
        }

    /**
     * ★ The cap is measured from **capture**, not from the press. The link setup is the
     * app's overhead; charging it against his sixty seconds of dictation would cut the
     * end off a long one.
     */
    @Test
    fun `the sixty-second cap runs from the moment capture starts`() = runTest(dispatcher) {
        var now = 0L
        val ptt = ptt { now }
        ptt.press(augment)
        advanceTimeBy(headset.setupMs + 1)
        now += headset.setupMs
        assertTrue(ptt.state.value is PttState.Listening)

        advanceTimeBy(Ptt.MAX_MS - 1_000)
        now += Ptt.MAX_MS - 1_000
        assertTrue("the setup must not be charged against the dictation",
            ptt.state.value is PttState.Listening)

        advanceUntilIdle()
        assertEquals(PttState.Confirming(augment, "run the test suite"), ptt.state.value)
    }

    // --- ⚠️ the link never outlives the press --------------------------------

    /**
     * ⚠️ SCO pins the headset in mono narrowband call mode for as long as it is up, and
     * an open link outside a press is a live microphone nobody asked for. It comes down
     * with the recorder, every time.
     */
    @Test
    fun `the link is torn down the moment the recorder closes`() = runTest(dispatcher) {
        val ptt = ptt()
        ptt.press(augment)
        advanceUntilIdle()
        ptt.release()

        assertEquals(listOf("link.open", "link.up", "mic.start", "mic.stop", "link.close"), trace)
        assertEquals(1, headset.closes)
    }

    @Test
    fun `cancel during the connect tears the link down and records nothing`() =
        runTest(dispatcher) {
            val ptt = ptt()
            ptt.press(augment)
            ptt.cancel()
            advanceUntilIdle()

            assertEquals("no microphone was ever opened", 0, mic.starts)
            assertTrue("the link must not be left up", headset.closes >= 1)
            assertEquals(PttState.Idle, ptt.state.value)
        }

    @Test
    fun `cancel while listening closes the link as well as the mic`() = runTest(dispatcher) {
        val ptt = ptt()
        ptt.press(augment)
        advanceUntilIdle()
        ptt.cancel()
        advanceUntilIdle()

        assertTrue(trace.contains("mic.discard"))
        assertEquals(PttState.Idle, ptt.state.value)
        assertTrue("cancel must not leave SCO up", headset.closes >= 1)
    }

    /** The cap ends the press, so it must release the link too. */
    @Test
    fun `hitting the cap closes the link`() = runTest(dispatcher) {
        val ptt = ptt { 0L }
        ptt.press(augment)
        advanceUntilIdle()
        assertTrue("the cap must not leave SCO up", headset.closes >= 1)
    }

    // --- letting go too early is not his fault -------------------------------

    /**
     * ★★ He let go during the connect. Nothing was captured — but "too short" would blame
     * his press for a wait the app imposed, which is precisely the class of message that
     * sent him looking in the wrong place last time. It tells him what to wait for.
     */
    @Test
    fun `letting go before the link is up blames the wait, not the press`() =
        runTest(dispatcher) {
            val ptt = ptt()
            ptt.press(augment)
            ptt.release()
            advanceUntilIdle()

            assertEquals(PttState.Failed(Ptt.RELEASED_WHILE_CONNECTING), ptt.state.value)
            assertEquals("nothing was recorded", 0, mic.starts)
            assertEquals(0, stt.calls)
            assertTrue("and the link must not be left up", headset.closes >= 1)
            assertTrue("it must not read as a fumbled press",
                Ptt.RELEASED_WHILE_CONNECTING != Ptt.TOO_SHORT)
            assertTrue("it must say what to wait for",
                Ptt.RELEASED_WHILE_CONNECTING.contains("LISTENING"))
        }

    /**
     * ⚠️ A release that lands after the link came up but before the state was read must
     * not leave a microphone open — the recorder is still started and stopped as a pair.
     */
    @Test
    fun `a release during the connect never leaves a microphone running`() =
        runTest(dispatcher) {
            val ptt = ptt()
            ptt.press(augment)
            ptt.release()
            advanceUntilIdle()
            assertFalse(mic.recording)
        }

    // --- the link failing is its own, named failure --------------------------

    @Test
    fun `a link that never comes up says so and opens no microphone`() = runTest(dispatcher) {
        headset.linkComesUp = false
        val ptt = ptt()

        ptt.press(augment)
        advanceUntilIdle()

        assertEquals(PttState.Failed(Ptt.HEADSET_NO_LINK), ptt.state.value)
        assertEquals(0, mic.starts)
        assertTrue("a failed connect must still be torn down", headset.closes >= 1)
        assertTrue("this is not the same fault as having no headset",
            Ptt.HEADSET_NO_LINK != Ptt.NO_HEADSET)
    }

    // --- ⚠️⚠️ the zero-samples discriminator survives ------------------------

    /**
     * ⚠️⚠️ **This must not be lost in the move to a headset.** A link that reports
     * CONNECTED and then delivers pure digital silence is still a microphone that never
     * started — a muted headset, or HFP up without audio flowing. A real microphone in a
     * silent room has a noise floor around −60 dBFS; all-zero samples are manufactured.
     * The message that names that stays, and stays distinct from "you didn't hold it".
     */
    @Test
    fun `a connected headset that delivers only zeroes still blames the input`() =
        runTest(dispatcher) {
            var now = 0L
            mic.willCapture(Recording(ByteArray(3_840)))   // 120 ms of pure zeroes
            val ptt = ptt { now }

            ptt.press(augment)
            advanceTimeBy(headset.setupMs + 1)
            now += headset.setupMs
            now += 3_449L
            ptt.release()
            advanceUntilIdle()

            val reason = (ptt.state.value as PttState.Failed).reason
            assertEquals(Ptt.MIC_NOT_DELIVERING, reason)
            assertTrue("it must not read as a mic that worked and stopped",
                !reason.contains("dropped out"))
            assertEquals("silence never goes to whisper", 0, stt.calls)
        }

    // --- ⚠️⚠️ the race a press across two threads created ---------------------

    /**
     * ⚠️⚠️ **A release that lands mid-connect must never walk away from an open mic.**
     *
     * The press is asynchronous now: it brings the headset link up on a coroutine and
     * opens the recorder there, while `release` arrives from the UI thread. Between
     * `recorder.start()` and the move to `Listening` there was a window in which a
     * release saw `Connecting`, said "let go too early", **and left the microphone
     * running** — a hot mic on a worn device, reached by nothing more exotic than a quick
     * tap. It showed up as `PttPolicyTest` failing about one run in three, which is
     * exactly how a concurrency bug announces itself and exactly how it gets dismissed
     * as flakiness.
     *
     * The two are one atomic step now. This hammers the window from two real threads;
     * against the unsynchronised version it fails within a few hundred iterations.
     */
    @Test
    fun `a release racing the start of capture never leaves a microphone open`() {
        repeat(400) {
            val scope = CoroutineScope(Dispatchers.Default)
            try {
                val headset = FakeHeadset().also { h -> h.setupMs = 0 }
                val mic = FakeRecorder()
                val ptt = Ptt(mic, FakeStt2("hello"), scope, headset)

                ptt.press(augment)
                // No sleep: land the release exactly where the coroutine is working.
                ptt.release()
                Thread.sleep(2)

                val state = ptt.state.value
                assertFalse(
                    "left recording in $state after press+release #$it",
                    mic.recording,
                )
                assertTrue(
                    "a press that never captured must not claim to be listening: $state",
                    state !is PttState.Listening || mic.recording,
                )
            } finally {
                scope.cancel()
            }
        }
    }

    // --- one press, one link -------------------------------------------------

    /**
     * ⚠️ A press repeated during the connect — the commonest thing a thumb does when a
     * button appears not to have worked — must not start a second SCO negotiation.
     */
    @Test
    fun `a press repeated while connecting never opens a second link`() = runTest(dispatcher) {
        val ptt = ptt()
        ptt.press(augment)
        repeat(20) { ptt.press(augment) }
        advanceUntilIdle()

        assertEquals("one press, one link", 1, headset.opens)
        assertEquals("one press, one recorder", 1, mic.starts)
    }

    // --- ⚠️⚠️ the tap that could not close what it opened ---------------------

    /**
     * ★★ **The safety regression.** The headset has one gesture, so the same tap must
     * start and stop. The panel used to make that decision from its own snapshot of the
     * state, which could be a recomposition behind — and when it guessed wrong it called
     * `press()` on an open microphone. `Ptt` logged "PRESS ignored, already Listening"
     * and **the mic stayed on**.
     *
     * That is what happened to the owner: a tap meant to stop a recording did nothing,
     * and 17 seconds of him and his crying son went through the transcriber before it
     * closed. [Ptt.toggle] decides against the state it owns, so this cannot recur.
     */
    @Test
    fun `a second toggle closes the microphone the first one opened`() =
        runTest(dispatcher) {
            val ptt = ptt()

            ptt.toggle(augment)
            // ⚠️ Only as far as the link — advanceUntilIdle would run the sixty-second
            // cap out and finish the recording before the second toggle could be tested,
            // which would pass for the wrong reason.
            advanceTimeBy(headset.setupMs + 1)
            assertTrue(
                "first toggle should be recording, was ${ptt.state.value}",
                ptt.state.value is PttState.Listening,
            )

            ptt.toggle(augment)
            assertFalse(
                "second toggle must not leave the mic open, was ${ptt.state.value}",
                ptt.state.value is PttState.Listening,
            )
        }

    /** ⚠️ And it must close from the SCO wait too — the window before capture starts. */
    @Test
    fun `a toggle during the SCO wait closes instead of opening a second recording`() =
        runTest(dispatcher) {
            val ptt = ptt()

            ptt.toggle(augment)
            assertTrue(
                "should be connecting, was ${ptt.state.value}",
                ptt.state.value is PttState.Connecting,
            )

            ptt.toggle(augment)
            advanceUntilIdle()
            assertFalse(
                "must not be left listening, was ${ptt.state.value}",
                ptt.state.value is PttState.Listening,
            )
        }
}

/** A local stand-in for Whisper — [PttTest]'s is private to that file. */
private class FakeStt2(private val reply: String) : SttClient {
    var calls = 0
        private set

    override suspend fun transcribe(recording: Recording): String {
        calls++
        return reply
    }
}
