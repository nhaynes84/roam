package com.roam.touch.channels.stt

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

/**
 * A microphone that behaves exactly as told.
 *
 * `script` is one entry per read: a positive number of bytes, `0` for "nothing right
 * now", or a negative [android.media.AudioRecord] error code. Once the script runs out
 * it idles, so a test can stop the recorder at a known point.
 */
private class ScriptedSource(
    override val bufferBytes: Int = 16_000,
    private val script: List<Int> = emptyList(),
) : PcmSource {

    private val next = AtomicInteger(0)
    val exhausted = CountDownLatch(1)
    val requestedSizes = mutableListOf<Int>()

    @Volatile
    var closed = false
        private set

    override fun read(into: ByteArray, size: Int): Int {
        synchronized(requestedSizes) { requestedSizes += size }
        val i = next.getAndIncrement()
        if (i >= script.size) {
            exhausted.countDown()
            Thread.sleep(2)
            return 0
        }
        if (i == script.size - 1) exhausted.countDown()
        val n = script[i]
        if (n > 0) {
            check(n <= size) { "source asked to return $n into a $size buffer" }
            // Loud enough to clear the level gate, so these tests exercise the real path.
            for (j in 0 until n step 2) {
                into[j] = 0x00
                if (j + 1 < n) into[j + 1] = 0x20
            }
        }
        return n
    }

    override fun close() {
        closed = true
    }
}

/**
 * ★★ The drain loop, which is where push-to-talk actually broke on hardware.
 *
 * ⚠️ **A caveat, added 2026-08-12.** The contract below is right and stays. The *story*
 * underneath it did not survive measurement: sailfish's audio HAL fails `pcm_prepare`
 * for every source, rate and buffer size, and hands back zero-filled buffers at 3 % of
 * real time — which alone explains the 240 ms-from-a-5-second-hold that this loop was
 * blamed for. Keep these tests; do not treat them as evidence about that device.
 *
 * ⚠️⚠️ **The bug this file exists for.** Nexus 0.4 did `if (n <= 0) break`. On sailfish
 * `AudioRecord.read` returned **0** after two buffers — thought at the time to be the
 * app asking for 4096 bytes out of a 3840-byte buffer — and the reader thread exited
 * while `running` stayed true. The recorder still reported one clean open and one clean
 * close with no error line, so a **five-second hold produced 240 ms of audio** and the
 * app blamed the user for not holding the button.
 *
 * None of this was testable while the loop was welded to `AudioRecord`; that is why it
 * shipped. It is now behind [PcmSource] and every one of those conditions is pinned
 * below.
 */
class MicRecorderTest {

    private fun recorder(
        source: ScriptedSource,
        onLevel: (Double) -> Unit = {},
    ) = MicRecorder(onLevel = onLevel, open = { source }, sleep = {})

    private fun ScriptedSource.awaitDrained() =
        assertTrue("the source was never fully read", exhausted.await(5, TimeUnit.SECONDS))

    // --- ⚠️⚠️ the regression -------------------------------------------------

    /**
     * ⚠️⚠️ **Zero is not end-of-stream.** This is the exact shape of the sailfish
     * failure: good reads, a zero, then more good reads. Every byte must survive.
     */
    @Test
    fun `a zero-length read does not end the recording`() {
        val source = ScriptedSource(script = listOf(3840, 3840, 0, 3840, 3840, 3840))
        val mic = recorder(source)

        assertTrue(mic.start())
        source.awaitDrained()
        val recording = mic.stop()

        assertEquals("every byte either side of the stall", 5 * 3840, recording.pcm.size)
    }

    @Test
    fun `a long run of zeros is survived, not treated as the end`() {
        val script = listOf(3840) + List(MicRecorder.MAX_EMPTY_READS - 1) { 0 } + listOf(3840)
        val source = ScriptedSource(script = script)
        val mic = recorder(source)

        mic.start()
        source.awaitDrained()
        assertEquals(2 * 3840, mic.stop().pcm.size)
    }

    /**
     * ⚠️ The other half of the sailfish bug: the app asked for **more than the capture
     * buffer held**. A read request larger than the buffer is what made the HAL return
     * zero in the first place, so it can never be issued again.
     */
    @Test
    fun `the recorder never asks for more than half the capture buffer`() {
        val source = ScriptedSource(bufferBytes = 3_840, script = listOf(1920, 1920))
        val mic = recorder(source)

        mic.start()
        source.awaitDrained()
        mic.stop()

        val asked = synchronized(source.requestedSizes) { source.requestedSizes.toList() }
        assertTrue("nothing was read", asked.isNotEmpty())
        assertTrue(
            "asked for ${asked.max()} B of a ${source.bufferBytes} B buffer",
            asked.all { it <= source.bufferBytes / 2 },
        )
    }

    @Test
    fun `the chunk size is bounded by the buffer at both ends`() {
        // sailfish: a 3840 B buffer must never see a 4096 B request.
        assertEquals(1_920, MicRecorder.chunkFor(3_840))
        // A generous buffer is still capped, so one read is never a huge allocation.
        assertEquals(4_096, MicRecorder.chunkFor(64_000))
        // A pathologically small buffer still gets a usable chunk.
        assertEquals(512, MicRecorder.chunkFor(64))
    }

    /**
     * ⚠️⚠️ **The capture buffer is a whole number of the driver's own buffers.**
     *
     * `getMinBufferSize` is the only size this device has ever agreed to; a byte count
     * computed from a millisecond target is a guess, and 0.5 shipped one (16000 B, from
     * "at least half a second") on a theory that a 2026-08-12 probe then disproved —
     * 1280 B, 5120 B and 16000 B all failed identically on sailfish. This is the shape
     * that survives being wrong about the cause: whatever the driver offers, times a
     * whole number.
     */
    @Test
    fun `the capture buffer is always a whole multiple of the driver's minimum`() {
        // sailfish, measured: getMinBufferSize returns 1280 B (40 ms) → 320 ms.
        assertEquals(10_240, MicRecorder.bufferFor(1_280))
        assertEquals(0, MicRecorder.bufferFor(960) % 960)
        assertEquals(0, MicRecorder.bufferFor(3_840) % 3_840)
        assertEquals(0, MicRecorder.bufferFor(20_000) % 20_000)
    }

    /** Never fewer than eight driver buffers of headroom, and never a silly allocation. */
    @Test
    fun `the capture buffer keeps its headroom at both ends`() {
        // A tiny minimum is padded out rather than taken literally...
        assertTrue(MicRecorder.bufferFor(320) >= 320 * 8)
        // ...and a huge one is not multiplied into megabytes.
        assertTrue(MicRecorder.bufferFor(20_000) <= 20_000 * 16)
        // A press is never longer than the buffer's own worth of chunks: the chunk
        // must still fit twice over, whatever the driver said.
        listOf(320, 960, 1_280, 3_840, 20_000).forEach { min ->
            val buffer = MicRecorder.bufferFor(min)
            assertTrue("$min B min gave a $buffer B buffer",
                MicRecorder.chunkFor(buffer) * 2 <= buffer)
        }
    }

    // --- a genuine error still stops, and says so ---------------------------

    @Test
    fun `a negative error code ends the session and keeps what was captured`() {
        // -3 is AudioRecord.ERROR_INVALID_OPERATION. The error is the last thing the
        // loop reads: unlike a zero, a negative code genuinely ends the session.
        val source = ScriptedSource(script = listOf(3840, 3840, -3))
        val mic = recorder(source)

        mic.start()
        source.awaitDrained()
        val recording = mic.stop()

        // What arrived before the fault is kept — never thrown away.
        assertEquals(2 * 3840, recording.pcm.size)
    }

    @Test
    fun `a source that throws does not take the process with it`() {
        val source = object : PcmSource {
            override val bufferBytes = 16_000
            val hit = CountDownLatch(1)
            override fun read(into: ByteArray, size: Int): Int {
                hit.countDown()
                throw IllegalStateException("HAL went away")
            }
            override fun close() = Unit
        }
        val mic = MicRecorder(open = { source }, sleep = {})
        assertTrue(mic.start())
        assertTrue(source.hit.await(5, TimeUnit.SECONDS))
        assertEquals(0, mic.stop().pcm.size)
    }

    // --- ★ one press, one recorder -------------------------------------------

    /**
     * ★ The guard the coordinator asked for. A second start while a session is live is
     * a bug upstream, and it must fail loudly rather than silently succeed — the old
     * code returned `true` here, which would have hidden a press-cycling fault entirely.
     */
    @Test
    fun `a second start while one is live is refused`() {
        val source = ScriptedSource(script = List(50) { 3840 })
        val mic = recorder(source)

        assertTrue(mic.start())
        assertFalse("the second start must fail, not silently succeed", mic.start())
        assertTrue(mic.recording)
        mic.stop()
        assertFalse(mic.recording)
    }

    @Test
    fun `each press gets a fresh buffer, never the previous press's audio`() {
        val first = ScriptedSource(script = listOf(3840, 3840))
        val second = ScriptedSource(script = listOf(3840))
        var next: ScriptedSource = first
        val mic = MicRecorder(open = { next }, sleep = {})

        mic.start(); first.awaitDrained()
        assertEquals(2 * 3840, mic.stop().pcm.size)

        next = second
        mic.start(); second.awaitDrained()
        assertEquals("the second press must not inherit the first", 3840, mic.stop().pcm.size)
    }

    @Test
    fun `the source is closed on stop and on discard`() {
        val stopped = ScriptedSource(script = listOf(3840))
        recorder(stopped).also { it.start(); stopped.awaitDrained(); it.stop() }
        assertTrue("stop must release the microphone", stopped.closed)

        val discarded = ScriptedSource(script = listOf(3840))
        recorder(discarded).also { it.start(); discarded.awaitDrained(); it.discard() }
        assertTrue("cancel must release the microphone", discarded.closed)
    }

    @Test
    fun `a microphone that will not open reports failure rather than pretending`() {
        val mic = MicRecorder(open = { null })
        assertFalse(mic.start())
        assertFalse(mic.recording)
        assertEquals(0, mic.stop().pcm.size)
    }

    // --- what the wearer sees -------------------------------------------------

    @Test
    fun `the level meter is fed from the audio actually captured`() {
        val levels = mutableListOf<Double>()
        val source = ScriptedSource(script = listOf(3840, 3840))
        val mic = recorder(source) { synchronized(levels) { levels += it } }

        mic.start()
        source.awaitDrained()
        mic.stop()

        val seen = synchronized(levels) { levels.toList() }
        assertTrue("the meter never moved", seen.isNotEmpty())
        assertTrue("scripted audio should clear the gate", seen.all { it > Ptt.MIN_RMS_DBFS })
    }

    @Test
    fun `the captured audio reports its own duration`() {
        // One second at 16 kHz mono 16-bit.
        val source = ScriptedSource(script = List(1000 / 120 + 1) { 3840 })
        val mic = recorder(source)
        mic.start()
        source.awaitDrained()
        val recording = mic.stop()
        assertEquals(recording.pcm.size / 2 * 1000L / Pcm.RATE, recording.durationMs)
    }
}
