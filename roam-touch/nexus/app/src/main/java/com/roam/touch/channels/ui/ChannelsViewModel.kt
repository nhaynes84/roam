package com.roam.touch.channels.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.roam.touch.channels.ChannelsState
import com.roam.touch.channels.HubLink
import com.roam.touch.channels.HubRepository
import com.roam.touch.channels.Roam
import com.roam.touch.channels.SendResult
import com.roam.touch.channels.model.Event
import com.roam.touch.channels.stt.Ptt
import com.roam.touch.channels.stt.PttState
import com.roam.touch.channels.stt.PttTarget
import com.roam.touch.channels.tts.Speaker
import com.roam.touch.ha.HaHome
import com.roam.touch.ha.HaRepository
import com.roam.touch.ha.HaState
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.launch

/** A one-shot message for the wearer: what just happened to something he did. */
data class Toast(val text: String, val bad: Boolean)

/**
 * ★★ A typed or canned message that is with the hub right now.
 *
 * ⚠️ This exists because the composer used to clear the field on tap and then say
 * nothing at all until the hub answered. Measured on the emulator against a wedged hub:
 * he tapped CONTINUE, his word vanished, and 105 seconds later there was still nothing
 * on screen — no pending state, no error, no message in the thread. A send that leaves
 * no trace is indistinguishable from an app that has stopped working, which is exactly
 * how it was reported.
 */
data class Outbox(val text: String, val startedAtMs: Long)

/**
 * Thin. Every decision worth testing lives in [com.roam.touch.channels.ChannelReducer],
 * [com.roam.touch.channels.Queue] or the repository; this exists so Compose has a
 * lifecycle-scoped place to launch from.
 */
class ChannelsViewModel(
    private val repo: HubRepository = Roam.repository,
    private val speaker: Speaker = Roam.speaker,
    /**
     * ⚠️ Resolved lazily, unlike the two above. Every existing Channels test constructs
     * this view model with its own fake hub and speaker and never touches Home
     * Assistant; an eager `Roam.homeAssistant` default would make all of them fail on
     * an uninitialised singleton, which is a test suite paying for a feature it does
     * not use. App #2 is loaded when app #2 is opened.
     */
    haProvider: () -> HaRepository = { Roam.homeAssistant },
    /** Lazy for the same reason as [haProvider] — see the note above. */
    pttProvider: () -> Ptt = { Roam.ptt },
    /** Injectable so "how long has this send been in flight" is a test, not a stopwatch. */
    private val clock: () -> Long = System::currentTimeMillis,
) : ViewModel() {

    private val ha: HaRepository by lazy(haProvider)
    private val ptt: Ptt by lazy(pttProvider)

    val state: StateFlow<ChannelsState> = repo.state
    val link: StateFlow<HubLink> = repo.link

    /** App #2. See [com.roam.touch.channels.ui.HomeAssistantScreen]. */
    val haHome: StateFlow<HaHome> get() = ha.home

    fun refreshHa() {
        viewModelScope.launch { ha.refresh() }
    }

    /**
     * A tap on an entity tile. The repository owns the optimism (it has none — it waits
     * for the states HA reports back), so this only surfaces the failure.
     */
    fun tapHa(entity: HaState) {
        viewModelScope.launch {
            ha.act(entity)?.let { toasts.send(Toast("${entity.friendlyName} — $it", bad = true)) }
        }
    }

    /**
     * Which message is being spoken, or null.
     *
     * ★ The *only* producer of audio in this app is [play], and the only caller of [play]
     * is a tap on a play control. Nothing observes [HubRepository.arrivals] to speak.
     * That is a requirement, not an implementation detail — see SpeechPolicyTest.
     */
    val speakingEventId: StateFlow<Long?> = speaker.speakingEventId

    /** He pressed play on this message. */
    /**
     * ★ Read this one aloud — all of it.
     *
     * ⚠️ The fetch comes first and is not optional. `repo.expand` is a no-op unless the
     * payload was trimmed, but when it was, speaking without it means Piper reads 4 KiB
     * and stops dead in the middle of a sentence with no indication that it did — the
     * audible version of showing a truncated tail as though it were the whole answer.
     */
    fun play(event: Event) {
        val now = repo.state.value
        val label = now.channel(event.paneId)?.displayLabel.orEmpty()
        // The common case: the whole body is already here, so speech starts on the tap
        // rather than after a round trip. Play has to feel immediate on a worn device.
        if (!now.needsExpansion(event)) {
            speaker.play(event, label, now.bodyOf(event))
            return
        }
        viewModelScope.launch {
            repo.expand(event)
            speaker.play(event, label, repo.state.value.bodyOf(event))
        }
    }

    fun stopSpeaking() = speaker.stop()

    private val toasts = Channel<Toast>(Channel.BUFFERED)
    val messages: Flow<Toast> = toasts.receiveAsFlow()

    /** For failures the UI notices itself — a launcher tile that will not start. */
    fun notify(text: String, bad: Boolean = true) {
        viewModelScope.launch { toasts.send(Toast(text, bad)) }
    }

    /**
     * ★★ **The channel his eyes are on, or null for none** — reported to the hub as
     * presence so it can keep from buzzing him about a screen he is already reading.
     *
     * ⚠️ Null is not "unknown", it is "nothing is covered", and it must reach the hub as
     * eagerly as an open channel does: on the list, anything at all should be able to
     * reach his arm. The UI decides what this is in exactly one place — [Nav.covered].
     */
    fun covering(paneId: String?) {
        repo.openPane = paneId
    }

    fun openThread(paneId: String) {
        viewModelScope.launch {
            if (paneId !in repo.state.value.hydrated) repo.loadHistory(paneId)
            repo.markRead(paneId)
        }
    }

    /** Called again while the thread is open: outcomes land while he is reading. */
    fun markRead(paneId: String) {
        viewModelScope.launch { repo.markRead(paneId) }
    }

    fun refreshThread(paneId: String) {
        viewModelScope.launch { repo.loadHistory(paneId) }
    }

    fun expand(event: Event) {
        viewModelScope.launch { repo.expand(event) }
    }

    // --- typed and canned sends ---------------------------------------------

    private val _draft = MutableStateFlow("")

    /**
     * ★ The composer's words, held here rather than in the composable.
     *
     * ⚠️ Above the screen on purpose, for the same reason the reader's event id is: state
     * inside the composer is disposed by anything that disposes the composer, and a
     * sentence he typed one-handed while walking must survive a recomposition, a rotation
     * and — above all — a send that failed.
     */
    val draft: StateFlow<String> = _draft.asStateFlow()

    private val _outbox = MutableStateFlow<Outbox?>(null)

    /** Non-null while a typed or canned message is with the hub. See [Outbox]. */
    val outbox: StateFlow<Outbox?> = _outbox.asStateFlow()

    fun draft(text: String) {
        _draft.value = text
    }

    /** A canned chip. Its word is its own; the draft is left exactly where it was. */
    fun send(paneId: String, text: String) {
        if (text.isBlank()) return
        launchSend(paneId, text, clearDraft = false)
    }

    /**
     * ★ The composer's Send.
     *
     * ⚠️ The field is cleared **only when the hub has actually taken the words**. It used
     * to clear on tap, so a refused or timed-out send silently deleted a sentence he had
     * just typed and told him about it in a toast that was gone three seconds later.
     */
    fun sendDraft(paneId: String) {
        val text = _draft.value
        if (text.isBlank()) return
        launchSend(paneId, text, clearDraft = true)
    }

    private fun launchSend(paneId: String, text: String, clearDraft: Boolean) {
        // One at a time. A second tap on a send that has not come back yet is a man
        // wondering whether the first one worked, not a request to say it twice.
        if (_outbox.value != null) return
        _outbox.value = Outbox(text, clock())
        viewModelScope.launch {
            try {
                val result = repo.send(paneId, text)
                if (result is SendResult.Ok && clearDraft) _draft.value = ""
                report(result, "sent")
            } finally {
                _outbox.value = null
            }
        }
    }

    // --- Push to talk -------------------------------------------------------

    val pttState: StateFlow<PttState> get() = ptt.state

    /** The mic's input level, kept off [pttState] so it cannot churn the state machine. */
    val pttLevel: StateFlow<Double> get() = ptt.level

    /** Thumb down. [target] is captured here and never re-read; see [PttTarget]. */
    fun pttPress(target: PttTarget) = ptt.press(target)

    /**
     * ⚠️ The one press that does NOT keep what he already said — HOLD TO REDO exists to
     * replace it. See [Ptt.press].
     */
    fun pttRedo(target: PttTarget) = ptt.press(target, append = false)

    fun pttRelease() = ptt.release()

    /**
     * ⚠️ The headset's one gesture. [Ptt.toggle] decides start-or-stop against its own
     * state rather than the panel's snapshot of it — see the note there.
     */
    fun pttToggle(target: PttTarget) = ptt.toggle(target)

    /**
     * ★★ The way out, from any state — including the one in flight to the hub.
     *
     * ⚠️ From [PttState.Sending] this means **stop waiting**, not "unsend": the request is
     * cancelled (which really does cancel the socket, see `HubApi.execute`), but the hub
     * may already have typed it. So the words go back onto the confirm card with
     * [Ptt.STOPPED_WAITING] written on them rather than being thrown away, and he decides
     * whether to say it again. Throwing them away would be the same silent loss this
     * whole confirm step exists to prevent.
     */
    fun pttCancel() {
        if (ptt.state.value is PttState.Sending) {
            pttSendJob?.cancel()
            pttSendJob = null
            ptt.sendFailed(Ptt.STOPPED_WAITING)
            return
        }
        ptt.cancel()
    }

    fun pttDismiss() = ptt.clear()

    /**
     * ★★ The confirmed send — **the only path from a microphone to the hub.**
     *
     * The pane id comes from the confirmation, which took it from the press, so the
     * words and the routing were approved in the same gesture. It posts as the app, so
     * the hub's last-input rule moves the channel to `app` and the outcome comes back
     * here rather than being left in tmux.
     *
     * ⚠️ A refused send returns the transcript to the confirm card instead of a toast.
     * He said it out loud; a dead pane is not a reason to make him say it twice.
     */
    private var pttSendJob: Job? = null

    fun pttConfirm() {
        val confirmed = ptt.confirm() ?: return
        pttSendJob = viewModelScope.launch {
            when (val result = repo.send(confirmed.paneId, confirmed.text)) {
                is SendResult.Ok -> {
                    ptt.sent()
                    toasts.send(Toast("sent", bad = false))
                }

                // ⚠️ If the card is no longer on screen — he stopped waiting, or walked
                // out of the thread — the complaint still has to reach him somewhere.
                // Silently dropping it is how a failed send becomes a message he thinks
                // he sent.
                is SendResult.Failed ->
                    if (!ptt.sendFailed(result.message)) {
                        toasts.send(Toast("not sent — ${result.message}", bad = true))
                    }
            }
        }
    }

    fun interrupt(paneId: String) {
        viewModelScope.launch { report(repo.interrupt(paneId), "interrupt sent") }
    }

    fun kill(paneId: String) {
        viewModelScope.launch { report(repo.kill(paneId), "kill sent") }
    }

    private suspend fun report(result: SendResult, okText: String) {
        when (result) {
            is SendResult.Ok -> toasts.send(Toast(okText, bad = false))
            // ⚠️ A failed send says exactly why. "pane is gone" and "hub unreachable"
            // call for completely different things from a man in a corridor, and a
            // generic "failed" makes him walk to the keyboard to find out which.
            is SendResult.Failed -> toasts.send(Toast("not sent — ${result.message}", bad = true))
        }
    }
}
