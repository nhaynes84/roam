package com.roam.touch.channels.controls

import android.view.KeyEvent
import androidx.test.core.app.ApplicationProvider
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * ★★ **The microphone-safety rules that live above [ControlRouter], pinned.**
 *
 * ⚠️⚠️ These paths decide whether a microphone in his house opens or closes, and until
 * now none of them had a test — they sit in [HeadsetControls], which needs an Android
 * context, so they fell outside the router's pure tests and were verified only by hand on
 * a device. That is not good enough for this particular code: the one time an agent got a
 * microphone decision wrong it recorded 17 seconds of him comforting his crying son.
 *
 * Robolectric because a real [KeyEvent] is the subject. With `returnDefaultValues` the
 * android.jar stub returns a key code of 0 for everything, which would make every one of
 * these tests pass while testing nothing.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [29])
class HeadsetControlsTest {

    /** A microphone that behaves like the real one: the toggle flips it. */
    private class FakeSurface(var micOpen: Boolean = false) : ControlSurface {
        var toggles = 0
        var sends = 0
        var cancels = 0
        var channelSteps = 0

        override fun pushToTalkToggle() {
            toggles++
            micOpen = !micOpen
        }

        override fun pushToTalkStart() {
            micOpen = true
        }

        override fun pushToTalkStop() {
            micOpen = false
        }

        override fun send() {
            sends++
        }

        override fun nextChannel() {
            channelSteps++
        }

        override fun previousChannel() {
            channelSteps--
        }

        override fun cancel() {
            cancels++
        }
    }

    private object NoStore : ControlBindingStore {
        override suspend fun profiles(): Map<String, HeadsetProfile> = emptyMap()
        override suspend fun save(profile: HeadsetProfile) = Unit
        override suspend fun forget(address: String) = Unit
    }

    private var now = 10_000L
    private lateinit var surface: FakeSurface
    private lateinit var controls: HeadsetControls

    @Before
    fun setUp() {
        surface = FakeSurface()
        controls = HeadsetControls(
            context = ApplicationProvider.getApplicationContext(),
            store = NoStore,
            scope = CoroutineScope(Dispatchers.Unconfined),
            clock = { now },
        ).also {
            it.surface = surface
            // ★ Read straight off the "microphone", never a snapshot of it — the same
            // contract the real wiring has with Ptt.
            it.micOpen = { surface.micOpen }
        }
    }

    private fun up(code: Int) = controls.dispatch(KeyEvent(KeyEvent.ACTION_UP, code))
    private fun down(code: Int) = controls.dispatch(KeyEvent(KeyEvent.ACTION_DOWN, code))

    // --- ★★ any key stops a running recording -------------------------------

    /**
     * ★★ **The rule.** Opening the mic puts the headset in a call, and in a call the
     * earbud keeps the single tap for call control — it never becomes a media key, so the
     * app never sees it. Owner, measuring it himself: *"the first tap works fine, but then
     * trying to stop is multiple taps... double tap seems to work reliably for stop."*
     *
     * Mid-sentence there is nothing else a key could mean, so every one of them is a stop.
     * ⚠️ The gesture that opens a microphone must always be able to close it.
     */
    @Test
    fun `every headset key stops a running recording`() {
        val keys = listOf(
            KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE,
            KeyEvent.KEYCODE_MEDIA_PLAY,
            KeyEvent.KEYCODE_MEDIA_PAUSE,
            KeyEvent.KEYCODE_MEDIA_STOP,
            KeyEvent.KEYCODE_MEDIA_NEXT,
            KeyEvent.KEYCODE_MEDIA_PREVIOUS,
            KeyEvent.KEYCODE_HEADSETHOOK,
        )
        for (code in keys) {
            surface = FakeSurface(micOpen = true).also {
                controls.surface = it
                controls.micOpen = { it.micOpen }
            }
            // ⚠️ Far enough from any earlier key that the echo window cannot be what
            // swallowed it — this test is about the stop rule, not about the filter.
            now += 5_000

            assertTrue(
                "${KeyEvent.keyCodeToString(code)} must be claimed while recording",
                up(code),
            )
            assertEquals(
                "${KeyEvent.keyCodeToString(code)} must stop the recording",
                1,
                surface.toggles,
            )
            assertFalse("the mic must be closed", surface.micOpen)
        }
    }

    /**
     * ⚠️ Volume is deliberately not a stop. He may genuinely want to turn the volume down
     * while a recording runs, and taking that away would be the "swallowing keys we were
     * not given" failure the router exists to prevent.
     */
    @Test
    fun `volume does not stop a recording, and is not swallowed`() {
        surface.micOpen = true
        for (code in listOf(KeyEvent.KEYCODE_VOLUME_UP, KeyEvent.KEYCODE_VOLUME_DOWN)) {
            assertFalse("volume is not ours unbound", up(code))
        }
        assertEquals(0, surface.toggles)
        assertTrue("the mic must still be open", surface.micOpen)
    }

    /** ⚠️ The stop happens on release, so a press cannot half-stop a sentence. */
    @Test
    fun `the press does not stop the recording, the release does`() {
        surface.micOpen = true
        down(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE)
        assertEquals("nothing on the down edge", 0, surface.toggles)
        up(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE)
        assertEquals(1, surface.toggles)
    }

    /** With the mic closed and nothing bound, a key is not ours and goes back. */
    @Test
    fun `an unbound key with the mic closed goes back to the system`() {
        assertFalse(up(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE))
        assertEquals(0, surface.toggles)
    }

    // --- ★★⚠️⚠️ the stop that restarted the recording ------------------------

    /**
     * ★★⚠️⚠️ **The double tap that stops the microphone must not immediately re-open it.**
     *
     * A multi-tap does not arrive alone: his Pixel Buds send MEDIA_PREVIOUS and then a
     * stray MEDIA_PLAY about 100 ms behind it. A double tap is how stopping actually
     * works mid-recording — it is the only gesture that leaks through the call profile —
     * so the stop rule above claims MEDIA_PREVIOUS and returns before [ControlRouter] ever
     * sees it. The tail then finds the microphone already closed, reads as a deliberate
     * tap, and starts a **new recording in his house**.
     *
     * Same shape as the 17-second failure, different cause. This is the test for it.
     */
    @Test
    fun `the tail of the double tap that stopped the mic does not start another recording`() {
        surface.micOpen = true

        assertTrue(up(KeyEvent.KEYCODE_MEDIA_PREVIOUS))
        assertEquals("the double tap stops it", 1, surface.toggles)
        assertFalse("mic closed", surface.micOpen)

        now += 102 // the measured tail
        assertTrue("the tail is ours to swallow", up(KeyEvent.KEYCODE_MEDIA_PLAY))
        assertTrue("and its orphaned down edge with it", down(KeyEvent.KEYCODE_MEDIA_PLAY))

        assertEquals("NOTHING may have toggled the mic again", 1, surface.toggles)
        assertFalse("★ the microphone must still be closed", surface.micOpen)
    }

    /** The same for a triple tap, which arrives as the other multi-tap key. */
    @Test
    fun `the tail of a triple tap that stopped the mic does not start another recording`() {
        surface.micOpen = true

        up(KeyEvent.KEYCODE_MEDIA_NEXT)
        now += 16 // the other measured tail
        up(KeyEvent.KEYCODE_MEDIA_PLAY)

        assertEquals(1, surface.toggles)
        assertFalse("★ the microphone must still be closed", surface.micOpen)
    }

    /**
     * ⚠️ And the window must not eat a real tap. A deliberate second press comes far later
     * than an echo; swallowing it would make the microphone impossible to re-open right
     * after a double tap, which reads as a dead earbud.
     */
    @Test
    fun `a deliberate tap after the window still reaches the stop rule`() {
        surface.micOpen = true
        up(KeyEvent.KEYCODE_MEDIA_PREVIOUS)
        assertEquals(1, surface.toggles)

        surface.micOpen = true
        now += ControlRouter.TAIL_MS + 1
        up(KeyEvent.KEYCODE_MEDIA_PLAY)
        assertEquals("a real tap is still a stop", 2, surface.toggles)
    }
}
