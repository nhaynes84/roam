package com.roam.touch.channels.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.decodeFromJsonElement

/**
 * Wire types for the ROAM hub, mirroring `hub/API.md` protocol 1.
 *
 * Everything is decoded with [HubJson], which ignores unknown keys on purpose: the
 * contract says event `kind` is an open set and frame types may grow, so a hub that
 * learns a new field must never crash the panel the wearer is looking at.
 */
@OptIn(kotlinx.serialization.ExperimentalSerializationApi::class)
val HubJson: Json = Json {
    ignoreUnknownKeys = true
    isLenient = true
    encodeDefaults = true
    explicitNulls = false
    coerceInputValues = true
}

/** Event kinds we know about. Unknown strings stay as [EventKind.OTHER]. */
enum class EventKind(val wire: String) {
    SENT("sent"),
    RECEIPT("receipt"),
    OUTCOME("outcome"),
    OPENED("opened"),
    CLOSED("closed"),
    NOTE("note"),
    CONTROL("control"),
    ERROR("error"),
    OTHER("");

    companion object {
        fun from(wire: String?): EventKind =
            entries.firstOrNull { it.wire == wire && it != OTHER } ?: OTHER
    }
}

/**
 * Where the conversation was when this event landed, stamped by the hub at event time.
 *
 * ★ "Reply where the last message came from." If he typed the prompt in tmux he is
 * reading the answer in tmux, and ROAM should stay quiet. This is the hub's answer to a
 * question the client used to guess at, so the client defers to it — with the contract's
 * own safety rule intact: `known: false` means notify, because a missed message is worse
 * than a redundant one.
 */
@Serializable
data class Coverage(
    val known: Boolean = false,
    val covered: Boolean = false,
    val by: List<String> = emptyList(),
    @SerialName("last_input") val lastInput: String? = null,
)

@Serializable
data class Event(
    val id: Long,
    @SerialName("pane_id") val paneId: String,
    val kind: String,
    val body: String = "",
    val summary: String = "",
    @SerialName("body_chars") val bodyChars: Int = 0,
    @SerialName("body_truncated") val bodyTruncated: Boolean = false,
    val coverage: Coverage? = null,
    val meta: JsonObject = JsonObject(emptyMap()),
    val ts: Double = 0.0,
    val archived: Boolean = false,
) {
    /**
     * True when the hub says this event's conversation is already in front of him
     * somewhere else. Governs notification and speech only — a covered event is still
     * stored, still in history, still shown in the thread exactly like any other.
     */
    val covered: Boolean get() = coverage?.let { it.known && it.covered } ?: false

    val kindEnum: EventKind get() = EventKind.from(kind)

    /** Epoch millis; `ts` is float seconds on the wire. */
    val tsMillis: Long get() = (ts * 1000.0).toLong()

    private fun metaString(key: String): String? =
        (meta[key] as? JsonPrimitive)?.takeIf { it.isString }?.content

    /**
     * True when the hub had to fall back to reading the transcript and the answer had
     * not landed on disk yet. `API.md`: *"the body may be an earlier block of the same
     * turn. Show such an outcome with a caveat rather than reading it out as the
     * answer."* So we caveat it, and [TtsGate] refuses to speak it.
     */
    val unsettled: Boolean
        get() = meta["transcript_settled"]?.let {
            (it as? JsonPrimitive)?.booleanOrNullSafe() == false
        } ?: false

    val origin: String? get() = metaString("origin")

    /**
     * ★ The id of the `sent` this event is the echo of, or null.
     *
     * Sending from ROAM types the text into the pane, which fires the same
     * `UserPromptSubmit` hook as his own typing — so one thing he said arrives twice,
     * a second apart, as a `sent` and then a `receipt` with identical text. The hub
     * decides which receipts are that echo (`API.md`, `meta.echo_of`) and the thread
     * collapses them, so a message he sent is **one** entry, not "YOU" followed by
     * "PROMPT".
     *
     * ⚠️ Null on a prompt he typed at the keyboard, and that receipt is the only
     * record the message exists. Never suppress receipts as a class.
     */
    val echoOf: Long?
        get() = (meta["echo_of"] as? JsonPrimitive)?.content?.toLongOrNull()

    /** What the wearer actually typed, for an `error` event whose send was refused. */
    val attempted: String? get() = metaString("attempted")

    /**
     * The action this event records, or null for an ordinary message. A `control`
     * event from the hub, or — in pre-1.5.0 history — a `sent` whose whole payload was
     * a control byte. Either way it renders as an action, never as text the wearer
     * "said". See [ControlKeys].
     */
    val controlKey: ControlKeys.Key? get() = ControlKeys.classify(this)

    /** Display text that is never empty and never a wall. */
    fun displaySummary(): String {
        controlKey?.let { return it.label }
        val s = summary.trim()
        if (s.isNotEmpty()) return s
        val b = body.trim()
        if (b.isNotEmpty()) return b.lineSequence().first().take(280)
        return kindEnum.name.lowercase()
    }

    /**
     * True when there is genuinely more to see behind the summary.
     *
     * ⚠️ Not simply "body != summary". The hub's summary always differs a little — it
     * strips emoji and markdown — so a naive comparison offered "full text · 16 chars"
     * on a channel-opened event, which is clutter that teaches him to ignore the
     * affordance. Seen on the device, 2026-08-12. Expansion is offered when the payload
     * was trimmed, when the summary explicitly stands in for something (`[code, 2
     * lines]`, `[table, 4 rows]`), or when the body is materially longer.
     */
    fun hasMore(): Boolean {
        if (controlKey != null) return false
        if (bodyTruncated) return true
        val b = body.trim()
        val s = summary.trim()
        if (b.isEmpty() || b == s) return false
        if (ELIDED.containsMatchIn(s)) return true
        if (CUT.containsMatchIn(s)) return true
        return b.length >= s.length + MATERIALLY_LONGER
    }

    companion object {
        /** What the hub writes when it replaces a block with a placeholder. */
        private val ELIDED = Regex("""\[(code|table)[^]]*]""")

        /**
         * ★ The hub cuts a summary at a sentence boundary within 280 chars and marks the
         * cut with a trailing ellipsis. That mark is the only reliable evidence that
         * something was removed, and it closes a hole [MATERIALLY_LONGER] left open:
         * event 365 on `%0` had a 280-char summary ending `…` and a 324-char body, so it
         * fell 16 characters short of the threshold and was drawn with **no affordance
         * at all** — six lines that simply stop. That silent stop is the whole bug.
         */
        private val CUT = Regex("""(…|\.\.\.)$""")

        /**
         * Below this, "more" is punctuation and markdown, not content — the hub's
         * summary always differs a little because it strips emoji and formatting, and
         * offering "full text · 16 chars" on a channel-opened event is the clutter that
         * teaches him to ignore the affordance. Seen on the device, 2026-08-12.
         */
        private const val MATERIALLY_LONGER = 60
    }
}

private fun JsonPrimitive.booleanOrNullSafe(): Boolean? =
    when (content.lowercase()) {
        "true" -> true
        "false" -> false
        else -> null
    }

/** `idle|working|dead`, plus a safety net for anything the hub adds later. */
enum class ChannelStatus(val wire: String) {
    IDLE("idle"), WORKING("working"), DEAD("dead"), UNKNOWN("");

    companion object {
        fun from(wire: String?): ChannelStatus =
            entries.firstOrNull { it.wire == wire && it != UNKNOWN } ?: UNKNOWN
    }
}

@Serializable
data class Channel(
    @SerialName("pane_id") val paneId: String,
    val label: String = "",
    val session: String? = null,
    val window: Int? = null,
    val index: Int? = null,
    val command: String? = null,
    val live: Boolean = false,
    val status: String = "idle",
    val archived: Boolean = false,
    @SerialName("first_seen") val firstSeen: Double = 0.0,
    @SerialName("last_seen") val lastSeen: Double = 0.0,
    @SerialName("last_output_at") val lastOutputAt: Double? = null,
    @SerialName("idle_s") val idleS: Double? = null,
    /** `tmux` | `app` | null — where this channel's conversation is happening. */
    @SerialName("last_input_source") val lastInputSource: String? = null,
    @SerialName("last_input_at") val lastInputAt: Double? = null,
    @SerialName("event_count") val eventCount: Int = 0,
    @SerialName("last_event") val lastEvent: Event? = null,
) {
    val statusEnum: ChannelStatus get() = ChannelStatus.from(status)

    /** `%3` -> `3`. API.md: strip the `%` and URL encoding stops being a problem. */
    val urlKey: String get() = paneId.removePrefix("%")

    val displayLabel: String
        get() = label.ifBlank { session?.let { "$it:$window.$index" } ?: paneId }

    val lastActivityMillis: Long
        get() = maxOf(
            (lastOutputAt ?: 0.0) * 1000.0,
            lastEvent?.ts?.times(1000.0) ?: 0.0,
            lastSeen * 1000.0,
        ).toLong()
}

@Serializable
data class PresenceSource(
    val id: String = "",
    val kind: String = "",
    val panes: List<String> = emptyList(),
    @SerialName("covers_all") val coversAll: Boolean = false,
    @SerialName("idle_s") val idleS: Double? = null,
    @SerialName("expires_in_s") val expiresInS: Double? = null,
)

@Serializable
data class Presence(
    val present: Boolean = false,
    @SerialName("covers_all") val coversAll: Boolean = false,
    @SerialName("covered_panes") val coveredPanes: List<String> = emptyList(),
    val sources: List<PresenceSource> = emptyList(),
    @SerialName("server_time") val serverTime: Double = 0.0,
)

// ---------------------------------------------------------------------------
// REST envelopes
// ---------------------------------------------------------------------------

@Serializable
data class ChannelsResponse(
    val channels: List<Channel> = emptyList(),
    @SerialName("latest_event_id") val latestEventId: Long = 0,
    @SerialName("server_time") val serverTime: Double = 0.0,
)

@Serializable
data class ChannelResponse(val channel: Channel)

@Serializable
data class HistoryResponse(
    @SerialName("pane_id") val paneId: String = "",
    val events: List<Event> = emptyList(),
    @SerialName("latest_event_id") val latestEventId: Long = 0,
)

@Serializable
data class EventResponse(val event: Event)

@Serializable
data class SendResponse(val event: Event, val channel: Channel? = null)

@Serializable
data class SendRequest(
    val text: String,
    val enter: Boolean = true,
    val origin: String = "roam-app",
)

/** `POST /channels/{pane}/interrupt` — a key press, recorded as an action, not a message. */
@Serializable
data class InterruptRequest(
    /** `escape` (stop the turn) or `interrupt` (C-c). An allow-list on the hub, not a passthrough. */
    val action: String = "escape",
    val origin: String = "roam-app",
)

/** `POST /channels/{pane}/kill` — end the pane. The channel and its history survive it. */
@Serializable
data class KillRequest(val origin: String = "roam-app")

/** `POST /channels` — spawn a new agent pane. Always a new window, never a split. */
@Serializable
data class CreateChannelRequest(
    val command: String,
    /** The pane title. Always set: unnamed panes all read as the hostname. */
    val label: String,
    val origin: String = "roam-app",
)

@Serializable
data class PresenceRequest(
    val source: String,
    val kind: String = "app",
    /**
     * ⚠️⚠️ **False, and that is the whole point.** The app used to claim `covers_all`,
     * which told the hub the wearer had eyes on every channel at once, so the hub
     * correctly concluded there was nothing worth interrupting him for and stopped
     * buzzing his arm entirely. The buzz path was never broken; it was never asked to run.
     *
     * Owner's rule, verbatim: *"haptic and buzz when I'm actually on that device, and I'm
     * not in the active channel at the time, that's it."* So presence covers exactly the
     * pane he has open — [panes] — and nothing else.
     */
    @SerialName("covers_all") val coversAll: Boolean = false,
    /** The pane he is looking at, if any. The hub's `covers()` checks membership here. */
    val panes: List<String> = emptyList(),
    @SerialName("ttl_s") val ttlS: Int = 90,
    val detail: JsonObject = JsonObject(emptyMap()),
)

@Serializable
data class StatusResponse(
    val ok: Boolean = false,
    val version: String = "",
    val protocol: Int = 0,
    @SerialName("tmux_ok") val tmuxOk: Boolean = false,
    @SerialName("latest_event_id") val latestEventId: Long = 0,
)

@Serializable
data class ErrorResponse(val detail: String = "")

// ---------------------------------------------------------------------------
// WebSocket frames
// ---------------------------------------------------------------------------

/**
 * A server frame, decoded loosely. `type` drives everything; unknown types are handed
 * back as [HubFrame.Unknown] and dropped by the store rather than closing the socket.
 */
sealed interface HubFrame {
    data class Hello(
        val protocol: Int,
        val version: String,
        val serverTime: Double,
        val latestEventId: Long,
        val channels: List<Channel>,
        val presence: Presence?,
    ) : HubFrame

    data class Backlog(val since: Long, val events: List<Event>) : HubFrame
    data class NewEvent(val event: Event) : HubFrame
    data class Channels(val channels: List<Channel>, val serverTime: Double) : HubFrame
    data class OneChannel(val channel: Channel) : HubFrame
    data class Activity(val panes: Map<String, Double>, val serverTime: Double) : HubFrame
    data class HistoryCleared(val paneId: String, val archived: Int) : HubFrame
    data class PresenceChanged(val presence: Presence) : HubFrame
    data class Desync(val latestEventId: Long) : HubFrame
    data class Error(val detail: String) : HubFrame
    data object Ping : HubFrame
    data object Pong : HubFrame
    data class Unknown(val type: String) : HubFrame
}

object FrameParser {
    fun parse(text: String): HubFrame? {
        val obj = runCatching { HubJson.parseToJsonElement(text) as? JsonObject }
            .getOrNull() ?: return null
        return when (obj.str("type")) {
            "hello" -> HubFrame.Hello(
                protocol = obj.int("protocol") ?: 0,
                version = obj.str("version") ?: "",
                serverTime = obj.dbl("server_time") ?: 0.0,
                latestEventId = obj.long("latest_event_id") ?: 0L,
                channels = obj.decodeList("channels"),
                presence = obj["presence"]?.let { decodeOrNull<Presence>(it) },
            )

            "backlog" -> HubFrame.Backlog(
                since = obj.long("since") ?: 0L,
                events = obj.decodeList("events"),
            )

            "event" -> obj["event"]?.let { decodeOrNull<Event>(it) }
                ?.let { HubFrame.NewEvent(it) }

            "channels" -> HubFrame.Channels(
                channels = obj.decodeList("channels"),
                serverTime = obj.dbl("server_time") ?: 0.0,
            )

            "channel" -> obj["channel"]?.let { decodeOrNull<Channel>(it) }
                ?.let { HubFrame.OneChannel(it) }

            "activity" -> HubFrame.Activity(
                panes = (obj["panes"] as? JsonObject).orEmpty()
                    .mapNotNull { (k, v) ->
                        (v as? JsonPrimitive)?.content?.toDoubleOrNull()?.let { k to it }
                    }.toMap(),
                serverTime = obj.dbl("server_time") ?: 0.0,
            )

            "history_cleared" -> HubFrame.HistoryCleared(
                paneId = obj.str("pane_id") ?: return null,
                archived = obj.int("archived") ?: 0,
            )

            // The presence snapshot is inlined into the frame, not nested.
            "presence" -> decodeOrNull<Presence>(obj)?.let { HubFrame.PresenceChanged(it) }

            "desync" -> HubFrame.Desync(obj.long("latest_event_id") ?: 0L)
            "error" -> HubFrame.Error(obj.str("detail") ?: "unknown error")
            "ping" -> HubFrame.Ping
            "pong" -> HubFrame.Pong
            null -> null
            else -> HubFrame.Unknown(obj.str("type")!!)
        }
    }

    private inline fun <reified T> decodeOrNull(el: JsonElement): T? =
        runCatching { HubJson.decodeFromJsonElement<T>(el) }.getOrNull()

    private inline fun <reified T> JsonObject.decodeList(key: String): List<T> =
        (this[key] as? JsonArray)
            ?.mapNotNull { decodeOrNull<T>(it) } ?: emptyList()

    private fun JsonObject.str(k: String) =
        (this[k] as? JsonPrimitive)?.takeIf { it.isString }?.content

    private fun JsonObject.int(k: String) = (this[k] as? JsonPrimitive)?.content?.toIntOrNull()
    private fun JsonObject.long(k: String) = (this[k] as? JsonPrimitive)?.content?.toLongOrNull()
    private fun JsonObject.dbl(k: String) = (this[k] as? JsonPrimitive)?.content?.toDoubleOrNull()
    private fun JsonObject?.orEmpty(): Map<String, JsonElement> = this ?: emptyMap()
}

/**
 * Control actions in a thread — rendered as chips, never as text the wearer "said".
 *
 * ⚠️ Interrupt and kill go over their own endpoints now (`/interrupt`, `/kill`), which
 * record a `control` event whose body names the action. Raw bytes through `/send` are
 * HISTORY, not a path: the hub rejects C0 control characters there with 400 since
 * 1.5.0. The byte forms below stay only so the `sent` events already in the ledger
 * keep rendering as the actions they were.
 */
object ControlKeys {
    enum class Key(val bytes: String, val label: String) {
        ESC("\u001B", "INTERRUPT"),
        CTRL_C("\u0003", "STOP"),

        /** `control`/`kill` — the hub ends the pane itself; there is no byte form. */
        KILL_PANE("", "KILL"),
    }

    /** ESC stops a Claude turn but keeps the session alive. The first thing to try. */
    val INTERRUPT = Key.ESC

    /** SIGINT — kept for classifying the old two-Ctrl-C kills in stored history. */
    val KILL = Key.CTRL_C

    fun classify(event: Event): Key? = when (EventKind.from(event.kind)) {
        // Pre-1.5.0 history: a `sent` whose whole payload was a control byte.
        EventKind.SENT -> Key.entries.firstOrNull {
            it.bytes.isNotEmpty() &&
                (event.body == it.bytes || event.body == it.bytes + it.bytes)
        }

        // The hub's own record of an interrupt or kill; the body names the action.
        EventKind.CONTROL -> when (event.body) {
            "escape" -> Key.ESC
            "interrupt" -> Key.CTRL_C
            "kill" -> Key.KILL_PANE
            else -> null
        }

        else -> null
    }
}
