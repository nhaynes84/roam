package com.roam.touch.apps

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The shelf is the only route off a home screen that cannot be replaced, so its
 * failure modes are all "he presses Home and is stuck". These tests cover the two that
 * matter: a tile that should not be there, and a tile that is missing.
 */
class AppShelfTest {

    /**
     * The real sailfish launcher set, **captured 2026-08-14** from
     * `cmd package query-activities -a android.intent.action.MAIN -c …LAUNCHER`.
     *
     * ⚠️ The previous capture (2026-08-12) had nine packages and was already stale; the
     * device has twenty. That matters to `it is a shelf, not a drawer`, which is only as
     * strong as the number of installed apps it proves stay off — a fixture that omits the
     * calculator cannot prove the calculator is excluded on purpose. Re-capture this
     * rather than adding to it by hand.
     */
    private val sailfish = listOf(
        InstalledApp("com.android.chrome", "Chrome"),
        InstalledApp("com.android.documentsui", "Files"),
        InstalledApp("com.android.settings", "Settings"),
        InstalledApp("com.google.android.GoogleCamera", "Camera"),
        InstalledApp("com.google.android.apps.photos", "Photos"),
        InstalledApp("com.google.android.apps.tycho", "Google Fi"),
        InstalledApp("com.google.android.calculator", "Calculator"),
        InstalledApp("com.google.android.calendar", "Calendar"),
        InstalledApp("com.google.android.contacts", "Contacts"),
        InstalledApp("com.google.android.deskclock", "Clock"),
        InstalledApp("com.google.android.dialer", "Phone"),
        InstalledApp("com.google.android.gm", "Gmail"),
        InstalledApp("com.google.android.googlequicksearchbox", "Google"),
        InstalledApp("com.google.android.talk", "Hangouts"),
        InstalledApp("com.roam.touch", "ROAM"),
        InstalledApp("com.tailscale.ipn", "Tailscale"),
        InstalledApp("com.termux", "Termux"),
        InstalledApp("com.termux.boot", "Termux:Boot"),
        InstalledApp("com.topjohnwu.magisk", "Magisk"),
        InstalledApp("io.homeassistant.companion.android.minimal", "Home Assistant"),
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
        // Growth here is a product decision, never an accident: this ceiling exists to
        // make an accidental tile fail the build rather than appear on his wrist.
        // 11 -> 12 on 2026-08-14 for the Radio tile. Deliberate, per the rule above.
        assertTrue("shelf grew to ${shelf.size}", shelf.size <= 12)
        val ids = shelf.map { it.id }

        // ★ Twenty packages are installed and six earn a tile. These are the ones that
        // are most obviously *useful* and still stay off — the shelf is short because the
        // device is an appliance, not because nothing else is there.
        listOf(
            "com.google.android.calculator",
            "com.google.android.calendar",
            "com.google.android.contacts",
            "com.google.android.gm",
            "com.google.android.apps.photos",
            "com.google.android.googlequicksearchbox",
            "com.google.android.deskclock",
            "com.google.android.dialer",
            "com.android.documentsui",
            "com.topjohnwu.magisk",
            "com.termux.boot",
        ).forEach { assertFalse("$it reached the shelf", ids.contains(it)) }

        // ⚠️ Nexus IS the home screen. A tile that re-launches it would look like a way
        // out and be a way back to where you already are.
        assertFalse(ids.contains("com.roam.touch"))

        // ★ The real invariant behind the count: every package tile was named on
        // purpose. Nothing reaches the shelf just because it is installed.
        val curated = setOf(
            "com.google.android.GoogleCamera",
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
        // Whichever build is installed, it is the one that cannot render — see `broken`.
        assertTrue(tile.broken)
    }

    @Test
    fun `the companion app is renamed so it cannot be confused with the native tile`() {
        val labels = AppShelf.build(sailfish).map { it.label }
        assertEquals(1, labels.count { it == "Home Assistant" })
        assertTrue(labels.contains("HA Companion"))
    }

    /**
     * ⚠️⚠️ This used to also assert that the tile carried the *reason* — "needs a newer
     * WebView…" — and that assertion is gone on purpose, not by neglect. Owner,
     * 2026-08-15: *"yeah HA companion too, i don't need debug notes on the widget, lol."*
     * The reason now lives in KDoc on `AppShelf`, where the person who has to maintain the
     * shelf reads it and the man wearing the phone does not.
     *
     * What is left is the part that was never text: it is dimmed, and it is **last**.
     */
    @Test
    fun `the companion app is marked broken, and sinks to the bottom`() {
        val shelf = AppShelf.build(sailfish)
        val companion = shelf.single { it.id.startsWith("io.homeassistant") }

        assertTrue(companion.broken)
        assertEquals(shelf.last(), companion)
        // ★ …and it still says what it *is*, in the same two words every other tile gets.
        assertEquals("official app", companion.subtitle)
    }

    @Test
    fun `working tiles keep their declaration order above any broken one`() {
        val ids = ids(sailfish)
        assertEquals(
            listOf(
                AppShelf.HOME_ASSISTANT,
                AppShelf.TORCH,
                "com.google.android.GoogleCamera",
                "com.termux",
                "com.tailscale.ipn",
                "com.android.settings",
                "com.android.chrome",
                "${AppShelf.HUB_BASE}/browse",
                "${AppShelf.HUB_BASE}/browse#Photos",
                "${AppShelf.HUB_BASE}/browse#CAD",
                "${AppShelf.HUB_BASE}/radio",
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
        assertFalse(native.broken)
    }

    // ---- the torch ------------------------------------------------------------------

    @Test
    fun `the torch is an internal switch, never a package`() {
        val torch = AppShelf.build(sailfish).single { it.id == AppShelf.TORCH }
        // ⚠️ There is no flashlight app on Android — on this phone it is a quick-settings
        // tile, which a launcher cannot start. If this ever becomes a PACKAGE tile
        // somebody has invented a package that does not exist.
        assertEquals(TileKind.INTERNAL, torch.kind)
        assertTrue(torch.internal)
        assertFalse(isLaunchableUrl(torch.id))
        assertEquals("Flashlight", torch.label)
    }

    @Test
    fun `the torch sits at the front, beside the other instant tile`() {
        val ids = ids(sailfish)
        assertEquals(AppShelf.TORCH, ids[1])
        // Both are reflexes and neither leaves the app; everything below is a tool you go
        // looking for.
        assertEquals(AppShelf.HOME_ASSISTANT, ids[0])
    }

    @Test
    fun `a device with no flash simply has no torch tile`() {
        // Same rule as an uninstalled package: a capability the hardware does not have is
        // an absent tile, never a tile that fails when pressed. The API 29 emulator is
        // exactly this case.
        val shelf = AppShelf.build(sailfish, hasTorch = false)
        assertFalse(shelf.map { it.id }.contains(AppShelf.TORCH))
        // …and nothing else moves.
        assertEquals(AppShelf.HOME_ASSISTANT, shelf.first().id)
        assertTrue(shelf.map { it.id }.contains("com.google.android.GoogleCamera"))
    }

    @Test
    fun `the torch id can never be confused for a package or a url`() {
        assertTrue(AppShelf.TORCH.startsWith("roam:"))
        assertFalse(isLaunchableUrl(AppShelf.TORCH))
        // Distinct from the other internal tile, or the grid key collides and one of them
        // silently disappears.
        assertFalse(AppShelf.TORCH == AppShelf.HOME_ASSISTANT)
    }

    // ---- the camera -----------------------------------------------------------------

    @Test
    fun `the camera is a plain package tile, resolved at runtime`() {
        val camera = AppShelf.build(sailfish).single { it.id == "com.google.android.GoogleCamera" }
        assertEquals(TileKind.PACKAGE, camera.kind)
        assertFalse(camera.broken)
        assertEquals("photos", camera.subtitle)
        // ★ The label comes from the system, not from here — see the Tailscale test.
        assertEquals("Camera", camera.label)
    }

    @Test
    fun `a device without the pixel camera simply has no camera tile`() {
        // The API 29 emulator has no GoogleCamera. That must be a missing tile and not a
        // hard-coded one that fails at the tap.
        val without = sailfish.filterNot { it.packageId == "com.google.android.GoogleCamera" }
        assertFalse(ids(without).contains("com.google.android.GoogleCamera"))
        assertTrue(ids(without).contains("com.termux"))
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

    /**
     * ★★ **Chrome is a tile like every other tile.** Owner, 2026-08-15: *"the chrome app
     * widget is weird, it tells me a bunch of shit about the old engine i don't need on
     * screen and blows the size out, just leave it as the logo and 'Chrome' label, with
     * the subtext 'search' so it's consistent with all the other widgets."*
     *
     * ⚠️ Chrome still is not `broken`, and that matters more now than it did: `broken` is
     * the only signal left, so using it to mean "old" would dim a working browser and sink
     * it below the tiles that cannot work at all.
     */
    @Test
    fun `chrome is icon, label and subtitle — the same as everything else`() {
        val chrome = AppShelf.build(sailfish).single { it.id == "com.android.chrome" }
        assertFalse(chrome.broken)
        assertEquals("search", chrome.subtitle)
        assertEquals("Chrome", chrome.label)
    }

    /**
     * ⚠️⚠️ The mechanism, not the two tiles that used it. Notes were a general facility —
     * *any* tile could carry a paragraph — so removing them from Chrome and the companion
     * app while leaving the field in place would just wait for the next tile to grow one.
     * There is no note type any more, and this is the assertion that keeps it that way:
     * **every tile on the shelf is icon + label + short subtitle.**
     */
    @Test
    fun `no tile carries prose, and every tile carries a subtitle`() {
        AppShelf.build(sailfish).forEach { tile ->
            val subtitle = tile.subtitle
            assertNotNull("${tile.label} has no subtitle at all", subtitle)
            assertTrue("${tile.label} has an empty subtitle", subtitle!!.isNotBlank())
            // Short enough to sit on one line of a tile — the shelf is three abreast in
            // landscape (`AppsScreenTest`), so a sentence here is a tile of a different size.
            assertTrue("${tile.label} subtitle is a sentence: $subtitle", subtitle.length <= 24)
        }
    }

    @Test
    fun `a working tile never sinks below a broken one`() {
        val shelf = AppShelf.build(sailfish)
        val chrome = shelf.indexOfFirst { it.id == "com.android.chrome" }
        val companion = shelf.indexOfFirst { it.id.startsWith("io.homeassistant.companion") }
        assertTrue("chrome sank below the broken tile", chrome < companion)
    }

    // ---- hub tiles ------------------------------------------------------------------

    private fun links() = AppShelf.build(sailfish).filter { it.kind == TileKind.HUB }

    @Test
    fun `the hub links are present, in order, with their subtitles`() {
        val links = links()
        assertEquals(listOf("Files", "Photos", "CAD", "Radio"), links.map { it.label })
        assertEquals(
            listOf("network drive", "shared album", "models", "internet stations"),
            links.map { it.subtitle },
        )
        assertEquals(
            listOf(
                "${AppShelf.HUB_BASE}/browse",
                "${AppShelf.HUB_BASE}/browse#Photos",
                "${AppShelf.HUB_BASE}/browse#CAD",
                "${AppShelf.HUB_BASE}/radio",
            ),
            links.map { it.id },
        )
    }

    @Test
    fun `the folder is a fragment, because that is the only browse route the hub has`() {
        // ⚠️⚠️ These tiles said `/browse/photos` and `/browse/cad`. Verified against the
        // live hub 2026-08-14: **both 404**. `GET /browse` is the only browse route, and
        // `web/browse.html` keeps its entire navigation state in `window.location.hash`,
        // so a folder is addressed by fragment. Two of the three tiles could not have
        // worked even with the auth fixed.
        val links = links()
        assertTrue("no tile may address a browse sub-path", links.none {
            it.id.startsWith("${AppShelf.HUB_BASE}/browse/")
        })
        // The folder names are the keys of `files.DEFAULT_ROOTS` and are case-sensitive.
        assertEquals("${AppShelf.HUB_BASE}/browse#Photos", links[1].id)
        assertEquals("${AppShelf.HUB_BASE}/browse#CAD", links[2].id)
        // The three BROWSE tiles are the same document, which is why one loaded page with
        // one authenticated request serves all three. ★ Radio is deliberately NOT one of
        // them — it is its own page with its own player, so it is excluded here rather
        // than folded in, and this assertion must never be widened to cover it.
        val browse = links.filter { it.id.startsWith("${AppShelf.HUB_BASE}/browse") }
        assertEquals(3, browse.size)
        assertTrue(browse.all { it.id.substringBefore('#') == "${AppShelf.HUB_BASE}/browse" })
    }

    @Test
    fun `the hub address lives in one place and every link is built from it`() {
        // ★ Change the hub host in build.gradle and all three tiles must follow. If a
        // literal address is ever pasted into a tile, this fails.
        val links = links()
        assertTrue(links.isNotEmpty())
        assertTrue(links.all { it.id.startsWith("${AppShelf.HUB_BASE}/") })
        assertFalse("base must not end in a slash", AppShelf.HUB_BASE.endsWith("/"))
        assertTrue(isLaunchableUrl(AppShelf.HUB_BASE))
    }

    @Test
    fun `no tile ever carries the token in its url`() {
        // ★★ The whole reason these are HUB tiles and not ACTION_VIEW links. The token
        // authenticates every endpoint on the hub; it travels as a request header, so it
        // must never appear in an address that can be stored, logged or suggested.
        // See HubBrowser.authHeaders.
        AppShelf.build(sailfish).forEach {
            assertFalse("token in tile id: ${it.id}", it.id.contains("token="))
        }
    }

    @Test
    fun `a hub tile is not a package tile and never claims one`() {
        val links = links()
        // The id IS the URL, so nothing can ask PackageManager for it by accident and
        // there is no such thing as a hub tile with a missing URL.
        assertTrue(links.all { isLaunchableUrl(it.id) })
        assertTrue(links.none { it.internal })
        assertTrue(links.none { it.broken })
    }

    @Test
    fun `the links are there even on a bare device, because the hub is not the phone`() {
        // A tile that vanishes when the hub is down changes the shape of the only screen
        // he can reach from Home. An error page is a page; a missing tile is a mystery.
        val bare = AppShelf.build(emptyList())
        // Files, Photos, CAD, Radio — all four are the hub's, so none of them depend on
        // anything being installed on the phone.
        assertEquals(4, bare.count { it.kind == TileKind.HUB })
    }

    @Test
    fun `only http urls are loadable, so a bad tile cannot address anything else`() {
        assertTrue(isLaunchableUrl("http://100.67.237.109:8787/browse"))
        assertTrue(isLaunchableUrl("https://example.org"))
        // Anything else is refused before it reaches the WebView.
        assertFalse(isLaunchableUrl(""))
        assertFalse(isLaunchableUrl("100.67.237.109:8787/browse"))
        assertFalse(isLaunchableUrl("file:///sdcard/secret"))
        assertFalse(isLaunchableUrl("intent://evil#Intent;end"))
        assertFalse(isLaunchableUrl(AppShelf.HOME_ASSISTANT))
        assertFalse(isLaunchableUrl(AppShelf.TORCH))
    }

    @Test
    fun `every tile id is unique, because the grid keys on it`() {
        val ids = ids(sailfish)
        assertEquals(ids.size, ids.toSet().size)
    }
}
