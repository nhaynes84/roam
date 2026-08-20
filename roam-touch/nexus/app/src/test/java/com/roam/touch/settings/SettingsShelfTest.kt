package com.roam.touch.settings

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * ★ The settings shelf as *data*, which is the whole design of it.
 *
 * Owner asked for a place to put settings and one setting in it. What makes this a place
 * rather than a screen is that the screen loops over this list and knows nothing else —
 * setting #2 is one declaration here, and these tests are what say so.
 */
class SettingsShelfTest {

    @Test
    fun `the headset is the first setting, and it is present`() {
        assertEquals(SettingsShelf.HEADSET, SettingsShelf.WIDGETS.first().id)
        assertEquals("Headset buttons", SettingsShelf.WIDGETS.first().label)
    }

    /**
     * ⚠️⚠️ It moved off the rail on 2026-08-15 and this is the only place it now lives.
     * With the handset microphone dead at the HAL, push-to-talk records through a
     * Bluetooth headset — a shelf that loses this entry is a device that cannot be told
     * which button talks.
     */
    @Test
    fun `the headset setting cannot quietly disappear`() {
        assertTrue(SettingsShelf.WIDGETS.any { it.id == SettingsShelf.HEADSET })
    }

    /** The grid keys on the id, so a duplicate would silently drop a widget. */
    @Test
    fun `every widget id is unique`() {
        val ids = SettingsShelf.WIDGETS.map { it.id }
        assertEquals(ids.size, ids.toSet().size)
    }

    /**
     * ⚠️ The same rule the app shelf now has: **no prose on a widget.** Owner, on the tiles
     * that used to carry a paragraph: *"i don't need debug notes on the widget, lol."* A
     * settings shelf built the day after that must not reintroduce them, and a subtitle
     * that has grown into a sentence is how it would start.
     */
    @Test
    fun `a widget says what it is in a few words, never a sentence`() {
        SettingsShelf.WIDGETS.forEach {
            assertTrue("${it.label} has no subtitle", it.subtitle.isNotBlank())
            assertTrue("${it.label} subtitle is a sentence: ${it.subtitle}", it.subtitle.length <= 24)
            assertTrue("${it.label} subtitle is punctuated prose", !it.subtitle.contains('.'))
        }
    }

    /**
     * ★ Every widget carries its own glyph, which is what keeps growth to one edit: if the
     * icon lived in a `when` inside the screen, adding a setting would be two changes in
     * two files and the second is the one that gets forgotten.
     */
    @Test
    fun `every widget brings its own icon`() {
        SettingsShelf.WIDGETS.forEach {
            assertTrue("${it.label} has a blank glyph", it.icon.defaultWidth.value > 0f)
        }
    }
}
