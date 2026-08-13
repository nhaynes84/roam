package com.roam.touch.channels.controls

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * ★★ Tap for volume, hold to talk — on the only control on this device that can tell the
 * difference. See [VolumePtt] for why the earbud and the wired hook both cannot.
 */
class VolumePttTest {

    private val key = VolumePtt()

    /** ⚠️ The whole reason it acts on release: at the down edge a tap and a hold look identical. */
    @Test
    fun `the down edge of a fresh press decides nothing`() {
        assertEquals(VolumeGesture.Nothing, key.onDown(repeat = 0, micOpen = false))
    }

    @Test
    fun `a tap adjusts the volume`() {
        key.onDown(repeat = 0, micOpen = false)
        assertEquals(VolumeGesture.VolumeDown, key.onUp(micOpen = false))
    }

    @Test
    fun `holding it starts talking`() {
        key.onDown(repeat = 0, micOpen = false)
        assertEquals(VolumeGesture.StartTalking, key.onDown(repeat = 1, micOpen = false))
    }

    /** ⚠️ And holding must not adjust the volume when he finally lets go. */
    @Test
    fun `letting go of a hold stops talking and does not touch the volume`() {
        key.onDown(repeat = 0, micOpen = false)
        key.onDown(repeat = 1, micOpen = false)
        assertEquals(VolumeGesture.StopTalking, key.onUp(micOpen = true))
    }

    /** A long hold repeats; only the first repeat may open a microphone. */
    @Test
    fun `further repeats do not start a second recording`() {
        key.onDown(repeat = 0, micOpen = false)
        assertEquals(VolumeGesture.StartTalking, key.onDown(repeat = 1, micOpen = false))
        for (r in 2..20) {
            assertEquals(
                "repeat $r must not re-open the mic",
                VolumeGesture.Nothing,
                key.onDown(repeat = r, micOpen = true),
            )
        }
    }

    /**
     * ⚠️⚠️ **A control that can only stop what it personally started is half a control.**
     * If a recording is running because he tapped an earbud or held the on-screen mic,
     * this key must still close it — the mic must always be closable by whatever is to
     * hand.
     */
    @Test
    fun `it stops a recording it did not start`() {
        key.onDown(repeat = 0, micOpen = true)
        assertEquals(VolumeGesture.StopTalking, key.onUp(micOpen = true))
    }

    /** ⚠️ …and that press must not also knock the volume down on the way past. */
    @Test
    fun `stopping someone else's recording does not also change the volume`() {
        key.onDown(repeat = 0, micOpen = true)
        assertEquals(VolumeGesture.StopTalking, key.onUp(micOpen = true))
        // The next tap, with nothing recording, is a plain volume tap again.
        key.onDown(repeat = 0, micOpen = false)
        assertEquals(VolumeGesture.VolumeDown, key.onUp(micOpen = false))
    }

    /** Two taps in a row are two volume steps, not a stuck hold. */
    @Test
    fun `consecutive taps are consecutive volume steps`() {
        repeat(3) {
            key.onDown(repeat = 0, micOpen = false)
            assertEquals(VolumeGesture.VolumeDown, key.onUp(micOpen = false))
        }
    }

    /** ⚠️ Focus taken mid-hold must not leave it believing the key is still down. */
    @Test
    fun `a reset mid-hold leaves the next tap behaving as a tap`() {
        key.onDown(repeat = 0, micOpen = false)
        key.onDown(repeat = 1, micOpen = false)
        key.reset()

        key.onDown(repeat = 0, micOpen = false)
        assertEquals(VolumeGesture.VolumeDown, key.onUp(micOpen = false))
    }
}
