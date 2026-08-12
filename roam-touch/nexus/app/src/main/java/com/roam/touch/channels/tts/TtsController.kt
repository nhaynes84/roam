package com.roam.touch.channels.tts

import android.util.Log
import com.roam.touch.channels.model.Event
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * The only way this app makes a sound.
 *
 * One method, and it takes the message he tapped. There is no queue, no policy and no
 * subscription to arriving events — playing a second message replaces the first, because
 * that is what pressing play on a second message means.
 */
interface Speaker {
    /** The event currently being spoken, or null. Drives the play/stop control. */
    val speakingEventId: StateFlow<Long?>

    /**
     * Speak [event]. Explicit user action only — nothing in this app may call this.
     *
     * ⚠️ [body] is the resolved full body, which the caller may have had to fetch: an
     * event that arrived in a bulk payload carries only its first 4 KiB. Defaulted so a
     * caller cannot accidentally fall back to the 280-character summary by omission.
     */
    fun play(event: Event, channelLabel: String, body: String = event.body)

    fun stop()
}

class TtsSpeaker(
    private val tts: WyomingTts,
    private val scope: CoroutineScope,
) : Speaker {

    private val _speakingEventId = MutableStateFlow<Long?>(null)
    override val speakingEventId: StateFlow<Long?> = _speakingEventId.asStateFlow()

    private var job: Job? = null

    override fun play(event: Event, channelLabel: String, body: String) {
        val text = Utterance.of(channelLabel, event, body)
        if (text.isBlank()) return
        // Tapping play on a different message stops the first one mid-sentence. Two
        // voices at once is worse than none, and he pressed the newer button.
        job?.cancel()
        _speakingEventId.value = event.id
        job = scope.launch {
            Log.i(TAG, "play(${event.id}): ${text.take(80)}")
            runCatching { tts.speak(text) }
                .onFailure { Log.w(TAG, "piper failed: ${it.message}") }
            if (_speakingEventId.value == event.id) _speakingEventId.value = null
        }
    }

    override fun stop() {
        job?.cancel()
        job = null
        _speakingEventId.value = null
    }

    companion object {
        private const val TAG = "RoamTts"
    }
}
