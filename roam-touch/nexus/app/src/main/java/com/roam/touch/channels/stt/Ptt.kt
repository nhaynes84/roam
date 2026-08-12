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

    /** The mic is open. This is the only state in which audio is being captured. */
    data class Listening(
        val target: PttTarget,
        val startedAtMs: Long,
        val levelDbfs: Double = Pcm.FLOOR_DBFS,
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
        when (_state.value) {
            is PttState.Listening, is PttState.Transcribing, is PttState.Sending -> return
            else -> Unit
        }
        work?.cancel()
        work = null
        replacing = _state.value as? PttState.Confirming
        if (!recorder.start()) {
            fail(NO_MIC)
            return
        }
        val startedAt = clock()
        _state.value = PttState.Listening(target, startedAt)
        Log.i(TAG, "listening for ${target.paneId}")

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
        val listening = _state.value as? PttState.Listening ?: return
        work?.cancel()
        finish(listening.target)
    }

    /** The mic's own level, for the meter. Ignored outside [PttState.Listening]. */
    fun onLevel(dbfs: Double) {
        _state.update<PttState.Listening> { it.copy(levelDbfs = dbfs) }
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
        val recording = recorder.stop()

        // ⚠️⚠️ The two gates below exist because of a measured fact, not a hunch:
        // wyoming-faster-whisper returned "Smart home commands." for one second of
        // digital silence (talos:10300, 2026-08-12). It advertises
        // `requires_external_vad: true`; a push-to-talk button IS that VAD, and these
        // are its edges. Without them a fumbled press produces a confident sentence
        // nobody said, one tap away from a live agent.
        if (recording.durationMs < MIN_MS) {
            fail(TOO_SHORT)
            return
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
        const val TOO_QUIET = "nothing heard — is the mic covered?"
        const val NOTHING_HEARD = "whisper heard nothing"
        const val WHISPER_UNREACHABLE = "whisper unreachable"
        const val WHISPER_FAILED = "whisper failed"
    }
}
