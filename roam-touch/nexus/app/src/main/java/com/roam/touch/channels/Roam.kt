package com.roam.touch.channels

import android.content.Context
import com.roam.touch.BuildConfig
import com.roam.touch.channels.net.HubApi
import com.roam.touch.channels.net.HubConfig
import com.roam.touch.channels.net.HubSocket
import com.roam.touch.channels.tts.TtsMode
import com.roam.touch.channels.tts.TtsSpeaker
import com.roam.touch.channels.tts.WyomingTts
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.plus
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * The object graph, wired once per process.
 *
 * A singleton rather than a DI framework because there is exactly one hub, one socket
 * and one voice on this device, and the connection has to outlive the Activity: the
 * launcher gets torn down and rebuilt constantly, and the socket must not go with it.
 */
object Roam {
    lateinit var settings: Settings
        private set
    lateinit var repository: HubRepository
        private set
    lateinit var device: DeviceStateMonitor
        private set
    lateinit var speaker: TtsSpeaker
        private set

    /** Long-lived, process scoped. Cancelled only when the process dies. */
    val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    private val _ttsMode = MutableStateFlow(TtsMode.AUTO)
    val ttsMode: StateFlow<TtsMode> get() = _ttsMode

    @Volatile
    private var initialised = false

    fun init(context: Context) {
        if (initialised) return
        initialised = true

        val app = context.applicationContext
        settings = Settings(app)

        val config = HubConfig(
            host = BuildConfig.HUB_HOST,
            port = BuildConfig.HUB_PORT,
            token = BuildConfig.HUB_TOKEN,
        )
        val client = HubApi.defaultClient()
        val api = HubApi(config, client)
        repository = HubRepository(api, HubSocket(config, client), settings)
        device = DeviceStateMonitor(app)
        speaker = TtsSpeaker(
            WyomingTts(BuildConfig.TTS_HOST, BuildConfig.TTS_PORT, BuildConfig.TTS_VOICE),
            scope,
        )

        scope.launch {
            settings.ttsMode.collect { _ttsMode.value = it }
        }
    }

    fun cycleTtsMode() {
        val next = _ttsMode.value.next()
        _ttsMode.value = next
        if (next == TtsMode.MUTED) speaker.flush()
        scope.launch { settings.setTtsMode(next) }
    }

    /** True once [init] has run; guards the UI against a cold-start race. */
    fun isReady(): Boolean = initialised
}
