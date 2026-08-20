package com.roam.touch.channels.audio

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * ★ The commands that cross into the hub's radio page.
 *
 * These are JVM tests over strings for the same reason [com.roam.touch.channels.ui.HubBrowser]
 * is: the decisions are string decisions, and the alternative is finding out on a worn
 * device with a 2019 engine and no console. Two things are being pinned — that the script
 * cannot carry anything but a number into the page, and that it is written in a dialect
 * Chrome 74 can parse.
 */
class RadioJsTest {

    private val all = listOf(
        RadioJs.pause(),
        RadioJs.play(1f),
        RadioJs.setVolume(0.2f),
    )

    // ---- what may cross ---------------------------------------------------------------

    @Test
    fun `volume is the only value that crosses, and it is always a bare number`() {
        assertEquals("0.500", RadioJs.clamp(0.5f))
        assertEquals("1.000", RadioJs.clamp(1f))
        assertEquals("0.000", RadioJs.clamp(0f))
    }

    @Test
    fun `a volume outside the range is clamped rather than passed through`() {
        // ⚠️ `m[i].volume = 5` throws in the page and kills the rest of the script — which
        // would leave the radio paused with no way back short of reloading the page.
        assertEquals("1.000", RadioJs.clamp(4f))
        assertEquals("0.000", RadioJs.clamp(-1f))
        assertEquals("0.000", RadioJs.clamp(Float.NaN))
    }

    @Test
    fun `the decimal separator is a point in every locale`() {
        // ⚠️⚠️ A phone set to French formats 0.2 as `0,200`, which is not a number in
        // JavaScript — it aborts the script and leaves the radio wherever it was. This is
        // the one place in the app where the device's locale must not reach.
        val was = java.util.Locale.getDefault()
        try {
            java.util.Locale.setDefault(java.util.Locale.FRANCE)
            assertEquals("0.200", RadioJs.clamp(0.2f))
        } finally {
            java.util.Locale.setDefault(was)
        }
    }

    @Test
    fun `the duck volume survives the round trip as a real attenuation`() {
        val js = RadioJs.setVolume(PlaybackFocus.DUCK_VOLUME)
        assertTrue(js.contains("0.200"))
    }

    // ---- the dialect ------------------------------------------------------------------

    @Test
    fun `every script is ES5 — the engine underneath is Chrome 74`() {
        // ⚠️ No Play Store on this phone and the WebView provider is signature-pinned, so
        // this is not a style rule: an arrow function is a syntax error that silently
        // does nothing at all.
        all.forEach { js ->
            assertFalse(js, js.contains("=>"))
            assertFalse(js, js.contains("`"))
            assertFalse(js, Regex("\\blet\\b").containsMatchIn(js))
            assertFalse(js, Regex("\\bconst\\b").containsMatchIn(js))
        }
    }

    @Test
    fun `every script is wrapped so it cannot clobber the page's globals`() {
        all.forEach { js ->
            assertTrue(js, js.startsWith("(function(){"))
            assertTrue(js, js.trimEnd().endsWith("})();"))
        }
    }

    // ---- the behaviour it asks for ----------------------------------------------------

    @Test
    fun `a page that offers its own hook is asked first`() {
        // ★ The page knows which of its players is live and whether a stale stream has to
        // be reopened; poking its elements is the fallback for a page that says nothing.
        assertTrue(RadioJs.pause().contains("${RadioJs.HOOK}.pause"))
        assertTrue(RadioJs.play(1f).contains("${RadioJs.HOOK}.play"))
        assertTrue(RadioJs.setVolume(0.5f).contains("${RadioJs.HOOK}.setVolume"))
    }

    @Test
    fun `pause marks what it paused, and play only resumes what was marked`() {
        // ⚠️ Without the mark, resuming would start every audio element on the page —
        // including one he paused himself, and including a second stream that was never
        // playing.
        assertTrue(RadioJs.pause().contains("setAttribute('${RadioJs.MARK}'"))
        assertTrue(RadioJs.play(1f).contains("hasAttribute('${RadioJs.MARK}')"))
        assertTrue(RadioJs.play(1f).contains("removeAttribute('${RadioJs.MARK}')"))
    }

    @Test
    fun `a duck never starts anything`() {
        // ★ setVolume is for music that is already playing. If it called play() it would
        // restart a stream during a notification chime.
        val js = RadioJs.setVolume(0.2f)
        assertFalse(js, js.contains(".play()"))
        assertFalse(js, js.contains("removeAttribute"))
    }

    @Test
    fun `a rejected play promise is caught rather than left unhandled`() {
        // ⚠️ `play()` returns a promise on this engine and it rejects on a stale stream.
        // Unhandled, that is a silent radio and a console message nobody on a forearm can
        // read.
        assertTrue(RadioJs.play(1f).contains("['catch']"))
    }
}
