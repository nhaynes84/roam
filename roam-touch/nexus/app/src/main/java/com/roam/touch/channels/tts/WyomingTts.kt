package com.roam.touch.channels.tts

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
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
import java.net.InetSocketAddress
import java.net.Socket
import kotlin.coroutines.coroutineContext

/**
 * Something that can say a sentence out loud, and takes as long as the sentence does.
 *
 * ★ An interface for the same reason [com.roam.touch.channels.stt.Recorder] is one: the
 * *policy* around speaking — what is spoken, what it does to the music, what happens when
 * it is cancelled halfway — has to be testable on a JVM, and the thing that opens a socket
 * and pushes PCM at a speaker cannot be.
 */
interface Voice {

    /**
     * Say [text], returning when the audio has finished playing.
     *
     * ⚠️ Cancellation stops the audio immediately — that is what makes "he picked the
     * phone up mid-sentence" work, and it is why every caller's cleanup has to live in a
     * `finally`.
     */
    suspend fun speak(text: String)
}

/**
 * Piper over the Wyoming protocol, streamed straight into an [AudioTrack].
 *
 * There is no Android package for Wyoming, so this is hand-rolled — but only just: the
 * protocol is four event types and the audio path is stock [AudioTrack]. Nothing is
 * buffered to a file, so speech starts about 70 ms after the request (measured), which
 * is what makes it usable on a device that is meant to talk while you walk.
 */
class WyomingTts(
    private val host: String,
    private val port: Int,
    private val voice: String?,
) : Voice {
    override suspend fun speak(text: String) = withContext(Dispatchers.IO) {
        if (text.isBlank()) return@withContext
        var track: AudioTrack? = null
        var played = 0L
        val socket = Socket()
        try {
            socket.connect(InetSocketAddress(host, port), CONNECT_TIMEOUT_MS)
            socket.soTimeout = READ_TIMEOUT_MS

            WyomingWriter(socket.getOutputStream()).write(
                "synthesize",
                buildJsonObject {
                    put("text", text)
                    if (voice != null) put("voice", buildJsonObject { put("name", voice) })
                },
            )

            val reader = WyomingReader(socket.getInputStream())
            while (true) {
                coroutineContext.ensureActive()
                val ev = try {
                    reader.next()
                } catch (e: EOFException) {
                    break
                }
                when (ev.type) {
                    "audio-start" -> {
                        val rate = ev.data["rate"]?.jsonPrimitive?.content?.toIntOrNull() ?: 22050
                        val width = ev.data["width"]?.jsonPrimitive?.content?.toIntOrNull() ?: 2
                        val channels =
                            ev.data["channels"]?.jsonPrimitive?.content?.toIntOrNull() ?: 1
                        Log.i(TAG, "piper audio-start ${rate}Hz w=$width ch=$channels")
                        track = newTrack(rate, width, channels).also { it.play() }
                    }

                    "audio-chunk" -> {
                        val t = track ?: newTrack(22050, 2, 1).also { track = it; it.play() }
                        var off = 0
                        while (off < ev.payload.size) {
                            coroutineContext.ensureActive()
                            val w = t.write(ev.payload, off, ev.payload.size - off)
                            if (w <= 0) break
                            off += w
                            played += w
                        }
                    }

                    "audio-stop" -> {
                        Log.i(TAG, "piper audio-stop, $played bytes played")
                        break
                    }
                    "error" -> {
                        Log.w(TAG, "piper error: ${ev.data}")
                        break
                    }
                }
            }
            // Let the tail of the buffer actually reach the speaker before tearing down.
            track?.let { t ->
                t.stop()
                while (t.playState == AudioTrack.PLAYSTATE_PLAYING) {
                    coroutineContext.ensureActive()
                    Thread.sleep(20)
                }
            }
        } finally {
            runCatching { track?.pause() }
            runCatching { track?.flush() }
            runCatching { track?.release() }
            runCatching { socket.close() }
        }
    }

    private fun newTrack(rate: Int, width: Int, channels: Int): AudioTrack {
        val encoding =
            if (width == 1) AudioFormat.ENCODING_PCM_8BIT else AudioFormat.ENCODING_PCM_16BIT
        val mask =
            if (channels >= 2) AudioFormat.CHANNEL_OUT_STEREO else AudioFormat.CHANNEL_OUT_MONO
        val minBuf = AudioTrack.getMinBufferSize(rate, mask, encoding)
            .coerceAtLeast(rate * width * channels / 4)
        return AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    // ASSISTANT, not MEDIA: this is the device speaking to its wearer,
                    // and it should duck music rather than be treated as music.
                    .setUsage(AudioAttributes.USAGE_ASSISTANT)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setEncoding(encoding)
                    .setSampleRate(rate)
                    .setChannelMask(mask)
                    .build()
            )
            .setBufferSizeInBytes(minBuf * 2)
            .setTransferMode(AudioTrack.MODE_STREAM)
            .setPerformanceMode(AudioTrack.PERFORMANCE_MODE_NONE)
            .build()
    }

    companion object {
        private const val TAG = "RoamTts"
        private const val CONNECT_TIMEOUT_MS = 4_000
        private const val READ_TIMEOUT_MS = 20_000

        const val DEFAULT_HOST = "100.67.237.109"
        const val DEFAULT_PORT = 10200

        /** Installed on talos; checked against `describe` rather than assumed. */
        const val DEFAULT_VOICE = "en_US-ryan-high"
    }
}
