package com.roam.touch.channels.net

import com.roam.touch.channels.model.Channel
import com.roam.touch.channels.model.ChannelResponse
import com.roam.touch.channels.model.ChannelsResponse
import com.roam.touch.channels.model.CreateChannelRequest
import com.roam.touch.channels.model.ErrorResponse
import com.roam.touch.channels.model.Event
import com.roam.touch.channels.model.EventResponse
import com.roam.touch.channels.model.HistoryResponse
import com.roam.touch.channels.model.HubJson
import com.roam.touch.channels.model.InterruptRequest
import com.roam.touch.channels.model.KillRequest
import com.roam.touch.channels.model.Presence
import com.roam.touch.channels.model.PresenceRequest
import com.roam.touch.channels.model.SendRequest
import com.roam.touch.channels.model.SendResponse
import com.roam.touch.channels.model.StatusResponse
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * Why a send failed, in the terms `API.md` defines. The UI shows the *cause*, because
 * "404 — the pane is not live" and "the hub is unreachable" call for different actions
 * from a man standing in a corridor.
 */
class HubHttpException(
    val status: Int,
    val detail: String,
) : IOException("HTTP $status: $detail") {

    val isNotLive: Boolean get() = status == 404
    val isUnauthorised: Boolean get() = status == 401
    val isTmuxRefusal: Boolean get() = status == 502
    val isTmuxDown: Boolean get() = status == 503

    /** One short line, safe to put in a chip. */
    fun shortReason(): String = when (status) {
        400 -> "bad pane id"
        401 -> "token rejected"
        404 -> "pane is gone"
        422 -> "empty message"
        502 -> "tmux refused"
        503 -> "tmux down"
        else -> "hub error $status"
    }
}

/**
 * Blocking-free REST client for the hub. Every call is `suspend` on [Dispatchers.IO].
 *
 * Nothing here polls. `GET /channels` is called exactly once per connection attempt to
 * seed the cursor, per the client algorithm in `API.md` §4.
 *
 * ⚠️⚠️ **Every call carries a deadline, and that is not optional.** OkHttp's
 * connect/read/write timeouts are per socket operation, not per call: a hub that answers
 * slowly — headers, then a trickle of body — resets the read timeout with every byte and
 * the call never ends. Measured against a deliberately wedged hub on 2026-08-12: a send
 * was still outstanding after 105 seconds with no error and nothing on screen. On the
 * tailnet that case is invisible in testing and inevitable in use, so the bound is a
 * whole-call deadline via [okhttp3.Call.timeout], applied in [execute].
 */
class HubApi(
    private val config: HubConfig,
    private val client: OkHttpClient = defaultClient(),
) {
    private val jsonMedia = "application/json; charset=utf-8".toMediaType()

    private fun url(vararg segments: String, query: Map<String, String> = emptyMap()): HttpUrl {
        val b = config.baseUrl.toHttpUrl().newBuilder()
        segments.forEach { b.addPathSegment(it) }
        query.forEach { (k, v) -> b.addQueryParameter(k, v) }
        return b.build()
    }

    private fun Request.Builder.auth() = apply {
        header("Authorization", "Bearer ${config.token}")
    }

    /**
     * One HTTP call, bounded and cancellable.
     *
     * ⚠️ Two separate problems are closed here, and both were measured rather than
     * imagined:
     *
     * 1. **The deadline.** [okhttp3.Call.timeout] is the only timeout that covers a whole
     *    call. Without it a hub that dribbles its answer holds the call open forever —
     *    every individual read lands inside `readTimeout`, so `readTimeout` never fires.
     * 2. **Cancellation.** `execute()` is a blocking socket read, and cancelling the
     *    coroutine cannot interrupt it. So the call is cancelled explicitly when the
     *    coroutine dies — otherwise walking away from a screen leaves the request running
     *    on an IO thread until the deadline expires.
     *
     * ⚠️ The watcher is a *suspended child*, not a completion handler. `invokeOnCompletion`
     * fires when a job finishes, and a job whose body is blocked in a socket read has not
     * finished — so it would arrive after the thing it was supposed to interrupt. A child
     * parked on [awaitCancellation] is torn down the instant the parent is cancelled,
     * which is the only moment at which cancelling the call still means anything.
     */
    private suspend fun <T> execute(
        request: Request,
        deadlineMs: Long,
        block: (Response) -> T,
    ): T = withContext(Dispatchers.IO) {
        val httpCall = client.newCall(request)
        httpCall.timeout().timeout(deadlineMs, TimeUnit.MILLISECONDS)
        val watcher = launch {
            try {
                awaitCancellation()
            } finally {
                httpCall.cancel()
            }
        }
        try {
            httpCall.execute().use(block)
        } finally {
            watcher.cancel()
        }
    }

    private suspend inline fun <reified T> call(
        request: Request,
        deadlineMs: Long = READ_DEADLINE_MS,
    ): T = execute(request, deadlineMs) { resp ->
        val text = resp.body?.string().orEmpty()
        if (!resp.isSuccessful) {
            val detail = runCatching {
                HubJson.decodeFromString<ErrorResponse>(text).detail
            }.getOrNull().orEmpty().ifBlank { resp.message }
            throw HubHttpException(resp.code, detail)
        }
        HubJson.decodeFromString<T>(text)
    }

    /** No auth on `/health` — this is the "is the hub even there" probe. */
    suspend fun health(): Boolean = runCatching {
        execute(Request.Builder().url(url("health")).build(), PROBE_DEADLINE_MS) {
            it.isSuccessful
        }
    }.getOrDefault(false)

    suspend fun status(): StatusResponse =
        call(Request.Builder().url(url("status")).auth().build())

    suspend fun channels(includeArchived: Boolean = false): ChannelsResponse =
        call(
            Request.Builder()
                .url(url("channels", query = mapOf("include_archived" to includeArchived.toString())))
                .auth().build()
        )

    suspend fun channel(paneId: String): Channel =
        call<ChannelResponse>(
            Request.Builder().url(url("channels", paneKey(paneId))).auth().build()
        ).channel

    suspend fun history(paneId: String, limit: Int = 200, since: Long? = null): HistoryResponse {
        val q = buildMap {
            put("limit", limit.toString())
            since?.let { put("since", it.toString()) }
        }
        return call(
            Request.Builder().url(url("channels", paneKey(paneId), "history", query = q))
                .auth().build()
        )
    }

    /**
     * Every event after [since], across all channels. `API.md` calls this the
     * poll-once-on-wake path, and that is exactly what it is used for here: one call
     * after each (re)connect so the unread counts are right without N per-channel
     * history fetches. It is never on a timer.
     */
    suspend fun events(since: Long, limit: Int = 500): HistoryResponse =
        call(
            Request.Builder().url(
                url(
                    "events",
                    query = mapOf("since" to since.toString(), "limit" to limit.toString())
                )
            ).auth().build()
        )

    suspend fun event(id: Long): Event =
        call<EventResponse>(
            Request.Builder().url(url("events", id.toString())).auth().build()
        ).event

    /**
     * Type [text] into the pane.
     *
     * ⚠️ Since hub 1.5.0 this REJECTS C0 control characters with 400. Stopping a
     * session is [interrupt] or [kill], never a byte through here.
     */
    suspend fun send(paneId: String, text: String, enter: Boolean = true): SendResponse {
        val body = HubJson.encodeToString(
            SendRequest.serializer(), SendRequest(text = text, enter = enter)
        )
        return call(
            Request.Builder().url(url("channels", paneKey(paneId), "send"))
                .auth().post(body.toRequestBody(jsonMedia)).build(),
            deadlineMs = SEND_DEADLINE_MS,
        )
    }

    /**
     * `POST /channels/{pane}/interrupt` — a key press, recorded as a `control` event
     * rather than as something he said. [action] is the hub's allow-list: `escape`
     * stops an agent mid-response, `interrupt` is C-c to the foreground process.
     */
    suspend fun interrupt(paneId: String, action: String = "escape"): SendResponse {
        val body = HubJson.encodeToString(
            InterruptRequest.serializer(), InterruptRequest(action = action)
        )
        return call(
            Request.Builder().url(url("channels", paneKey(paneId), "interrupt"))
                .auth().post(body.toRequestBody(jsonMedia)).build(),
            deadlineMs = SEND_DEADLINE_MS,
        )
    }

    /**
     * `POST /channels/{pane}/kill` — end the pane and whatever runs in it. The channel
     * outlives the pane: history stays readable, and the poller's canonical `closed`
     * event follows within a poll cycle.
     */
    suspend fun kill(paneId: String): SendResponse {
        val body = HubJson.encodeToString(KillRequest.serializer(), KillRequest())
        return call(
            Request.Builder().url(url("channels", paneKey(paneId), "kill"))
                .auth().post(body.toRequestBody(jsonMedia)).build(),
            deadlineMs = SEND_DEADLINE_MS,
        )
    }

    /**
     * `POST /channels` — spawn a new agent pane. `201` with the channel, live
     * immediately. Every client also gets it via a `channels` frame plus an `opened`
     * event, so applying the response is a head start, not the source of truth.
     */
    suspend fun createChannel(command: String, label: String): Channel {
        val body = HubJson.encodeToString(
            CreateChannelRequest.serializer(),
            CreateChannelRequest(command = command, label = label),
        )
        return call<ChannelResponse>(
            Request.Builder().url(url("channels")).auth()
                .post(body.toRequestBody(jsonMedia)).build(),
            deadlineMs = SEND_DEADLINE_MS,
        ).channel
    }

    suspend fun presence(): Presence =
        call(Request.Builder().url(url("presence")).auth().build())

    /**
     * "I am looking at **this** channel — stop notifying me about it." The bridge reads
     * this straight out of the hub, so nothing about suppression lives in the client.
     * Re-post while foregrounded; a crash then lapses on its own inside [ttlS].
     *
     * @param openPane the channel on screen, or null when he is on the list or elsewhere.
     *   ⚠️ Null means **nothing is covered** — a message on any channel should buzz,
     *   because he is not reading any of them. See [PresenceRequest.coversAll] for what
     *   claiming more than this cost him.
     */
    suspend fun registerPresence(openPane: String?, ttlS: Int = PRESENCE_TTL_S) {
        val req = PresenceRequest(
            source = PRESENCE_SOURCE,
            kind = "app",
            coversAll = false,
            panes = listOfNotNull(openPane),
            ttlS = ttlS,
            detail = JsonObject(mapOf("device" to JsonPrimitive("pixel"))),
        )
        val body = HubJson.encodeToString(PresenceRequest.serializer(), req)
        execute(
            Request.Builder().url(url("presence")).auth()
                .post(body.toRequestBody(jsonMedia)).build(),
            PROBE_DEADLINE_MS,
        ) { resp ->
            if (!resp.isSuccessful) throw HubHttpException(resp.code, resp.message)
        }
    }

    suspend fun clearPresence() {
        runCatching {
            execute(
                Request.Builder().url(url("presence", PRESENCE_SOURCE)).auth().delete().build(),
                PROBE_DEADLINE_MS,
            ) { }
        }
    }

    companion object {
        const val PRESENCE_SOURCE = "roam-app"

        /**
         * ★★ How long he is made to stand there.
         *
         * A send is a man in a corridor waiting to find out whether his words landed, so
         * this is a *human* budget, not a network one: the hub is on a tailnet and types
         * into a pane in milliseconds, so anything past a few seconds is already wrong
         * and he needs to be told rather than kept waiting. Short enough that the answer
         * arrives while he is still looking at the screen he sent from.
         */
        const val SEND_DEADLINE_MS = 8_000L

        /**
         * Reads — history, the catch-up sweep, one expanded body. Longer than a send
         * because 500 events is a real payload and nobody is standing still for it, but
         * still bounded: a read that never returns is a screen that never fills in.
         */
        const val READ_DEADLINE_MS = 25_000L

        /** Health and presence: fire-and-forget housekeeping. Fail fast, retry later. */
        const val PROBE_DEADLINE_MS = 6_000L

        /** A few times the 30 s refresh, so a killed app lapses fast but not mid-glance. */
        const val PRESENCE_TTL_S = 90

        /**
         * The pane id goes into the path with its `%` stripped. `API.md` accepts both
         * forms; stripping means never having to reason about double-encoding, and
         * OkHttp's [HttpUrl.Builder.addPathSegment] would encode the `%` for us anyway.
         */
        fun paneKey(paneId: String): String = paneId.removePrefix("%")

        /**
         * ⚠️ These are per-socket-operation, and that is the whole reason [execute] adds
         * a deadline on top. `readTimeout` bounds one read, not one call; a hub that
         * sends a byte every ten seconds satisfies it forever.
         *
         * ⚠️ There is deliberately **no** `callTimeout` here. This client is shared with
         * [HubSocket], and a whole-call deadline on a WebSocket is a deadline on the
         * connection itself — the one thing on this device that is meant to stay open for
         * days. The deadline belongs on the REST calls, one at a time.
         */
        fun defaultClient(): OkHttpClient = OkHttpClient.Builder()
            // The tailnet is not the internet: a dead hub should read as dead in
            // seconds, not after a 30 s stall the wearer interprets as "quiet".
            .connectTimeout(java.time.Duration.ofSeconds(6))
            .readTimeout(java.time.Duration.ofSeconds(20))
            .writeTimeout(java.time.Duration.ofSeconds(10))
            .pingInterval(java.time.Duration.ofSeconds(25))
            .retryOnConnectionFailure(true)
            .build()
    }
}
