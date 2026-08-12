package com.roam.touch.ha

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException

/**
 * Where Home Assistant is and how to prove we may talk to it.
 *
 * ⚠️ [token] is a **long-lived access token** and only the owner can mint one — HA
 * issues them from Profile → Security, behind his password, and there is no API to
 * create one. It is therefore a build-time config value read out of `local.properties`
 * exactly like the hub token, and it is blank until he fills it in. Blank is a
 * first-class state here, not an error: the screen says so plainly and tells him where
 * to put it, rather than failing with 401s he has to decode.
 */
data class HaConfig(
    val baseUrl: String = DEFAULT_BASE_URL,
    val token: String = "",
    val pinned: List<String> = emptyList(),
) {
    val configured: Boolean get() = token.isNotBlank()

    companion object {
        /**
         * argus on the tailnet. The LAN address (192.168.86.56) works only at home; the
         * tailnet one works from anywhere, which is the entire reason this device runs
         * Tailscale. Confirmed answering 2026-08-12.
         */
        const val DEFAULT_BASE_URL = "http://100.67.114.94:8123"
    }
}

/**
 * A failed HA call, in terms the panel can print in a chip.
 *
 * ★ 401 is called out by name because it is the one failure he can actually fix, and
 * the fix is a specific thing in a specific place — not "check your settings".
 */
class HaHttpException(val status: Int, val detail: String) :
    IOException("HTTP $status: $detail") {

    val isUnauthorised: Boolean get() = status == 401 || status == 403

    fun shortReason(): String = when (status) {
        400 -> "bad request"
        401, 403 -> "token rejected"
        404 -> "not found — check the URL"
        405 -> "method not allowed"
        500, 502, 503 -> "home assistant error $status"
        else -> "ha error $status"
    }
}

/**
 * The three REST calls the panel needs. Nothing else.
 *
 * HA also speaks WebSocket, which is how the official app stays live, and that is the
 * right upgrade once this is proven. It is deliberately not V1: a poll while the screen
 * is open is a tenth of the code, and this device's screen is off most of the time.
 */
class HaApi(
    private val config: HaConfig,
    private val client: OkHttpClient = defaultClient(),
) {
    private val jsonMedia = "application/json; charset=utf-8".toMediaType()

    private fun url(vararg segments: String): HttpUrl {
        val base = config.baseUrl.trimEnd('/').toHttpUrlOrNull()
            ?: throw HaHttpException(0, "bad base url: ${config.baseUrl}")
        val b = base.newBuilder().addPathSegment("api")
        segments.forEach { b.addPathSegment(it) }
        return b.build()
    }

    private fun Request.Builder.auth() = apply {
        header("Authorization", "Bearer ${config.token}")
        header("Content-Type", "application/json")
    }

    private suspend inline fun <reified T> call(request: Request): T =
        withContext(Dispatchers.IO) {
            client.newCall(request).execute().use { resp ->
                val text = resp.body?.string().orEmpty()
                if (!resp.isSuccessful) {
                    // HA returns {"message": "..."} on error, and bare HTML from the
                    // reverse proxy in front of it. Take whichever is there.
                    val detail = runCatching { HaJson.decodeFromString<HaPing>(text).message }
                        .getOrNull().orEmpty().ifBlank { resp.message }
                    throw HaHttpException(resp.code, detail)
                }
                HaJson.decodeFromString<T>(text)
            }
        }

    /** `GET /api/` — 200 means URL and token are both good. Cheapest possible probe. */
    suspend fun ping(): String = call<HaPing>(
        Request.Builder().url(url()).auth().get().build()
    ).message

    /** Every entity HA knows about. Filtered down to tiles by [HaEntities.tiles]. */
    suspend fun states(): List<HaState> = call(
        Request.Builder().url(url("states")).auth().get().build()
    )

    suspend fun state(entityId: String): HaState = call(
        Request.Builder().url(url("states", entityId)).auth().get().build()
    )

    /**
     * Call a service against one entity, e.g. `light` / `turn_on`.
     *
     * Returns the states HA changed, so the tile can settle on the truth instead of
     * assuming the tap worked — an assumption that is wrong exactly when a bulb is
     * unplugged, which is precisely when he needs to know.
     */
    suspend fun callService(domain: String, service: String, entityId: String): List<HaState> {
        val body = """{"entity_id":"$entityId"}"""
        return call(
            Request.Builder().url(url("services", domain, service))
                .auth().post(body.toRequestBody(jsonMedia)).build()
        )
    }

    companion object {
        fun defaultClient(): OkHttpClient = OkHttpClient.Builder()
            // Same reasoning as the hub client: on a tailnet, dead should read as dead
            // in seconds. A service call gets longer because HA blocks on the device.
            .connectTimeout(java.time.Duration.ofSeconds(6))
            .readTimeout(java.time.Duration.ofSeconds(15))
            .writeTimeout(java.time.Duration.ofSeconds(10))
            .retryOnConnectionFailure(true)
            .build()
    }
}
