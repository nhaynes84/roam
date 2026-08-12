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
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.launch

/** A one-shot message for the wearer: what just happened to something he did. */
data class Toast(val text: String, val bad: Boolean)

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

    fun send(paneId: String, text: String) {
        if (text.isBlank()) return
        viewModelScope.launch { report(repo.send(paneId, text), "sent") }
    }

    // --- Push to talk -------------------------------------------------------

    val pttState: StateFlow<PttState> get() = ptt.state

    /** The mic's input level, kept off [pttState] so it cannot churn the state machine. */
    val pttLevel: StateFlow<Double> get() = ptt.level

    /** Thumb down. [target] is captured here and never re-read; see [PttTarget]. */
    fun pttPress(target: PttTarget) = ptt.press(target)

    fun pttRelease() = ptt.release()

    fun pttCancel() = ptt.cancel()

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
    fun pttConfirm() {
        val confirmed = ptt.confirm() ?: return
        viewModelScope.launch {
            when (val result = repo.send(confirmed.paneId, confirmed.text)) {
                is SendResult.Ok -> {
                    ptt.sent()
                    toasts.send(Toast("sent", bad = false))
                }

                is SendResult.Failed -> ptt.sendFailed(result.message)
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
