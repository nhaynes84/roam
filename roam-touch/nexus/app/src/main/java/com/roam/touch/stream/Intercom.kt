package com.roam.touch.stream

import com.roam.touch.channels.net.HubConfig
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import okio.ByteString.Companion.toByteString
import java.util.concurrent.TimeUnit
import kotlinx.serialization.json.jsonObject

/**
 * The Stream wire format and the client that speaks it.
 *
 * ★ The shape, in the owner's words: *"set it as sender, it just sends; if someone on
 * a receiving device holds the PTT, it blocks the incoming signal while the button is
 * pushed, and sends that message to all listening channels; sender and other
 * listeners; so it blocks the channel (half duplex) while sending, then automatically
 * relinquishes when the button is released."*
 *
 * ★★ THE HUB DECIDES, NOT THE DEVICE. His framing: *"same as a multiplayer hosting
 * server for any video game, the server makes core timing decisions, not any
 * individual device."* So this client never assumes it has the floor because it
 * pressed a button — it presses, and then it believes [Floor] coming back. Two devices
 * that each decided locally would eventually both be live, and that is a howl.
 */
object Wire {
    /** 16 kHz mono PCM16. No codec on purpose: nothing to negotiate, nothing to
     *  install, and ~256 kbit/s is free on a tailnet. Voice, not music. */
    const val SAMPLE_RATE = 16_000
    const val FRAME_MS = 20
    const val SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_MS / 1000     // 320
    const val BYTES_PER_FRAME = SAMPLES_PER_FRAME * 2               // 640
}

/** Who the hub says owns the channel right now. */
data class Floor(
    val open: Boolean,
    val sender: String?,
    val talker: String?,
    val holder: String?,
    val receivers: List<String>,
    /** device -> lens it is showing. NOT floor-governed — video has no echo. */
    val video: Map<String, String> = emptyMap(),
) {
    fun videoLive(device: String) = device in video
    fun videoFacing(device: String) = video[device]
    /** Should THIS device's microphone be live? */
    fun micLive(device: String) = holder == device

    /** Should this device be playing what arrives? */
    fun shouldPlay(device: String) = holder != null && holder != device
}

sealed interface StreamEvent {
    data class FloorChanged(val floor: Floor) : StreamEvent
    /** A frame of PCM from whoever holds the floor. */
    data class Audio(val pcm: ByteArray) : StreamEvent
    data class Denied(val detail: String) : StreamEvent
    data class Failed(val reason: String) : StreamEvent
}

enum class Role { OFF, SENDER, RECEIVER }

class IntercomClient(
    private val config: HubConfig,
    private val device: String,
    private val client: OkHttpClient = OkHttpClient.Builder()
        // A silent socket is normal here — nobody is talking. Ping so a dead peer is
        // still noticed rather than looking like a quiet house.
        .pingInterval(20, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build(),
) {
    private val json = Json { ignoreUnknownKeys = true }
    @Volatile private var socket: WebSocket? = null
    @Volatile private var videoSocket: WebSocket? = null

    /**
     * ⚠️ `http://`, not `ws://` — OkHttp's HttpUrl rejects a ws scheme outright and
     * throws at request-build time inside a coroutine, taking the process with it.
     * The same trap is documented on [HubConfig.wsUrl]; it applies identically here.
     */
    private fun url(role: Role): String {
        val r = if (role == Role.SENDER) "sender" else "receiver"
        return "http://${config.host}:${config.port}/intercom" +
                "?device=$device&role=$r&token=${config.token}"
    }

    fun connect(role: Role): Flow<StreamEvent> = callbackFlow {
        val request = Request.Builder().url(url(role)).build()
        val ws = client.newWebSocket(request, object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, text: String) {
                val obj = runCatching { json.parseToJsonElement(text) as JsonObject }
                    .getOrNull() ?: return
                when (obj["type"]?.jsonPrimitive?.content) {
                    "floor" -> parseFloor(obj)?.let { trySend(StreamEvent.FloorChanged(it)) }
                    "denied" -> trySend(
                        StreamEvent.Denied(obj["detail"]?.jsonPrimitive?.content ?: "refused")
                    )
                    "error" -> trySend(
                        StreamEvent.Failed(obj["detail"]?.jsonPrimitive?.content ?: "error")
                    )
                }
            }

            override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                trySend(StreamEvent.Audio(bytes.toByteArray()))
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                trySend(StreamEvent.Failed(t.message ?: "connection failed"))
                close()
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                close()
            }
        })
        socket = ws
        awaitClose {
            socket = null
            ws.close(1000, null)
        }
    }

    /**
     * Video rides its OWN socket.
     *
     * ⚠️ Not multiplexed onto the audio socket: a video frame is orders of magnitude
     * bigger than a 640-byte audio frame and would head-of-line block the speech
     * behind it. Audio is the stream that must never stutter; video may drop a frame
     * and nobody notices.
     */
    /** A frame and the camera it came from. */
    data class VideoFrame(val from: String, val jpeg: ByteArray)

    fun connectVideo(): Flow<VideoFrame> = callbackFlow {
        val url = "http://${config.host}:${config.port}/intercom/video" +
                "?device=$device&token=${config.token}"
        val ws = client.newWebSocket(Request.Builder().url(url).build(),
            object : WebSocketListener() {
                override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                    // [1 byte id length][id utf8][jpeg] — see the hub's video relay.
                    val raw = bytes.toByteArray()
                    if (raw.isEmpty()) return
                    val n = raw[0].toInt() and 0xFF
                    if (raw.size < 1 + n) return
                    val from = String(raw, 1, n, Charsets.UTF_8)
                    trySend(VideoFrame(from, raw.copyOfRange(1 + n, raw.size)))
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    close()
                }

                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    close()
                }
            })
        videoSocket = ws
        awaitClose {
            videoSocket = null
            ws.close(1000, null)
        }
    }

    fun sendVideo(jpeg: ByteArray) {
        videoSocket?.send(jpeg.toByteString())
    }

    /**
     * Ask the hub to turn a camera on, and which lens.
     *
     * ⚠️ Built by concatenation, not a raw string. The previous version wrote
     * `""",\"target\":\"$it\""""` — inside a Kotlin RAW string `\"` is a literal
     * backslash followed by a quote, so it emitted malformed JSON and the hub could
     * never have parsed a target. It was never exercised because target is normally
     * null.
     *
     * ★ `target` defaults to the SENDER: "receiver can select sender cam option".
     * A listener's own camera is self-only and the hub enforces that.
     */
    fun setVideo(on: Boolean, facing: String = "back", target: String? = null) {
        val sb = StringBuilder("{\"type\":\"video\",\"on\":")
        sb.append(on).append(",\"facing\":\"").append(facing).append('"')
        if (target != null) sb.append(",\"target\":\"").append(target).append('"')
        sb.append('}')
        socket?.send(sb.toString())
    }

    /** Hold PTT. The hub answers with a [Floor]; do not assume it was granted. */
    fun press() { socket?.send("""{"type":"press"}""") }

    fun release() { socket?.send("""{"type":"release"}""") }

    /**
     * Audio out. Sent unconditionally — the hub drops it if this device does not hold
     * the floor, which is the safety net for a laggy release. Gating locally as well
     * is what keeps the radio quiet; gating ONLY locally is what would eventually put
     * two speakers live in one house.
     */
    fun sendAudio(pcm: ByteArray, length: Int) {
        socket?.send(pcm.copyOf(length).toByteString())
    }

}

/**
 * Parse a `floor` frame.
 *
 * ⚠️ Tested against payloads captured off the LIVE hub, not against what this file
 * assumed they looked like. Two things bite here and neither is visible from the
 * Kotlin side: `open` is a JSON BOOLEAN (unquoted `true`), and an absent party is
 * JSON `null`, which kotlinx surfaces as a primitive whose content is the four
 * characters "null". Reading either naively yields a Floor that is quietly wrong —
 * a holder of "null" would mean every device believes someone else has the mic.
 */
fun parseFloor(obj: JsonObject): Floor? {
    if (obj["type"]?.jsonPrimitive?.content != "floor") return null
    return Floor(
        open = obj["open"]?.jsonPrimitive?.content == "true",
        sender = obj.str("sender"),
        talker = obj.str("talker"),
        holder = obj.str("holder"),
        receivers = obj["receivers"]?.jsonArray
            ?.mapNotNull { it.jsonPrimitive.nullSafe() } ?: emptyList(),
        // ⚠️ A MAP now: which lens a device shows is state, not a flag.
        video = obj["video"]?.jsonObject
            ?.mapNotNull { entry ->
                entry.value.jsonPrimitive.nullSafe()?.let { entry.key to it }
            }
            ?.toMap() ?: emptyMap(),
    )
}

fun parseFloor(text: String): Floor? = runCatching {
    parseFloor(Json { ignoreUnknownKeys = true }.parseToJsonElement(text) as JsonObject)
}.getOrNull()

private fun JsonObject.str(key: String): String? = this[key]?.jsonPrimitive?.nullSafe()

/** JSON null arrives as an unquoted primitive whose content is "null". */
private fun kotlinx.serialization.json.JsonPrimitive.nullSafe(): String? =
    if (!isString && content == "null") null else content
