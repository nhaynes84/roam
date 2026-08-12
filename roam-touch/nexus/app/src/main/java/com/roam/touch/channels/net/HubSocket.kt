package com.roam.touch.channels.net

import com.roam.touch.channels.model.FrameParser
import com.roam.touch.channels.model.HubFrame
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener

/** One connection's worth of signals. The flow completes when the socket goes away. */
sealed interface SocketEvent {
    data object Open : SocketEvent
    data class Frame(val frame: HubFrame) : SocketEvent

    /** Clean-ish close. [code] 4401 means the token was rejected. */
    data class Closed(val code: Int, val reason: String) : SocketEvent
    data class Failed(val error: Throwable) : SocketEvent
}

/**
 * The hub WebSocket, one attempt at a time.
 *
 * Deliberately *not* self-healing: reconnect, backoff and cursor bookkeeping live in
 * [com.roam.touch.channels.HubRepository], where they can be driven by a test clock.
 * This class only knows how to hold one socket open and turn frames into objects.
 */
class HubSocket(
    private val config: HubConfig,
    private val client: OkHttpClient = HubApi.defaultClient(),
) {
    /**
     * @param since last event id already applied, or `null` on a first connection.
     *   `API.md` §4: with `?since=` the hub replays a `backlog` frame and never repeats
     *   those events as `event` frames, so nothing is lost and nothing is doubled.
     */
    fun connect(since: Long?): Flow<SocketEvent> = callbackFlow {
        val url = config.wsUrl.toHttpUrl().newBuilder().apply {
            if (since != null && since > 0) addQueryParameter("since", since.toString())
        }.build()

        val request = Request.Builder()
            .url(url)
            // Header auth is preferred over ?token=; OkHttp can set headers, so the
            // token never lands in a URL that might be logged.
            .header("Authorization", "Bearer ${config.token}")
            .build()

        val listener = object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                trySend(SocketEvent.Open)
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                // An unparseable or unknown frame is dropped, never fatal: the contract
                // says "ignore unknown types", and the wearer must not lose the panel
                // because the hub grew a feature.
                FrameParser.parse(text)?.let { trySend(SocketEvent.Frame(it)) }
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                webSocket.close(1000, null)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                trySend(SocketEvent.Closed(code, reason))
                close()
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                val code = response?.code
                if (code == 401 || code == 403) {
                    trySend(SocketEvent.Closed(UNAUTHORISED_CODE, "unauthorised"))
                } else {
                    trySend(SocketEvent.Failed(t))
                }
                close()
            }
        }

        val socket = client.newWebSocket(request, listener)
        awaitClose { socket.cancel() }
    }

    companion object {
        /** The hub's own close code for a bad token (`API.md` §4). */
        const val UNAUTHORISED_CODE = 4401
    }
}

/**
 * Reconnect backoff: 1, 2, 4, 8, 16, 30, 30 … seconds, exactly as `API.md` §4 step 8
 * prescribes. Pure so the schedule is a test, not a stopwatch.
 */
object Backoff {
    const val MAX_MS = 30_000L

    fun delayMs(attempt: Int): Long {
        if (attempt <= 0) return 0L
        val shift = (attempt - 1).coerceAtMost(20)
        val ms = 1_000L shl shift
        return if (ms in 1..MAX_MS) ms else MAX_MS
    }
}
