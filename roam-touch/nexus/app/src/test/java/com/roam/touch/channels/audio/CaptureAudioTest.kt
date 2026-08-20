package com.roam.touch.channels.audio

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Records what was asked of the framework, and lets a test refuse. */
private class RecordingFocus : AudioFocusManager {

    var grant = true
    val requests = mutableListOf<FocusKind>()
    val abandons = mutableListOf<FocusKind>()
    private val held = mutableSetOf<FocusKind>()
    var captureListener: ((FocusChange) -> Unit)? = null

    override fun request(kind: FocusKind, onChange: (FocusChange) -> Unit): Boolean {
        requests += kind
        if (kind == FocusKind.CAPTURE) captureListener = onChange
        if (!grant) return false
        held += kind
        return true
    }

    override fun abandon(kind: FocusKind) {
        abandons += kind
        held -= kind
    }

    override fun holds(kind: FocusKind): Boolean = kind in held
}

private class CountingSurface : PlaybackSurface {
    var playing = false
        private set
    var pauses = 0
        private set

    override fun play(volume: Float) {
        playing = true
    }

    override fun pause() {
        playing = false
        pauses++
    }

    override fun setVolume(volume: Float) = Unit
}

/**
 * ★★ The PTT side of the arbitration: what a press takes, and that it always gives it
 * back.
 *
 * Both halves are here because both are load-bearing and they fail differently. The
 * framework request is what stops apps we did not write — a podcast, a music player he
 * left running. The direct call to [PlaybackFocus] is what stops **ours**, synchronously,
 * because the WebView's audio is in this process and the mic opens ~600 ms later; waiting
 * for a focus callback to come back around would leave music playing over the whole
 * CONNECTING state and into his first word.
 */
class CaptureAudioTest {

    private val focus = RecordingFocus()
    private val surface = CountingSurface()
    private val playback = PlaybackFocus { surface }
    private val audio = FocusCaptureAudio(focus, playback)

    @Test
    fun `a press takes capture focus and pauses our own radio`() {
        playback.onPlayRequested()
        assertTrue(surface.playing)

        audio.begin()
        assertTrue(focus.requests.contains(FocusKind.CAPTURE))
        assertFalse(surface.playing)
    }

    @Test
    fun `the end of a press gives the focus back and the music with it`() {
        playback.onPlayRequested()
        audio.begin()
        audio.end()
        assertEquals(listOf(FocusKind.CAPTURE), focus.abandons)
        assertTrue(surface.playing)
    }

    @Test
    fun `ending twice releases once`() {
        // ⚠️ Ptt closes the link from six places and some of them overlap; a second
        // abandon would release focus a later press had just taken.
        audio.begin()
        audio.end()
        audio.end()
        assertEquals(1, focus.abandons.size)
    }

    @Test
    fun `beginning twice takes focus once`() {
        audio.begin()
        audio.begin()
        assertEquals(1, focus.requests.count { it == FocusKind.CAPTURE })
    }

    @Test
    fun `ending without a press still lets the radio go`() {
        // ★ Ptt.cancel closes the link unconditionally, from Idle included. That must be
        // harmless rather than a stuck pause.
        playback.onPlayRequested()
        audio.end()
        assertTrue(focus.abandons.isEmpty())
        assertTrue(surface.playing)
    }

    @Test
    fun `a denied focus request never stops the recording`() {
        // ⚠️⚠️ The standing rule for this device: it has exactly one working microphone
        // and a press that quietly declines to record is the worst failure it has. Focus
        // is an ask, not a permission.
        playback.onPlayRequested()
        focus.grant = false
        audio.begin()
        // Our own radio is still silenced — that part does not depend on the framework.
        assertFalse(surface.playing)
        audio.end()
        assertTrue(surface.playing)
    }

    @Test
    fun `losing capture focus mid-press does not stop the microphone`() {
        // ★ Stopping a recording is Ptt's decision and it has its own stop signals. A
        // second, invisible one firing on a notification would be a sentence that ends
        // without him knowing why.
        audio.begin()
        focus.captureListener?.invoke(FocusChange.LOST_TRANSIENT)
        // Nothing to assert on the recorder here — the point is that this object has no
        // path to it at all. What it must not do is release the focus it is still using.
        assertTrue(focus.abandons.isEmpty())
    }

    @Test
    fun `with no radio at all a press is still arbitrated with the rest of the phone`() {
        val alone = FocusCaptureAudio(focus, playback = null)
        alone.begin()
        alone.end()
        assertEquals(listOf(FocusKind.CAPTURE), focus.requests)
        assertEquals(listOf(FocusKind.CAPTURE), focus.abandons)
    }
}
