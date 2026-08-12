package com.roam.touch.channels.stt

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log
import java.io.ByteArrayOutputStream
import java.util.concurrent.atomic.AtomicBoolean

/**
 * [Recorder] over [AudioRecord]: 16 kHz, mono, signed 16-bit — Whisper's native format,
 * captured directly so nothing has to be resampled on a phone strapped to an arm.
 *
 * The buffer is held in memory and shipped on release rather than streamed during the
 * press. That is a deliberate trade: `wyoming-faster-whisper` reports
 * `supports_transcript_streaming: false` and does all its work at `audio-stop` anyway,
 * so streaming would only overlap a ~100 ms upload over the tailnet while keeping a
 * socket open for as long as a thumb stays down. A minute of speech is 1.9 MB.
 *
 * ⚠️ [MediaRecorder.AudioSource.VOICE_RECOGNITION], not `MIC`: it is the one source
 * Android guarantees will not have the "assistant" processing chain or an unpredictable
 * AGC applied, which is what an ASR model wants to be handed.
 */
class MicRecorder(
    private val onLevel: (Double) -> Unit = {},
) : Recorder {

    private var record: AudioRecord? = null
    private var reader: Thread? = null
    private val running = AtomicBoolean(false)
    private val buffer = ByteArrayOutputStream(INITIAL_BYTES)

    override val recording: Boolean get() = running.get()

    @SuppressLint("MissingPermission") // The caller gates on RECORD_AUDIO; see PttHost.
    override fun start(): Boolean {
        if (running.get()) return true
        val minBuf = AudioRecord.getMinBufferSize(
            Pcm.RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT
        )
        if (minBuf <= 0) {
            Log.w(TAG, "no usable mic buffer size ($minBuf)")
            return false
        }
        val rec = try {
            AudioRecord(
                MediaRecorder.AudioSource.VOICE_RECOGNITION,
                Pcm.RATE,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                minBuf * 4,
            )
        } catch (e: Exception) {
            // Denied permission surfaces here as an IllegalStateException, not a crash.
            Log.w(TAG, "AudioRecord refused: ${e.message}")
            return false
        }
        if (rec.state != AudioRecord.STATE_INITIALIZED) {
            Log.w(TAG, "AudioRecord did not initialise (state=${rec.state})")
            rec.release()
            return false
        }

        buffer.reset()
        record = rec
        running.set(true)
        rec.startRecording()
        if (rec.recordingState != AudioRecord.RECORDSTATE_RECORDING) {
            Log.w(TAG, "AudioRecord would not start")
            teardown()
            return false
        }

        reader = Thread({
            val chunk = ByteArray(CHUNK_BYTES)
            while (running.get()) {
                val n = rec.read(chunk, 0, chunk.size)
                if (n <= 0) {
                    if (n < 0) Log.w(TAG, "mic read error $n")
                    break
                }
                synchronized(buffer) { buffer.write(chunk, 0, n) }
                // ★ The level meter is the only thing that distinguishes "the mic is
                // dead" from "you are too quiet" on a device with no other feedback.
                onLevel(Pcm.rmsDbfs(chunk.copyOf(n)))
            }
        }, "roam-mic").also { it.isDaemon = true; it.start() }

        Log.i(TAG, "mic open at ${Pcm.RATE} Hz")
        return true
    }

    override fun stop(): Recording {
        if (!running.get()) return Recording.EMPTY
        val pcm = finish()
        Log.i(TAG, "mic closed, ${pcm.size} bytes")
        return Recording(pcm, Pcm.RATE)
    }

    override fun discard() {
        if (!running.get()) return
        finish()
        Log.i(TAG, "mic closed, audio discarded")
    }

    private fun finish(): ByteArray {
        running.set(false)
        reader?.join(READER_JOIN_MS)
        reader = null
        teardown()
        return synchronized(buffer) { buffer.toByteArray().also { buffer.reset() } }
    }

    private fun teardown() {
        running.set(false)
        record?.let { rec ->
            runCatching { if (rec.recordingState == AudioRecord.RECORDSTATE_RECORDING) rec.stop() }
            runCatching { rec.release() }
        }
        record = null
    }

    private companion object {
        const val TAG = "RoamStt"
        const val CHUNK_BYTES = 4_096
        const val INITIAL_BYTES = Pcm.RATE * Pcm.WIDTH * 4   // four seconds
        const val READER_JOIN_MS = 500L
    }
}
