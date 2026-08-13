package com.roam.touch.channels

import android.util.Log
import com.roam.touch.channels.model.ControlKeys
import com.roam.touch.channels.model.Event
import com.roam.touch.channels.model.HubFrame
import com.roam.touch.channels.net.Backoff
import com.roam.touch.channels.net.HubApi
import com.roam.touch.channels.net.HubHttpException
import com.roam.touch.channels.net.HubSocket
import com.roam.touch.channels.net.SocketEvent
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.IOException
import java.io.InterruptedIOException

/** Why the panel is not showing live truth. Each one reads differently to a wearer. */
enum class OfflineReason {
    /** No route to the hub: Tailscale down, talos asleep, hub crashed. */
    UNREACHABLE,

    /** The hub answered and refused us. The token is wrong; retrying will not help. */
    UNAUTHORISED,

    /** We fell so far behind the hub cut us off. Harmless; we re-sync. */
    DESYNC,
}

/**
 * ★ The state that must never be silent.
 *
 * A panel that shows nothing arriving looks exactly the same whether the world is quiet
 * or the link is dead. That ambiguity is the failure mode that makes the whole device
 * worthless, so the link state is a first-class, always-rendered value — not a toast.
 */
sealed interface HubLink {
    data object Connecting : HubLink
    data class Online(val sinceMs: Long) : HubLink
    data class Offline(
        val reason: OfflineReason,
        val sinceMs: Long,
        val lastContactMs: Long?,
        val attempt: Int,
        val nextRetryAtMs: Long,
        val detail: String = "",
    ) : HubLink

    val isOnline: Boolean get() = this is Online
}

/** An event that just arrived live, tagged with where it came from, for the TTS gate. */
data class ArrivedEvent(val event: Event, val fromBacklog: Boolean)

/** Result of a send, so the UI can say what actually happened rather than guessing. */
sealed interface SendResult {
    data object Ok : SendResult
    data class Failed(val message: String, val fatal: Boolean) : SendResult
}

/**
 * Owns the connection, the cursor and the state. Everything the UI does goes through
 * here; everything the hub says lands here first.
 *
 * The loop is exactly the client algorithm in `API.md` §4, including the part that says
 * never to poll: the only repeated HTTP call in this class is the presence heartbeat,
 * which the contract asks for explicitly.
 */
class HubRepository(
    private val api: HubApi,
    private val socket: HubSocket,
    private val settings: ReadCursorStore,
    private val clock: () -> Long = System::currentTimeMillis,
) {
    private val _state = MutableStateFlow(ChannelsState())
    val state: StateFlow<ChannelsState> = _state.asStateFlow()

    private val _link = MutableStateFlow<HubLink>(HubLink.Connecting)
    val link: StateFlow<HubLink> = _link.asStateFlow()

    private val _arrivals = MutableSharedFlow<ArrivedEvent>(extraBufferCapacity = 64)
    val arrivals: SharedFlow<ArrivedEvent> = _arrivals.asSharedFlow()

    private var lastContactMs: Long? = null
    private var presenceJob: Job? = null

    /**
     * ★ The channel on screen. Presence covers this and nothing else — see
     * [PresenceRequest.coversAll]. Set from the UI whenever the open thread changes so a
     * message on any *other* channel still reaches his arm.
     */
    @Volatile
    var openPane: String? = null
        set(value) {
            val changed = field != value
            field = value
            // ⚠️ Push it immediately rather than waiting up to 30 s for the heartbeat:
            // he switches channel and expects the next message to behave accordingly.
            if (changed) scope?.launch { runCatching { api.registerPresence(value) } }
        }

    private var scope: CoroutineScope? = null

    /** Restore what he had already read before the process was killed. */
    suspend fun restore() {
        val cursors = runCatching { settings.loadReadCursors() }.getOrDefault(emptyMap())
        _state.update { it.copy(readCursors = cursors) }
    }

    /**
     * Connect, and stay connected, forever. Returns only on cancellation.
     *
     * Each pass: seed from `GET /channels`, hold the socket, and when it dies wait out
     * the backoff and go again with `?since=<cursor>`. Nothing is lost across a drop —
     * the hub replays by id, which is the entire reason this design does not poll.
     */
    suspend fun run(scope: CoroutineScope) {
        var attempt = 0
        while (scope.isActive) {
            _link.value = HubLink.Connecting

            val seeded = runCatching { api.channels() }
            if (seeded.isFailure) {
                val err = seeded.exceptionOrNull()
                attempt++
                goOffline(reasonFor(err), attempt, err?.message.orEmpty())
                delay(Backoff.delayMs(attempt))
                continue
            }
            seeded.getOrNull()?.let { resp ->
                lastContactMs = clock()
                _state.update {
                    ChannelReducer.applyChannels(
                        it, resp.channels, resp.latestEventId, resp.serverTime, clock()
                    )
                }
                catchUp()
            }

            var opened = false
            var reason = OfflineReason.UNREACHABLE
            var detail = ""

            // ⚠️ Everything inside the socket's lifetime is caught. An uncaught throw in
            // a coroutine kills the *process* — verified on the device: one malformed URL
            // took down the launcher in a restart loop. On a worn device the correct
            // response to any unexpected failure is the visible offline banner, never a
            // dead panel. Cancellation is re-thrown so shutdown still works.
            try {
            // `since` is the cursor we have actually applied, never the hub's latest.
            socket.connect(_state.value.cursor.takeIf { it > 0 }).collect { ev ->
                when (ev) {
                    is SocketEvent.Open -> {
                        opened = true
                        attempt = 0
                        lastContactMs = clock()
                        _link.value = HubLink.Online(clock())
                    }

                    is SocketEvent.Frame -> {
                        lastContactMs = clock()
                        handleFrame(ev.frame)
                        if (ev.frame is HubFrame.Desync) reason = OfflineReason.DESYNC
                    }

                    is SocketEvent.Closed -> {
                        if (ev.code == HubSocket.UNAUTHORISED_CODE) {
                            reason = OfflineReason.UNAUTHORISED
                            detail = ev.reason
                        }
                    }

                    is SocketEvent.Failed -> {
                        detail = ev.error.message.orEmpty()
                    }
                }
            }
            } catch (ce: kotlinx.coroutines.CancellationException) {
                throw ce
            } catch (t: Throwable) {
                Log.e(TAG, "socket loop failed", t)
                detail = t.message ?: t::class.java.simpleName
            }

            attempt = if (opened) 1 else attempt + 1
            goOffline(reason, attempt, detail)
            delay(Backoff.delayMs(attempt))
        }
    }

    /**
     * ★ Make the unread badges true after a cold start.
     *
     * The channel list alone cannot say how much he missed — it carries one `last_event`
     * per channel, not a count of what is new. Android kills this process routinely, so
     * "how much is waiting" has to be reconstructible from nothing but the persisted read
     * cursors. One `GET /events?since=` does it for every channel at once.
     */
    private suspend fun catchUp() {
        val cursors = _state.value.readCursors
        if (cursors.isEmpty()) {
            _state.update { ChannelReducer.seedReadFromSnapshot(it) }
            runCatching { settings.saveReadCursors(_state.value.readCursors) }
            return
        }
        // The oldest cursor across channels: anything newer than that is potentially
        // unread somewhere, and the per-channel comparison sorts out where.
        val since = cursors.values.minOrNull() ?: return
        runCatching { api.events(since = since, limit = CATCHUP_LIMIT) }
            .onSuccess { resp ->
                lastContactMs = clock()
                _state.update { st ->
                    resp.events.groupBy { it.paneId }.entries.fold(st) { acc, (pane, evs) ->
                        // hydrate = false: this is a slice across all channels, not one
                        // channel's history, so opening a thread must still fetch it.
                        ChannelReducer.applyHistory(acc, pane, evs, 0L, hydrate = false)
                    }
                }
            }
            .onFailure { Log.w(TAG, "catch-up failed: ${it.message}") }
    }

    private fun reasonFor(err: Throwable?): OfflineReason =
        if (err is HubHttpException && err.isUnauthorised) OfflineReason.UNAUTHORISED
        else OfflineReason.UNREACHABLE

    private fun goOffline(reason: OfflineReason, attempt: Int, detail: String) {
        val now = clock()
        _link.value = HubLink.Offline(
            reason = reason,
            sinceMs = now,
            lastContactMs = lastContactMs,
            attempt = attempt,
            nextRetryAtMs = now + Backoff.delayMs(attempt),
            detail = detail,
        )
    }

    private suspend fun handleFrame(frame: HubFrame) {
        when (frame) {
            is HubFrame.NewEvent -> {
                _state.update { ChannelReducer.applyEvent(it, frame.event) }
                _arrivals.emit(ArrivedEvent(frame.event, fromBacklog = false))
            }

            is HubFrame.Backlog -> {
                _state.update { ChannelReducer.applyFrame(it, frame, clock()) }
                frame.events.forEach { _arrivals.emit(ArrivedEvent(it, fromBacklog = true)) }
            }

            else -> _state.update { ChannelReducer.applyFrame(it, frame, clock()) }
        }
    }

    // -----------------------------------------------------------------------
    // Reads
    // -----------------------------------------------------------------------

    /**
     * Pull a thread's history. Called when a channel is opened, and after a reconnect
     * for the thread currently on screen — a `backlog` covers the socket's own gap, but
     * a thread opened for the first time has never had one.
     */
    suspend fun loadHistory(paneId: String, limit: Int = 200) {
        runCatching { api.history(paneId, limit = limit) }
            .onSuccess { resp ->
                lastContactMs = clock()
                _state.update { ChannelReducer.applyHistory(it, paneId, resp.events, 0L) }
            }
            .onFailure { Log.w(TAG, "history($paneId) failed: ${it.message}") }
    }

    /** Behind "show more" on a body the bulk payload trimmed to 4 KiB. */
    suspend fun expand(event: Event) {
        if (!event.bodyTruncated || _state.value.fullBodies.containsKey(event.id)) return
        runCatching { api.event(event.id) }
            .onSuccess { full ->
                _state.update { ChannelReducer.applyFullBody(it, full.id, full.body) }
            }
            .onFailure { Log.w(TAG, "expand(${event.id}) failed: ${it.message}") }
    }

    suspend fun markRead(paneId: String) {
        _state.update { ChannelReducer.markRead(it, paneId) }
        runCatching { settings.saveReadCursors(_state.value.readCursors) }
    }

    // -----------------------------------------------------------------------
    // Writes
    // -----------------------------------------------------------------------

    suspend fun send(paneId: String, text: String): SendResult = write(paneId, text, enter = true)

    /**
     * ESC — stop the current turn, keep the session. The first thing to reach for when
     * `idle_s` has been climbing and he decides it is stuck.
     */
    suspend fun interrupt(paneId: String): SendResult =
        write(paneId, ControlKeys.INTERRUPT.bytes, enter = false)

    /**
     * Ctrl-C twice — what actually exits Claude Code. Sent as one payload so the two
     * bytes cannot be separated by a reconnect, and never with Enter behind it.
     */
    suspend fun kill(paneId: String): SendResult =
        write(paneId, ControlKeys.KILL.bytes.repeat(2), enter = false)

    private suspend fun write(paneId: String, text: String, enter: Boolean): SendResult =
        try {
            val resp = api.send(paneId, text, enter)
            lastContactMs = clock()
            // The hub pushes this back over the socket too; applying it here means the
            // thread updates immediately instead of one round trip later.
            _state.update { ChannelReducer.applyEvent(it, resp.event) }
            SendResult.Ok
        } catch (e: HubHttpException) {
            SendResult.Failed(e.shortReason(), fatal = e.isNotLive || e.isUnauthorised)
        } catch (e: InterruptedIOException) {
            // ★★ The deadline in HubApi expired: the hub answered the phone and then
            // stopped talking. Told apart from "unreachable" because the two send him to
            // completely different places — this one means the route is fine and
            // something on talos is wedged, and it is the only one where trying the exact
            // same thing again in ten seconds is a reasonable idea.
            //
            // ⚠️ It is deliberately not fatal and deliberately not silent: the words are
            // kept and handed back, because a timeout says nothing about whether the hub
            // will take them on the next try.
            Log.w(TAG, "send($paneId) timed out: ${e.message}")
            SendResult.Failed(TIMED_OUT, fatal = false)
        } catch (e: IOException) {
            SendResult.Failed("hub unreachable", fatal = false)
        }

    // -----------------------------------------------------------------------
    // Presence
    // -----------------------------------------------------------------------

    /**
     * Tell the hub which channel he is looking at, and keep telling it.
     *
     * `API.md`: post presence on foreground, refresh every ~30 s, delete on background.
     * The bridge then stops buzzing his arm about the screen he is reading — and *only*
     * about that one. None of that logic is duplicated here, which is the point.
     */
    fun startPresence(scope: CoroutineScope) {
        this.scope = scope
        if (presenceJob?.isActive == true) return
        presenceJob = scope.launch {
            while (isActive) {
                // ⚠️ Logged, not swallowed. This silently failing is invisible from the
                // outside: the only symptom is the bridge notifying him about a screen
                // he is looking at, which reads as a notification bug, not a presence bug.
                runCatching { api.registerPresence(openPane) }
                    .onSuccess { Log.i(TAG, "presence: covering ${openPane ?: "nothing"}") }
                    .onFailure { Log.w(TAG, "presence POST failed: ${it.message}") }
                delay(PRESENCE_REFRESH_MS)
            }
        }
    }

    suspend fun stopPresence() {
        presenceJob?.cancel()
        presenceJob = null
        api.clearPresence()
        Log.i(TAG, "presence dropped")
    }

    companion object {
        private const val TAG = "RoamChannels"

        /**
         * ★ What a wedged hub is called on screen. Short enough for a chip, and it names
         * the hub rather than the network, because that is which one is broken.
         */
        const val TIMED_OUT = "hub did not answer in time"

        /** Well inside the 90 s TTL, so one dropped refresh does not lapse presence. */
        const val PRESENCE_REFRESH_MS = 30_000L

        /** Bounded: if he is further behind than this, the exact number stops mattering. */
        const val CATCHUP_LIMIT = 500
    }
}
