package com.roam.touch.channels.net

import com.roam.touch.channels.model.Channel
import com.roam.touch.channels.model.ChannelResponse
import com.roam.touch.channels.model.ChannelsResponse
import com.roam.touch.channels.model.ErrorResponse
import com.roam.touch.channels.model.Event
import com.roam.touch.channels.model.EventResponse
import com.roam.touch.channels.model.HistoryResponse
import com.roam.touch.channels.model.HubJson
import com.roam.touch.channels.model.Presence
import com.roam.touch.channels.model.PresenceRequest
import com.roam.touch.channels.model.SendRequest
import com.roam.touch.channels.model.SendResponse
import com.roam.touch.channels.model.StatusResponse
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException

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

    private suspend inline fun <reified T> call(request: Request): T =
        withContext(Dispatchers.IO) {
            client.newCall(request).execute().use { resp ->
                val text = resp.body?.string().orEmpty()
                if (!resp.isSuccessful) {
                    val detail = runCatching {
                        HubJson.decodeFromString<ErrorResponse>(text).detail
                    }.getOrNull().orEmpty().ifBlank { resp.message }
                    throw HubHttpException(resp.code, detail)
                }
                HubJson.decodeFromString<T>(text)
            }
        }

    /** No auth on `/health` — this is the "is the hub even there" probe. */
    suspend fun health(): Boolean = withContext(Dispatchers.IO) {
        runCatching {
            client.newCall(Request.Builder().url(url("health")).build()).execute()
                .use { it.isSuccessful }
        }.getOrDefault(false)
    }

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
     * ⚠️ `enter = false` is not a nicety — it is how a control byte (interrupt/kill) is
     * delivered without also submitting a stray empty prompt behind it.
     */
    suspend fun send(paneId: String, text: String, enter: Boolean = true): SendResponse {
        val body = HubJson.encodeToString(
            SendRequest.serializer(), SendRequest(text = text, enter = enter)
        )
        return call(
            Request.Builder().url(url("channels", paneKey(paneId), "send"))
                .auth().post(body.toRequestBody(jsonMedia)).build()
        )
    }

    suspend fun presence(): Presence =
        call(Request.Builder().url(url("presence")).auth().build())

    /**
     * "I am looking at the panel — stop notifying me." The bridge reads this straight
     * out of the hub, so nothing about suppression lives in the client. Re-post while
     * foregrounded; a crash then lapses on its own inside [ttlS].
     */
    suspend fun registerPresence(ttlS: Int = PRESENCE_TTL_S) {
        val req = PresenceRequest(
            source = PRESENCE_SOURCE,
            kind = "app",
            coversAll = true,
            ttlS = ttlS,
            detail = JsonObject(mapOf("device" to JsonPrimitive("pixel"))),
        )
        val body = HubJson.encodeToString(PresenceRequest.serializer(), req)
        withContext(Dispatchers.IO) {
            client.newCall(
                Request.Builder().url(url("presence")).auth()
                    .post(body.toRequestBody(jsonMedia)).build()
            ).execute().use { resp ->
                if (!resp.isSuccessful) {
                    throw HubHttpException(resp.code, resp.message)
                }
            }
        }
    }

    suspend fun clearPresence() {
        withContext(Dispatchers.IO) {
            runCatching {
                client.newCall(
                    Request.Builder().url(url("presence", PRESENCE_SOURCE)).auth()
                        .delete().build()
                ).execute().close()
            }
        }
    }

    companion object {
        const val PRESENCE_SOURCE = "roam-app"

        /** A few times the 30 s refresh, so a killed app lapses fast but not mid-glance. */
        const val PRESENCE_TTL_S = 90

        /**
         * The pane id goes into the path with its `%` stripped. `API.md` accepts both
         * forms; stripping means never having to reason about double-encoding, and
         * OkHttp's [HttpUrl.Builder.addPathSegment] would encode the `%` for us anyway.
         */
        fun paneKey(paneId: String): String = paneId.removePrefix("%")

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
