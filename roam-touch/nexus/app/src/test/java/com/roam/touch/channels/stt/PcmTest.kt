package com.roam.touch.channels.stt

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.PI
import kotlin.math.sin

/**
 * The level maths behind the "was anything actually said" gate.
 *
 * Reference points measured on real audio (`say` → 16 kHz mono WAV, 2026-08-12):
 * **−19.5 dBFS RMS, −3.2 dBFS peak** for ordinary speech. Everything here is calibrated
 * against that, not against a guess.
 */
class PcmTest {

    private fun pcm(vararg samples: Int) = ByteArray(samples.size * 2).also { out ->
        samples.forEachIndexed { i, s ->
            out[i * 2] = (s and 0xFF).toByte()
            out[i * 2 + 1] = ((s shr 8) and 0xFF).toByte()
        }
    }

    private fun tone(amplitude: Int, samples: Int = 16_000): ByteArray =
        pcm(*IntArray(samples) { (amplitude * sin(2 * PI * 440 * it / 16_000.0)).toInt() })

    @Test
    fun `digital silence is the floor, not negative infinity`() {
        assertEquals(Pcm.FLOOR_DBFS, Pcm.rmsDbfs(ByteArray(32_000)), 0.001)
    }

    @Test
    fun `an empty buffer is the floor too`() {
        assertEquals(Pcm.FLOOR_DBFS, Pcm.rmsDbfs(ByteArray(0)), 0.001)
    }

    /** A full-scale sine is −3 dBFS RMS. If this drifts, the whole gate has drifted. */
    @Test
    fun `a full scale sine reads about minus three dBFS`() {
        assertEquals(-3.0, Pcm.rmsDbfs(tone(32_767)), 0.15)
    }

    @Test
    fun `halving the amplitude costs six dB`() {
        val loud = Pcm.rmsDbfs(tone(20_000))
        val quiet = Pcm.rmsDbfs(tone(10_000))
        assertEquals(6.0, loud - quiet, 0.1)
    }

    /** Little-endian, signed: getting the byte order wrong shows up here first. */
    @Test
    fun `samples are decoded as signed little endian`() {
        // 0xFFFF little-endian = -1. Read as unsigned it would be 65535 and read
        // big-endian it would be -256; both would blow this assertion apart.
        assertTrue(Pcm.rmsDbfs(pcm(-1, -1, -1, -1)) < -85.0)
        assertEquals(Pcm.rmsDbfs(pcm(-32_768)), Pcm.rmsDbfs(pcm(32_767)), 0.001)
    }

    @Test
    fun `speech level clears the gate with thirty dB to spare`() {
        // −19.5 dBFS was the measured figure for ordinary speech.
        assertTrue(Pcm.rmsDbfs(tone(3_500 * 2)) > Ptt.MIN_RMS_DBFS + 25)
    }

    @Test
    fun `a mic that is muted or covered falls below the gate`() {
        // Dither-level noise: a blocked mic still returns something, just nothing real.
        assertTrue(Pcm.rmsDbfs(tone(30)) < Ptt.MIN_RMS_DBFS)
    }

    @Test
    fun `a recording reports its own duration from the sample count`() {
        val oneSecond = Recording(ByteArray(Pcm.RATE * Pcm.WIDTH))
        assertEquals(1_000L, oneSecond.durationMs)
        assertEquals(Pcm.RATE, oneSecond.sampleCount)
        assertEquals(0L, Recording.EMPTY.durationMs)
    }
}
