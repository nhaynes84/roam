package com.roam.touch.channels.audio

import android.media.AudioManager
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * ★ The framework's five overlapping integers, mapped onto the four things the radio can
 * actually do.
 *
 * A JVM test rather than a device one because the mapping is where a silent inversion
 * would live: swap `LOSS` and `LOSS_TRANSIENT` and everything still compiles, the app
 * still runs, and the only symptom is music that comes back by itself in the middle of a
 * phone call — on a device that is on his arm, in his house, weeks later.
 */
class FocusTranslationTest {

    @Test
    fun `the framework's vocabulary maps onto ours`() {
        assertEquals(
            FocusChange.GAINED,
            SystemAudioFocus.translate(AudioManager.AUDIOFOCUS_GAIN),
        )
        assertEquals(
            FocusChange.LOST,
            SystemAudioFocus.translate(AudioManager.AUDIOFOCUS_LOSS),
        )
        assertEquals(
            FocusChange.LOST_TRANSIENT,
            SystemAudioFocus.translate(AudioManager.AUDIOFOCUS_LOSS_TRANSIENT),
        )
        assertEquals(
            FocusChange.LOST_TRANSIENT_CAN_DUCK,
            SystemAudioFocus.translate(AudioManager.AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK),
        )
    }

    @Test
    fun `anything unrecognised is a permanent loss`() {
        // ⚠️ The safe direction, and the choice is deliberate: the worst case is music he
        // has to press play on again, versus a radio that keeps playing over whatever the
        // system thought was important enough to take the audio for.
        assertEquals(FocusChange.LOST, SystemAudioFocus.translate(0))
        assertEquals(FocusChange.LOST, SystemAudioFocus.translate(99))
        assertEquals(FocusChange.LOST, SystemAudioFocus.translate(-99))
    }
}
