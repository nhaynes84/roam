package com.roam.touch.channels.audio

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * A focus service that grants everything and remembers who asked.
 *
 * ⚠️ Listeners are kept per [FocusKind] rather than in a single slot: the capture request
 * and the speech request are two different things that must not clear each other, and a
 * fake that conflated them would pass tests the device fails.
 */
private class FakeFocus : AudioFocusManager {

    var grant = true

    val requests = mutableListOf<FocusKind>()
    val abandons = mutableListOf<FocusKind>()

    private val listeners = mutableMapOf<FocusKind, (FocusChange) -> Unit>()
    val held = mutableSetOf<FocusKind>()

    override fun request(kind: FocusKind, onChange: (FocusChange) -> Unit): Boolean {
        requests += kind
        if (!grant) return false
        listeners[kind] = onChange
        held += kind
        return true
    }

    override fun abandon(kind: FocusKind) {
        abandons += kind
        listeners.remove(kind)
        held -= kind
    }

    override fun holds(kind: FocusKind): Boolean = kind in held

    /**
     * The framework telling **everything this app registered** what happened — which is what
     * one focus event actually does. Deliberately not addressed to a [FocusKind]: the point
     * of the test that uses it is that while the radio plays there is nothing here to tell.
     */
    fun deliverToAll(change: FocusChange) {
        listeners.values.toList().forEach { it(change) }
    }
}

/** The radio page, as a list of what it was told to do. */
private class FakeSurface : PlaybackSurface {

    val calls = mutableListOf<String>()
    var volume = 1f
        private set
    var playing = false
        private set

    override fun play(volume: Float) {
        this.volume = volume
        playing = true
        calls += "play@$volume"
    }

    override fun pause() {
        playing = false
        calls += "pause"
    }

    override fun setVolume(volume: Float) {
        this.volume = volume
        calls += "volume@$volume"
    }
}

/**
 * ★★ **Music and the microphone share one earbud, and this is the referee.**
 *
 * Every test here is a thing that happens to a man walking around with a phone on his
 * forearm: he keys PTT while the radio plays, Piper reads him a message mid-stream, he walks
 * away from the page. The property being pinned throughout is that **two interruptions never
 * clear each other** — the resume belongs to whichever hold is lifted last, and getting that
 * wrong leaves quiet music under an open microphone in the only ear he has.
 *
 * ⚠️ There is nothing here about phone calls or navigation prompts, and that is not an
 * omission. Those arrive as focus losses at the WebView's own Chromium, which suspends and
 * resumes the page's `<audio>` element itself — this app is not a media-focus client for the
 * radio and must not become one. See [WebViewOwnsMediaFocusTest].
 */
class PlaybackFocusTest {

    private val surface = FakeSurface()
    private val playback = PlaybackFocus { surface }

    // ---- the ordinary path -----------------------------------------------------------

    @Test
    fun `play starts the page`() {
        playback.onPlayRequested()
        assertTrue(surface.playing)
        assertEquals(1f, surface.volume, 0f)
        assertTrue(playback.state.value.wanted)
    }

    @Test
    fun `pause stops the page and drops the intent`() {
        playback.onPlayRequested()
        playback.onPauseRequested()
        assertFalse(surface.playing)
        assertFalse(playback.state.value.wanted)
    }

    // ---- PTT -------------------------------------------------------------------------

    @Test
    fun `keying PTT pauses the radio and releasing brings it back`() {
        playback.onPlayRequested()
        playback.onCaptureStarted()
        assertFalse(surface.playing)
        assertEquals(PlaybackState.Reason.PTT, playback.state.value.reason)
        // ★ Still wanted. The interruption is not a decision he made about the music.
        assertTrue(playback.state.value.wanted)

        playback.onCaptureEnded()
        assertTrue(surface.playing)
        assertEquals(1f, surface.volume, 0f)
        assertEquals(PlaybackState.Reason.NONE, playback.state.value.reason)
    }

    @Test
    fun `PTT pauses outright — it never ducks`() {
        // ⚠️ The one decision in this file that is not the Android default. Quiet music in
        // the same earbud he is talking into is still music he is talking over, and the
        // link is about to be switched into mono call mode anyway.
        playback.onPlayRequested()
        playback.onCaptureStarted()
        assertFalse(playback.state.value.playing)
        assertFalse(surface.calls.any { it.startsWith("volume@") })
    }

    @Test
    fun `PTT with no music playing touches the page not at all`() {
        playback.onCaptureStarted()
        playback.onCaptureEnded()
        // ★ Nothing was playing, so nothing resumes. A press must not *start* the radio.
        assertTrue(surface.calls.isEmpty())
        assertFalse(playback.state.value.wanted)
    }

    @Test
    fun `a repeated capture start is not a second pause`() {
        // ⚠️ A pause re-issued at a media element mid-buffer is a stutter he hears, and on
        // the hub's radio page a re-issued *play* re-opens the stream outright. Both ends of
        // every hold are reached from more than one path.
        playback.onPlayRequested()
        playback.onCaptureStarted()
        playback.onCaptureStarted()
        playback.onCaptureEnded()
        playback.onCaptureEnded()
        assertEquals(1, surface.calls.count { it == "pause" })
        assertEquals(2, surface.calls.count { it.startsWith("play@") })
    }

    // ---- our own voice ---------------------------------------------------------------

    @Test
    fun `Piper ducks the radio rather than stopping it`() {
        // ★ The "where appropriate" half of the ducking rule. A ten-second sentence is
        // not worth a re-buffer at each end of a tailnet stream, and speech over quiet
        // music is perfectly intelligible — which is the entire point of ducking.
        playback.onPlayRequested()
        playback.onSpeechStarted()
        assertTrue(playback.state.value.playing)
        assertEquals(PlaybackFocus.DUCK_VOLUME, surface.volume, 0f)

        playback.onSpeechEnded()
        assertEquals(1f, surface.volume, 0f)
        assertTrue(playback.state.value.playing)
    }

    @Test
    fun `PTT beats a message being read aloud`() {
        // ⚠️ Both can be live: he taps play on a message and then keys the mic while it is
        // still talking. Quiet music under an open microphone is still music he is talking
        // over, so the pause wins and the duck does not undo it.
        playback.onPlayRequested()
        playback.onSpeechStarted()
        playback.onCaptureStarted()
        assertFalse(playback.state.value.playing)
        assertEquals(PlaybackState.Reason.PTT, playback.state.value.reason)

        playback.onCaptureEnded()
        // Piper is still talking, so it comes back ducked rather than at full volume.
        assertTrue(playback.state.value.playing)
        assertEquals(PlaybackFocus.DUCK_VOLUME, surface.volume, 0f)

        playback.onSpeechEnded()
        assertEquals(1f, surface.volume, 0f)
    }

    @Test
    fun `a message that starts mid-press cannot turn the pause into quiet music`() {
        playback.onPlayRequested()
        playback.onCaptureStarted()
        playback.onSpeechStarted()
        assertFalse(playback.state.value.playing)
        assertEquals(PlaybackState.Reason.PTT, playback.state.value.reason)
    }

    // ---- the two holds, overlapping --------------------------------------------------

    @Test
    fun `stopping the radio while the mic is open leaves nothing to come back`() {
        // ⚠️⚠️ He can reach the page's Stop button with his other thumb while a press is
        // live. Releasing the button after that must not start music he has just switched
        // off — the failure being avoided is a phone on his arm that plays by itself.
        playback.onPlayRequested()
        playback.onCaptureStarted()
        playback.onPauseRequested()
        playback.onCaptureEnded()
        assertFalse(surface.playing)
        assertFalse(playback.state.value.wanted)
    }

    // ---- the page comes and goes -----------------------------------------------------

    @Test
    fun `leaving the radio page drops the intent to play`() {
        playback.onPlayRequested()
        playback.onSurfaceGone()
        assertFalse(playback.state.value.wanted)
        // ★ And a press afterwards has nothing to resume: the WebView is gone with the
        // screen, and so is the element that was playing.
        playback.onCaptureStarted()
        playback.onCaptureEnded()
        assertFalse(playback.state.value.playing)
    }

    @Test
    fun `with no page on screen the state is still tracked and nothing explodes`() {
        // ★ The WebView is created and destroyed by navigation; PTT is not, and a press
        // with no radio page open must be a no-op rather than a null dereference.
        val detached = PlaybackFocus { null }
        detached.onCaptureStarted()
        detached.onPlayRequested()
        assertTrue(detached.state.value.wanted)
        // Wanted, but held down by the open microphone — exactly as it would be with a page.
        assertFalse(detached.state.value.playing)
        detached.onCaptureEnded()
        assertTrue(detached.state.value.playing)
    }
}

/**
 * ★★ **The WebView is this app's media client, and there may only be one.**
 *
 * ⚠️⚠️ Chromium requests audio focus for the page's own `<audio>` element, from inside this
 * process, the instant it starts. Device log, Pixel 1 / API 29, on every tap on a station:
 *
 * ```
 * requestAudioFocus() clientId=...SystemAudioFocus$$Lambda   req=1   ← ours
 * requestAudioFocus() clientId=...AudioFocusDelegate         req=1   ← Chromium's, for our page
 * onAudioFocusChange(-1) → ...SystemAudioFocus$$Lambda              ← AUDIOFOCUS_LOSS
 * RoamAudio: radio: pause                                            ← we kill our own stream
 * ```
 *
 * A durable `AUDIOFOCUS_GAIN` revokes every other holder, and "every other holder" included
 * us: the framework has no notion of two clients in one process cooperating. So the app took
 * media focus, its own page took it away half a second later, and the loss callback did
 * exactly what it is written to do — concluded another app had started something and stopped
 * the radio. **The music never survived its own first note.**
 *
 * The fix is not a guard against that particular loss; it is that the request was redundant
 * from the start. Chromium is a better media-focus client for the page than we can be — it
 * knows which element is live and it suspends and resumes it for calls and prompts by
 * itself. What this app keeps is the focus it alone can ask for: the microphone and its own
 * voice.
 */
class WebViewOwnsMediaFocusTest {

    private val focus = FakeFocus()
    private val surface = FakeSurface()
    private val playback = PlaybackFocus { surface }
    private val bridge = RadioBridge(playback)

    /** The rest of the graph, so "nothing of ours holds focus" is a claim about all of it. */
    private val capture = FocusCaptureAudio(focus, playback)
    private val speech = SpeechAudio(focus, playback)

    @Test
    fun `music playing in the page is not a reason for this app to hold audio focus`() {
        bridge.onPlay()

        assertTrue("the page's own Chromium holds media focus for it", focus.held.isEmpty())
        assertEquals("and we asked for nothing at all", emptyList<FocusKind>(), focus.requests)
        assertTrue(surface.playing)
    }

    @Test
    fun `a focus loss caused by our own page starting cannot pause it`() {
        bridge.onPlay()
        assertTrue(surface.playing)

        // The device sequence: Chromium's GAIN lands, and the framework revokes whatever
        // else this process was holding. There is nothing to revoke.
        focus.deliverToAll(FocusChange.LOST)

        assertTrue("the radio must survive its own first note", surface.playing)
        assertTrue(playback.state.value.playing)
        assertTrue(playback.state.value.wanted)
        assertFalse("we never paused the page we had just started", surface.calls.contains("pause"))
    }

    @Test
    fun `there is no media focus kind left to ask for`() {
        // ⚠️ A structural pin, because this is the trap: the next person to want a call to
        // pause the radio will reach for a PLAYBACK request, and it will look right, and it
        // will silently switch the radio off on the device instead. Chromium already does
        // that job — see the class comment.
        assertEquals(
            setOf(FocusKind.CAPTURE, FocusKind.SPEECH),
            FocusKind.values().toSet(),
        )
    }

    // ---- PTT, which is what the focus we *do* take is for -----------------------------

    @Test
    fun `a PTT cycle pauses and resumes the page exactly once`() {
        // ★★ The interaction the fix has to keep deterministic. Three things now want to
        // stop and start this element: our own JS, Chromium suspending it because our
        // capture request took its focus, and the page reporting what happened. Only one
        // of them may reach the surface.
        bridge.onPlay()
        capture.begin()
        // Chromium suspends the element for our GAIN_TRANSIENT_EXCLUSIVE, and the page's
        // pause handler reports it back to us — indistinguishable, from here, from his thumb.
        bridge.onPause()
        capture.end()
        // ...and Chromium resumes the element when the abandon reaches it, so the page
        // reports a play as well.
        bridge.onPlay()

        assertEquals(listOf("play@1.0", "pause", "play@1.0"), surface.calls)
        assertTrue(playback.state.value.playing)
        assertEquals(listOf(FocusKind.CAPTURE), focus.requests)
        assertEquals(listOf(FocusKind.CAPTURE), focus.abandons)
    }

    @Test
    fun `the capture request is made only after the radio believes it is silent`() {
        // ⚠️⚠️ The ordering inside [FocusCaptureAudio.begin], pinned from the outside: by
        // the time anything can hear our focus request, `playing` is already false, which is
        // the only thing that tells the page's echoed pause apart from a pause he made.
        bridge.onPlay()
        var playingWhenAsked: Boolean? = null
        val watchful = object : AudioFocusManager by focus {
            override fun request(kind: FocusKind, onChange: (FocusChange) -> Unit): Boolean {
                playingWhenAsked = playback.state.value.playing
                return focus.request(kind, onChange)
            }
        }

        FocusCaptureAudio(watchful, playback).begin()

        assertEquals(false, playingWhenAsked)
    }

    @Test
    fun `Piper still ducks the radio while holding speech focus`() {
        bridge.onPlay()
        speech.begin()

        assertEquals(listOf(FocusKind.SPEECH), focus.requests)
        assertTrue(playback.state.value.playing)
        assertEquals(PlaybackFocus.DUCK_VOLUME, surface.volume, 0f)

        speech.end()
        assertEquals(listOf(FocusKind.SPEECH), focus.abandons)
        assertEquals(1f, surface.volume, 0f)
    }
}

/**
 * ★★ **Telling his pause apart from our own — the page reports both the same way.**
 *
 * ⚠️⚠️ [RadioJs.pause] prefers the page's `window.RoamRadio` hook, but a page that does
 * not define one is paused by the element fallback, which makes the `<audio>` element fire
 * its own `pause` event; and Chromium suspends the element by itself when the exclusive
 * focus we take for the microphone lands on it. Either way **our** pause can come back to us
 * looking exactly like his.
 *
 * The old guard was `wanted`, which is still true through a PTT press, so the echo was
 * accepted as a decision he had made and the radio never came back after the first press of
 * the button this device is built around.
 *
 * `playing` is the honest test: a pause he made always arrives while we believe sound is
 * coming out.
 */
class RadioBridgeTest {

    private val surface = FakeSurface()
    private val playback = PlaybackFocus { surface }
    private val bridge = RadioBridge(playback)

    /** The page with no hook, echoing back whatever we just did to its media element. */
    private fun echoOurPause() = bridge.onPause()

    // ---- the trap --------------------------------------------------------------------

    @Test
    fun `the page echoing our PTT pause does not abandon the radio`() {
        playback.onPlayRequested()

        playback.onCaptureStarted()
        echoOurPause()

        assertTrue("the intent to play survives our own pause", playback.state.value.wanted)

        playback.onCaptureEnded()
        assertTrue("the radio has to come back after the first press", surface.playing)
    }

    @Test
    fun `a hookless page cannot walk the radio down press by press`() {
        // ⚠️ The shape of the real failure: it is not one lost resume, it is the radio
        // being permanently switched off by the third thing he does with the device.
        playback.onPlayRequested()
        repeat(5) {
            playback.onCaptureStarted()
            echoOurPause()
            playback.onCaptureEnded()
        }
        assertTrue(playback.state.value.playing)
        assertTrue(playback.state.value.wanted)
    }

    // ---- his own hand still works ----------------------------------------------------

    @Test
    fun `a pause he made still stops the radio`() {
        playback.onPlayRequested()
        bridge.onPause()

        assertFalse(playback.state.value.wanted)
        assertFalse(surface.playing)
    }

    @Test
    fun `a pause reported when nothing is playing is not a second stop`() {
        playback.onPlayRequested()
        bridge.onPause()
        bridge.onPause()
        // ★ Idempotent from the page's side too — a stalled page may report twice.
        assertEquals(1, surface.calls.count { it == "pause" })
    }

    // ---- and play is unchanged -------------------------------------------------------

    @Test
    fun `the page reporting play records that music is wanted`() {
        bridge.onPlay()
        assertTrue(playback.state.value.wanted)
        assertTrue(surface.playing)
    }

    @Test
    fun `the page echoing our own resume does not re-open the stream forever`() {
        // ⚠️ The mirror image of the pause bug: our resume calls `RoamRadio.play()` in the
        // page, which re-opens the stream and makes the page report it, and an ungated
        // report would re-issue the resume for as long as the process lived.
        playback.onPlayRequested()
        repeat(5) { bridge.onPlay() }
        assertEquals(1, surface.calls.count { it.startsWith("play@") })
    }
}
