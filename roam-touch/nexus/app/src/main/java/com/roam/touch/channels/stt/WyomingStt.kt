package com.roam.touch.channels.stt

import android.util.Log
import com.roam.touch.channels.wyoming.WyomingReader
import com.roam.touch.channels.wyoming.WyomingWriter
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import java.io.EOFException
import java.io.IOException
import java.net.InetSocketAddress
import java.net.Socket
import kotlin.coroutines.coroutineContext

/** Whisper said no. The message is short enough to put on a chip. */
class SttException(message: String) : IOException(message)

/**
 * Speech in, text out. One method, because that is the whole job.
 *
 * ⚠️ This never opens a microphone. It is handed audio that a press already captured —
 * see [Recorder].
 */
interface SttClient {
    suspend fun transcribe(recording: Recording): String
}

/**
 * `wyoming-faster-whisper` over the Wyoming protocol, same framing as Piper.
 *
 * The exchange, verified end to end against `talos:10300`
 * (faster-whisper 3.5.0, `small-int8`) on 2026-08-12:
 *
 * ```
 * → transcribe {"language":"en"}          (optional: it transcribes without it)
 * → audio-start {rate,width,channels}
 * → audio-chunk × N, PCM in the payload
 * → audio-stop
 * ← transcript {"text":" Run the test suite and tell me if it is green."}
 * ```
 *
 * 2.2 s of speech came back in **0.9–1.2 s**, so the wait after release is real but
 * short enough to hold a thumb through.
 *
 * ⚠️⚠️ **Whisper hallucinates on silence.** One second of digital silence, sent through
 * this exact path, returned `"Smart home commands."` — a confident sentence nobody said.
 * The service advertises `requires_external_vad: true` and means it. Endpointing is the
 * caller's job: [Ptt] refuses to send audio that is too short or too quiet, and the
 * confirm step catches whatever slips past. **Do not remove either guard.**
 */
class WyomingStt(
    private val host: String,
    private val port: Int,
    private val language: String? = "en",
) : SttClient {

    override suspend fun transcribe(recording: Recording): String = withContext(Dispatchers.IO) {
        if (recording.pcm.isEmpty()) return@withContext ""
        val socket = Socket()
        try {
            socket.connect(InetSocketAddress(host, port), CONNECT_TIMEOUT_MS)
            socket.soTimeout = READ_TIMEOUT_MS

            val writer = WyomingWriter(socket.getOutputStream())
            val format = buildJsonObject {
                put("rate", recording.rate)
                put("width", Pcm.WIDTH)
                put("channels", Pcm.CHANNELS)
            }
            writer.write("transcribe", buildJsonObject {
                if (language != null) put("language", language)
            })
            writer.write("audio-start", format)

            var offset = 0
            while (offset < recording.pcm.size) {
                coroutineContext.ensureActive()
                val n = minOf(CHUNK_BYTES, recording.pcm.size - offset)
                writer.write("audio-chunk", format, recording.pcm.copyOfRange(offset, offset + n))
                offset += n
            }
            writer.write("audio-stop", buildJsonObject {
                put("timestamp", recording.durationMs)
            })

            val reader = WyomingReader(socket.getInputStream())
            while (true) {
                coroutineContext.ensureActive()
                val ev = try {
                    reader.next()
                } catch (e: EOFException) {
                    throw SttException("whisper closed the connection")
                }
                when (ev.type) {
                    "transcript" -> {
                        // ⚠️ Whisper's text always arrives with a leading space.
                        val text = ev.data["text"]?.jsonPrimitive?.content.orEmpty().trim()
                        Log.i(TAG, "transcript (${recording.durationMs} ms): ${text.take(80)}")
                        return@withContext text
                    }

                    "error" -> throw SttException(
                        ev.data["text"]?.jsonPrimitive?.content ?: "whisper error"
                    )
                    // audio-start/audio-stop can be echoed back; ignore anything else.
                }
            }
            @Suppress("UNREACHABLE_CODE") ""
        } finally {
            runCatching { socket.close() }
        }
    }

    companion object {
        private const val TAG = "RoamStt"
        private const val CHUNK_BYTES = 4_096
        private const val CONNECT_TIMEOUT_MS = 4_000

        /**
         * Generous: `small-int8` on CPU takes about half the wall time of the audio, and
         * a 60 s press is the longest thing that can arrive here.
         */
        private const val READ_TIMEOUT_MS = 60_000

        const val DEFAULT_HOST = "100.67.237.109"
        const val DEFAULT_PORT = 10300
    }
}
