package com.roam.touch.channels.ui

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * The breakpoint, on the two window sizes that actually exist.
 *
 * ⚠️ sailfish is the device. Its numbers are not a round example — they are the whole
 * requirement, and a breakpoint that put 731 dp in [Shell.Narrow] would mean the owner
 * rotated his arm and got the portrait layout back.
 */
class ShellTest {

    @Test
    fun `sailfish landscape is Wide and sailfish portrait is Narrow`() {
        assertEquals(Shell.Wide, Shell.of(731))
        assertEquals(Shell.Narrow, Shell.of(411))
    }

    @Test
    fun `the boundary is inclusive and does not wobble`() {
        assertEquals(Shell.Narrow, Shell.of(Shell.WIDE_MIN_WIDTH_DP - 1))
        assertEquals(Shell.Wide, Shell.of(Shell.WIDE_MIN_WIDTH_DP))
    }

    /**
     * A tiny window is Narrow whatever its aspect ratio. The rail needs ~196 dp of its
     * own plus a thread worth reading; splitting 480 dp into two useless columns is worse
     * than one usable one.
     */
    @Test
    fun `a short wide window that cannot hold two panes stays Narrow`() {
        assertEquals(Shell.Narrow, Shell.of(480))
    }
}
