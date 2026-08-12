package com.roam.touch.channels.stt

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.os.SystemClock
import android.util.Log
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.delay
import kotlinx.coroutines.withTimeoutOrNull

/**
 * ★★ The Bluetooth headset's microphone — **the only working input this device has.**
 *
 * ⚠️⚠️ This is not a fallback and not an accessory path. sailfish's built-in analog
 * capture is dead: the HAL fails `pcm_prepare` for every source, every sample rate and
 * every buffer size and hands back zero-filled buffers at 3 % of real time. A Bluetooth
 * headset carries its own microphone, its own codec and its own link, and it lands in
 * `bt-sco-mic-wb` on the far side of everything that is broken. Measured 2026-08-12:
 * **48640 frames, 0 muted, 0 errors, peak −6.2 dBFS** against **2560/2560 muted, −inf**
 * from the handset in the same four minutes. So the headset is the normal case — see
 * [Ptt.press], which will not open a microphone without one.
 *
 * Behind an interface because the whole PTT state machine has to be testable without a
 * device, and because SCO takes the better part of a second to come up — which is a
 * user-visible state, not an implementation detail.
 */
interface HeadsetLink {

    /**
     * True when an HFP headset is connected to the phone **right now**.
     *
     * This is the paired-and-connected question, not the "is audio flowing" question:
     * it is what decides whether a press can produce anything at all, and it is checked
     * before the mic is opened so a headset-less press gets an honest message instead of
     * a silent recording.
     */
    val connected: Boolean

    /**
     * Bring the SCO audio link up and leave it ready to capture.
     *
     * Suspends until the link is genuinely connected — **not** until the request was
     * accepted. Returns false on timeout or error; the caller must still [close].
     */
    suspend fun open(): Boolean

    /** Tear the link down and hand the audio mode back. Idempotent, safe any time. */
    fun close()
}

/**
 * The real one, over [AudioManager].
 *
 * ⚠️⚠️ **The sequence below is a measured artifact, not a design.** It is the one that
 * was proven to reach `bt-sco-mic-wb` on this handset (`nexus/tools/TESTscoprobe`,
 * 2026-08-12) and it is replicated in order: set the mode, start SCO, **wait for
 * `SCO_AUDIO_STATE_CONNECTED`**, only then route recording to it, settle, and only then
 * open [android.media.AudioRecord] — with
 * [android.media.MediaRecorder.AudioSource.VOICE_RECOGNITION], which is the other half of
 * the trap and lives in [MicRecorder].
 */
class BluetoothHeadsetLink(context: Context) : HeadsetLink {

    private val app = context.applicationContext
    private val audio = app.getSystemService(Context.AUDIO_SERVICE) as AudioManager

    @Volatile
    private var up = false

    /**
     * ⚠️ Asked of the **output** device list, deliberately.
     *
     * A connected HFP headset shows up as a `TYPE_BLUETOOTH_SCO` *output* immediately,
     * but as an *input* only once the SCO link is actually running — the probe recorded
     * exactly that ("no TYPE_BLUETOOTH_SCO input device listed yet (normal before SCO is
     * up)"). Asking the input list here would report "no headset" for every first press.
     */
    override val connected: Boolean
        get() {
            // ⚠️ If this were ever false, PTT would report "no headset" forever and the
            // device would have no working microphone at all — so it is named in the log
            // rather than folded silently into the answer. (Measured true on sailfish:
            // TESTscoprobe brought SCO up off-call.)
            val offCall = audio.isBluetoothScoAvailableOffCall
            val present = audio
                .getDevices(AudioManager.GET_DEVICES_OUTPUTS)
                .any { it.type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO }
            if (!offCall) Log.e(TAG, "isBluetoothScoAvailableOffCall=false — SCO capture is impossible here")
            return offCall && present
        }

    override suspend fun open(): Boolean {
        if (up) {
            Log.i(TAG, "SCO already up")
            return true
        }
        val connectedOrError = CompletableDeferred<Boolean>()
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(context: Context, intent: Intent) {
                when (val state = intent.getIntExtra(AudioManager.EXTRA_SCO_AUDIO_STATE, -1)) {
                    AudioManager.SCO_AUDIO_STATE_CONNECTED -> connectedOrError.complete(true)
                    AudioManager.SCO_AUDIO_STATE_ERROR -> {
                        Log.e(TAG, "SCO_AUDIO_STATE_ERROR")
                        connectedOrError.complete(false)
                    }

                    else -> Log.i(TAG, "SCO_AUDIO_STATE -> $state")
                }
            }
        }
        app.registerReceiver(
            receiver,
            IntentFilter(AudioManager.ACTION_SCO_AUDIO_STATE_UPDATED),
        )
        val startedAt = SystemClock.elapsedRealtime()
        try {
            // ⚠️ Order is load-bearing. MODE_IN_COMMUNICATION first: the routing policy
            // is evaluated when SCO starts, not when the recorder opens.
            audio.mode = AudioManager.MODE_IN_COMMUNICATION
            @Suppress("DEPRECATION")
            audio.startBluetoothSco()
            val ok = withTimeoutOrNull(CONNECT_TIMEOUT_MS) { connectedOrError.await() } ?: false
            if (!ok) {
                Log.e(
                    TAG,
                    "SCO did not connect within $CONNECT_TIMEOUT_MS ms " +
                            "(waited ${SystemClock.elapsedRealtime() - startedAt} ms)"
                )
                return false
            }
            @Suppress("DEPRECATION")
            audio.setBluetoothScoOn(true)
            // ★ From the proven probe, kept verbatim rather than tuned: the framework
            // re-enumerates devices after the link comes up, and the probe's working run
            // waited here before opening AudioRecord. It has not been re-derived, so it
            // is not shortened on a hunch.
            delay(SETTLE_MS)
            up = true
            Log.i(
                TAG,
                "SCO UP in ${SystemClock.elapsedRealtime() - startedAt} ms " +
                        "(incl. ${SETTLE_MS} ms settle), isBluetoothScoOn=" +
                        @Suppress("DEPRECATION") audio.isBluetoothScoOn
            )
            return true
        } finally {
            runCatching { app.unregisterReceiver(receiver) }
        }
    }

    /**
     * ⚠️ Unconditional. A press that was abandoned halfway through [open] has already
     * issued `startBluetoothSco()`, and leaving that standing is a headset stuck in call
     * mode — mono, narrowband, and a live link nobody asked for.
     */
    override fun close() {
        @Suppress("DEPRECATION")
        runCatching { audio.setBluetoothScoOn(false) }
        @Suppress("DEPRECATION")
        runCatching { audio.stopBluetoothSco() }
        runCatching { audio.mode = AudioManager.MODE_NORMAL }
        if (up) Log.i(TAG, "SCO down")
        up = false
    }

    companion object {
        private const val TAG = "RoamStt"

        /**
         * How long a press waits for the link before giving up.
         *
         * ★ Measured setup on the WH-1000XM6 is roughly 600 ms, so this is generous by
         * about 5×. It is deliberately **not** the probe's 12 s: that was a diagnostic
         * budget, and a thumb held for twelve seconds on nothing is worse feedback than
         * a clear failure at four.
         */
        const val CONNECT_TIMEOUT_MS = 4_000L

        /** See [open] — copied from the run that worked, not re-derived. */
        const val SETTLE_MS = 500L
    }
}
