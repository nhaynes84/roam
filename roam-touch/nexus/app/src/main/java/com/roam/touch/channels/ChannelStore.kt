package com.roam.touch.channels

import com.roam.touch.channels.model.Channel
import com.roam.touch.channels.model.ChannelStatus
import com.roam.touch.channels.model.Event
import com.roam.touch.channels.model.EventKind
import com.roam.touch.channels.model.HubFrame
import com.roam.touch.channels.model.Presence
import com.roam.touch.channels.ui.Format

/**
 * The whole client-side model of the hub, as one immutable value.
 *
 * Every mutation is a pure function on this class. That is not architecture for its own
 * sake: the awkward cases on this device — a socket that dropped during doze, a backlog
 * replayed out of a cold start, an `activity` frame for a pane the list has not heard of
 * yet — are all reducer inputs, and a reducer is something a test can hit a hundred
 * times in a millisecond.
 */
data class ChannelsState(
    val channels: List<Channel> = emptyList(),

    /** pane id -> events, oldest first, unique by id. */
    val threads: Map<String, List<Event>> = emptyMap(),

    /** Highest event id applied. This is the reconnect cursor (`?since=`). */
    val cursor: Long = 0L,

    /** serverTimeMillis - localTimeMillis, so `idle_s` can be aged between frames. */
    val serverSkewMs: Long = 0L,

    val presence: Presence? = null,

    /** pane id -> highest event id the wearer has seen in the thread view. */
    val readCursors: Map<String, Long> = emptyMap(),

    /** Untrimmed bodies fetched via `GET /events/{id}`. */
    val fullBodies: Map<Long, String> = emptyMap(),

    /** Panes whose history has been loaded at least once. */
    val hydrated: Set<String> = emptySet(),
) {
    fun channel(paneId: String): Channel? = channels.firstOrNull { it.paneId == paneId }

    fun thread(paneId: String): List<Event> = threads[paneId].orEmpty()

    /** The full body if we have it, otherwise whatever the bulk payload carried. */
    fun bodyOf(event: Event): String = fullBodies[event.id] ?: event.body

    /** True when the wearer would still learn something by tapping "more". */
    fun needsExpansion(event: Event): Boolean =
        event.bodyTruncated && !fullBodies.containsKey(event.id)

    /**
     * Events in [paneId] the wearer has not read *and* that came from the other side.
     * His own `sent` events are never unread, and neither is a `receipt` — he just
     * typed it. This mirrors the bridge's PUSH_KINDS plus `note`, so the badge and the
     * arm buzz agree about what counts as news.
     */
    fun unread(paneId: String): List<Event> {
        val floor = readCursors[paneId] ?: 0L
        return thread(paneId).filter { it.id > floor && it.kindEnum in ATTENTION_KINDS }
    }

    fun unreadCount(paneId: String): Int = unread(paneId).size

    fun totalUnread(): Int = channels.sumOf { unreadCount(it.paneId) }

    /** Server-side "now" in millis, corrected for whatever this phone's clock thinks. */
    fun serverNowMs(localNowMs: Long): Long = localNowMs + serverSkewMs

    /**
     * How long since this pane's visible output last changed, in millis, aged locally.
     * `null` when the hub has never sampled it — `API.md` is emphatic that this is not
     * the same as zero and must not be rendered as "active now".
     */
    fun idleMs(paneId: String, localNowMs: Long): Long? {
        val ch = channel(paneId) ?: return null
        val lastOut = ch.lastOutputAt ?: return null
        if (lastOut <= 0.0) return null
        return (serverNowMs(localNowMs) - (lastOut * 1000.0).toLong()).coerceAtLeast(0L)
    }

    companion object {
        val ATTENTION_KINDS = setOf(EventKind.OUTCOME, EventKind.ERROR, EventKind.NOTE)
    }
}

/**
 * What the row's live indicator should say. Derived, never stored, so it cannot go
 * stale behind the clock.
 */
sealed interface Liveness {
    /** Output moved recently — draw the typing ellipsis. */
    data class Working(val idleMs: Long?) : Liveness

    /**
     * Still `working`, but nothing has come out for a while. This is the whole reason
     * `idle_s` exists: *"a typing ellipsis while you're in process, otherwise I
     * wouldn't know when to kill."* It is "nothing is coming out", never "it is dead".
     */
    data class Quiet(val idleMs: Long) : Liveness

    data class Idle(val idleMs: Long?) : Liveness
    data object Dead : Liveness
    data object Unknown : Liveness
}

/**
 * The words on the state chip. Derived, pure, and deliberately *not* in the composable:
 * this is the one string on the screen that has to be right, and a rule that lives in a
 * `@Composable` can only be checked by looking at a phone.
 *
 * ★ **`idle_s` is only rendered where it can change.** Owner, on the device: *"your
 * 'Working' counter just seems to go 0, 1, 0, 1 — it doesn't count past 1."* He was
 * right, and the hub was right too: a working pane repaints its spinner every second, so
 * `idle_s` legitimately oscillates between 0.1 s and 2.1 s forever. Floored to seconds
 * that is a number which can never leave 0–2, next to an animation that already says the
 * same thing. So `WORKING` carries no digits; the ellipsis is the signal. The number
 * appears exactly where it becomes information: a session that has gone [Liveness.Quiet],
 * and a long-[Liveness.Idle] channel.
 */
object LivenessLabel {

    /**
     * Below this, a duration is jitter rather than news, and rendering it produces the
     * flicker above. Five seconds is longer than two hub samples, so anything shown is
     * a genuine gap and not a missed repaint.
     */
    const val MEANINGFUL_MS = 5_000L

    fun text(liveness: Liveness): String = when (liveness) {
        // No number, ever. The animation carries this state.
        is Liveness.Working -> "WORKING"
        // Always a number. This one *is* the kill decision.
        is Liveness.Quiet -> "QUIET " + Format.duration(liveness.idleMs)
        is Liveness.Idle -> liveness.idleMs
            ?.takeIf { it >= MEANINGFUL_MS }
            ?.let { "IDLE " + Format.duration(it) }
            ?: "IDLE"

        Liveness.Dead -> "DEAD"
        Liveness.Unknown -> "UNKNOWN"
    }
}

object Liveliness {
    /**
     * How long a `working` pane may produce nothing before the row stops saying
     * "working" and starts saying "quiet for N".
     *
     * The hub fingerprints the screen every 2 s and a Claude pane repaints a spinner
     * and an elapsed counter while it thinks, so a healthy working pane sits near zero.
     * 20 s is ten samples of nothing — far past jitter, well short of accusing a slow
     * tool call of being wedged.
     */
    const val QUIET_THRESHOLD_MS = 20_000L

    fun of(state: ChannelsState, channel: Channel, localNowMs: Long): Liveness {
        if (channel.statusEnum == ChannelStatus.DEAD || !channel.live) return Liveness.Dead
        val idle = state.idleMs(channel.paneId, localNowMs)
        return when (channel.statusEnum) {
            ChannelStatus.WORKING ->
                if (idle != null && idle >= QUIET_THRESHOLD_MS) Liveness.Quiet(idle)
                else Liveness.Working(idle)

            ChannelStatus.IDLE -> Liveness.Idle(idle)
            else -> Liveness.Unknown
        }
    }
}

/**
 * Queue order — *which session needs me first*, not a chronological feed.
 *
 * The thesis says the screen is glanced at while walking. So the top of the list is
 * always the thing that would make him stop walking.
 */
object Queue {
    const val RANK_UNREAD = 0
    const val RANK_QUIET = 1
    const val RANK_WORKING = 2
    const val RANK_IDLE = 3
    const val RANK_DEAD = 4

    fun rank(state: ChannelsState, channel: Channel, localNowMs: Long): Int {
        // Unread outranks everything, including death: a dead pane's last words are
        // exactly the outcome you were waiting for.
        if (state.unreadCount(channel.paneId) > 0) return RANK_UNREAD
        return when (Liveliness.of(state, channel, localNowMs)) {
            is Liveness.Quiet -> RANK_QUIET
            is Liveness.Working -> RANK_WORKING
            is Liveness.Dead -> RANK_DEAD
            is Liveness.Idle, Liveness.Unknown -> RANK_IDLE
        }
    }

    fun order(state: ChannelsState, localNowMs: Long): List<Channel> =
        state.channels.sortedWith(
            compareBy<Channel> { rank(state, it, localNowMs) }
                .thenByDescending { it.lastActivityMillis }
                .thenBy { it.paneId }
        )
}

/** Pure reducers. Each returns a new [ChannelsState]; none of them touch the network. */
object ChannelReducer {

    fun applyFrame(state: ChannelsState, frame: HubFrame, localNowMs: Long): ChannelsState =
        when (frame) {
            // hello's channel list is authoritative (API.md §4 step 3). It deliberately
            // does NOT move the cursor: `backlog` arrives immediately after, and a
            // socket that dies in between would otherwise have skipped every event it
            // was about to replay. The cursor only advances over events actually
            // applied — except on a cold start, where GET /channels seeds it.
            is HubFrame.Hello -> state
                .withServerTime(frame.serverTime, localNowMs)
                .copy(
                    channels = frame.channels,
                    presence = frame.presence ?: state.presence,
                    cursor = if (state.cursor == 0L) frame.latestEventId else state.cursor,
                )

            is HubFrame.Backlog -> frame.events.fold(state) { acc, e -> applyEvent(acc, e) }

            is HubFrame.NewEvent -> applyEvent(state, frame.event)

            is HubFrame.Channels -> state
                .withServerTime(frame.serverTime, localNowMs)
                .copy(channels = frame.channels)

            is HubFrame.OneChannel -> state.copy(channels = upsert(state.channels, frame.channel))

            is HubFrame.Activity -> state
                .withServerTime(frame.serverTime, localNowMs)
                .copy(channels = state.channels.map { ch ->
                    frame.panes[ch.paneId]?.let { ch.copy(lastOutputAt = it, idleS = 0.0) } ?: ch
                })

            is HubFrame.HistoryCleared -> state.copy(
                threads = state.threads - frame.paneId,
                hydrated = state.hydrated - frame.paneId,
            )

            is HubFrame.PresenceChanged -> state.copy(presence = frame.presence)

            // desync/error/ping/pong/unknown carry no model change; the repository
            // reacts to them at the connection level.
            else -> state
        }

    /**
     * Append one event.
     *
     * Idempotent by id, because the same event can legitimately arrive twice: a
     * `backlog` replay racing a `GET /channels/{pane}/history` after a resume. The
     * cursor only ever moves forward.
     */
    fun applyEvent(state: ChannelsState, event: Event): ChannelsState {
        val existing = state.thread(event.paneId)
        if (existing.any { it.id == event.id }) {
            return state.copy(cursor = maxOf(state.cursor, event.id))
        }
        val merged = (existing + event).sortedBy { it.id }
        val channels = state.channels.map {
            if (it.paneId != event.paneId) return@map it
            // ⚠️ Only an event *newer* than the channel snapshot counts as new. A
            // `backlog` replay or a catch-up sweep re-delivers events the snapshot's
            // `event_count` already includes, and it would otherwise both double-count
            // them and drag `last_event` backwards to something stale — which would show
            // the wearer an old answer as the newest thing in that channel.
            val newer = (it.lastEvent?.id ?: 0L) < event.id
            if (newer) it.copy(lastEvent = event, eventCount = it.eventCount + 1) else it
        }
        return state.copy(
            threads = state.threads + (event.paneId to merged),
            channels = channels,
            cursor = maxOf(state.cursor, event.id),
        )
    }

    /**
     * @param hydrate whether this counts as "the thread has been loaded". A catch-up
     *   sweep (`GET /events?since=`) fills in recent events across every channel but is
     *   *not* a full thread, so it must not stop the thread view from fetching history
     *   when he actually opens one.
     */
    fun applyHistory(
        state: ChannelsState,
        paneId: String,
        events: List<Event>,
        latestEventId: Long,
        hydrate: Boolean = true,
    ): ChannelsState {
        val byId = LinkedHashMap<Long, Event>()
        state.thread(paneId).forEach { byId[it.id] = it }
        events.forEach { byId[it.id] = it }
        return state.copy(
            threads = state.threads + (paneId to byId.values.sortedBy { it.id }),
            hydrated = if (hydrate) state.hydrated + paneId else state.hydrated,
            cursor = maxOf(state.cursor, latestEventId),
        )
    }

    /**
     * First ever launch: mark everything already on the hub as read.
     *
     * Otherwise the queue opens with a badge on every channel counting history he lived
     * through at a keyboard, and a badge that is wrong on day one is a badge he learns
     * to ignore — which destroys the only signal the list has.
     */
    fun seedReadFromSnapshot(state: ChannelsState): ChannelsState = state.copy(
        readCursors = state.channels.mapNotNull { ch ->
            ch.lastEvent?.id?.let { ch.paneId to it }
        }.toMap()
    )

    fun applyChannels(
        state: ChannelsState,
        channels: List<Channel>,
        latestEventId: Long,
        serverTime: Double,
        localNowMs: Long,
    ): ChannelsState = state
        .withServerTime(serverTime, localNowMs)
        .copy(channels = channels, cursor = maxOf(state.cursor, latestEventId))

    fun applyFullBody(state: ChannelsState, id: Long, body: String): ChannelsState =
        state.copy(fullBodies = state.fullBodies + (id to body))

    /**
     * Mark a thread read up to its newest event. Called when the wearer opens the
     * thread — and again while it is open, because outcomes land while he is looking.
     */
    fun markRead(state: ChannelsState, paneId: String): ChannelsState {
        val newest = state.thread(paneId).maxOfOrNull { it.id }
            ?: state.channel(paneId)?.lastEvent?.id
            ?: return state
        val current = state.readCursors[paneId] ?: 0L
        if (newest <= current) return state
        return state.copy(readCursors = state.readCursors + (paneId to maxOf(current, newest)))
    }

    fun markAllRead(state: ChannelsState): ChannelsState =
        state.channels.fold(state) { acc, ch -> markRead(acc, ch.paneId) }

    private fun upsert(channels: List<Channel>, channel: Channel): List<Channel> {
        val idx = channels.indexOfFirst { it.paneId == channel.paneId }
        return if (idx < 0) channels + channel
        else channels.toMutableList().also { it[idx] = channel }
    }

    private fun ChannelsState.withServerTime(serverTime: Double, localNowMs: Long): ChannelsState {
        if (serverTime <= 0.0) return this
        return copy(serverSkewMs = (serverTime * 1000.0).toLong() - localNowMs)
    }
}
