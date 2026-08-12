package com.roam.touch.channels.tts

import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Serialises speech, because two voices at once is worse than none.
 *
 * The queue is deliberately shallow. If four outcomes land while he is walking, hearing
 * the newest one promptly beats hearing all four in a two-minute monologue — and the
 * ones he skipped are still sitting in their channels with unread badges, which is
 * where he will look anyway.
 */
class TtsSpeaker(
    private val tts: WyomingTts,
    private val scope: CoroutineScope,
    private val depth: Int = MAX_QUEUE,
) {
    private val queue = Channel<String>(capacity = depth, onBufferOverflow =
        kotlinx.coroutines.channels.BufferOverflow.DROP_OLDEST)

    private var pump: Job? = null

    private val _speaking = MutableStateFlow(false)
    val speaking: StateFlow<Boolean> = _speaking.asStateFlow()

    fun start() {
        if (pump?.isActive == true) return
        pump = scope.launch {
            while (isActive) {
                val text = queue.receive()
                _speaking.value = true
                // Verifiable from `adb logcat -s RoamTts` — speech is the one output
                // that leaves no trace on the screen, so it leaves one in the log.
                Log.i(TAG, "speaking: ${text.take(80)}")
                runCatching { tts.speak(text) }
                    .onFailure { Log.w(TAG, "piper failed: ${it.message}") }
                _speaking.value = false
            }
        }
    }

    fun enqueue(text: String) {
        queue.trySend(text)
    }

    /** Drop everything pending. Used the instant he looks at the screen. */
    fun flush() {
        while (queue.tryReceive().isSuccess) { /* drain */ }
    }

    fun stop() {
        pump?.cancel()
        pump = null
        flush()
        _speaking.value = false
    }

    companion object {
        private const val TAG = "RoamTts"
        const val MAX_QUEUE = 3
    }
}
