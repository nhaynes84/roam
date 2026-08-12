package com.roam.touch.channels.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.roam.touch.channels.ChannelsState
import com.roam.touch.channels.HubLink
import com.roam.touch.channels.HubRepository
import com.roam.touch.channels.Roam
import com.roam.touch.channels.SendResult
import com.roam.touch.channels.model.Event
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
) : ViewModel() {

    private val ha: HaRepository by lazy(haProvider)

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
    fun play(event: Event) {
        val label = repo.state.value.channel(event.paneId)?.displayLabel.orEmpty()
        speaker.play(event, label)
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
