package com.roam.touch.apps

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The shelf is the only route off a home screen that cannot be replaced, so its
 * failure modes are all "he presses Home and is stuck". These tests cover the two that
 * matter: a tile that should not be there, and a tile that is missing.
 */
class AppShelfTest {

    /** The real sailfish launcher set, captured 2026-08-12 from `queryIntentActivities`. */
    private val sailfish = listOf(
        InstalledApp("com.android.chrome", "Chrome"),
        InstalledApp("com.android.settings", "Settings"),
        InstalledApp("com.google.android.deskclock", "Clock"),
        InstalledApp("com.google.android.dialer", "Phone"),
        InstalledApp("com.tailscale.ipn", "Tailscale"),
        InstalledApp("com.termux", "Termux"),
        InstalledApp("com.termux.boot", "Termux:Boot"),
        InstalledApp("io.homeassistant.companion.android.minimal", "Home Assistant"),
        InstalledApp("com.roam.touch", "ROAM"),
    )

    private fun ids(installed: List<InstalledApp>) = AppShelf.build(installed).map { it.id }

    @Test
    fun `the native home assistant tile is always first`() {
        assertEquals(AppShelf.HOME_ASSISTANT, AppShelf.build(sailfish).first().id)
        // Even on a device with nothing else installed at all.
        assertEquals(listOf(AppShelf.HOME_ASSISTANT), ids(emptyList()))
    }

    @Test
    fun `it is a shelf, not a drawer`() {
        val shelf = AppShelf.build(sailfish)
        // Chrome, Clock, Phone, Termux:Boot and Nexus itself are all installed and all
        // stay off. Growth here is a product decision, never an accident.
        assertTrue("shelf grew to ${shelf.size}", shelf.size <= 6)
        val ids = shelf.map { it.id }
        assertFalse(ids.contains("com.android.chrome"))
        assertFalse(ids.contains("com.google.android.deskclock"))
        assertFalse(ids.contains("com.termux.boot"))
        // ⚠️ Nexus IS the home screen. A tile that re-launches it would look like a way
        // out and be a way back to where you already are.
        assertFalse(ids.contains("com.roam.touch"))
    }

    @Test
    fun `an uninstalled app simply stops appearing`() {
        val withoutTermux = sailfish.filterNot { it.packageId == "com.termux" }
        assertFalse(ids(withoutTermux).contains("com.termux"))
        // …and the rest of the shelf is unaffected.
        assertTrue(ids(withoutTermux).contains("com.tailscale.ipn"))
    }

    @Test
    fun `either home assistant build resolves to the same tile`() {
        val full = sailfish.map {
            if (it.packageId.endsWith(".minimal"))
                InstalledApp("io.homeassistant.companion.android", "Home Assistant") else it
        }
        val tile = AppShelf.build(full).single { it.id.startsWith("io.homeassistant") }
        assertEquals("io.homeassistant.companion.android", tile.id)
        assertNotNull(tile.note)
    }

    @Test
    fun `the companion app is renamed so it cannot be confused with the native tile`() {
        val labels = AppShelf.build(sailfish).map { it.label }
        assertEquals(1, labels.count { it == "Home Assistant" })
        assertTrue(labels.contains("HA Companion"))
    }

    @Test
    fun `the companion app is marked broken with a reason, and sinks to the bottom`() {
        val shelf = AppShelf.build(sailfish)
        val companion = shelf.single { it.id.startsWith("io.homeassistant") }

        assertTrue(companion.broken)
        assertEquals(shelf.last(), companion)

        // ★ The reason has to be specific enough that he does not debug it again at 3am.
        val detail = companion.note!!.detail
        assertTrue("reason was: $detail", detail.contains("WebView"))
        assertTrue("reason was: $detail", companion.note!!.chip.isNotBlank())
    }

    @Test
    fun `working tiles keep their declaration order above any broken one`() {
        val ids = ids(sailfish)
        assertEquals(
            listOf(
                AppShelf.HOME_ASSISTANT,
                "com.termux",
                "com.tailscale.ipn",
                "com.android.settings",
                "io.homeassistant.companion.android.minimal",
            ),
            ids,
        )
    }

    @Test
    fun `the native tile launches no package`() {
        val native = AppShelf.build(sailfish).first()
        assertTrue(native.internal)
        assertNull(native.note)
    }

    @Test
    fun `system labels are used, not hard-coded ones`() {
        // Tailscale renaming itself must not need a code change here.
        val renamed = sailfish.map {
            if (it.packageId == "com.tailscale.ipn") it.copy(label = "Tailscale VPN") else it
        }
        val tile = AppShelf.build(renamed).single { it.id == "com.tailscale.ipn" }
        assertEquals("Tailscale VPN", tile.label)
    }
}
