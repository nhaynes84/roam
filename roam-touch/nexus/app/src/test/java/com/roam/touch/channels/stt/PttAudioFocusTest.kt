package com.roam.touch.channels.stt

import com.roam.touch.channels.audio.AudioHold
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.cancel
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException

/**
 * The audio the press took, as a trace shared with the recorder and the link so the
 * *ordering* can be asserted — which is the property that matters, not the counts.
 */
private class TracingAudio(private val trace: MutableList<String>) : AudioHold {

    var begins = 0
        private set
    var ends = 0
        private set

    /** True while this object believes a press is holding the phone's audio. */
    val held: Boolean get() = begins > ends

    override fun begin() {
        begins++
        trace += "audio.begin"
    }

    override fun end() {
        ends++
        trace += "audio.end"
    }
}

/**
 * A recorder that writes into the same trace as the link and the audio hold, so the one
 * ordering that matters — audio taken, link up, mic open — can be asserted across all
 * three.
 */
private class TracingRec(private val trace: MutableList<String>) : Recorder {

    override var recording: Boolean = false
        private set

    override fun start(): Boolean {
        trace += "mic.start"
        recording = true
        return true
    }

    override fun stop(): Recording {
        trace += "mic.stop"
        recording = false
        return FakeRecorder.speech()
    }

    override fun discard() {
        recording = false
    }
}

private class QuietStt(private val reply: String = "shut the garage") : SttClient {
    var fail: IOException? = null
    override suspend fun transcribe(recording: Recording): String {
        fail?.let { throw it }
        return reply
    }
}

/**
 * ★★ **The music stops when the microphone opens, and it comes back however the press
 * ends.**
 *
 * The owner wears the phone on his forearm and hears everything through one Bluetooth
 * headset — the same headset that carries the only working microphone this handset has.
 * Before this, keying PTT left the hub's radio playing into the ear he was talking with;
 * his report was that *he talks over his own music every time*.
 *
 * ⚠️⚠️ The half that is easy to get wrong is not the pause, it is the release. A press
 * can end **six** ways — thumb up, the 60 s cap, cancel, no link, no mic, and letting go
 * mid-connect — and every one of them has to hand the audio back. One that does not is a
 * radio that never plays again until the app is restarted, with nothing on screen to say
 * why. Each of those paths gets a test here, deliberately, and they are the reason
 * [Ptt.closeLink] exists rather than a call at each site.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class PttAudioFocusTest {

    private val target = PttTarget("%1", "✳ Augment things")

    private val dispatcher = StandardTestDispatcher()
    private val scope = CoroutineScope(dispatcher)

    private val trace = mutableListOf<String>()
    private val audio = TracingAudio(trace)

    @After
    fun tearDown() = scope.cancel()

    private fun ptt(
        recorder: Recorder = FakeRecorder(),
        stt: SttClient = QuietStt(),
        headset: FakeHeadset = FakeHeadset(trace).also { it.setupMs = 0 },
    ) = Ptt(recorder, stt, scope, headset, { 1_000L }, audio)

    private fun Ptt.hold(): Ptt {
        press(target)
        dispatcher.scheduler.runCurrent()
        return this
    }

    // ---- the pause happens first ------------------------------------------------------

    @Test
    fun `the audio is taken before the link comes up, not after`() = runTest(dispatcher) {
        // ★★ The ordering *is* the fix. SCO takes ~600 ms to establish and the recording
        // starts the instant it does; silencing the radio at the far end of that wait
        // would leave music playing through the whole CONNECTING state and into his first
        // word.
        val headset = FakeHeadset(trace).also { it.setupMs = 600 }
        val p = Ptt(TracingRec(trace), QuietStt(), scope, headset, { 1_000L }, audio)
        p.press(target)
        advanceUntilIdle()

        assertEquals(
            listOf("audio.begin", "link.open", "link.up", "mic.start"),
            trace.take(4),
        )
    }

    @Test
    fun `a press with no headset takes nothing at all`() = runTest(dispatcher) {
        // ⚠️ This press cannot record — the handset's own mic is dead — so it must not
        // silence his music on the way to saying so.
        val headset = FakeHeadset(trace, connected = false)
        val p = Ptt(FakeRecorder(), QuietStt(), scope, headset, { 1_000L }, audio)
        p.press(target)
        advanceUntilIdle()

        assertEquals(0, audio.begins)
        assertTrue(p.state.value is PttState.Failed)
    }

    // ---- every way a press can end ----------------------------------------------------

    @Test
    fun `thumb up hands the audio back`() = runTest(dispatcher) {
        val p = ptt().hold()
        assertTrue("the radio is silenced while the mic is open", audio.held)

        p.release()
        advanceUntilIdle()
        assertEquals(1, audio.ends)
        assertTrue("released before whisper answers, not after", !audio.held)
    }

    @Test
    fun `the audio comes back on release, not when the transcript does`() = runTest(dispatcher) {
        // ★ He let go; the words are Whisper's problem now. Holding the music down for a
        // network round trip he cannot see would be a radio that stutters on every press.
        val p = ptt().hold()
        p.release()
        // ⚠️ Asserted before the dispatcher is run at all: the release path hands the
        // audio back on the same line it closes the link, and the state it leaves behind
        // is TRANSCRIBING — Whisper has not answered yet and the music is already back.
        assertEquals(PttState.Transcribing(target), p.state.value)
        assertEquals(1, audio.ends)
        advanceUntilIdle()
    }

    @Test
    fun `cancel hands the audio back`() = runTest(dispatcher) {
        val p = ptt().hold()
        p.cancel()
        advanceUntilIdle()
        assertTrue(!audio.held)
    }

    @Test
    fun `the sixty second cap hands the audio back`() = runTest(dispatcher) {
        // ⚠️ A snagged sleeve, a stuck pointer event. The mic closes on its own and the
        // audio must go with it.
        val p = ptt().hold()
        advanceTimeBy(Ptt.MAX_MS + 1)
        advanceUntilIdle()
        assertTrue(!audio.held)
    }

    @Test
    fun `letting go mid-connect hands the audio back`() = runTest(dispatcher) {
        // ★ The commonest fumble there is: a tap where a hold was meant, landing inside
        // the 600 ms of link setup. Nothing was recorded — and nothing may be left held.
        val headset = FakeHeadset(trace).also { it.setupMs = 600 }
        val p = Ptt(FakeRecorder(), QuietStt(), scope, headset, { 1_000L }, audio)
        p.press(target)
        dispatcher.scheduler.runCurrent()
        p.release()
        advanceUntilIdle()

        assertEquals(Ptt.RELEASED_WHILE_CONNECTING, (p.state.value as PttState.Failed).reason)
        assertTrue(!audio.held)
    }

    @Test
    fun `a link that never comes up hands the audio back`() = runTest(dispatcher) {
        val headset = FakeHeadset(trace).also { it.setupMs = 0; it.linkComesUp = false }
        val p = Ptt(FakeRecorder(), QuietStt(), scope, headset, { 1_000L }, audio)
        p.press(target)
        advanceUntilIdle()

        assertEquals(Ptt.HEADSET_NO_LINK, (p.state.value as PttState.Failed).reason)
        assertTrue(!audio.held)
    }

    @Test
    fun `a microphone that refuses to open hands the audio back`() = runTest(dispatcher) {
        val rec = FakeRecorder().also { it.refuse = true }
        val p = ptt(recorder = rec)
        p.press(target)
        advanceUntilIdle()

        assertEquals(Ptt.NO_MIC, (p.state.value as PttState.Failed).reason)
        assertTrue(!audio.held)
    }

    @Test
    fun `a whisper that fails still leaves the audio released`() = runTest(dispatcher) {
        val stt = QuietStt().also { it.fail = IOException("whisper is down") }
        val p = ptt(stt = stt).hold()
        p.release()
        advanceUntilIdle()

        assertTrue(p.state.value is PttState.Failed)
        assertTrue(!audio.held)
    }

    @Test
    fun `the earbud hang-up hands the audio back`() = runTest(dispatcher) {
        // ★ While SCO is up a tap on the earbud is a hang-up, and that is the wearer's
        // stop. It ends the press, so it ends the hold on the audio.
        val headset = FakeHeadset(trace).also { it.setupMs = 0 }
        val p = Ptt(FakeRecorder(), QuietStt(), scope, headset, { 1_000L }, audio)
        p.press(target)
        dispatcher.scheduler.runCurrent()
        headset.hangUp()
        advanceUntilIdle()
        assertTrue(!audio.held)
    }

    // ---- pressing again ---------------------------------------------------------------

    @Test
    fun `a second press after a failure takes the audio again`() = runTest(dispatcher) {
        // ⚠️ The hold has to be re-takeable. An early version released once and never
        // re-requested, so the music came back and then played over every press after the
        // first.
        val p = ptt().hold()
        p.release()
        advanceUntilIdle()
        assertTrue(!audio.held)

        p.press(target)
        dispatcher.scheduler.runCurrent()
        assertTrue(audio.held)
        assertEquals(2, audio.begins)
    }

    @Test
    fun `a press ignored because one is already live does not double-take the audio`() =
        runTest(dispatcher) {
            val p = ptt().hold()
            p.press(target)
            dispatcher.scheduler.runCurrent()
            assertEquals(1, audio.begins)
        }
}
