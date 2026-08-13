package com.roam.touch.channels.controls

import android.view.KeyEvent
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * ★★ Which headset gestures this app takes, and — far more importantly — which it leaves
 * alone.
 *
 * ⚠️⚠️ **There is no standard gesture set.** Measured against the owner's own kit: the
 * Pixel Buds bind long-press to Assistant, his Jabras bind it to volume, and the Jabras
 * fire an independent action set per ear. So nothing here may hard-code a mapping, and the
 * rule that keeps that honest is the one this file pins hardest: **an unbound key is not
 * ours.** It passes through untouched, so volume stays volume and track-skip stays
 * track-skip on a headset whose gestures we have never seen.
 */
class ControlRouterTest {

    private val tap = HeadsetGesture(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE)
    private val held = HeadsetGesture(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE, longPress = true)
    private val next = HeadsetGesture(KeyEvent.KEYCODE_MEDIA_NEXT)
    private val volumeUp = HeadsetGesture(KeyEvent.KEYCODE_VOLUME_UP)

    private val router = ControlRouter()

    private fun down(code: Int, repeat: Int = 0) =
        router.onKey(KeyRecord(code, down = true, repeat = repeat))

    private fun up(code: Int) = router.onKey(KeyRecord(code, down = false))

    private fun profile(vararg bindings: Pair<HeadsetGesture, ControlAction>) {
        router.profile = HeadsetProfile("80:99:E7:DE:66:E6", "WH-1000XM6", bindings.toMap())
    }

    // --- ⚠️⚠️ the rule that protects everything else -------------------------

    /**
     * ⚠️⚠️ **Only what he bound.** Swallowing a key we were not given would break the
     * headset's own controls — the owner's warning was explicit about volume — and it
     * would do so invisibly, on a device he is not looking at.
     */
    @Test
    fun `an unbound key is passed straight back to the system`() {
        profile(tap to ControlAction.PUSH_TO_TALK)

        assertEquals(ControlDecision.PassThrough, down(KeyEvent.KEYCODE_VOLUME_UP))
        assertEquals(ControlDecision.PassThrough, up(KeyEvent.KEYCODE_VOLUME_UP))
        assertEquals(ControlDecision.PassThrough, down(KeyEvent.KEYCODE_MEDIA_NEXT))
    }

    /** With no headset known at all, nothing is ours. */
    @Test
    fun `with no profile every key passes through`() {
        router.profile = null
        assertEquals(ControlDecision.PassThrough, down(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE))
        assertEquals(ControlDecision.PassThrough, up(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE))
    }

    /**
     * ⚠️ Volume is bindable, but only on purpose. Unbinding it hands the rocker back —
     * a gesture he stops wanting intercepted has to go back to doing what it did before.
     */
    @Test
    fun `volume is ours only while it is bound, and is released when it is not`() {
        profile(volumeUp to ControlAction.NEXT_CHANNEL)
        assertEquals(ControlDecision.Consumed, down(KeyEvent.KEYCODE_VOLUME_UP))
        assertEquals(ControlDecision.Perform(ControlAction.NEXT_CHANNEL),
            up(KeyEvent.KEYCODE_VOLUME_UP))

        router.profile = router.profile!!.unbind(volumeUp)
        assertEquals(ControlDecision.PassThrough, down(KeyEvent.KEYCODE_VOLUME_UP))
        assertTrue("volume must stop being captured", !router.profile!!.capturesVolume)
    }

    // --- acting on the release, not the press --------------------------------

    /**
     * ★ The down edge is claimed but does nothing: at the moment of the press it is not
     * yet known whether he is going to hold it, and letting the down through would let
     * the system act on a key we are about to take.
     */
    @Test
    fun `a bound key acts on release, and its press is claimed but silent`() {
        profile(tap to ControlAction.PUSH_TO_TALK)

        assertEquals(ControlDecision.Consumed, down(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE))
        assertEquals(
            ControlDecision.Perform(ControlAction.PUSH_TO_TALK),
            up(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE),
        )
    }

    @Test
    fun `a held key performs the held binding, not the tap one`() {
        profile(tap to ControlAction.PUSH_TO_TALK, held to ControlAction.CANCEL)

        down(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE)
        down(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE, repeat = 1)
        assertEquals(
            ControlDecision.Perform(ControlAction.CANCEL),
            up(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE),
        )
    }

    /**
     * ★ Some headsets never report a repeat at all. A hold that arrives looking like a
     * tap must still do the tap's job — a dead-feeling button is worse than losing a
     * distinction he did not ask for.
     */
    @Test
    fun `a hold with no held binding falls back to the tap binding`() {
        profile(tap to ControlAction.PUSH_TO_TALK)

        down(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE, repeat = 3)
        assertEquals(
            ControlDecision.Perform(ControlAction.PUSH_TO_TALK),
            up(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE),
        )
    }

    /** ⚠️ A long press must not leak into the next, separate tap. */
    @Test
    fun `the held flag does not survive into the following gesture`() {
        profile(tap to ControlAction.PUSH_TO_TALK, held to ControlAction.CANCEL)

        down(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE, repeat = 2)
        up(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE)

        down(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE)
        assertEquals(
            ControlDecision.Perform(ControlAction.PUSH_TO_TALK),
            up(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE),
        )
    }

    // --- ★ learn mode: discovery, not assumption ------------------------------

    /**
     * ★★ The whole reason this is bindable. He makes the gesture, and whatever the
     * headset actually sent becomes the binding — which works for a headset neither of us
     * has ever seen.
     */
    @Test
    fun `learn mode captures whatever the headset actually sent`() {
        router.startLearning()

        assertEquals(ControlDecision.Consumed, down(KeyEvent.KEYCODE_MEDIA_NEXT))
        assertEquals(ControlDecision.Learned(next), up(KeyEvent.KEYCODE_MEDIA_NEXT))
    }

    @Test
    fun `learn mode tells a hold apart from a tap`() {
        router.startLearning()
        down(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE, repeat = 1)
        assertEquals(ControlDecision.Learned(held), up(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE))
    }

    /**
     * ⚠️ Learning captures keys it would otherwise pass through — he is being asked to
     * make a gesture, and having it skip a track while he does would be absurd. It is
     * one gesture only, and it ends itself.
     */
    @Test
    fun `learn mode captures unbound keys too, and ends after one gesture`() {
        router.profile = null
        router.startLearning()

        assertEquals(ControlDecision.Consumed, down(KeyEvent.KEYCODE_VOLUME_DOWN))
        assertEquals(
            ControlDecision.Learned(HeadsetGesture(KeyEvent.KEYCODE_VOLUME_DOWN)),
            up(KeyEvent.KEYCODE_VOLUME_DOWN),
        )
        assertTrue("one gesture, then it stops", !router.isLearning)
        assertEquals("and the key goes back to the system", ControlDecision.PassThrough,
            down(KeyEvent.KEYCODE_VOLUME_DOWN))
    }

    @Test
    fun `learning can be abandoned without capturing anything`() {
        router.startLearning()
        router.stopLearning()
        router.profile = null
        assertEquals(ControlDecision.PassThrough, down(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE))
    }

    // --- profiles are per headset --------------------------------------------

    /**
     * ⚠️⚠️ Keyed on the Bluetooth address. Two headsets that send the same code for
     * different gestures — which is the owner's actual situation — must not share a
     * mapping, or swapping earbuds silently rebinds the microphone.
     */
    @Test
    fun `bindings belong to one headset and do not follow another`() {
        val buds = HeadsetProfile("11:22:33:44:55:66", "Pixel Buds")
            .bind(tap, ControlAction.PUSH_TO_TALK)
        val jabra = HeadsetProfile("aa:bb:cc:dd:ee:ff", "Jabra Elite")
            .bind(volumeUp, ControlAction.NEXT_CHANNEL)

        router.profile = buds
        assertEquals(ControlDecision.Consumed, down(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE))
        up(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE)
        assertEquals(ControlDecision.PassThrough, down(KeyEvent.KEYCODE_VOLUME_UP))

        router.profile = jabra
        assertEquals("the other headset's PTT gesture is not this one's",
            ControlDecision.PassThrough, down(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE))
        assertEquals(ControlDecision.Consumed, down(KeyEvent.KEYCODE_VOLUME_UP))
    }

    @Test
    fun `a binding can be moved to a different gesture and the old one is released`() {
        var profile = HeadsetProfile("11:22", "Buds").bind(tap, ControlAction.PUSH_TO_TALK)
        profile = profile.unbind(tap).bind(next, ControlAction.PUSH_TO_TALK)

        assertEquals(next, profile.boundTo(ControlAction.PUSH_TO_TALK))
        router.profile = profile
        assertEquals("the old gesture is the headset's again",
            ControlDecision.PassThrough, down(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE))
    }

    @Test
    fun `unbinding leaves nothing bound to that action`() {
        val profile = HeadsetProfile("11:22", "Buds")
            .bind(tap, ControlAction.PUSH_TO_TALK)
            .unbind(tap)
        assertNull(profile.boundTo(ControlAction.PUSH_TO_TALK))
    }

    /**
     * ★ The one default worth having: nearly every headset sends `MEDIA_PLAY_PAUSE` for a
     * single tap. It is offered, named in words, and overridable — not assumed.
     */
    @Test
    fun `a brand new headset gets a tap-to-talk default and nothing else`() {
        val fresh = HeadsetProfile.forNewHeadset("11:22", "Some Buds")

        assertEquals(tap, fresh.boundTo(ControlAction.PUSH_TO_TALK))
        assertEquals("only the convention is assumed", 1, fresh.bindings.size)
        assertTrue("and it must not silently claim volume", !fresh.capturesVolume)
        assertTrue("he has not been asked yet", !fresh.introduced)
    }

    /** Gestures have to read as gestures on screen, not as key codes. */
    @Test
    fun `gestures describe themselves in words`() {
        assertEquals("tap", tap.label)
        assertEquals("tap, held", held.label)
        assertEquals("next / double tap", next.label)
        assertEquals("volume up", volumeUp.label)
    }

    // --- ⚠️⚠️ the keycode Android decided to send us this time ----------------

    /**
     * ★★ **The bug that made a bound tap do nothing on a real headset.**
     *
     * `MediaSessionService` rewrites `MEDIA_PLAY_PAUSE` into `MEDIA_PLAY` or `MEDIA_PAUSE`
     * according to the playback state *our own session* reports. The owner bound a tap
     * while the session was idle — `85~0=PUSH_TO_TALK` went into the store — and by the
     * time he used it the session was playing, so every tap arrived as 127, matched
     * nothing, and passed through. Both of his headsets were bound; neither worked.
     */
    @Test
    fun `a tap bound as PLAY_PAUSE still fires when it arrives as PAUSE`() {
        profile(tap to ControlAction.PUSH_TO_TALK)

        assertEquals(ControlDecision.Consumed, down(KeyEvent.KEYCODE_MEDIA_PAUSE))
        assertEquals(
            ControlDecision.Perform(ControlAction.PUSH_TO_TALK),
            up(KeyEvent.KEYCODE_MEDIA_PAUSE),
        )
    }

    /** …and as PLAY, which is what the same tap becomes when the session is idle. */
    @Test
    fun `a tap bound as PLAY_PAUSE still fires when it arrives as PLAY`() {
        profile(tap to ControlAction.PUSH_TO_TALK)

        assertEquals(ControlDecision.Consumed, down(KeyEvent.KEYCODE_MEDIA_PLAY))
        assertEquals(
            ControlDecision.Perform(ControlAction.PUSH_TO_TALK),
            up(KeyEvent.KEYCODE_MEDIA_PLAY),
        )
    }

    /** Older wired headsets send HEADSETHOOK for the same press. Same gesture. */
    @Test
    fun `a tap bound as PLAY_PAUSE still fires when it arrives as HEADSETHOOK`() {
        profile(tap to ControlAction.PUSH_TO_TALK)

        assertEquals(ControlDecision.Consumed, down(KeyEvent.KEYCODE_HEADSETHOOK))
        assertEquals(
            ControlDecision.Perform(ControlAction.PUSH_TO_TALK),
            up(KeyEvent.KEYCODE_HEADSETHOOK),
        )
    }

    /**
     * ⚠️ Learning has to canonicalise too, or a gesture captured while the session happens
     * to be playing gets stored as 127 and stops matching the moment playback stops —
     * the same failure, mirrored.
     */
    @Test
    fun `learning a tap stores it canonically whatever code it arrived as`() {
        router.profile = HeadsetProfile("80:99:E7:DE:66:E6", "WH-1000XM6")
        router.startLearning()

        down(KeyEvent.KEYCODE_MEDIA_PAUSE)
        val decision = up(KeyEvent.KEYCODE_MEDIA_PAUSE)

        assertEquals(ControlDecision.Learned(tap), decision)
    }

    /**
     * ⚠️ Canonicalising must not swallow the neighbours. Double and triple tap arrive as
     * NEXT and PREVIOUS and stay their own gestures — folding those in would bind three
     * distinct controls to one action.
     */
    @Test
    fun `next and previous are not folded into the tap`() {
        profile(tap to ControlAction.PUSH_TO_TALK)

        assertEquals(ControlDecision.PassThrough, down(KeyEvent.KEYCODE_MEDIA_NEXT))
        assertEquals(ControlDecision.PassThrough, down(KeyEvent.KEYCODE_MEDIA_PREVIOUS))
    }
}
