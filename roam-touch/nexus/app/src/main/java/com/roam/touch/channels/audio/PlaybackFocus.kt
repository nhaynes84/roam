package com.roam.touch.channels.audio

import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Something that makes music and can be told to stop. The hub's radio page inside the
 * WebView is the one that exists ([WebViewPlayback]); tests use a fake.
 *
 * ⚠️ Deliberately dumb. It has no opinion about *why* it is being turned down — every
 * decision lives in [PlaybackFocus], where a JVM test can reach it, and the surface is the
 * only part that needs a device.
 */
interface PlaybackSurface {

    /**
     * Play, and at [volume] (0..1).
     *
     * ⚠️ Volume is passed on every call rather than kept by the surface: the WebView's
     * media elements are recreated by page navigation, and a surface that remembered a
     * duck would silently apply it to a page that never heard about it.
     */
    fun play(volume: Float)

    /** Stop making sound, keeping position if it can. */
    fun pause()

    /** Keep playing, quieter. */
    fun setVolume(volume: Float)
}

/**
 * What the radio should be doing right now, and why.
 *
 * ★ Everything here is *derived*, never assigned piecemeal — see [PlaybackFocus.derive].
 * The bug this shape rules out is the one every ad-hoc duck/resume has: two independent
 * interruptions overlap, the first one ends, and the music comes back on top of the second.
 */
data class PlaybackState(
    /**
     * He pressed play and has not pressed pause.
     *
     * ★ Survives every interruption. Only the page reporting a stop *he* made clears it —
     * see [RadioBridge.onPause], which is guarded on [playing] for exactly that reason.
     */
    val wanted: Boolean = false,
    /** Whether sound should be coming out at this instant. */
    val playing: Boolean = false,
    /** 1.0 normally, [PlaybackFocus.DUCK_VOLUME] while something is talking over it. */
    val volume: Float = 1f,
    /** Why it is not at full volume, for the UI and the log. */
    val reason: Reason = Reason.NONE,
) {
    enum class Reason {
        /** Nothing is interfering. */
        NONE,

        /** ★ The owner keyed PTT. The one this whole file exists for. */
        PTT,

        /** Piper is talking over it, so it is playing quietly underneath. */
        DUCKED,
    }
}

/**
 * ★★ **The radio's half of the arbitration** — what this app's own microphone and voice do
 * to the music in the page, as play/pause/duck on the surface.
 *
 * Two holds are tracked separately and neither may clear the other:
 *
 * 1. **capture** — [onCaptureStarted] / [onCaptureEnded], called in-process by
 *    [FocusCaptureAudio] when PTT keys the microphone. Direct rather than via the framework
 *    because the music has to be gone *before* SCO comes up ~600 ms later, and because a
 *    round trip through [android.media.AudioManager] is not something a JVM test can wait
 *    for. **Pauses.**
 * 2. **speech** — [onSpeechStarted] / [onSpeechEnded], from [SpeechAudio] when Piper reads
 *    a message he tapped play on. **Ducks**, because that is what an assistant talking over
 *    music is for.
 *
 * ⚠️⚠️ **This holds no audio focus of its own, and must never be given any.** The surface is
 * an `<audio>` element in a WebView, and Chromium is already a media-focus client for it in
 * this same process. A durable `AUDIOFOCUS_GAIN` taken here was revoked by our own page the
 * instant it started playing, and the loss callback — reading exactly as designed, "another
 * app took the audio for good" — paused the stream a heartbeat after starting it. **On the
 * device, no station ever played.** `WebViewOwnsMediaFocusTest` pins it.
 *
 * ★ Everything that made the framework callback worth having still happens, one layer down:
 * a call, an alarm or a maps prompt takes focus from *Chromium*, which suspends the element
 * itself and resumes it when the interruption ends. The two arbiters do not overlap, because
 * they are not arbitrating the same thing — Chromium owns the page against the rest of the
 * phone, and this class owns the page against PTT and Piper, which are inside the process
 * and which Chromium cannot see.
 */
class PlaybackFocus(
    /**
     * The live surface, looked up at call time. Null when no radio page is on screen —
     * the WebView is created and destroyed by navigation, and holding a reference to a
     * dead one is how a paused page never comes back.
     */
    private val surface: () -> PlaybackSurface?,
) {

    private val _state = MutableStateFlow(PlaybackState())
    val state: StateFlow<PlaybackState> = _state.asStateFlow()

    /** PTT has the microphone open. */
    private var capture = false

    /** Piper is reading him a message — see [onSpeechStarted]. */
    private var speech = false

    /**
     * ★ He pressed play on the hub's radio page — reported by the page itself through
     * [RadioBridge.onPlay], because the page is where the button is.
     *
     * ⚠️ It cannot fail, and it does not ask anyone's permission. The music is Chromium's
     * to start and it has already started it; this only records that music is wanted, so
     * that a PTT press knows to put it back afterwards.
     */
    @Synchronized
    fun onPlayRequested() {
        Log.i(TAG, "play")
        apply(derive(wanted = true), force = true)
    }

    /** He pressed pause. Nothing of ours was being held, so there is nothing to give back. */
    @Synchronized
    fun onPauseRequested() {
        Log.i(TAG, "pause")
        apply(derive(wanted = false), force = true)
    }

    /**
     * ★ The page that was playing has gone — he navigated away from the radio.
     *
     * ⚠️ The intent is dropped rather than remembered. The WebView is destroyed with the
     * screen and the element inside it with it, so a later PTT release must not try to
     * resume a page that no longer exists — and the next visit to the radio starts from
     * whatever the page itself restores, not from what we remembered about the last one.
     */
    @Synchronized
    fun onSurfaceGone() {
        if (_state.value.wanted) Log.i(TAG, "radio page left")
        _state.value = derive(wanted = false)
    }

    /**
     * ★ The microphone is opening. Called from [com.roam.touch.channels.stt.Ptt] before
     * the headset link even starts coming up.
     *
     * ⚠️ Pause, never duck. Ducking is for a voice arriving *over* music; this is the
     * owner speaking into the same earbud the music is playing out of, on a link that is
     * about to be switched into mono narrowband call mode. Quiet music in that ear is
     * still music he is talking over.
     *
     * ⚠️⚠️ **Called before the CAPTURE focus request, and the order is load-bearing** — see
     * [FocusCaptureAudio.begin]. `playing` is false the moment this returns, so when the
     * framework hands Chromium the loss for our own `GAIN_TRANSIENT_EXCLUSIVE` and the page
     * reports a pause, [RadioBridge.onPause] sees a radio it already believes is silent and
     * ignores it. Ask for focus first and that same report arrives while we still believe
     * music is coming out, is read as a pause *he* made, and the radio does not come back
     * when he lets go of the button.
     */
    @Synchronized
    fun onCaptureStarted() {
        if (capture) return
        capture = true
        if (_state.value.wanted) Log.i(TAG, "PTT keyed — pausing the radio")
        apply(derive(_state.value.wanted))
    }

    /**
     * The microphone is closed. Resume — unless Piper is still talking, in which case it
     * comes back ducked rather than at full volume.
     *
     * ⚠️ Called *after* the CAPTURE focus is abandoned ([FocusCaptureAudio.end]), so the
     * resume reaches a page whose Chromium is free to take media focus again. Reversed, our
     * `play()` would reach the element while this app still holds
     * `GAIN_TRANSIENT_EXCLUSIVE`, and the page would have to take that focus off us to make
     * a sound — an app fighting itself over an earbud, in the 600 ms after he lets go.
     */
    @Synchronized
    fun onCaptureEnded() {
        if (!capture) return
        capture = false
        apply(derive(_state.value.wanted))
    }

    /**
     * ★ Piper is about to speak a message he tapped play on.
     *
     * ⚠️ Ducks, where [onCaptureStarted] pauses, and the difference is the direction the
     * sound is travelling. Speech comes *out* of the earbud alongside the music and is
     * perfectly intelligible over an attenuated stream; a capture is his own voice going
     * *in*, on a link that is about to become a mono phone call.
     */
    @Synchronized
    fun onSpeechStarted() {
        if (speech) return
        speech = true
        apply(derive(_state.value.wanted))
    }

    /** Piper has finished, been cancelled, or failed. Back up to full. */
    @Synchronized
    fun onSpeechEnded() {
        if (!speech) return
        speech = false
        apply(derive(_state.value.wanted))
    }

    /**
     * The whole policy, in one place: the two holds in, one state out.
     *
     * ⚠️ Capture outranks speech. A message that starts being read while the mic is open
     * must not turn a pause back into quiet music.
     */
    private fun derive(wanted: Boolean): PlaybackState {
        if (!wanted) {
            return PlaybackState(wanted = false, playing = false, volume = 1f, reason = PlaybackState.Reason.NONE)
        }
        if (capture) {
            return PlaybackState(wanted = true, playing = false, volume = 1f, reason = PlaybackState.Reason.PTT)
        }
        if (speech) {
            return PlaybackState(
                wanted = true,
                playing = true,
                volume = DUCK_VOLUME,
                reason = PlaybackState.Reason.DUCKED,
            )
        }
        return PlaybackState(wanted = true, playing = true, volume = 1f)
    }

    /**
     * Publish [next] and tell the surface, but only about what actually changed.
     *
     * ⚠️ The idempotence is load-bearing rather than an optimisation. The same hold is
     * begun and ended from several paths — a PTT press abandoned mid-connect, a Piper socket
     * that times out — and a `pause()` re-issued at an HTML5 media element mid-buffer is a
     * stutter he hears; on this page a re-issued `play()` is worse, because
     * `RoamRadio.play()` re-opens the stream. [force] is for the user's own play/pause,
     * which must reach the page even when the derived state looks identical.
     */
    private fun apply(next: PlaybackState, force: Boolean = false) {
        val previous = _state.value
        _state.value = next
        val target = surface()
        if (target == null) {
            if (next != previous) Log.i(TAG, "no radio page on screen; state only: $next")
            return
        }
        when {
            !next.playing && (previous.playing || force) -> target.pause()
            next.playing && (!previous.playing || force) -> target.play(next.volume)
            next.playing && next.volume != previous.volume -> target.setVolume(next.volume)
        }
    }

    companion object {
        private const val TAG = "RoamAudio"

        /**
         * How far down "quieter" is.
         *
         * ★ 20 %, not 50 %. This is a single earbud under a helmet or a hood, and the
         * point of ducking is that the thing talking over the music is intelligible — at
         * half volume a full-range radio stream still buries a navigation prompt.
         */
        const val DUCK_VOLUME = 0.2f
    }
}
