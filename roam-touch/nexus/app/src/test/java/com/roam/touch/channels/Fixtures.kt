package com.roam.touch.channels

import com.roam.touch.channels.model.Channel
import com.roam.touch.channels.model.Coverage
import com.roam.touch.channels.model.Event
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * Shapes taken from real hub payloads (`hub/API.md` §2 and live responses captured on
 * 2026-08-12), not invented. A fixture that drifts from the wire is worse than none.
 */
object Fx {

    const val T0 = 1_786_511_500.0

    fun event(
        id: Long,
        pane: String = "%0",
        kind: String = "outcome",
        body: String = "the suite is green",
        summary: String = body,
        chars: Int = body.length,
        truncated: Boolean = false,
        ts: Double = T0,
        meta: Map<String, String> = emptyMap(),
        /** `meta.echo_of` — a JSON *number* on the wire, so it is one here too. */
        echoOf: Long? = null,
        coverage: Coverage? = null,
    ) = Event(
        id = id,
        paneId = pane,
        kind = kind,
        body = body,
        summary = summary,
        bodyChars = chars,
        bodyTruncated = truncated,
        coverage = coverage,
        meta = JsonObject(
            meta.mapValues { JsonPrimitive(it.value) as JsonElement } +
                (echoOf?.let { mapOf<String, JsonElement>("echo_of" to JsonPrimitive(it)) }
                    ?: emptyMap())
        ),
        ts = ts,
    )

    fun channel(
        pane: String = "%0",
        label: String = "◑ Roam Touch rebuild discussion",
        status: String = "idle",
        live: Boolean = true,
        lastOutputAt: Double? = T0,
        lastSeen: Double = T0,
        eventCount: Int = 3,
        lastEvent: Event? = null,
    ) = Channel(
        paneId = pane,
        label = label,
        session = "main",
        window = 1,
        index = 1,
        command = "claude.exe",
        live = live,
        status = status,
        lastSeen = lastSeen,
        lastOutputAt = lastOutputAt,
        idleS = lastOutputAt?.let { 0.4 },
        eventCount = eventCount,
        lastEvent = lastEvent,
    )

    /** Local "now" chosen so that server time T0 maps onto it exactly (zero skew). */
    const val NOW_MS = (T0 * 1000).toLong()

    fun stateWith(vararg channels: Channel) = ChannelsState(channels = channels.toList())
}

/** In-memory [ReadCursorStore] so the connection tests need no Android context. */
class FakeCursorStore(initial: Map<String, Long> = emptyMap()) : ReadCursorStore {
    var saved: Map<String, Long> = initial
        private set

    var saveCount = 0
        private set

    override suspend fun loadReadCursors(): Map<String, Long> = saved

    override suspend fun saveReadCursors(cursors: Map<String, Long>) {
        saved = cursors
        saveCount++
    }
}
