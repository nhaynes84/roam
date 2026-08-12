package com.roam.touch.channels.controls

import android.view.KeyEvent
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * ⚠️ Bindings survive a process death, and a corrupt line is dropped rather than guessed.
 *
 * This app is routinely killed — it is a launcher under doze — so a mapping that lived
 * only in memory would have to be re-taught every time Android felt like it. And the
 * failure mode matters more than usual: a *wrong* binding can open a microphone, so
 * anything unparseable is discarded, never approximated.
 */
class ControlStoreTest {

    private val tap = HeadsetGesture(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE)
    private val held = HeadsetGesture(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE, longPress = true)

    private fun roundTrip(vararg profiles: HeadsetProfile): Map<String, HeadsetProfile> =
        ControlStore.Codec.decode(
            ControlStore.Codec.encode(profiles.associateBy { it.address })
        )

    @Test
    fun `a mapped headset survives being written out and read back`() {
        val profile = HeadsetProfile("80:99:E7:DE:66:E6", "WH-1000XM6")
            .bind(tap, ControlAction.PUSH_TO_TALK)
            .bind(held, ControlAction.CANCEL)
            .copy(introduced = true)

        assertEquals(profile, roundTrip(profile)["80:99:E7:DE:66:E6"])
    }

    /** ⚠️ Addresses are full of colons and names are full of spaces and dashes. */
    @Test
    fun `addresses and names with punctuation survive`() {
        val profile = HeadsetProfile("aa:bb:cc:dd:ee:ff", "Nick's Jabra Elite 8 - right")
            .bind(HeadsetGesture(KeyEvent.KEYCODE_VOLUME_UP), ControlAction.NEXT_CHANNEL)

        val back = roundTrip(profile)["aa:bb:cc:dd:ee:ff"]!!
        assertEquals("aa:bb:cc:dd:ee:ff", back.address)
        assertEquals("Nick's Jabra Elite 8 - right", back.name)
        assertTrue(back.capturesVolume)
    }

    /** ⚠️⚠️ Two headsets, two mappings, and neither may bleed into the other. */
    @Test
    fun `several headsets are kept apart`() {
        val buds = HeadsetProfile("11:22:33:44:55:66", "Pixel Buds")
            .bind(tap, ControlAction.PUSH_TO_TALK)
        val jabra = HeadsetProfile("aa:bb:cc:dd:ee:ff", "Jabra Elite")
            .bind(HeadsetGesture(KeyEvent.KEYCODE_MEDIA_NEXT), ControlAction.NEXT_CHANNEL)

        val back = roundTrip(buds, jabra)
        assertEquals(2, back.size)
        assertEquals(tap, back["11:22:33:44:55:66"]!!.boundTo(ControlAction.PUSH_TO_TALK))
        assertNull(back["aa:bb:cc:dd:ee:ff"]!!.boundTo(ControlAction.PUSH_TO_TALK))
    }

    @Test
    fun `a headset with nothing bound still round-trips`() {
        val bare = HeadsetProfile("11:22", "Bare", introduced = true)
        val back = roundTrip(bare)["11:22"]!!
        assertEquals(emptyMap<HeadsetGesture, ControlAction>(), back.bindings)
        assertTrue("he has already been asked about it", back.introduced)
    }

    @Test
    fun `nothing stored decodes to nothing, not to a crash`() {
        assertEquals(emptyMap<String, HeadsetProfile>(), ControlStore.Codec.decode(null))
        assertEquals(emptyMap<String, HeadsetProfile>(), ControlStore.Codec.decode(""))
    }

    /**
     * ⚠️⚠️ A line that cannot be read is **dropped**. Half-parsing it could bind a
     * microphone to a gesture he never chose, which is the one outcome worth failing
     * loudly-quietly for: no binding at all, and the on-screen button still works.
     */
    @Test
    fun `unreadable entries are discarded rather than guessed at`() {
        val salvaged = ControlStore.Codec.decode(
            listOf(
                "11:22|Good|1|85~0=PUSH_TO_TALK",
                "nonsense",
                "33:44|Truncated|1",
                "55:66|BadAction|1|85~0=SET_FIRE_TO_IT",
                "77:88|BadCode|1|banana~0=PUSH_TO_TALK",
                "|NoAddress|1|85~0=CANCEL",
            ).joinToString("\n")
        )

        // ★ A truncated line is dropped whole. It is not repaired into "a headset with no
        // bindings", because a record we cannot read is not a record we should act on.
        assertEquals("only the readable headsets survive", setOf("11:22", "55:66", "77:88"),
            salvaged.keys)
        assertEquals(tap, salvaged["11:22"]!!.boundTo(ControlAction.PUSH_TO_TALK))
        assertEquals("an unknown action binds nothing", emptyMap<HeadsetGesture, ControlAction>(),
            salvaged["55:66"]!!.bindings)
        assertEquals("an unreadable key code binds nothing",
            emptyMap<HeadsetGesture, ControlAction>(), salvaged["77:88"]!!.bindings)
    }

    @Test
    fun `a pipe in a headset name cannot corrupt the record after it`() {
        val sneaky = HeadsetProfile("11:22", "Buds|1|85~0=PUSH_TO_TALK")
            .copy(introduced = false)
        val back = roundTrip(sneaky)["11:22"]!!
        assertTrue("the separator must not survive into the name", '|' !in back.name)
        assertEquals("and it must not have injected a binding", 0, back.bindings.size)
        assertTrue(!back.introduced)
    }
}
