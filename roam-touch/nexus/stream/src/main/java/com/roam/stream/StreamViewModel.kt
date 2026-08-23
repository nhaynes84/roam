package com.roam.stream

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.roam.touch.channels.net.HubConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

data class StreamUi(
    val role: Role = Role.OFF,
    val floor: Floor? = null,
    val connected: Boolean = false,
    val micGranted: Boolean = false,
    val notice: String? = null,
) {
    val channelOpen: Boolean get() = floor?.open == true
    val talkingNow: String? get() = floor?.talker
}

/**
 * Ties the socket, the floor and the audio together.
 *
 * ★★ THE HUB IS THE AUTHORITY. His framing: *"same as a multiplayer hosting server for
 * any video game, the server makes core timing decisions, not any individual device."*
 * So nothing here turns the microphone on because a button was pressed. Pressing sends
 * `press`; the mic follows [Floor.micLive] when the hub says so. The round trip is a
 * few milliseconds on a tailnet and it is what stops two devices ever being live at
 * once — which is the one failure that actually hurts, because it howls.
 */
class StreamViewModel(
    private val config: HubConfig,
    private val device: String,
    private val audio: StreamAudio = StreamAudio(),
) : ViewModel() {

    private val _ui = MutableStateFlow(StreamUi())
    val ui: StateFlow<StreamUi> = _ui.asStateFlow()

    private var client: IntercomClient? = null
    private var socketJob: Job? = null
    private var captureJob: Job? = null

    fun onMicPermission(granted: Boolean) {
        _ui.value = _ui.value.copy(
            micGranted = granted,
            notice = if (granted) null else "Stream needs the microphone to send or talk back",
        )
    }

    /** OFF tears everything down. That is also the launch default — see MainActivity. */
    fun setRole(role: Role) {
        if (_ui.value.role == role) return
        stopEverything()
        _ui.value = _ui.value.copy(role = role, floor = null, connected = false, notice = null)
        if (role == Role.OFF) return

        val c = IntercomClient(config, device)
        client = c
        socketJob = viewModelScope.launch {
            c.connect(role).collect { event ->
                when (event) {
                    is StreamEvent.FloorChanged -> onFloor(event.floor)
                    is StreamEvent.Audio -> audio.write(event.pcm)
                    is StreamEvent.Denied ->
                        _ui.value = _ui.value.copy(notice = event.detail)
                    is StreamEvent.Failed ->
                        _ui.value = _ui.value.copy(connected = false, notice = event.reason)
                }
            }
        }
    }

    fun press() {
        if (!_ui.value.micGranted) {
            _ui.value = _ui.value.copy(notice = "Microphone permission is needed to talk")
            return
        }
        client?.press()
    }

    fun release() { client?.release() }

    /**
     * ⚠️ Playback and capture are driven ENTIRELY by what the hub last said, never by
     * which button is down. A press that the hub refused (someone else got there
     * first) must not open this microphone, and the only way to guarantee that is to
     * let the answer decide.
     */
    private fun onFloor(floor: Floor) {
        _ui.value = _ui.value.copy(floor = floor, connected = true)

        if (floor.shouldPlay(device)) audio.startPlayback() else audio.stopPlayback()

        val shouldCapture = floor.micLive(device) && _ui.value.micGranted
        if (shouldCapture) startCapture() else stopCapture()
    }

    private fun startCapture() {
        if (captureJob?.isActive == true) return
        if (!audio.startCapture()) {
            _ui.value = _ui.value.copy(notice = "Could not open the microphone")
            return
        }
        captureJob = viewModelScope.launch(Dispatchers.IO) {
            val buf = ByteArray(Wire.BYTES_PER_FRAME)
            while (isActive) {
                val n = audio.read(buf)
                if (n <= 0) break
                client?.sendAudio(buf, n)
            }
        }
    }

    private fun stopCapture() {
        captureJob?.cancel()
        captureJob = null
        audio.stopCapture()
    }

    private fun stopEverything() {
        stopCapture()
        audio.stopPlayback()
        socketJob?.cancel()
        socketJob = null
        client = null
    }

    override fun onCleared() {
        stopEverything()
        audio.release()
        super.onCleared()
    }
}
