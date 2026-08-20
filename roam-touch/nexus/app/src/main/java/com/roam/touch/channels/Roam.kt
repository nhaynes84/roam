package com.roam.touch.channels

import android.content.Context
import com.roam.touch.BuildConfig
import com.roam.touch.channels.net.HubApi
import com.roam.touch.channels.net.HubConfig
import com.roam.touch.channels.controls.ControlStore
import com.roam.touch.channels.controls.HeadsetControls
import com.roam.touch.channels.audio.AudioFocusManager
import com.roam.touch.channels.audio.FocusCaptureAudio
import com.roam.touch.channels.audio.PlaybackFocus
import com.roam.touch.channels.audio.PlaybackSurface
import com.roam.touch.channels.audio.SpeechAudio
import com.roam.touch.channels.audio.SystemAudioFocus
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

    /**
     * ★ Where the hub is and how we prove we may talk to it — the one instance, exposed
     * rather than copied.
     *
     * ⚠️ It is read by the shelf's in-app browser, which needs the same bearer token the
     * REST client and the socket already use. Rebuilding a `HubConfig` there from
     * `BuildConfig` would be a second copy of a shared secret and a second place to change
     * the address; both would then be free to drift from this one.
     */
    lateinit var hub: HubConfig
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
     * ★★ **The referee for the one earbud.**
     *
     * Music (the hub's radio, in the WebView) and the microphone (PTT, over the same
     * Bluetooth headset) cannot both have it. This pauses the page for PTT and ducks it for
     * Piper — the two sound sources inside this process, which the framework cannot
     * arbitrate because they are all one app to it.
     *
     * ⚠️ It holds no audio focus of its own. Media focus for the radio belongs to the
     * WebView's Chromium, which already takes it for the page and is what a phone call or a
     * navigation prompt actually interrupts; a second media request from this app revoked
     * its own page. See [PlaybackFocus].
     *
     * ⚠️ Process-scoped, like the socket and for the same reason: playback outlives the
     * Activity, and state tied to a torn-down Activity is a PTT press that resumes nothing.
     *
     * ⚠️ The surface is looked up through [radio], which the browser screen sets while a
     * page is on screen and clears when it leaves. Nothing here holds a WebView.
     */
    lateinit var playback: PlaybackFocus
        private set

    /**
     * The live radio page, or null when none is on screen.
     *
     * ★ A field rather than a constructor argument because the WebView is created and
     * destroyed by navigation, many times, while [playback] is created once.
     */
    @Volatile
    var radio: PlaybackSurface? = null

    /** The system audio-focus service. Exposed so the browser screen can wire a page in. */
    lateinit var audioFocus: AudioFocusManager
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
        hub = config
        val client = HubApi.defaultClient()
        val api = HubApi(config, client)
        repository = HubRepository(api, HubSocket(config, client), settings)
        device = DeviceStateMonitor(app)
        // ★ Built before the two things that make a sound, because it arbitrates between
        // them: the radio in the WebView, PTT's microphone, and Piper's voice all reach
        // the wearer through one Bluetooth earbud.
        audioFocus = SystemAudioFocus(app)
        playback = PlaybackFocus { radio }

        speaker = TtsSpeaker(
            WyomingTts(BuildConfig.TTS_HOST, BuildConfig.TTS_PORT, BuildConfig.TTS_VOICE),
            scope,
            // ⚠️ Ducks the radio rather than pausing it — a spoken message is meant to sit
            // on top of music, and a stream stopped for a sentence re-buffers twice.
            audio = SpeechAudio(audioFocus, playback),
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
            // ★★ The half that makes music and PTT survive each other: a press takes
            // exclusive transient focus (so other apps stop) and pauses our own radio
            // directly (so it is silent before SCO even comes up).
            audio = FocusCaptureAudio(audioFocus, playback),
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
