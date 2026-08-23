package com.roam.nexus.stream

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

    @SuppressLint("MissingPermission")   // the caller holds RECORD_AUDIO or does not call
    fun startCapture(): Boolean {
        if (record != null) return true
        val r = AudioRecord(
            MediaRecorder.AudioSource.VOICE_COMMUNICATION,
            Wire.SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            minRecordBytes,
        )
        if (r.state != AudioRecord.STATE_INITIALIZED) {
            r.release()
            return false
        }
        attachEffects(r.audioSessionId)
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

    fun startPlayback() {
        if (track != null) return
        val t = AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    // ⚠️ VOICE_COMMUNICATION so it rides the call stream: it ducks
                    //    music, follows the earpiece/speaker routing the user expects
                    //    of a call, and is not silenced by Do Not Disturb the way a
                    //    media stream can be. A monitor that DND can mute is not a
                    //    monitor.
                    .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
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
        track = t
    }

    fun write(pcm: ByteArray) {
        track?.write(pcm, 0, pcm.size)
    }

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
    private fun attachEffects(sessionId: Int) {
        runCatching {
            if (AcousticEchoCanceler.isAvailable())
                AcousticEchoCanceler.create(sessionId)?.also { it.enabled = true; effects += it }
        }
        runCatching {
            if (NoiseSuppressor.isAvailable())
                NoiseSuppressor.create(sessionId)?.also { it.enabled = true; effects += it }
        }
        runCatching {
            if (AutomaticGainControl.isAvailable())
                AutomaticGainControl.create(sessionId)?.also { it.enabled = true; effects += it }
        }
    }
}
