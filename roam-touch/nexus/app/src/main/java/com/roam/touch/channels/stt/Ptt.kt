package com.roam.touch.channels.stt

import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.IOException

/**
 * Where a spoken message is going. Captured at the moment the thumb goes down and
 * carried, unchanged, all the way to the send.
 *
 * ★★ This is the point of the whole confirm step. The architecture's rule is that **one
 * confirmation covers the words *and* the routing**, so a good command cannot hit the
 * wrong session. Re-reading "the channel he is looking at" at send time would quietly
 * break that: an outcome landing mid-confirm, or a stray back-press, and the sentence
 * goes somewhere he never chose.
 */
data class PttTarget(val paneId: String, val label: String)

/** What was confirmed, ready to hand to the hub. */
data class PttConfirmed(val paneId: String, val text: String)

/**
 * ★ Every state the wearer can be in, and each one is *shown*.
 *
 * On a device strapped to a forearm there is no other feedback: without a distinct
 * listening/transcribing/failed you cannot tell a dead mic from a slow one, and you
 * stand in a corridor talking to something that stopped listening a minute ago.
 */
sealed interface PttState {

    /** Nothing is happening, and no microphone is open. */
    data object Idle : PttState

    /**
     * The mic is open. This is the only state in which audio is being captured.
     *
     * ⚠️ The input level is deliberately **not** here. It changes eight times a second
     * on a real microphone, and folding it into the state made every consumer of the
     * state machine churn at that rate — while a silent emulator mic conflated the
     * identical values away and hid it. The level is a signal; see [Ptt.level].
     */
    data class Listening(
        val target: PttTarget,
        val startedAtMs: Long,
    ) : PttState

    /** Thumb up, audio sent, waiting on Whisper. */
    data class Transcribing(val target: PttTarget) : PttState

    /** ★ The safety rail: the words and the destination, together, awaiting a decision. */
    data class Confirming(
        val target: PttTarget,
        val transcript: String,
        val error: String? = null,
    ) : PttState

    /** Confirmed and in flight to the hub. */
    data class Sending(val target: PttTarget, val transcript: String) : PttState

    /** It did not work, and it says why. */
    data class Failed(val reason: String) : PttState
}

/**
 * Push to talk.
 *
 * The loop from the architecture, exactly: **pick channel → PTT → Whisper → "send
 * «transcript» to «channel»?" → Send / Redo / Cancel**. Everything that decides anything
 * lives here rather than in the composable, so all of it is testable without a device —
 * which matters, because the device this ships to is worn and cannot be a test rig.
 *
 * ⚠️ **The mic opens in exactly one place: [press].** There is no wake word, no VAD, no
 * timer, no "listen while the thread is open". `MicPolicyTest` pins that.
 */
class Ptt(
    private val recorder: Recorder,
    private val stt: SttClient,
    private val scope: CoroutineScope,
    private val clock: () -> Long = System::currentTimeMillis,
) {

    private val _state = MutableStateFlow<PttState>(PttState.Idle)
    val state: StateFlow<PttState> = _state.asStateFlow()

    private val _level = MutableStateFlow(Pcm.FLOOR_DBFS)

    /**
     * The live input level in dBFS, for the meter — a signal, not part of the state.
     *
     * ⚠️ Kept off [state] on purpose: a real mic updates this ~8 Hz, and anything that
     * recomposes or re-subscribes on a state change must not be dragged along with it.
     */
    val level: StateFlow<Double> = _level.asStateFlow()

    private var work: Job? = null

    /**
     * ⚠️ A confirmation that a new press is *replacing*, held until the replacement
     * actually produces words.
     *
     * Redo is a press-and-hold, and a hold that turns out to be a tap is the commonest
     * fumble there is on a worn screen. Without this, brushing Redo would delete a
     * sentence he already said and leave him with "too short". He gets the old
     * transcript back with the complaint written on it instead.
     */
    private var replacing: PttState.Confirming? = null

    /**
     * Thumb down on the PTT control, while looking at [target].
     *
     * Accepted from idle, from a failure, and from a pending confirmation — the mic
     * button is the mic button, and pressing it means "forget that, listen to this".
     * Ignored while transcribing or sending, where there is already a thumb-up in
     * flight and a second recording would race it.
     */
    fun press(target: PttTarget) {
        when (val current = _state.value) {
            is PttState.Listening, is PttState.Transcribing, is PttState.Sending -> {
                Log.w(TAG, "PRESS ignored, already ${current.javaClass.simpleName}")
                return
            }
            else -> Unit
        }
        Log.i(TAG, "PRESS ${target.paneId}")
        work?.cancel()
        work = null
        replacing = _state.value as? PttState.Confirming
        if (!recorder.start()) {
            fail(NO_MIC)
            return
        }
        val startedAt = clock()
        _level.value = Pcm.FLOOR_DBFS
        _state.value = PttState.Listening(target, startedAt)

        // ⚠️ A thumb that never comes up — a snagged sleeve, a stuck pointer event —
        // must not hold the mic open indefinitely. The cap ends the recording and
        // transcribes it, so a long dictation is kept rather than thrown away.
        work = scope.launch {
            delay(MAX_MS)
            if (isActive && (_state.value as? PttState.Listening)?.startedAtMs == startedAt) {
                Log.i(TAG, "hit the ${MAX_MS} ms cap")
                finish(target)
            }
        }
    }

    /** Thumb up. Ignored unless the mic is actually open. */
    fun release() {
        val listening = _state.value as? PttState.Listening
        if (listening == null) {
            Log.w(TAG, "RELEASE ignored, not listening")
            return
        }
        Log.i(TAG, "RELEASE after ${clock() - listening.startedAtMs} ms held")
        work?.cancel()
        finish(listening.target)
    }

    /** The mic's own level, for the meter. Ignored unless the mic is actually open. */
    fun onLevel(dbfs: Double) {
        if (_state.value is PttState.Listening) _level.value = dbfs
    }

    /**
     * Cancel — from any state, at any time.
     *
     * Throws the audio away, drops the pending transcript and closes the mic. This is
     * the "say nothing after all" button and it must never be more than one press away.
     */
    fun cancel() {
        work?.cancel()
        work = null
        replacing = null
        recorder.discard()
        _state.value = PttState.Idle
    }

    /** Dismiss a failure without starting anything. */
    fun clear() {
        if (_state.value is PttState.Failed) _state.value = PttState.Idle
    }

    /**
     * Send pressed. Returns what to post, and moves to [PttState.Sending].
     *
     * Returns null unless there is something confirmed — a double-tap on Send cannot
     * post the same sentence twice.
     */
    fun confirm(): PttConfirmed? {
        val confirming = _state.value as? PttState.Confirming ?: return null
        replacing = null
        _state.value = PttState.Sending(confirming.target, confirming.transcript)
        return PttConfirmed(confirming.target.paneId, confirming.transcript)
    }

    /** The hub took it. */
    fun sent() {
        if (_state.value is PttState.Sending) _state.value = PttState.Idle
    }

    /**
     * The hub refused it.
     *
     * ⚠️ The transcript comes *back*, it is not lost. He said a sentence out loud; a
     * dead pane or a dropped tailnet is not a reason to make him say it again.
     */
    fun sendFailed(reason: String) {
        val sending = _state.value as? PttState.Sending ?: return
        _state.value = PttState.Confirming(sending.target, sending.transcript, error = reason)
    }

    // -----------------------------------------------------------------------

    private fun finish(target: PttTarget) {
        val heldMs = (clock() - (_state.value as? PttState.Listening)?.startedAtMs.orZero())
            .coerceAtLeast(0)
        val recording = recorder.stop()
        _level.value = Pcm.FLOOR_DBFS

        // ⚠️⚠️ The two gates below exist because of a measured fact, not a hunch:
        // wyoming-faster-whisper returned "Smart home commands." for one second of
        // digital silence (talos:10300, 2026-08-12). It advertises
        // `requires_external_vad: true`; a push-to-talk button IS that VAD, and these
        // are its edges. Without them a fumbled press produces a confident sentence
        // nobody said, one tap away from a live agent.
        if (recording.durationMs < MIN_MS) {
            // ★★ Say which of the two things went wrong.
            //
            // "not held long enough" was a true statement about the audio and a false
            // one about the user: he held it for five seconds and the recorder dropped
            // all but 240 ms of it (Nexus 0.4, sailfish). Blaming the press for a
            // capture fault sent him looking in the wrong place, and it is the single
            // thing that would have made the bug diagnose itself. So the two are now
            // told apart by comparing the press against the audio it produced.
            if (heldMs >= MIN_MS) {
                // ★★ Two different faults wear the same shape here, and telling him the
                // wrong one costs an evening. *Starved and silent* is the phone's audio
                // input failing to start — measured on sailfish 2026-08-12, where the
                // HAL fails `pcm_prepare` for every source, rate and buffer size and
                // returns zero-filled buffers at 3 % of real time. *Starved but audible*
                // is the app's own drain loop losing audio it was actually handed. He
                // can act on the first (it is not his app and not his press); the second
                // is ours to fix.
                if (recording.isDigitalSilence) {
                    Log.e(
                        TAG,
                        "AUDIO INPUT DEAD: a $heldMs ms press produced " +
                                "${recording.durationMs} ms of pure digital silence. " +
                                "The microphone never started; nothing was recorded."
                    )
                    fail(MIC_NOT_DELIVERING)
                    return
                }
                Log.e(
                    TAG,
                    "CAPTURE FAULT: ${recording.durationMs} ms of audio from a " +
                            "$heldMs ms press — the recorder stopped collecting"
                )
                fail(micDropout(recording.durationMs, heldMs))
            } else {
                fail(TOO_SHORT)
            }
            return
        }
        // Long enough to use, but well short of the press: transcribe it — he can read
        // it and redo — but never let it pass unrecorded.
        if (heldMs > MIN_MS && recording.durationMs < heldMs / 2) {
            Log.w(
                TAG,
                "capture short: ${recording.durationMs} ms of audio from a $heldMs ms press"
            )
        }
        if (recording.rmsDbfs < MIN_RMS_DBFS) {
            Log.i(TAG, "rejected at ${"%.1f".format(recording.rmsDbfs)} dBFS")
            fail(TOO_QUIET)
            return
        }

        _state.value = PttState.Transcribing(target)
        work = scope.launch {
            val text = try {
                stt.transcribe(recording)
            } catch (e: IOException) {
                Log.w(TAG, "whisper failed: ${e.message}")
                fail(reasonFor(e))
                return@launch
            }
            if (text.isBlank()) {
                fail(NOTHING_HEARD)
            } else {
                replacing = null
                _state.value = PttState.Confirming(target, text)
            }
        }
    }

    /** Fall back to the confirmation this attempt was replacing, if there was one. */
    private fun fail(reason: String) {
        val back = replacing
        replacing = null
        _state.value = back?.copy(error = reason) ?: PttState.Failed(reason)
    }

    private fun reasonFor(e: IOException): String =
        if (e is SttException) e.message.orEmpty().ifBlank { WHISPER_FAILED }
        else WHISPER_UNREACHABLE

    private fun Long?.orZero(): Long = this ?: 0L

    /** Update [_state] only when it is currently of type [T]. */
    private inline fun <reified T : PttState> MutableStateFlow<PttState>.update(
        transform: (T) -> PttState,
    ) {
        val current = value
        if (current is T) value = transform(current)
    }

    companion object {
        private const val TAG = "RoamStt"

        /** Anything shorter than this is a fumbled press, not a sentence. */
        const val MIN_MS = 350L

        /** A thumb that never comes up still ends, and keeps what it captured. */
        const val MAX_MS = 60_000L

        /**
         * The "was anything actually said" floor. Real speech measures about −20 dBFS
         * RMS, so this is 30 dB of slack — it is here to catch a muted or blocked mic,
         * not to judge how loudly he talks.
         */
        const val MIN_RMS_DBFS = -50.0

        const val NO_MIC = "no microphone — check the mic permission"
        const val TOO_SHORT = "too short — hold the button while you talk"

        /**
         * ★ A long press that produced almost no audio. Names both numbers, because
         * the difference between them *is* the diagnosis.
         */
        fun micDropout(audioMs: Long, heldMs: Long): String =
            "mic dropped out — only ${tenths(audioMs)}s captured from a " +
                    "${tenths(heldMs)}s hold"

        private fun tenths(ms: Long): String = "%.1f".format(ms / 1000.0)

        /**
         * ★★ The press was fine, the app was fine, and the phone's audio input never
         * started.
         *
         * ⚠️ Deliberately does **not** say "mic dropped out" — dropping out implies it
         * was working, which sends him to the app and to the way he pressed it. This is
         * the one failure here he cannot fix by doing anything differently, so it says
         * so, and it points at the layer that is actually broken.
         */
        const val MIC_NOT_DELIVERING =
            "the phone's microphone never started — no audio at all, not your press"
        const val TOO_QUIET = "nothing heard — is the mic covered?"
        const val NOTHING_HEARD = "whisper heard nothing"
        const val WHISPER_UNREACHABLE = "whisper unreachable"
        const val WHISPER_FAILED = "whisper failed"
    }
}
