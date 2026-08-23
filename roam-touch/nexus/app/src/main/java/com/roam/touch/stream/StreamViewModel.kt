package com.roam.touch.stream

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.roam.touch.channels.net.HubConfig
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.cancel
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.launch as coLaunch
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
    /** ★ Whether the microphone is ACTUALLY delivering, not merely permitted. */
    val capturing: Boolean = false,
    /** ★ Frames off the socket vs frames the speaker actually accepted. One glance
     *  separates "never arrived" from "arrived and went nowhere". */
    val framesIn: Long = 0,
    val framesPlayed: Long = 0,
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

    /**
     * ⚠️⚠️ EVERY audio call runs here, never on the main thread.
     *
     * This caused a real ANR on the wrist: "Input dispatching timed out … wait queue
     * head age 7108ms". Two separate main-thread blockers, both mine —
     * `AudioRecord`'s constructor blocks for seconds when the audio HAL is unwell
     * (which is exactly what the device was doing), and `AudioTrack.write()` in
     * MODE_STREAM BLOCKS whenever the buffer is full, at fifty frames a second.
     *
     * Single-threaded on purpose: audio device setup, teardown and writes must stay
     * in order, and a pool would let a stop overtake a start.
     */
    private val audioThread = java.util.concurrent.Executors
        .newSingleThreadExecutor { r -> Thread(r, "stream-audio") }
    private val audioDispatcher = audioThread.asCoroutineDispatcher()
    private val audioScope = CoroutineScope(SupervisorJob() + audioDispatcher)

    /**
     * ★ DROP_OLDEST, not suspend. If playback cannot keep up, the honest thing for a
     * live channel is to lose the oldest frames and stay current — buffering them
     * makes the room you are listening to drift further and further into the past.
     */
    private val incoming = Channel<ByteArray>(
        capacity = 64, onBufferOverflow = BufferOverflow.DROP_OLDEST
    )

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
        startPlaybackPump()
        socketJob = viewModelScope.launch {
            c.connect(role).collect { event ->
                when (event) {
                    is StreamEvent.FloorChanged -> onFloor(event.floor)
                    is StreamEvent.Audio -> {
                        _ui.value = _ui.value.copy(framesIn = _ui.value.framesIn + 1)
                        incoming.trySend(event.pcm)
                    }
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
        val wantCapture = floor.micLive(device) && _ui.value.micGranted
        val wantPlayback = floor.shouldPlay(device)
        audioScope.coLaunch {
            if (wantPlayback) {
                audio.startPlayback()?.let { why ->
                    _ui.value = _ui.value.copy(notice = "Speaker would not open — $why")
                }
            } else {
                audio.stopPlayback()
            }
            if (wantCapture) startCaptureOnAudioThread() else stopCaptureOnAudioThread()
        }
    }

    private fun startPlaybackPump() {
        audioScope.coLaunch {
            for (frame in incoming) {
                val n = audio.write(frame)
                if (n > 0) _ui.value = _ui.value.copy(framesPlayed = _ui.value.framesPlayed + 1)
            }
        }
    }

    /**
     * ⚠️ Reports failure into the UI. The status line used to say "LIVE — this device
     * is the open mic" purely because the HUB granted the floor, while capture had in
     * fact failed to open — he saw exactly that: "it did say the mic was hot, but that
     * it couldn't find it". For a baby monitor that is the worst possible lie, because
     * he would walk away believing the room was covered.
     */
    private fun startCaptureOnAudioThread() {
        if (captureJob?.isActive == true) return
        // The sender is the monitor; a listener holding PTT is close-talking.
        val monitor = _ui.value.role == Role.SENDER
        if (!audio.startCapture(monitor = monitor)) {
            _ui.value = _ui.value.copy(
                capturing = false,
                notice = "Microphone would not open — this device is NOT sending",
            )
            return
        }
        _ui.value = _ui.value.copy(capturing = true, notice = null)
        captureJob = audioScope.coLaunch {
            val buf = ByteArray(Wire.BYTES_PER_FRAME)
            while (isActive) {
                val n = audio.read(buf)
                if (n <= 0) break
                client?.sendAudio(buf, n)
            }
            _ui.value = _ui.value.copy(capturing = false)
        }
    }

    private fun stopCaptureOnAudioThread() {
        captureJob?.cancel()
        captureJob = null
        audio.stopCapture()
        _ui.value = _ui.value.copy(capturing = false)
    }

    private fun stopEverything() {
        socketJob?.cancel()
        socketJob = null
        client = null
        audioScope.coLaunch {
            stopCaptureOnAudioThread()
            audio.stopPlayback()
        }
    }

    override fun onCleared() {
        socketJob?.cancel()
        audioScope.coLaunch { audio.release() }
        audioScope.cancel()
        audioThread.shutdown()
        super.onCleared()
    }
}
