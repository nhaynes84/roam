package com.roam.touch.channels.audio

import android.util.Log

/**
 * ★★ **What one of this app's own audio users does to everything else that is making a
 * sound**, in two calls and no Android types.
 *
 * Held by [com.roam.touch.channels.stt.Ptt] and by
 * [com.roam.touch.channels.tts.TtsSpeaker], which is what keeps both of those free of
 * `AudioManager` and therefore testable on a JVM — the device this ships to is worn and
 * cannot be a test rig.
 *
 * ⚠️ The contract is an invariant, not a suggestion: **[begin] and [end] bracket the sound
 * exactly.** Every path that ends the sound ends the hold, including the ones where it
 * never started — a press abandoned mid-connect, a Piper socket that times out. A hold
 * left standing is a radio that never plays again until the app is restarted, with nothing
 * on screen to say why.
 */
interface AudioHold {

    /**
     * The sound is about to start — or the link that carries it is coming up.
     *
     * ⚠️ Returns nothing, and a refusal never blocks anything. A phone call holds focus
     * permanently, and the one thing that must not happen on this device is a PTT button
     * that quietly declines to record — this handset has no other input, and "nothing was
     * recorded, no reason given" is precisely the failure the whole PTT design exists to
     * prevent.
     */
    fun begin()

    /** It is over. Idempotent — several paths end the same sound. */
    fun end()

    /** For tests and for the paths that legitimately have no audio system at all. */
    object None : AudioHold {
        override fun begin() = Unit
        override fun end() = Unit
    }
}

/**
 * The real one: takes system focus away from every other app, and tells our own radio
 * directly.
 *
 * ★ Both, deliberately. The framework request is what stops *other* apps — Spotify, a
 * podcast, whatever he had going before he strapped the phone on. The in-process call is
 * what stops *ours*, immediately and synchronously, because the WebView's media element is
 * inside this process and waiting for a focus callback to come back around would leave
 * music playing through the 600 ms of SCO setup and into the first word of his sentence.
 *
 * ⚠️ The framework request does reach our own page as well — Chromium holds media focus for
 * it — but as a suspend that arrives whenever the system gets round to it, and on an element
 * whose stream is still open and buffering. That is not a substitute for the direct call;
 * it is the reason [begin] and [end] are ordered the way they are.
 */
class FocusCaptureAudio(
    private val focus: AudioFocusManager,
    private val playback: PlaybackFocus?,
) : AudioHold {

    /** ⚠️ Guards against a double release; [end] is called from several paths. */
    private var held = false

    @Synchronized
    override fun begin() {
        // ★★ Our own radio first, and this ordering is a rule rather than a preference.
        //
        // The request below takes GAIN_TRANSIENT_EXCLUSIVE, which the framework delivers to
        // the WebView's own Chromium — a media-focus client in this same process — and
        // Chromium suspends the page's <audio> element for it. The page reports that pause
        // back through `RadioBridge.onPause`, where the only thing separating our
        // interruption from one he made with his thumb is that we already believe the radio
        // is silent. Calling this first is what makes that true. See
        // [PlaybackFocus.onCaptureStarted].
        playback?.onCaptureStarted()
        if (held) return
        held = true
        if (!focus.request(FocusKind.CAPTURE) { change -> onChange(change) }) {
            // ⚠️ Logged and ignored. See [AudioHold.begin]: a denied focus request is
            // not a reason to refuse a press on the only microphone this phone has.
            Log.w(TAG, "capture focus denied — recording anyway")
        }
    }

    /**
     * ⚠️⚠️ **The mirror image of [begin]: focus goes back first, our radio second.** The
     * resume reaches the page as `RoamRadio.play()`, which re-opens the stream and makes
     * Chromium ask the framework for media focus — and it must not have to take that focus
     * off this app's own still-standing exclusive capture request to get it. Chromium may
     * also resume the element by itself when the abandon reaches it; on today's `radio.html`
     * it cannot, because our pause dropped the element's `src` outright, and a page that
     * does resume itself is asked to play something that is already playing. Either way
     * exactly one stream comes back.
     */
    @Synchronized
    override fun end() {
        if (held) {
            held = false
            focus.abandon(FocusKind.CAPTURE)
        }
        playback?.onCaptureEnded()
    }

    /**
     * We lost the focus we took for the recording — a call arrived mid-sentence.
     *
     * ⚠️ It does **not** stop the recording. Stopping the microphone is
     * [com.roam.touch.channels.stt.Ptt]'s decision and it has its own stop signals (the
     * thumb, the earbud hang-up, the 60 s cap); a second, invisible one that fires on a
     * notification would be a sentence that ends without him knowing why.
     */
    private fun onChange(change: FocusChange) {
        if (change != FocusChange.GAINED) Log.w(TAG, "capture focus lost mid-press: $change")
    }

    companion object {
        private const val TAG = "RoamAudio"
    }
}

/**
 * ★ Piper reading him a message — **ducks the music, does not stop it.**
 *
 * This is the "where appropriate" half of the ducking rule. The device speaking over the
 * radio is the normal case for an assistant; stopping a stream for a ten-second sentence
 * costs a re-buffer at each end and, on a tailnet radio, a gap he hears twice.
 *
 * ⚠️ Both halves again, and for the same reasons as [FocusCaptureAudio]: the framework
 * request is what leans on other apps, and the direct call is what turns *our* radio down
 * now rather than whenever a callback comes back around. `WyomingTts` builds its
 * `AudioTrack` with USAGE_ASSISTANT already — this is what makes that declaration mean
 * something instead of being a comment.
 */
class SpeechAudio(
    private val focus: AudioFocusManager,
    private val playback: PlaybackFocus?,
) : AudioHold {

    private var held = false

    @Synchronized
    override fun begin() {
        playback?.onSpeechStarted()
        if (held) return
        held = true
        if (!focus.request(FocusKind.SPEECH) { }) {
            // ⚠️ Ignored, like the capture one. He tapped play on a specific message and
            // the answer to "something else has the audio" is not silence with no reason.
            Log.w(TAG, "speech focus denied — speaking anyway")
        }
    }

    @Synchronized
    override fun end() {
        if (held) {
            held = false
            focus.abandon(FocusKind.SPEECH)
        }
        playback?.onSpeechEnded()
    }

    private companion object {
        private const val TAG = "RoamAudio"
    }
}
