package com.roam.touch.channels.stt

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.cancel
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException
import kotlin.math.sin
import kotlin.math.PI

/** A microphone that records nothing but remembers exactly when it was asked to. */
class FakeRecorder(private var next: Recording = speech()) : Recorder {
    var starts = 0
        private set
    var stops = 0
        private set
    var discards = 0
        private set
    var refuse = false

    override var recording: Boolean = false
        private set

    override fun start(): Boolean {
        if (refuse) return false
        starts++
        recording = true
        return true
    }

    override fun stop(): Recording {
        stops++
        recording = false
        return next
    }

    override fun discard() {
        discards++
        recording = false
    }

    fun willCapture(recording: Recording) {
        next = recording
    }

    companion object {
        /** Two seconds of something loud enough to be a sentence. */
        fun speech(ms: Int = 2_000): Recording {
            val samples = Pcm.RATE * ms / 1_000
            val pcm = ByteArray(samples * 2)
            for (i in 0 until samples) {
                val s = (8_000 * sin(2 * PI * 220 * i / Pcm.RATE)).toInt()
                pcm[i * 2] = (s and 0xFF).toByte()
                pcm[i * 2 + 1] = ((s shr 8) and 0xFF).toByte()
            }
            return Recording(pcm)
        }

        /** Long enough to pass the duration gate, far too quiet to be speech. */
        fun silence(ms: Int = 2_000) = Recording(ByteArray(Pcm.RATE * ms / 1_000 * 2))
    }
}

private class FakeStt(var reply: String = "run the test suite") : SttClient {
    var calls = 0
        private set
    var fail: IOException? = null
    var lastAudio: Recording? = null

    override suspend fun transcribe(recording: Recording): String {
        calls++
        lastAudio = recording
        fail?.let { throw it }
        return reply
    }
}

/**
 * ★★ Push to talk, and the confirmation that guards it.
 *
 * The loop under test is the one the architecture specifies: **PTT → Whisper → "send
 * «transcript» to «channel»?" → Send / Redo / Cancel.** Two properties matter more than
 * all the rest, and each has several tests pointed at it:
 *
 * 1. **Nothing records without a press**, and every press ends.
 * 2. **The words and the destination are confirmed together**, and the destination is
 *    the one that was on screen when he started talking — not whatever it is when he
 *    finishes.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class PttTest {

    private val augment = PttTarget("%1", "✳ Augment things")
    private val roam = PttTarget("%3", "◑ Roam Touch rebuild")

    /**
     * The controller's own scope, on the same virtual clock as the test.
     *
     * ⚠️ Not `runTest`'s `backgroundScope`: the 60-second cap timer would never be
     * advanced there, and every assertion after a release would read a stale state.
     * Sharing one [StandardTestDispatcher] means `advanceUntilIdle()` drives the
     * controller exactly as a real dispatcher would, only instantly.
     */
    private val dispatcher = StandardTestDispatcher()
    private val scope = CoroutineScope(dispatcher)

    @After
    fun tearDown() = scope.cancel()

    private fun mic() = FakeRecorder()

    // --- the happy path -----------------------------------------------------

    @Test
    fun `press listens, release transcribes, and the result awaits confirmation`() = runTest(dispatcher) {
        val rec = mic()
        val stt = FakeStt("run the test suite")
        val ptt = Ptt(rec, stt, scope) { 1_000L }

        assertEquals(PttState.Idle, ptt.state.value)

        ptt.press(augment)
        assertEquals(1, rec.starts)
        assertTrue(rec.recording)
        assertEquals(PttState.Listening(augment, 1_000L), ptt.state.value)

        ptt.release()
        assertEquals(1, rec.stops)
        assertTrue("the mic closes on release", !rec.recording)
        assertEquals(PttState.Transcribing(augment), ptt.state.value)

        advanceUntilIdle()
        assertEquals(PttState.Confirming(augment, "run the test suite"), ptt.state.value)
    }

    @Test
    fun `confirm hands over the words and the pane they were spoken to`() = runTest(dispatcher) {
        val ptt = Ptt(mic(), FakeStt("continue"), scope)
        ptt.press(roam)
        ptt.release()
        advanceUntilIdle()

        val confirmed = ptt.confirm()
        assertEquals(PttConfirmed("%3", "continue"), confirmed)
        assertTrue(ptt.state.value is PttState.Sending)

        ptt.sent()
        assertEquals(PttState.Idle, ptt.state.value)
    }

    /**
     * ★★ The routing guarantee, stated as a test.
     *
     * The confirmation carries the pane from the press. Nothing that happens between
     * the press and the Send — an outcome landing, a redo aimed at another channel —
     * can move a sentence to a session he did not choose while saying it.
     */
    @Test
    fun `the destination is the one that was on screen when he started talking`() = runTest(dispatcher) {
        val ptt = Ptt(mic(), FakeStt("deploy it"), scope)

        ptt.press(augment)
        ptt.release()
        advanceUntilIdle()
        assertEquals(augment, (ptt.state.value as PttState.Confirming).target)
        assertEquals("%1", ptt.confirm()!!.paneId)
        ptt.sent()

        // A second press, on a different channel, routes to that one — and only from
        // the press, which is the only place a target is ever taken from.
        ptt.press(roam)
        ptt.release()
        advanceUntilIdle()
        assertEquals("%3", ptt.confirm()!!.paneId)
    }

    @Test
    fun `send cannot fire twice for one sentence`() = runTest(dispatcher) {
        val ptt = Ptt(mic(), FakeStt("yes"), scope)
        ptt.press(augment)
        ptt.release()
        advanceUntilIdle()

        assertEquals(PttConfirmed("%1", "yes"), ptt.confirm())
        assertNull("a second Send has nothing to send", ptt.confirm())
    }

    // --- ⚠️ the guards against Whisper's imagination ------------------------

    /**
     * ⚠️⚠️ Measured, not theorised: one second of digital silence through
     * `wyoming-faster-whisper` at `talos:10300` came back as **"Smart home commands."**
     * — a confident sentence nobody said. The service declares
     * `requires_external_vad: true`; the PTT button is that VAD, and this is its floor.
     */
    @Test
    fun `silence is never sent to whisper at all`() = runTest(dispatcher) {
        val rec = mic().also { it.willCapture(FakeRecorder.silence()) }
        val stt = FakeStt("Smart home commands.")
        val ptt = Ptt(rec, stt, scope)

        ptt.press(augment)
        ptt.release()
        advanceUntilIdle()

        assertEquals(0, stt.calls)
        assertEquals(PttState.Failed(Ptt.TOO_QUIET), ptt.state.value)
    }

    @Test
    fun `a fumbled tap is rejected on duration before anything is transcribed`() = runTest(dispatcher) {
        val rec = mic().also { it.willCapture(FakeRecorder.speech(ms = 100)) }
        val stt = FakeStt()
        val ptt = Ptt(rec, stt, scope)

        ptt.press(augment)
        ptt.release()
        advanceUntilIdle()

        assertEquals(0, stt.calls)
        assertEquals(PttState.Failed(Ptt.TOO_SHORT), ptt.state.value)
    }

    @Test
    fun `an empty transcript is a failure, not an empty confirmation`() = runTest(dispatcher) {
        val ptt = Ptt(mic(), FakeStt(reply = "   "), scope)
        ptt.press(augment)
        ptt.release()
        advanceUntilIdle()
        assertEquals(PttState.Failed(Ptt.NOTHING_HEARD), ptt.state.value)
    }

    // --- failures say which failure it was ----------------------------------

    @Test
    fun `an unreachable whisper is distinguishable from a refused one`() = runTest(dispatcher) {
        val unreachable = FakeStt().also { it.fail = IOException("connect timed out") }
        val ptt = Ptt(mic(), unreachable, scope)
        ptt.press(augment); ptt.release(); advanceUntilIdle()
        assertEquals(PttState.Failed(Ptt.WHISPER_UNREACHABLE), ptt.state.value)

        val refused = FakeStt().also { it.fail = SttException("model not loaded") }
        val ptt2 = Ptt(mic(), refused, scope)
        ptt2.press(augment); ptt2.release(); advanceUntilIdle()
        assertEquals(PttState.Failed("model not loaded"), ptt2.state.value)
    }

    @Test
    fun `a microphone that will not open says so instead of silently doing nothing`() =
        runTest(dispatcher) {
            val rec = mic().also { it.refuse = true }
            val ptt = Ptt(rec, FakeStt(), scope)
            ptt.press(augment)
            assertEquals(PttState.Failed(Ptt.NO_MIC), ptt.state.value)
            ptt.release()
            assertEquals("release on a mic that never opened is a no-op",
                PttState.Failed(Ptt.NO_MIC), ptt.state.value)
        }

    @Test
    fun `a failure clears without starting anything`() = runTest(dispatcher) {
        val rec = mic().also { it.refuse = true }
        val ptt = Ptt(rec, FakeStt(), scope)
        ptt.press(augment)
        ptt.clear()
        assertEquals(PttState.Idle, ptt.state.value)
        assertEquals("clearing a message must not open a mic", 0, rec.starts)
    }

    // --- ⚠️ the transcript is never thrown away silently --------------------

    /**
     * ⚠️ Redo is a press-and-hold, so the commonest fumble on a worn screen — a hold
     * that lands as a tap — must not delete a sentence he already said. He gets it
     * back with the complaint written on it.
     */
    @Test
    fun `a fumbled redo returns the original transcript with the reason attached`() =
        runTest(dispatcher) {
            val rec = mic()
            val ptt = Ptt(rec, FakeStt("run the test suite"), scope)
            ptt.press(augment); ptt.release(); advanceUntilIdle()
            assertEquals(PttState.Confirming(augment, "run the test suite"), ptt.state.value)

            rec.willCapture(FakeRecorder.speech(ms = 80))
            ptt.press(augment); ptt.release(); advanceUntilIdle()

            assertEquals(
                PttState.Confirming(augment, "run the test suite", error = Ptt.TOO_SHORT),
                ptt.state.value,
            )
        }

    @Test
    fun `a redo that works replaces the transcript outright`() = runTest(dispatcher) {
        val rec = mic()
        val stt = FakeStt("run the tests")
        val ptt = Ptt(rec, stt, scope)
        ptt.press(augment); ptt.release(); advanceUntilIdle()

        stt.reply = "run the tests and deploy"
        ptt.press(augment); ptt.release(); advanceUntilIdle()
        assertEquals(
            PttState.Confirming(augment, "run the tests and deploy"),
            ptt.state.value,
        )
    }

    /**
     * ⚠️ A refused send hands the words back rather than swallowing them. He said a
     * sentence out loud; a dead pane is not a reason to make him say it again.
     */
    @Test
    fun `a refused send returns the transcript to the confirm step`() = runTest(dispatcher) {
        val ptt = Ptt(mic(), FakeStt("continue"), scope)
        ptt.press(augment); ptt.release(); advanceUntilIdle()
        ptt.confirm()

        ptt.sendFailed("pane is gone")
        assertEquals(
            PttState.Confirming(augment, "continue", error = "pane is gone"),
            ptt.state.value,
        )
        // And it can be sent again once he picks a live channel.
        assertEquals(PttConfirmed("%1", "continue"), ptt.confirm())
    }

    // --- cancel, and the mic always closing ---------------------------------

    @Test
    fun `cancel from listening closes the mic and keeps nothing`() = runTest(dispatcher) {
        val rec = mic()
        val ptt = Ptt(rec, FakeStt(), scope)
        ptt.press(augment)
        ptt.cancel()
        assertEquals(1, rec.discards)
        assertTrue(!rec.recording)
        assertEquals(PttState.Idle, ptt.state.value)
    }

    @Test
    fun `cancel from a pending confirmation drops the transcript`() = runTest(dispatcher) {
        val ptt = Ptt(mic(), FakeStt("delete everything"), scope)
        ptt.press(augment); ptt.release(); advanceUntilIdle()
        ptt.cancel()
        assertEquals(PttState.Idle, ptt.state.value)
        assertNull("nothing is left to send", ptt.confirm())
    }

    @Test
    fun `cancel while transcribing abandons the result`() = runTest(dispatcher) {
        val ptt = Ptt(mic(), FakeStt("something"), scope)
        ptt.press(augment)
        ptt.release()
        assertEquals(PttState.Transcribing(augment), ptt.state.value)
        ptt.cancel()
        advanceUntilIdle()
        assertEquals(PttState.Idle, ptt.state.value)
    }

    /**
     * ⚠️ A thumb that never comes up — a snagged sleeve, a pointer event eaten by a
     * scroll — must not hold a microphone open forever on a worn device.
     */
    @Test
    fun `a press that is never released still ends, and keeps what it heard`() = runTest(dispatcher) {
        val rec = mic()
        val ptt = Ptt(rec, FakeStt("a long dictation"), scope) { 0L }
        ptt.press(augment)

        advanceTimeBy(Ptt.MAX_MS - 1_000)
        assertTrue("still listening before the cap", ptt.state.value is PttState.Listening)

        advanceUntilIdle()
        assertEquals("the mic is closed", 1, rec.stops)
        assertEquals(PttState.Confirming(augment, "a long dictation"), ptt.state.value)
    }

    // --- presses that must be ignored ---------------------------------------

    @Test
    fun `a second press while listening does not open a second mic`() = runTest(dispatcher) {
        val rec = mic()
        val ptt = Ptt(rec, FakeStt(), scope)
        ptt.press(augment)
        ptt.press(roam)
        assertEquals(1, rec.starts)
        assertEquals(augment, (ptt.state.value as PttState.Listening).target)
    }

    @Test
    fun `a press while transcribing or sending is ignored`() = runTest(dispatcher) {
        val rec = mic()
        val ptt = Ptt(rec, FakeStt("hello"), scope)
        ptt.press(augment)
        ptt.release()
        ptt.press(roam)
        assertEquals("no mic during transcription", 1, rec.starts)

        advanceUntilIdle()
        ptt.confirm()
        ptt.press(roam)
        assertEquals("no mic during a send", 1, rec.starts)
    }

    @Test
    fun `release without a press does nothing at all`() = runTest(dispatcher) {
        val rec = mic()
        val ptt = Ptt(rec, FakeStt(), scope)
        ptt.release()
        assertEquals(PttState.Idle, ptt.state.value)
        assertEquals(0, rec.stops)
    }

    // --- what the wearer sees ------------------------------------------------

    @Test
    fun `the level meter only moves while the mic is open`() = runTest(dispatcher) {
        val ptt = Ptt(mic(), FakeStt(), scope) { 5L }
        ptt.onLevel(-22.0)
        assertEquals("no level outside listening", PttState.Idle, ptt.state.value)

        ptt.press(augment)
        ptt.onLevel(-22.0)
        assertEquals(-22.0, (ptt.state.value as PttState.Listening).levelDbfs, 0.001)

        ptt.release()
        ptt.onLevel(-10.0)
        assertEquals(PttState.Transcribing(augment), ptt.state.value)
    }

    /** Whisper is handed exactly the audio that was captured — no resampling anywhere. */
    @Test
    fun `the captured audio reaches whisper unchanged`() = runTest(dispatcher) {
        val captured = FakeRecorder.speech(ms = 1_500)
        val rec = mic().also { it.willCapture(captured) }
        val stt = FakeStt()
        val ptt = Ptt(rec, stt, scope)
        ptt.press(augment); ptt.release(); advanceUntilIdle()

        assertEquals(Pcm.RATE, stt.lastAudio!!.rate)
        assertEquals(1_500L, stt.lastAudio!!.durationMs)
        assertTrue(captured.pcm.contentEquals(stt.lastAudio!!.pcm))
    }
}
