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
        assertEquals(AppShelf.HOME_ASSISTANT, AppShelf.build(emptyList()).first().id)
    }

    @Test
    fun `it is a shelf, not a drawer`() {
        val shelf = AppShelf.build(sailfish)
        // Clock, Phone, Termux:Boot and Nexus itself are all installed and all stay off.
        // Growth here is a product decision, never an accident: this ceiling exists to
        // make an accidental tile fail the build rather than appear on his wrist.
        assertTrue("shelf grew to ${shelf.size}", shelf.size <= 9)
        val ids = shelf.map { it.id }
        assertFalse(ids.contains("com.google.android.deskclock"))
        assertFalse(ids.contains("com.google.android.dialer"))
        assertFalse(ids.contains("com.termux.boot"))
        // ⚠️ Nexus IS the home screen. A tile that re-launches it would look like a way
        // out and be a way back to where you already are.
        assertFalse(ids.contains("com.roam.touch"))

        // ★ The real invariant behind the count: every package tile was named on
        // purpose. Nothing reaches the shelf just because it is installed.
        val curated = setOf(
            "com.termux",
            "com.tailscale.ipn",
            "com.android.settings",
            "com.android.chrome",
            "io.homeassistant.companion.android",
            "io.homeassistant.companion.android.minimal",
        )
        val fromPackages = shelf.filter { it.kind == TileKind.PACKAGE }.map { it.id }
        assertTrue("uncurated tile: $fromPackages", curated.containsAll(fromPackages))
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
                "com.android.chrome",
                "${AppShelf.HUB_BASE}/browse",
                "${AppShelf.HUB_BASE}/browse/photos",
                "${AppShelf.HUB_BASE}/browse/cad",
                "io.homeassistant.companion.android.minimal",
            ),
            ids,
        )
    }

    @Test
    fun `the native tile launches no package`() {
        val native = AppShelf.build(sailfish).first()
        assertTrue(native.internal)
        assertEquals(TileKind.INTERNAL, native.kind)
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

    // ---- Chrome -------------------------------------------------------------------

    @Test
    fun `chrome warns about its 2019 engine before the tap, but is not broken`() {
        val chrome = AppShelf.build(sailfish).single { it.id == "com.android.chrome" }
        val note = chrome.note!!

        // ★ It works — it just cannot render every site. A caution must not be dressed
        // as a failure, or the one thing that means "do not bother" stops meaning it.
        assertFalse(note.broken)
        assertFalse(chrome.broken)
        assertTrue("reason was: ${note.detail}", note.detail.contains("2019"))
        assertTrue(note.chip.isNotBlank())
        assertEquals("search", chrome.subtitle)
    }

    @Test
    fun `a caution note does not sink a tile to the bottom`() {
        val shelf = AppShelf.build(sailfish)
        val chrome = shelf.indexOfFirst { it.id == "com.android.chrome" }
        val companion = shelf.indexOfFirst { it.id.startsWith("io.homeassistant.companion") }
        assertTrue("chrome sank below the broken tile", chrome < companion)
    }

    // ---- URL tiles ----------------------------------------------------------------

    @Test
    fun `the hub links are present, in order, with their subtitles`() {
        val links = AppShelf.build(sailfish).filter { it.kind == TileKind.URL }
        assertEquals(listOf("Files", "Photos", "CAD"), links.map { it.label })
        assertEquals(
            listOf("network drive", "shared album", "models"),
            links.map { it.subtitle },
        )
        assertEquals(
            listOf(
                "${AppShelf.HUB_BASE}/browse",
                "${AppShelf.HUB_BASE}/browse/photos",
                "${AppShelf.HUB_BASE}/browse/cad",
            ),
            links.map { it.id },
        )
    }

    @Test
    fun `the hub address lives in one place and every link is built from it`() {
        // ★ Change the hub host in build.gradle and all three tiles must follow. If a
        // literal address is ever pasted into a tile, this fails.
        val links = AppShelf.build(sailfish).filter { it.kind == TileKind.URL }
        assertTrue(links.isNotEmpty())
        assertTrue(links.all { it.id.startsWith("${AppShelf.HUB_BASE}/") })
        assertFalse("base must not end in a slash", AppShelf.HUB_BASE.endsWith("/"))
        assertTrue(isLaunchableUrl(AppShelf.HUB_BASE))
    }

    @Test
    fun `a link tile is not a package tile and never claims one`() {
        val links = AppShelf.build(sailfish).filter { it.kind == TileKind.URL }
        // The id IS the URL, so nothing can ask PackageManager for it by accident and
        // there is no such thing as a URL tile with a missing URL.
        assertTrue(links.all { isLaunchableUrl(it.id) })
        assertTrue(links.none { it.internal })
        assertTrue(links.none { it.broken })
    }

    @Test
    fun `the links are there even on a bare device, because the hub is not the phone`() {
        // A tile that vanishes when the hub is down changes the shape of the only screen
        // he can reach from Home. A 404 is a page; a missing tile is a mystery.
        val bare = AppShelf.build(emptyList())
        assertEquals(3, bare.count { it.kind == TileKind.URL })
    }

    @Test
    fun `only http urls are launchable, so a bad tile cannot fire an arbitrary intent`() {
        assertTrue(isLaunchableUrl("http://100.67.237.109:8787/browse"))
        assertTrue(isLaunchableUrl("https://example.org"))
        // Anything else is refused before it becomes an Intent — the home screen is the
        // one place where an ActivityNotFoundException costs the device its whole UI.
        assertFalse(isLaunchableUrl(""))
        assertFalse(isLaunchableUrl("100.67.237.109:8787/browse"))
        assertFalse(isLaunchableUrl("file:///sdcard/secret"))
        assertFalse(isLaunchableUrl("intent://evil#Intent;end"))
        assertFalse(isLaunchableUrl(AppShelf.HOME_ASSISTANT))
    }

    @Test
    fun `every tile id is unique, because the grid keys on it`() {
        val ids = ids(sailfish)
        assertEquals(ids.size, ids.toSet().size)
    }
}
