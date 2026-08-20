package com.roam.touch.channels.audio

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.os.Handler
import android.os.Looper
import android.util.Log

/**
 * ★★ **One earbud, two things that want it.**
 *
 * The owner wears this phone on a forearm and hears it through a single Bluetooth headset.
 * That headset carries the *only* working microphone this handset has (see
 * [com.roam.touch.channels.stt.HeadsetLink]) **and** it is where the hub's radio comes out.
 * Without an arbiter he keys the mic and talks over his own music, every time — and the
 * music is still playing in his ear while he is trying to hear whether the app said
 * LISTENING.
 *
 * Audio focus is the Android mechanism for exactly this, and it is used here for its real
 * purpose rather than as a formality: it is how *this app's own microphone and voice* tell
 * every other app on the phone — including the WebView's Chromium — to get out of the way.
 * Our own radio is handled in-process as well ([PlaybackFocus]) because a direct call is
 * immediate and testable, where a round trip through the framework is neither.
 *
 * ⚠️⚠️ **There is no request here for the music, and that is the point.** The radio is an
 * `<audio>` element in a WebView, and Chromium requests media focus for it itself, from
 * inside this process, the moment it starts. A durable `AUDIOFOCUS_GAIN` revokes every other
 * holder and the framework has no notion of two clients in one process cooperating — so the
 * app's own media request was revoked by its own page half a second after it was made, the
 * loss callback concluded that another app had started something, and the radio was stopped
 * by the very code that had just started it. See `WebViewOwnsMediaFocusTest`. Media focus
 * for the page belongs to the page; what is left here is [FocusKind.CAPTURE] and
 * [FocusKind.SPEECH], which are ours and have no other owner.
 */

/**
 * What happened to focus we were holding, in our own words.
 *
 * ⚠️ Deliberately not `Int` constants from [AudioManager]. The framework hands out five
 * values with overlapping meanings and two of them are negative; a small closed set is
 * what the playback state machine actually reasons about, and it is what a JVM test can
 * hand it without an Android runtime.
 */
enum class FocusChange {

    /** We have it (again). Whatever we suspended for it may come back. */
    GAINED,

    /**
     * Gone for good — another app took it and is not giving it back on its own.
     *
     * ⚠️ **Never auto-resumes.** A permanent loss is another app *starting* something; if
     * the radio came back by itself when that finished, the phone on his arm would begin
     * playing music in the middle of a conversation he had walked into.
     */
    LOST,

    /** Gone for a moment — a call, a prompt, our own PTT. Resume on [GAINED]. */
    LOST_TRANSIENT,

    /**
     * Gone for a moment, but we may keep playing quietly underneath.
     *
     * ⚠️ On API 26+ the framework may duck us itself instead of delivering this, depending
     * on the requester's attributes. Handled anyway: if it arrives we attenuate, and if it
     * never does the framework's own attenuation gets the same outcome. Both ends are
     * "quieter, still playing", which is the only thing the caller cares about.
     */
    LOST_TRANSIENT_CAN_DUCK,
}

/**
 * Which of the two roles is asking, which decides *how* it asks.
 *
 * ★ The distinction is not cosmetic. A capture request has to stop other audio outright
 * ([AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_EXCLUSIVE], the value Android documents for
 * speech recognition); a spoken message is meant to sit on top of whatever is playing.
 *
 * ⚠️⚠️ **Both are transient, and there is deliberately no media/playback kind.** Every
 * request this app makes is a borrow that is given back — the durable
 * [AudioManager.AUDIOFOCUS_GAIN] that a media app takes for its stream is taken by Chromium
 * for the hub's radio page, in this same process, and a second one from us only revokes
 * itself. Adding a `PLAYBACK` back here is the bug this file was fixed for; see the header.
 */
enum class FocusKind {

    /** PTT has the microphone open. Everything else stops. */
    CAPTURE,

    /**
     * ★ Piper reading him a message. **Ducks rather than stops**, and that is the
     * "where appropriate" in the ducking rule.
     *
     * ⚠️ Different from [CAPTURE] on purpose. A capture is his own voice going *into* the
     * same earbud the music comes out of, over a link that is about to be switched into
     * mono call mode — nothing else may be playing. Speech is the device talking *over*
     * music, which is exactly what ducking is for, and pausing a stream for a
     * ten-second sentence costs a re-buffer at both ends.
     */
    SPEECH,
}

/**
 * The audio-focus service, behind an interface so every decision above it is testable on a
 * JVM. [SystemAudioFocus] is the real one; tests use a fake that records requests.
 */
interface AudioFocusManager {

    /**
     * Ask for focus of [kind]. [onChange] is called for every later change to *that*
     * request, until it is abandoned.
     *
     * @return true if focus was granted. A denial is not fatal for [FocusKind.CAPTURE] —
     *   see [FocusCaptureAudio].
     */
    fun request(kind: FocusKind, onChange: (FocusChange) -> Unit): Boolean

    /** Give it back. Idempotent: abandoning what we do not hold is a no-op, not an error. */
    fun abandon(kind: FocusKind)

    /** True while we hold focus of [kind]. For tests and for logging, not for policy. */
    fun holds(kind: FocusKind): Boolean
}

/** The real one, over [AudioManager]. minSdk is 26, so there is no legacy branch. */
class SystemAudioFocus(context: Context) : AudioFocusManager {

    private val audio =
        context.applicationContext.getSystemService(Context.AUDIO_SERVICE) as AudioManager

    /** One live [AudioFocusRequest] per role, so the two never abandon each other's. */
    private val live = mutableMapOf<FocusKind, AudioFocusRequest>()

    /**
     * ★★ Where focus callbacks land — chosen, not inherited. See [request].
     *
     * ⚠️ An instance field rather than a companion constant on purpose: constructing a
     * [Handler] is class-initialisation work, and the pure `translate` below is read by a
     * plain JVM test that must not need a Looper to exist.
     */
    private val callbacks = Handler(Looper.getMainLooper())

    @Synchronized
    override fun request(kind: FocusKind, onChange: (FocusChange) -> Unit): Boolean {
        // ⚠️ Re-requesting while we already hold it would leave the old request object
        // behind, and abandoning the new one would not release the old — an app that
        // silently pins the audio for every other app on the device.
        live[kind]?.let { audio.abandonAudioFocusRequest(it) }

        val req = AudioFocusRequest.Builder(gainFor(kind))
            .setAudioAttributes(attributesFor(kind))
            // ★ False on purpose. Neither of these requests owns a stream that would need
            // pausing, and asking the framework for a *pause* on every notification chime —
            // on a worn device — turns a two-second beep into a recording that stops.
            .setWillPauseWhenDucked(false)
            // ⚠️⚠️ **The Handler is not optional here.** Without one, AudioManager delivers
            // every later focus callback on whichever thread made the *request*, and this
            // method is called from several: the main thread (PTT from the panel) and
            // `Dispatchers.Default` (the Ptt and TTS coroutines) at least. A callback pinned
            // to a caller's thread is a callback that blocks whatever that thread was for —
            // and on this device the audio HAL does stall. One thread, always the same one,
            // and it is the one every other Android media app uses.
            .setOnAudioFocusChangeListener(
                { change -> onChange(translate(change)) },
                callbacks,
            )
            .build()
        live[kind] = req
        val granted = audio.requestAudioFocus(req) == AudioManager.AUDIOFOCUS_REQUEST_GRANTED
        if (!granted) {
            Log.w(TAG, "$kind focus DENIED")
            live.remove(kind)
        }
        return granted
    }

    @Synchronized
    override fun abandon(kind: FocusKind) {
        val req = live.remove(kind) ?: return
        audio.abandonAudioFocusRequest(req)
        Log.i(TAG, "$kind focus released")
    }

    @Synchronized
    override fun holds(kind: FocusKind): Boolean = live.containsKey(kind)

    private fun gainFor(kind: FocusKind): Int = when (kind) {
        // ★★ EXCLUSIVE, not plain TRANSIENT. This is the value Android documents for
        // speech recognition, and it is the one that tells everything else "do not duck,
        // stop" — which is the only correct answer when the microphone and the speaker
        // are the same earbud.
        FocusKind.CAPTURE -> AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_EXCLUSIVE
        // ★ MAY_DUCK: a message being read aloud is meant to sit on top of whatever else
        // is playing, not to stop it. See [FocusKind.SPEECH].
        FocusKind.SPEECH -> AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK
    }

    private fun attributesFor(kind: FocusKind): AudioAttributes = when (kind) {
        FocusKind.CAPTURE -> AudioAttributes.Builder()
            // ⚠️ VOICE_COMMUNICATION matches what the link actually is: PTT runs over
            // SCO with the audio mode set to MODE_IN_COMMUNICATION, and the attributes
            // handed to the focus request should say the same thing the routing does.
            .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
            .build()

        // ⚠️ The same attributes the Piper AudioTrack is built with (see WyomingTts):
        // ASSISTANT, not MEDIA — this is the device speaking to its wearer. The focus
        // request and the track it is taken for must not describe themselves differently.
        FocusKind.SPEECH -> AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_ASSISTANT)
            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
            .build()
    }

    companion object {
        private const val TAG = "RoamAudio"

        /** The framework's vocabulary, mapped to ours. Pure, so a JVM test pins it. */
        fun translate(change: Int): FocusChange = when (change) {
            AudioManager.AUDIOFOCUS_GAIN -> FocusChange.GAINED
            AudioManager.AUDIOFOCUS_LOSS_TRANSIENT -> FocusChange.LOST_TRANSIENT
            AudioManager.AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK ->
                FocusChange.LOST_TRANSIENT_CAN_DUCK
            // ⚠️ Anything unrecognised is treated as a permanent loss, which is the safe
            // direction: the worst case is music he has to press play on again, against a
            // radio that keeps playing over something the system thought was important.
            else -> FocusChange.LOST
        }
    }
}
