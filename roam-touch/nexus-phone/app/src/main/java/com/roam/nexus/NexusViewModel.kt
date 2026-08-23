package com.roam.nexus

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.roam.touch.channels.model.Channel
import com.roam.touch.channels.model.Event
import com.roam.touch.channels.net.HubApi
import com.roam.touch.channels.net.HubConfig
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

data class NexusUi(
    val channels: List<Channel> = emptyList(),
    val thread: List<Event> = emptyList(),
    val openPane: String? = null,
    val connected: Boolean = false,
    val error: String? = null,
)

/**
 * The channels half of Nexus on a phone.
 *
 * ⚠️ Polling, not the WebSocket, deliberately for this first cut. `HubSocket` is
 * shared source and works, but a phone that sleeps strands a socket without an error
 * — the Mac client needed a watchdog and reconnect-on-activate to survive exactly
 * that, and a phone sleeps far more aggressively than a laptop. A short poll is
 * honest, survives sleep with no bookkeeping, and can be swapped for the socket once
 * the lifecycle handling is written rather than guessed at.
 */
class NexusViewModel(
    private val api: HubApi,
) : ViewModel() {

    private val _ui = MutableStateFlow(NexusUi())
    val ui: StateFlow<NexusUi> = _ui.asStateFlow()

    init {
        viewModelScope.launch {
            while (isActive) {
                refresh()
                delay(3_000)
            }
        }
    }

    private suspend fun refresh() {
        runCatching { api.channels() }
            .onSuccess { res ->
                _ui.value = _ui.value.copy(
                    channels = res.channels.filter { !it.archived },
                    connected = true,
                    error = null,
                )
            }
            .onFailure { _ui.value = _ui.value.copy(connected = false, error = it.message) }

        val pane = _ui.value.openPane ?: return
        runCatching { api.history(pane, limit = 100) }
            .onSuccess { _ui.value = _ui.value.copy(thread = it.events) }
    }

    fun open(pane: String?) {
        _ui.value = _ui.value.copy(openPane = pane, thread = emptyList())
        if (pane != null) viewModelScope.launch { refresh() }
    }

    fun send(text: String) {
        val pane = _ui.value.openPane ?: return
        viewModelScope.launch {
            runCatching { api.send(pane, text) }
                .onFailure { _ui.value = _ui.value.copy(error = "send failed: ${it.message}") }
            refresh()
        }
    }

    companion object {
        fun config() = HubConfig(
            host = BuildConfig.HUB_HOST,
            port = BuildConfig.HUB_PORT,
            token = BuildConfig.HUB_TOKEN,
        )
    }
}
