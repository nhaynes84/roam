package com.roam.touch.channels.controls

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothHeadset
import android.bluetooth.BluetoothProfile
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.session.MediaSession
import android.media.session.PlaybackState
import android.util.Log
import android.view.KeyEvent
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** What a bound gesture actually does. Implemented by the UI, which owns navigation. */
interface ControlSurface {

    /**
     * ⚠️ A **toggle** — a headset tap has no press-and-hold. Start listening, tap again
     * to stop and transcribe. See [ControlAction.PUSH_TO_TALK].
     */
    fun pushToTalkToggle()

    fun nextChannel()
    fun previousChannel()
    fun cancel()
}

/**
 * ★★ The headset's buttons, wired to this app.
 *
 * ⚠️⚠️ **Discovery, not assumption.** Every key event that arrives is logged in full —
 * code, edge, repeat count, and the input device that sent it — under `RoamKeys`, because
 * the gesture set is a property of the headset and the only reliable way to learn it is to
 * watch what turns up:
 *
 *     adb logcat -s RoamKeys
 *
 * That log is also what feeds [seen], which the bindings screen shows him directly. It
 * exists so a headset neither of us has thought about can still be mapped.
 *
 * ⚠️ **Nothing is swallowed unless he bound it.** [ControlRouter] returns
 * [ControlDecision.PassThrough] for every unbound key, and this class then returns false
 * from `onMediaButtonEvent` so the system handles it exactly as it would have. Volume is
 * only ever intercepted while a volume gesture is bound for the connected headset.
 */
class HeadsetControls(
    context: Context,
    private val store: ControlBindingStore,
    private val scope: CoroutineScope,
) {

    private val app = context.applicationContext
    private val router = ControlRouter()

    @Volatile
    var surface: ControlSurface? = null

    private val _active = MutableStateFlow<HeadsetProfile?>(null)

    /** The connected headset and its bindings, or null when nothing is connected. */
    val active: StateFlow<HeadsetProfile?> = _active.asStateFlow()

    private val _intro = MutableStateFlow<HeadsetProfile?>(null)

    /**
     * ★ An unfamiliar headset has just connected and has never been set up.
     *
     * ⚠️ A prompt, never a gate. The owner's rule: *"we just map it on first connect"* —
     * and if he waves it away the headset still works as a microphone, PTT just stays on
     * the on-screen button. Nothing waits on this.
     */
    val intro: StateFlow<HeadsetProfile?> = _intro.asStateFlow()

    private val _learned = MutableSharedFlow<HeadsetGesture>(extraBufferCapacity = 4)

    /** Emits the gesture captured by [learnNext]. */
    val learned: SharedFlow<HeadsetGesture> = _learned.asSharedFlow()

    private val _seen = MutableStateFlow<List<String>>(emptyList())

    /** The last few raw key events, in plain words. Discovery, shown on the screen. */
    val seen: StateFlow<List<String>> = _seen.asStateFlow()

    val isLearning: Boolean get() = router.isLearning

    private var session: MediaSession? = null

    // ------------------------------------------------------------------ life

    fun start() {
        if (session != null) return
        session = MediaSession(app, "RoamHeadset").apply {
            @Suppress("DEPRECATION")
            setFlags(MediaSession.FLAG_HANDLES_MEDIA_BUTTONS)
            setCallback(object : MediaSession.Callback() {
                override fun onMediaButtonEvent(intent: Intent): Boolean =
                    handle(intent) || super.onMediaButtonEvent(intent)
            })
            // ⚠️⚠️ Load-bearing, and the least obvious line here. Media buttons go to the
            // most recently *active, playing* session; a session that never claims to be
            // playing loses every key to whatever last played music. Nothing is actually
            // played — this app produces no media — it is purely how Android decides who
            // owns the buttons.
            setPlaybackState(
                PlaybackState.Builder()
                    .setActions(
                        PlaybackState.ACTION_PLAY_PAUSE or PlaybackState.ACTION_PLAY or
                                PlaybackState.ACTION_PAUSE or
                                PlaybackState.ACTION_SKIP_TO_NEXT or
                                PlaybackState.ACTION_SKIP_TO_PREVIOUS or
                                PlaybackState.ACTION_STOP
                    )
                    .setState(PlaybackState.STATE_PLAYING, 0L, 1f)
                    .build()
            )
            isActive = true
        }
        app.registerReceiver(
            connectionReceiver,
            IntentFilter(BluetoothHeadset.ACTION_CONNECTION_STATE_CHANGED),
        )
        refreshConnected()
        Log.i(TAG, "media session up — headset keys will be logged here")
    }

    fun stop() {
        runCatching { app.unregisterReceiver(connectionReceiver) }
        session?.run {
            isActive = false
            release()
        }
        session = null
    }

    // --------------------------------------------------------------- the keys

    private fun handle(intent: Intent): Boolean {
        val event: KeyEvent = intent.getParcelableExtra(Intent.EXTRA_KEY_EVENT) ?: return false
        return dispatch(event)
    }

    /** Visible for the volume path and for instrumentation; the routing is all in here. */
    fun dispatch(event: KeyEvent): Boolean {
        val name = KeyEvent.keyCodeToString(event.keyCode)
        val edge = if (event.action == KeyEvent.ACTION_DOWN) "DOWN" else "UP"
        val line = "$name $edge repeat=${event.repeatCount} " +
                "flags=0x${Integer.toHexString(event.flags)} " +
                "source=${event.device?.name ?: "?"}"
        // ⚠️ Logged before anything is decided, so a gesture that is not bound — and
        // therefore does nothing — still leaves the evidence needed to bind it.
        Log.i(TAG, line)
        _seen.value = (listOf(line) + _seen.value).take(SEEN_LIMIT)

        val record = KeyRecord(
            keyCode = event.keyCode,
            down = event.action == KeyEvent.ACTION_DOWN,
            repeat = event.repeatCount,
        )
        return when (val decision = router.onKey(record)) {
            is ControlDecision.PassThrough -> false
            is ControlDecision.Consumed -> true
            is ControlDecision.Learned -> {
                Log.i(TAG, "LEARNED ${decision.gesture.label} (${decision.gesture})")
                _learned.tryEmit(decision.gesture)
                true
            }

            is ControlDecision.Perform -> {
                Log.i(TAG, "PERFORM ${decision.action}")
                perform(decision.action)
                true
            }
        }
    }

    private fun perform(action: ControlAction) {
        val target = surface
        if (target == null) {
            Log.w(TAG, "no control surface attached — $action dropped")
            return
        }
        when (action) {
            ControlAction.PUSH_TO_TALK -> target.pushToTalkToggle()
            ControlAction.NEXT_CHANNEL -> target.nextChannel()
            ControlAction.PREVIOUS_CHANNEL -> target.previousChannel()
            ControlAction.CANCEL -> target.cancel()
        }
    }

    // ----------------------------------------------------------- learn / edit

    /** Capture the next gesture instead of acting on it. */
    fun learnNext() = router.startLearning()

    fun cancelLearning() = router.stopLearning()

    fun bind(gesture: HeadsetGesture, action: ControlAction) =
        update { it.bind(gesture, action).copy(introduced = true) }

    /** ⚠️ Give the gesture back to the headset and the system. */
    fun unbind(gesture: HeadsetGesture) = update { it.unbind(gesture) }

    /** He waved the first-connect prompt away. The headset still works as a microphone. */
    fun dismissIntro() {
        _intro.value = null
        update { it.copy(introduced = true) }
    }

    private fun update(change: (HeadsetProfile) -> HeadsetProfile) {
        val current = _active.value ?: return
        val next = change(current)
        _active.value = next
        router.profile = next
        applyVolumeCapture(next)
        scope.launch { store.save(next) }
    }

    // ------------------------------------------------------ which headset

    private val connectionReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            refreshConnected()
        }
    }

    @SuppressLint("MissingPermission") // BLUETOOTH is a normal permission; declared.
    fun refreshConnected() {
        val adapter = BluetoothAdapter.getDefaultAdapter()
        if (adapter == null || !adapter.isEnabled) {
            clearActive()
            return
        }
        adapter.getProfileProxy(app, object : BluetoothProfile.ServiceListener {
            override fun onServiceConnected(profile: Int, proxy: BluetoothProfile) {
                val device: BluetoothDevice? = proxy.connectedDevices.firstOrNull()
                adapter.closeProfileProxy(profile, proxy)
                if (device == null) {
                    clearActive()
                    return
                }
                scope.launch { adopt(device.address, device.name ?: device.address) }
            }

            override fun onServiceDisconnected(profile: Int) = clearActive()
        }, BluetoothProfile.HEADSET)
    }

    private fun clearActive() {
        _active.value = null
        _intro.value = null
        router.profile = null
    }

    private suspend fun adopt(address: String, name: String) {
        val known = store.profiles()[address]
        val profile = known ?: HeadsetProfile.forNewHeadset(address, name)
        _active.value = profile
        router.profile = profile
        applyVolumeCapture(profile)
        // ★ A known headset connecting is silent. An unknown one asks, once, and never
        // again — whether or not he answers.
        _intro.value = if (profile.introduced) null else profile
        if (known == null) store.save(profile)
        Log.i(TAG, "headset $name ($address) — ${profile.bindings.size} bindings, " +
                "introduced=${profile.introduced}")
    }

    /**
     * ⚠️⚠️ Volume is taken from the system **only** while he has a volume gesture bound.
     *
     * A `VolumeProvider` is the one way a media session sees volume keys, and it works by
     * declaring that this session's playback is remote — which means the volume rocker and
     * a headset's volume gesture stop adjusting the stream for as long as it is armed.
     * That is exactly the "swallowing volume globally" failure to avoid, so it is armed
     * from a binding he made and disarmed the moment he unbinds it.
     */
    private fun applyVolumeCapture(profile: HeadsetProfile) {
        val session = session ?: return
        if (!profile.capturesVolume) {
            session.setPlaybackToLocal(android.media.AudioAttributes.Builder().build())
            return
        }
        session.setPlaybackToRemote(object : android.media.VolumeProvider(
            VOLUME_CONTROL_RELATIVE, 100, 50,
        ) {
            override fun onAdjustVolume(direction: Int) {
                val code = when {
                    direction > 0 -> KeyEvent.KEYCODE_VOLUME_UP
                    direction < 0 -> KeyEvent.KEYCODE_VOLUME_DOWN
                    else -> return
                }
                // A volume gesture has no separate up edge; synthesise both so the
                // router sees the same shape it sees for every other key.
                dispatch(KeyEvent(KeyEvent.ACTION_DOWN, code))
                dispatch(KeyEvent(KeyEvent.ACTION_UP, code))
            }
        })
    }

    private companion object {
        const val TAG = "RoamKeys"
        const val SEEN_LIMIT = 12
    }
}
