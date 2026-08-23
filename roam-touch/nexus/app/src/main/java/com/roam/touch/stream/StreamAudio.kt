package com.roam.touch.stream

import android.annotation.SuppressLint
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.AutomaticGainControl
import android.media.audiofx.NoiseSuppressor

/**
 * Microphone in, speaker out, at [Wire]'s format.
 *
 * ★ Half-duplex is what makes this simple. Because a receiver's PTT INTERRUPTS the
 * feed rather than joining it, capture and playback are never live at the same moment
 * on the same device — so there is no echo path to cancel and no AEC to get right.
 * The effects below are still enabled where the device offers them, but as a bonus
 * for a room with a television in it, not as load-bearing structure.
 *
 * ⚠️ VOICE_COMMUNICATION, not MIC: it engages the platform's own preprocessing and,
 * on most hardware, the front mic tuned for speech rather than the camera mic tuned
 * for scenery. A baby monitor across a room is exactly the case that needs it.
 */
class StreamAudio {

    private var record: AudioRecord? = null
    private var track: AudioTrack? = null
    private val effects = mutableListOf<Any>()

    private val minRecordBytes = AudioRecord.getMinBufferSize(
        Wire.SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT
    ).coerceAtLeast(Wire.BYTES_PER_FRAME * 4)

    private val minTrackBytes = AudioTrack.getMinBufferSize(
        Wire.SAMPLE_RATE, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT
    ).coerceAtLeast(Wire.BYTES_PER_FRAME * 4)

    /**
     * @param monitor true when this device is the OPEN CHANNEL (the baby monitor),
     *   false when it is a listener holding PTT.
     *
     * ★★ THE TWO DIRECTIONS WANT OPPOSITE AUDIO. He found this immediately: *"it
     * actually does a surprisingly good job of ignoring background noise, which also
     * means, my son would have to intentionally yell to get through."*
     *
     * That is VOICE_COMMUNICATION doing its job — it is tuned for a handset held to
     * your face, and everything distant or quiet is treated as noise and gated away.
     * Correct for talk-back, exactly wrong for a monitor, whose entire purpose is to
     * carry a small voice from across a room.
     */
    @SuppressLint("MissingPermission")   // the caller holds RECORD_AUDIO or does not call
    fun startCapture(monitor: Boolean = false): Boolean =
        runCatching { openRecord(monitor) }.getOrDefault(false)

    /**
     * ⚠️ Wrapped by [startCapture] because the AudioRecord CONSTRUCTOR throws —
     * IllegalArgumentException for a rate/source the device will not give, and
     * IllegalStateException from startRecording() when the HAL is unwell. Both were
     * uncaught, and on a device whose audio HAL had died that is an app that
     * disappears rather than a channel that says it could not open.
     */
    @SuppressLint("MissingPermission")
    private fun openRecord(monitor: Boolean): Boolean {
        if (record != null) return true
        val source =
            if (monitor) MediaRecorder.AudioSource.MIC
            else MediaRecorder.AudioSource.VOICE_COMMUNICATION
        val r = AudioRecord(
            source,
            Wire.SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            minRecordBytes,
        )
        if (r.state != AudioRecord.STATE_INITIALIZED) {
            r.release()
            return false
        }
        // ⚠️ On a monitor, only AGC — and deliberately NO NoiseSuppressor. NS is what
        //    decides a child two metres away is noise. AGC is the opposite: it lifts a
        //    quiet room instead of gating it.
        attachEffects(r.audioSessionId, monitor = monitor)
        r.startRecording()
        record = r
        return true
    }

    /** Fill [buf]; returns bytes read, or -1 when capture is not running. */
    fun read(buf: ByteArray): Int =
        record?.read(buf, 0, minOf(buf.size, Wire.BYTES_PER_FRAME)) ?: -1

    fun stopCapture() {
        record?.let {
            runCatching { it.stop() }
            it.release()
        }
        record = null
        effects.forEach { fx ->
            runCatching {
                when (fx) {
                    is AcousticEchoCanceler -> fx.release()
                    is NoiseSuppressor -> fx.release()
                    is AutomaticGainControl -> fx.release()
                }
            }
        }
        effects.clear()
    }

    /**
     * @return null on success, or why it failed.
     *
     * ⚠️⚠️ AudioTrack.Builder().build() THROWS — UnsupportedOperationException for a
     * format the device will not give, IllegalStateException when the track cannot be
     * created. I wrapped AudioRecord after it bit once and left this one bare, so a
     * throw here killed the whole onFloor block: playback never started AND the
     * capture teardown after it never ran. Silent, on both phones, in exactly the way
     * he reported — "pixel sends audio just fine but doesn't receive the PTT".
     */
    fun startPlayback(): String? = runCatching { openTrack(); null }
        .getOrElse { "${it::class.simpleName}: ${it.message}" }

    private fun openTrack() {
        if (track != null) return
        val t = AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    // ⚠️⚠️ USAGE_MEDIA, *not* USAGE_VOICE_COMMUNICATION.
                    //
                    // VOICE_COMMUNICATION routes to the EARPIECE — the little speaker
                    // you hold to your head on a call. Everything worked and he heard
                    // nothing: "the other way doesn't seem to push audio back ... it
                    // all works, i just didn't hear anything." It was playing, into a
                    // speaker nobody's ear was against.
                    //
                    // An intercom is a loudspeaker device by definition; a talk-back
                    // you must hold to your face is not talk-back.
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setSampleRate(Wire.SAMPLE_RATE)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build()
            )
            .setBufferSizeInBytes(minTrackBytes)
            .setTransferMode(AudioTrack.MODE_STREAM)
            .build()
        t.play()
        // ⚠️ play() is not a promise. A track that failed to start is silent and
        //    reports it only here.
        check(t.playState == AudioTrack.PLAYSTATE_PLAYING) {
            "AudioTrack did not enter PLAYING (state ${t.playState}, buf $minTrackBytes)"
        }
        track = t
    }

    /** @return bytes actually written; negative is an AudioTrack error code. */
    fun write(pcm: ByteArray): Int = track?.write(pcm, 0, pcm.size) ?: 0

    fun stopPlayback() {
        track?.let {
            runCatching { it.pause(); it.flush(); it.stop() }
            it.release()
        }
        track = null
    }

    fun release() {
        stopCapture()
        stopPlayback()
    }

    /**
     * Best-effort. Every one of these is optional on Android and absent on plenty of
     * hardware, so a missing effect is a shrug, never a failure — the channel still
     * works, it just sounds like a room.
     */
    private fun attachEffects(sessionId: Int, monitor: Boolean) {
        // Half-duplex means there is no echo path to cancel, so AEC is a bonus for a
        // room with a television in it — and on a monitor it is another gate, so off.
        if (!monitor) runCatching {
            if (AcousticEchoCanceler.isAvailable())
                AcousticEchoCanceler.create(sessionId)?.also { it.enabled = true; effects += it }
        }
        if (!monitor) runCatching {
            if (NoiseSuppressor.isAvailable())
                NoiseSuppressor.create(sessionId)?.also { it.enabled = true; effects += it }
        }
        runCatching {
            if (AutomaticGainControl.isAvailable())
                AutomaticGainControl.create(sessionId)?.also { it.enabled = true; effects += it }
        }
    }
}
