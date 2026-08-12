package com.roam.touch.channels.stt

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log
import java.io.ByteArrayOutputStream
import java.util.concurrent.atomic.AtomicBoolean

/**
 * A stream of 16-bit PCM. [AudioRecord] in production, a scripted one in tests.
 *
 * This seam exists because of a real bug: the drain loop below is the part that broke on
 * hardware, and it could not be tested at all while it was welded to [AudioRecord]. Now
 * it can be handed a source that stalls, errors, or returns short reads, and the loop is
 * held to its contract without a device.
 */
interface PcmSource {
    /** The capture buffer, in bytes. Never ask this source for more than it holds. */
    val bufferBytes: Int

    /**
     * Read up to [size] bytes.
     *
     * ⚠️ **Zero means "nothing right now", not "end of stream".** That distinction is
     * the whole bug of Nexus 0.4 — see [MicRecorder.drain].
     */
    fun read(into: ByteArray, size: Int): Int

    fun close()
}

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
 *
 * ★ Measured on sailfish 2026-08-12, so nobody swaps it hoping for a cure: `MIC`,
 * `DEFAULT`, `VOICE_COMMUNICATION`, `UNPROCESSED` and `CAMCORDER` route to five
 * different `snd_device`s (handset-mic, speaker-dmic-endfire, unprocessed-mic,
 * camcorder-mic) and **all five fail identically** to this one. The source is not a
 * lever on that device.
 */
class MicRecorder(
    private val onLevel: (Double) -> Unit = {},
    private val open: () -> PcmSource? = ::openAudioRecord,
    private val sleep: (Long) -> Unit = Thread::sleep,
) : Recorder {

    private var source: PcmSource? = null
    private var reader: Thread? = null
    private val running = AtomicBoolean(false)
    private val buffer = ByteArrayOutputStream(INITIAL_BYTES)
    private var session = 0
    private var openedAtMs = 0L

    /** Why a session stopped collecting early, or null. Reported in the close log. */
    @Volatile
    private var stalledBecause: String? = null

    /**
     * The loudest chunk this session produced, in dBFS.
     *
     * ★ Tracked here rather than measured again at the end because it is what tells a
     * *starved* capture apart from a *silent* one, and those have different culprits:
     * digital silence arriving far slower than real time is the audio HAL's error path
     * handing back zero-filled buffers, not a microphone that heard nothing.
     */
    @Volatile
    private var loudestDbfs = Pcm.FLOOR_DBFS

    override val recording: Boolean get() = running.get()

    override fun start(): Boolean {
        // ⚠️⚠️ One press, one recorder. A second start while a session is live means
        // something upstream is cycling the press. This used to return `true` and hide
        // it; now it is loud and it fails, so that class of bug cannot be silent again.
        if (running.get()) {
            Log.e(
                TAG,
                "REFUSED start() while session #$session is still open — the press is " +
                        "being restarted. That is a bug upstream, not a microphone fault."
            )
            return false
        }

        val src = open() ?: return false
        buffer.reset()
        stalledBecause = null
        loudestDbfs = Pcm.FLOOR_DBFS
        source = src
        session++
        openedAtMs = System.currentTimeMillis()
        running.set(true)

        val id = session
        Log.i(TAG, "mic OPEN  #$id at ${Pcm.RATE} Hz, buffer ${src.bufferBytes} B")
        reader = Thread({ drain(src, id) }, "roam-mic").also {
            it.isDaemon = true
            it.start()
        }
        return true
    }

    /**
     * ★★ The loop that broke on hardware, and the contract it now keeps.
     *
     * ⚠️⚠️ **A read of 0 is not end-of-stream.** Nexus 0.4 did `if (n <= 0) break`, and
     * on sailfish `AudioRecord.read` returned 0 after two buffers. The thread exited
     * while `running` stayed true, so the recorder still looked healthy: the session
     * reported one clean open and one clean close, no error line, and a five-second
     * hold yielded **7680 bytes — 240 ms**. Downstream that surfaced as "you didn't
     * hold the button long enough", which was true of the audio and a lie about the
     * user. Nothing in the app said otherwise, which is what made it cost an evening.
     *
     * The contract that came out of it stands: the chunk never exceeds half the buffer,
     * zero backs off and retries, and only a genuine negative error code — or a full
     * second of nothing — ends the session, loudly.
     *
     * ⚠️ **What did *not* survive is the diagnosis.** 0.4 blamed an oversized read
     * request, and 0.5 sized the buffer around that theory. Neither was ever tested. A
     * 2026-08-12 probe of this device found the audio HAL failing `pcm_prepare` for
     * **every** source, rate and buffer size, delivering zero-filled buffers at ~3 % of
     * real time — which produces exactly the 240 ms-from-a-5-second-hold that 0.4 was
     * blamed for. The loop below is defensively correct; it was never the culprit.
     */
    private fun drain(src: PcmSource, id: Int) {
        val chunk = ByteArray(chunkFor(src.bufferBytes))
        var emptyReads = 0
        var totalReads = 0

        while (running.get()) {
            val n = try {
                src.read(chunk, chunk.size)
            } catch (e: Exception) {
                stall(id, "read threw ${e.javaClass.simpleName}: ${e.message}")
                return
            }
            when {
                n > 0 -> {
                    emptyReads = 0
                    totalReads++
                    synchronized(buffer) { buffer.write(chunk, 0, n) }
                    // ★ The level meter is the only thing that distinguishes "the mic
                    // is dead" from "you are too quiet" on a device with no other
                    // feedback. It is a signal, not state — see Ptt.level.
                    val dbfs = Pcm.rmsDbfs(if (n == chunk.size) chunk else chunk.copyOf(n))
                    if (dbfs > loudestDbfs) loudestDbfs = dbfs
                    onLevel(dbfs)
                }

                n == 0 -> {
                    emptyReads++
                    if (emptyReads == 1) {
                        Log.w(TAG, "#$id empty read after $totalReads good ones — waiting")
                    }
                    if (emptyReads > MAX_EMPTY_READS) {
                        stall(id, "no audio for ${MAX_EMPTY_READS * EMPTY_BACKOFF_MS} ms")
                        return
                    }
                    sleep(EMPTY_BACKOFF_MS)
                }

                else -> {
                    stall(id, "AudioRecord read error $n")
                    return
                }
            }
        }
    }

    private fun stall(id: Int, why: String) {
        stalledBecause = why
        Log.e(TAG, "#$id STOPPED COLLECTING: $why — the rest of this press is lost")
    }

    override fun stop(): Recording {
        if (!running.get()) return Recording.EMPTY
        val id = session
        val openMs = System.currentTimeMillis() - openedAtMs
        val why = stalledBecause
        val loudest = loudestDbfs
        val recording = Recording(finish(), Pcm.RATE)
        // ★ One line per session carrying both numbers, so "the mic was open for five
        // seconds and gave me a quarter of a second" is legible from `adb logcat -s
        // RoamStt` without a debugger attached. `live` is the ratio of audio to wall
        // clock: a healthy capture sits at ~1.0, and this HAL's failure sits at 0.03.
        val short = recording.durationMs < openMs / 2
        val live = if (openMs <= 0) 0.0 else recording.durationMs.toDouble() / openMs
        Log.i(
            TAG,
            "mic CLOSE #$id ${recording.pcm.size} B = ${recording.durationMs} ms audio, " +
                    "open ${openMs} ms, live ${"%.2f".format(live)}, " +
                    "loudest ${"%.1f".format(loudest)} dBFS" +
                    (if (short) "  ⚠️ SHORT" else "") +
                    (why?.let { " ($it)" } ?: "")
        )
        // ⚠️⚠️ Starved *and* pure digital silence is not a microphone problem and not a
        // press problem: it is the phone's audio input failing to start. Named here at
        // the moment it happens, because the same line in logcat is what took an evening
        // to find by hand — see [Ptt.MIC_NOT_DELIVERING].
        if (short && recording.pcm.isNotEmpty() && loudest <= Pcm.FLOOR_DBFS) {
            Log.e(
                TAG,
                "#$id AUDIO INPUT DEAD: ${recording.durationMs} ms of *silent* audio " +
                        "from ${openMs} ms open. The HAL is handing back zero-filled " +
                        "buffers — check `adb logcat -s audio_hw_primary` for " +
                        "'start_input_stream: pcm_prepare returned -1'. Nothing the app " +
                        "asks for changes this."
            )
        }
        return recording
    }

    override fun discard() {
        if (!running.get()) return
        val id = session
        val openMs = System.currentTimeMillis() - openedAtMs
        val dropped = finish().size
        Log.i(TAG, "mic CLOSE #$id discarded $dropped B after $openMs ms")
    }

    private fun finish(): ByteArray {
        running.set(false)
        reader?.join(READER_JOIN_MS)
        reader = null
        runCatching { source?.close() }
        source = null
        return synchronized(buffer) { buffer.toByteArray().also { buffer.reset() } }
    }

    companion object {
        private const val TAG = "RoamStt"
        private const val INITIAL_BYTES = Pcm.RATE * Pcm.WIDTH * 4   // four seconds
        private const val READER_JOIN_MS = 500L

        /** How long a silent HAL is tolerated before the session is declared dead. */
        const val EMPTY_BACKOFF_MS = 20L
        const val MAX_EMPTY_READS = 50                                // one second

        private const val MAX_CHUNK_BYTES = 4_096
        private const val MIN_CHUNK_BYTES = 512

        /**
         * ⚠️ **Never ask for more than half the capture buffer.** Asking 4096 B of
         * sailfish's 3840 B buffer is what made `read` return 0 in the first place.
         */
        fun chunkFor(bufferBytes: Int): Int =
            (bufferBytes / 2).coerceIn(MIN_CHUNK_BYTES, MAX_CHUNK_BYTES)

        /** Roughly 320 ms, but only ever as a whole number of driver buffers. */
        private const val TARGET_BYTES = Pcm.RATE * Pcm.WIDTH * 320 / 1_000

        /** Headroom against a scheduling hiccup, in driver buffers, at both ends. */
        private const val MIN_MULTIPLE = 8
        private const val MAX_MULTIPLE = 16

        /**
         * The capture buffer, as **a whole multiple of `getMinBufferSize`**.
         *
         * ⚠️ Never a byte count computed from a millisecond target. The minimum buffer
         * is the only size the driver has ever told us it can do; anything else is a
         * guess wearing the costume of a measurement.
         *
         * ★ **Measured on sailfish, 2026-08-12: the buffer size has no bearing on the
         * capture fault.** 1280 B, 5120 B and 16000 B each produced the identical
         * `start_input_stream: pcm_prepare returned -1`, at every sample rate and from
         * every audio source. The previous rationale here — "at least half a second or
         * this HAL returns zero reads" — was inferred, never tested, and is wrong. It is
         * recorded rather than deleted so nobody re-derives it. (`getMinBufferSize` on
         * this device returns **1280 B / 40 ms**, not the 960 B once noted, so this
         * yields 10240 B ≈ 320 ms.)
         */
        fun bufferFor(minBufferBytes: Int): Int {
            val wanted = (TARGET_BYTES + minBufferBytes - 1) / minBufferBytes
            return minBufferBytes * wanted.coerceIn(MIN_MULTIPLE, MAX_MULTIPLE)
        }
    }
}

/** The real microphone. Separated so [MicRecorder] itself needs no Android framework. */
@SuppressLint("MissingPermission") // The caller gates on RECORD_AUDIO; see ChannelsApp.
private fun openAudioRecord(): PcmSource? {
    val tag = "RoamStt"
    val minBuf = AudioRecord.getMinBufferSize(
        Pcm.RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT
    )
    if (minBuf <= 0) {
        Log.e(tag, "no usable mic buffer size ($minBuf)")
        return null
    }
    val size = MicRecorder.bufferFor(minBuf)
    val rec = try {
        AudioRecord(
            MediaRecorder.AudioSource.VOICE_RECOGNITION,
            Pcm.RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            size,
        )
    } catch (e: Exception) {
        // A denied permission surfaces here as an exception, not a crash.
        Log.e(tag, "AudioRecord refused: ${e.message}")
        return null
    }
    if (rec.state != AudioRecord.STATE_INITIALIZED) {
        Log.e(tag, "AudioRecord did not initialise (state=${rec.state})")
        rec.release()
        return null
    }
    rec.startRecording()
    if (rec.recordingState != AudioRecord.RECORDSTATE_RECORDING) {
        Log.e(tag, "AudioRecord would not start")
        runCatching { rec.release() }
        return null
    }
    // ⚠️ Log what was *granted*, not what was asked for. The framework is free to hand
    // back a different buffer than the one requested, and on sailfish both numbers look
    // perfectly healthy — state INITIALIZED, recordingState RECORDING — while the HAL
    // underneath never starts. These two lines are evidence, not reassurance.
    Log.i(
        tag,
        "AudioRecord up: minBuffer $minBuf B, asked $size B, " +
                "granted ${rec.bufferSizeInFrames} frames " +
                "(${rec.bufferSizeInFrames * Pcm.WIDTH} B) at ${rec.sampleRate} Hz"
    )

    return object : PcmSource {
        override val bufferBytes = size

        override fun read(into: ByteArray, size: Int): Int =
            rec.read(into, 0, size)

        override fun close() {
            runCatching {
                if (rec.recordingState == AudioRecord.RECORDSTATE_RECORDING) rec.stop()
            }
            runCatching { rec.release() }
        }
    }
}
