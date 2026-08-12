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
) : ViewModel() {

    val state: StateFlow<ChannelsState> = repo.state
    val link: StateFlow<HubLink> = repo.link

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
