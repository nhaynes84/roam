package com.roam.touch.channels.stt

import kotlin.math.log10
import kotlin.math.sqrt

/**
 * Signed 16-bit little-endian mono PCM — the only audio format in this app.
 *
 * 16 kHz mono is what Whisper wants, so it is what the mic is opened at: no resampling
 * anywhere in the path, and therefore no place for a rate mismatch to hide.
 */
object Pcm {
    const val RATE = 16_000
    const val WIDTH = 2
    const val CHANNELS = 1

    /** Below this the buffer is treated as having no signal at all. */
    const val FLOOR_DBFS = -120.0

    /**
     * RMS level of [pcm] in dBFS, or [FLOOR_DBFS] for digital silence.
     *
     * Measured for reference on real speech (`say` → 16 kHz mono, 2026-08-12): **−19.5
     * dBFS RMS**, −3.2 dBFS peak. That is 30 dB of headroom above [Ptt.MIN_RMS_DBFS],
     * which is why a lenient gate is still a useful one.
     */
    fun rmsDbfs(pcm: ByteArray): Double {
        val samples = pcm.size / WIDTH
        if (samples == 0) return FLOOR_DBFS
        var sumSquares = 0.0
        for (i in 0 until samples) {
            val lo = pcm[i * 2].toInt() and 0xFF
            val hi = pcm[i * 2 + 1].toInt()          // signed: this is the high byte
            val sample = ((hi shl 8) or lo).toShort().toInt()
            sumSquares += sample.toDouble() * sample.toDouble()
        }
        val rms = sqrt(sumSquares / samples)
        if (rms <= 0.0) return FLOOR_DBFS
        return (20.0 * log10(rms / 32768.0)).coerceAtLeast(FLOOR_DBFS)
    }
}

/**
 * What one press of the PTT captured.
 *
 * Duration and level are derived, never reported by the recorder: a fake recorder in a
 * test and the real mic then agree by construction, and the gate in [Ptt] is testing the
 * same numbers the device produces.
 */
class Recording(val pcm: ByteArray, val rate: Int = Pcm.RATE) {

    val sampleCount: Int get() = pcm.size / Pcm.WIDTH

    val durationMs: Long get() = if (rate <= 0) 0 else sampleCount * 1_000L / rate

    /** Computed once — this walks every sample and a press can be a megabyte. */
    val rmsDbfs: Double by lazy { Pcm.rmsDbfs(pcm) }

    /**
     * ★ Every sample is exactly zero — not "quiet", *nothing*.
     *
     * ⚠️ A real microphone in a silent room does not produce this: it produces a noise
     * floor, which measures around −60 dBFS and is nowhere near [Pcm.FLOOR_DBFS]. Bytes
     * that are all zero came from software, and the software that produces them is the
     * audio HAL's error path — it zero-fills the buffer when it cannot start the input
     * stream. Paired with a capture that ran far behind the clock, that is a diagnosis.
     */
    val isDigitalSilence: Boolean get() = pcm.isNotEmpty() && rmsDbfs <= Pcm.FLOOR_DBFS

    companion object {
        val EMPTY = Recording(ByteArray(0))
    }
}

/**
 * The microphone, behind an interface.
 *
 * ⚠️ **Nothing in this app may call [start] except a press on the PTT control.** There is
 * no wake word, no VAD, no "listen while the screen is on" — the owner had automatic
 * speech *output* deleted for being presumptuous, and a hot mic is the same mistake with
 * worse consequences. `MicPolicyTest` fails if anything else starts it.
 */
interface Recorder {
    /** True if the mic actually opened. False means no permission or no mic. */
    fun start(): Boolean

    /** Stop and hand back what was captured. Safe to call when not started. */
    fun stop(): Recording

    /** Stop and throw the audio away. Used by Cancel, and by teardown. */
    fun discard()

    /** True between a successful [start] and a [stop]/[discard]. */
    val recording: Boolean
}
