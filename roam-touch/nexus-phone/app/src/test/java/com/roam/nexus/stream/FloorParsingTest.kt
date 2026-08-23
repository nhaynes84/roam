package com.roam.nexus.stream

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The payloads below were captured off the LIVE hub on 2026-08-23, not written from
 * imagination — a test invented alongside the parser agrees with the parser's own
 * assumptions and proves nothing about the wire.
 */
class FloorParsingTest {

    private val monitorIdle =
        """{"type":"floor","open":true,"sender":"TEST-nursery","talker":null,""" +
        """"holder":"TEST-nursery","receivers":["TEST-phone"]}"""

    private val phoneTalking =
        """{"type":"floor","open":true,"sender":"TEST-nursery","talker":"TEST-phone",""" +
        """"holder":"TEST-phone","receivers":["TEST-phone"]}"""

    @Test fun `open is a json boolean not a string`() {
        assertTrue(parseFloor(monitorIdle)!!.open)
    }

    @Test fun `an absent talker is null, never the four characters null`() {
        val floor = parseFloor(monitorIdle)!!
        assertNull(floor.talker)
        assertEquals("TEST-nursery", floor.holder)
    }

    @Test fun `the sender holds the floor while nobody is talking`() {
        val floor = parseFloor(monitorIdle)!!
        assertTrue(floor.micLive("TEST-nursery"))
        assertFalse(floor.micLive("TEST-phone"))
        assertTrue(floor.shouldPlay("TEST-phone"))
        assertFalse(floor.shouldPlay("TEST-nursery"))
    }

    @Test fun `ptt flips who is live and who plays`() {
        val floor = parseFloor(phoneTalking)!!
        assertTrue(floor.micLive("TEST-phone"))
        assertFalse(floor.micLive("TEST-nursery"))
        // the monitor now HEARS the person talking back
        assertTrue(floor.shouldPlay("TEST-nursery"))
        assertFalse(floor.shouldPlay("TEST-phone"))
    }

    @Test fun `a third listener hears the talker too`() {
        val floor = parseFloor(phoneTalking)!!
        assertTrue(floor.shouldPlay("TEST-tablet"))
    }

    @Test fun `a closed channel means nobody plays and nobody is live`() {
        val floor = parseFloor(
            """{"type":"floor","open":false,"sender":null,"talker":null,""" +
            """"holder":null,"receivers":[]}"""
        )!!
        assertFalse(floor.open)
        assertFalse(floor.shouldPlay("TEST-phone"))
        assertFalse(floor.micLive("TEST-phone"))
    }

    @Test fun `a non-floor frame is not a floor`() {
        assertNull(parseFloor("""{"type":"denied","detail":"x is already talking"}"""))
        assertNull(parseFloor("not json at all"))
    }
}
