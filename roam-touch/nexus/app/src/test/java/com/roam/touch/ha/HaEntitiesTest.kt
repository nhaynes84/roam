package com.roam.touch.ha

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Everything the panel decides about a Home Assistant entity, tested exhaustively —
 * because this is the half that *can* be tested without his token, and the half where a
 * wrong answer has physical consequences (see the lock).
 */
class HaEntitiesTest {

    // -- naming -------------------------------------------------------------

    @Test
    fun `friendly name is used when HA supplies one`() {
        assertEquals("Kitchen", HaFx.state(HaFx.LIGHT_ON).friendlyName)
    }

    @Test
    fun `an entity with no friendly name gets a readable one, never a raw id`() {
        // "fan.office_ceiling" on a forearm at arm's length has to read as words.
        assertEquals("Office Ceiling", HaFx.state(HaFx.UNNAMED_FAN).friendlyName)
    }

    @Test
    fun `domain is everything before the dot`() {
        assertEquals("light", HaFx.state(HaFx.LIGHT_ON).domain)
        assertEquals("lock", HaFx.state(HaFx.LOCK_LOCKED).domain)
        assertEquals("", HaEntities.domainOf("nonsense"))
    }

    // -- what a tap does ----------------------------------------------------

    @Test
    fun `a light toggles both ways`() {
        assertEquals(
            HaEntities.Action("light", "turn_off"),
            HaEntities.actionFor(HaFx.state(HaFx.LIGHT_ON)),
        )
        assertEquals(
            HaEntities.Action("light", "turn_on"),
            HaEntities.actionFor(HaFx.state(HaFx.LIGHT_OFF)),
        )
    }

    @Test
    fun `switches and fans use the same on-off services`() {
        assertEquals(
            HaEntities.Action("switch", "turn_off"),
            HaEntities.actionFor(HaFx.state(HaFx.SWITCH_ON)),
        )
        assertEquals(
            HaEntities.Action("fan", "turn_on"),
            HaEntities.actionFor(HaFx.state(HaFx.UNNAMED_FAN)),
        )
    }

    @Test
    fun `a locked door unlocks and an unlocked door locks`() {
        // ⚠️ The regression this test exists for: a generic homeassistant.toggle reads
        // `locked` as "not on" and would have UNLOCKED a locked front door on tap.
        assertEquals(
            HaEntities.Action("lock", "unlock"),
            HaEntities.actionFor(HaFx.state(HaFx.LOCK_LOCKED)),
        )
        val unlocked = HaFx.state("""{"entity_id":"lock.front_door","state":"unlocked"}""")
        assertEquals(HaEntities.Action("lock", "lock"), HaEntities.actionFor(unlocked))
    }

    @Test
    fun `a cover opens and closes rather than turning on and off`() {
        assertEquals(
            HaEntities.Action("cover", "close_cover"),
            HaEntities.actionFor(HaFx.state(HaFx.COVER_OPEN)),
        )
        val closed = HaFx.state("""{"entity_id":"cover.garage","state":"closed"}""")
        assertEquals(HaEntities.Action("cover", "open_cover"), HaEntities.actionFor(closed))
    }

    @Test
    fun `a scene only ever turns on`() {
        // Its `state` is a timestamp, not on/off. Nothing may read that as "already on".
        assertEquals(
            HaEntities.Action("scene", "turn_on"),
            HaEntities.actionFor(HaFx.state(HaFx.SCENE)),
        )
    }

    @Test
    fun `a sensor is read-only`() {
        assertNull(HaEntities.actionFor(HaFx.state(HaFx.SENSOR)))
        assertFalse(HaEntities.isActionable(HaFx.state(HaFx.SENSOR)))
    }

    @Test
    fun `an unavailable entity is not tappable`() {
        val porch = HaFx.state(HaFx.UNAVAILABLE_LIGHT)
        assertTrue(HaEntities.isUnavailable(porch.state))
        assertFalse(HaEntities.isActionable(porch))
    }

    // -- what it says -------------------------------------------------------

    @Test
    fun `a dimmed light shows its brightness, because on and on at four percent differ`() {
        assertEquals("on · 50%", HaEntities.stateText(HaFx.state(HaFx.LIGHT_ON)))
    }

    @Test
    fun `brightness never rounds down to zero on a light that is on`() {
        val dim = HaFx.state("""{"entity_id":"light.x","state":"on","attributes":{"brightness":1}}""")
        assertEquals("on · 1%", HaEntities.stateText(dim))
    }

    @Test
    fun `an off light says off, with no percentage`() {
        assertEquals("off", HaEntities.stateText(HaFx.state(HaFx.LIGHT_OFF)))
    }

    @Test
    fun `a sensor carries its unit`() {
        assertEquals("21.4 °C", HaEntities.stateText(HaFx.state(HaFx.SENSOR)))
    }

    @Test
    fun `a scene says what tapping it will do`() {
        assertEquals("tap to run", HaEntities.stateText(HaFx.state(HaFx.SCENE)))
    }

    @Test
    fun `unavailable is shown as itself, never dressed up as off`() {
        assertEquals("unavailable", HaEntities.stateText(HaFx.state(HaFx.UNAVAILABLE_LIGHT)))
    }

    // -- which entities get tiles -------------------------------------------

    @Test
    fun `a default install is filtered down to things worth touching`() {
        val tiles = HaEntities.tiles(HaFx.states(HaFx.ALL)).map { it.entityId }
        assertFalse(tiles.contains("device_tracker.pixel"))
        assertFalse(tiles.contains("sun.sun"))
        assertFalse(tiles.contains("sensor.office_temperature"))
        assertTrue(tiles.contains("light.kitchen"))
        assertTrue(tiles.contains("lock.front_door"))
    }

    @Test
    fun `tiles group by domain then sort by name`() {
        val tiles = HaEntities.tiles(HaFx.states(HaFx.ALL)).map { it.entityId }
        assertEquals(
            listOf(
                "light.desk_lamp", "light.kitchen", "light.porch",   // lights, by name
                "switch.roaster",
                "fan.office_ceiling",
                "cover.garage",
                "lock.front_door",
                "scene.goodnight",
            ),
            tiles,
        )
    }

    @Test
    fun `an unavailable entity still gets a tile`() {
        // ★ Hiding it would turn a broken bulb into a missing tile, which reads as
        // "I never had one" — the exact silence this device exists to prevent.
        assertTrue(HaEntities.tiles(HaFx.states(HaFx.ALL)).any { it.entityId == "light.porch" })
    }

    @Test
    fun `the grid is capped so a big install cannot bury the panel`() {
        val many = (1..40).map { HaFx.state("""{"entity_id":"light.l$it","state":"off"}""") }
        assertEquals(12, HaEntities.tiles(many).size)
        assertEquals(4, HaEntities.tiles(many, limit = 4).size)
    }

    @Test
    fun `pinned entities win outright, in his order, including read-only ones`() {
        val pinned = listOf("sensor.office_temperature", "lock.front_door", "light.kitchen")
        assertEquals(pinned, HaEntities.tiles(HaFx.states(HaFx.ALL), pinned).map { it.entityId })
    }

    @Test
    fun `a pinned entity that does not exist is skipped, not rendered empty`() {
        val tiles = HaEntities.tiles(HaFx.states(HaFx.ALL), listOf("light.ghost", "light.kitchen"))
        assertEquals(listOf("light.kitchen"), tiles.map { it.entityId })
    }

    @Test
    fun `the pinned config string tolerates the way a human types it`() {
        assertEquals(
            listOf("light.kitchen", "lock.front_door", "switch.desk"),
            HaEntities.parsePinned(" light.kitchen, lock.front_door ,\nswitch.desk , "),
        )
        assertEquals(emptyList<String>(), HaEntities.parsePinned(""))
        assertEquals(emptyList<String>(), HaEntities.parsePinned(null))
        // Something that is not an entity id is dropped rather than 404-ing later.
        assertEquals(emptyList<String>(), HaEntities.parsePinned("kitchen"))
    }
}
