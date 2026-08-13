package com.roam.touch.channels

import android.content.Context
import com.roam.touch.BuildConfig
import com.roam.touch.channels.net.HubApi
import com.roam.touch.channels.net.HubConfig
import com.roam.touch.channels.controls.ControlStore
import com.roam.touch.channels.controls.HeadsetControls
import com.roam.touch.channels.net.HubSocket
import com.roam.touch.channels.stt.BluetoothHeadsetLink
import com.roam.touch.channels.stt.MicRecorder
import com.roam.touch.channels.stt.Ptt
import com.roam.touch.channels.stt.PttState
import com.roam.touch.channels.stt.WyomingStt
import com.roam.touch.channels.tts.Speaker
import com.roam.touch.channels.tts.TtsSpeaker
import com.roam.touch.channels.tts.WyomingTts
import com.roam.touch.ha.HaApi
import com.roam.touch.ha.HaConfig
import com.roam.touch.ha.HaEntities
import com.roam.touch.ha.HaRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.plus
import kotlinx.coroutines.Dispatchers

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
    lateinit var speaker: Speaker
        private set

    /**
     * ★ The input half. Voice is the input; the screen reads output and confirms input.
     *
     * ⚠️ Constructed here but **inert** — a [Ptt] holds a closed microphone until
     * something presses it, and the only thing that does is the PTT control.
     */
    lateinit var ptt: Ptt
        private set

    /**
     * ★★ The headset's own buttons, wired to this app.
     *
     * ⚠️ Owned here rather than by the Activity because it must keep working while the
     * panel is backgrounded — the phone is strapped to an arm, and a control surface that
     * only works when he is looking at the screen defeats the point of it.
     */
    lateinit var controls: HeadsetControls
        private set

    /**
     * App #2. Shares nothing with the hub but the process — different server, different
     * token, different failure modes — so it gets its own repository and its own client.
     */
    lateinit var homeAssistant: HaRepository
        private set

    /** Long-lived, process scoped. Cancelled only when the process dies. */
    val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

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

        // The level callback is read back through `ptt` at call time, which is why the
        // recorder can be built before the controller that consumes it.
        ptt = Ptt(
            recorder = MicRecorder(onLevel = { level -> ptt.onLevel(level) }),
            stt = WyomingStt(BuildConfig.STT_HOST, BuildConfig.STT_PORT, BuildConfig.STT_LANG),
            scope = scope,
            // ⚠️ Not an accessory path. This handset's own microphone is dead at the
            // HAL, so the headset link IS the microphone — see HeadsetLink.
            headset = BluetoothHeadsetLink(app),
        )

        // ⚠️ Inert until a gesture he bound arrives: the router passes every unbound key
        // straight back to the system, so this claims nothing it was not given.
        controls = HeadsetControls(app, ControlStore(app), scope).also {
            // ★ So a key arriving mid-recording can be treated as a stop — see
            // HeadsetControls.dispatch. Read off Ptt, never off a UI snapshot.
            it.micOpen = {
                val s = ptt.state.value
                s is PttState.Listening || s is PttState.Connecting
            }
            it.start()
        }

        val haConfig = HaConfig(
            baseUrl = BuildConfig.HA_URL,
            token = BuildConfig.HA_TOKEN,
            pinned = HaEntities.parsePinned(BuildConfig.HA_ENTITIES),
        )
        homeAssistant = HaRepository(HaApi(haConfig), haConfig)
    }

    /** True once [init] has run; guards the UI against a cold-start race. */
    fun isReady(): Boolean = initialised
}
