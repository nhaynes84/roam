package com.roam.touch.apps

import com.roam.touch.BuildConfig

/**
 * How a tile is opened. The UI dispatches on this and on nothing else.
 *
 * ⚠️ Deliberately about *mechanism*, not about content: [PACKAGE] means "ask the system
 * for this package's launch intent", [HUB] means "open in this app's own WebView, with
 * the hub's bearer token on the request", [INTERNAL] means "a screen or a switch this app
 * owns". Adding a kind is adding a way to open something, which is why there are only
 * three.
 *
 * ⚠️⚠️ [HUB] replaced an earlier `URL` kind that fired `ACTION_VIEW` and let the system
 * pick a browser, and the replacement is the whole point rather than a refactor. The hub
 * refuses `/browse` without a bearer token, so the tile answered *"bearer token
 * required"*; the only way to authenticate an `ACTION_VIEW` is `?token=` in the URL, and
 * that token authenticates every endpoint on the hub — it must not be written into
 * another app's history, omnibox suggestions or logs. A WebView takes the token as a
 * request *header*, so there is no URL to leak. There is deliberately no general "open
 * any URL" mechanism left: it cannot be used wrongly if it does not exist.
 */
enum class TileKind { PACKAGE, INTERNAL, HUB }

/**
 * What a launchable thing looks like to the panel.
 *
 * [id] is the package name for anything the system launches, a `roam:` id for a screen or
 * a switch this app owns, or — for a [TileKind.HUB] tile — the URL itself. A hub tile
 * carries no second `url` field on purpose: one field means there is no such thing as a
 * hub tile with a missing URL, and the grid key stays unique for free. The UI never
 * branches on the label.
 */
data class AppTile(
    val id: String,
    val label: String,
    val subtitle: String?,
    val note: TileNote? = null,
    val kind: TileKind = TileKind.PACKAGE,
) {
    val broken: Boolean get() = note?.broken == true

    /** Drawn by this app, so it has no package icon and never touches PackageManager. */
    val internal: Boolean get() = kind == TileKind.INTERNAL
}

/**
 * ★ A tile that will not work says so *before* the tap.
 *
 * Standing law: stale/dead state is surfaced up front, never discovered by clicking.
 * [chip] is the two-word badge; [detail] is the one-line reason, and it has to be
 * specific enough to stop him debugging it a second time.
 *
 * `broken = false` is a *caution*: the tile works, but it has a limit worth knowing
 * before the tap rather than after. It stays in normal sort order and is not dimmed.
 */
data class TileNote(val chip: String, val detail: String, val broken: Boolean = true)

/** A launchable package as the system reports it. Resolved by [AppCatalog] on device. */
data class InstalledApp(val packageId: String, val label: String)

/**
 * ★ Whether a hub tile addresses something we are willing to load at all, decided
 * without touching Android.
 *
 * Kept pure so the "a bad URL is refused rather than followed" rule is covered by a plain
 * JVM test. It is no longer guarding against an ActivityNotFoundException — nothing here
 * fires an intent any more — but it still guards the WebView against a tile whose id is a
 * `file://` or `intent://` URL, and it is what keeps a `roam:` id from ever being
 * mistaken for something to load.
 */
fun isLaunchableUrl(url: String): Boolean =
    url.startsWith("http://") || url.startsWith("https://")

/**
 * ★ The shelf is a short, deliberate list — not an app drawer.
 *
 * Nexus is the home screen, so without this there is literally no route to anything
 * else on the phone: press Home and you are in Channels forever. That is the problem
 * being solved, and it is solved by a handful of tiles, not by enumerating 188 packages.
 *
 * ⚠️ The candidate list below names *what belongs on a worn appliance*; it never names
 * a component or an activity. Everything else — is it installed, what is it called, what
 * icon does it have, how do you launch it — is asked of the system at runtime, so a
 * package that is uninstalled simply stops appearing and one that changes its label or
 * its launcher activity keeps working. Alternates exist for exactly that reason: Home
 * Assistant ships as `…android` or `…android.minimal` depending on the build installed.
 */
object AppShelf {

    /** The internal tile id for the native Home Assistant screen. */
    const val HOME_ASSISTANT = "roam:ha"

    /**
     * The internal tile id for the torch.
     *
     * ⚠️ There is no flashlight *app* on Android and never was — on this phone it is a
     * quick-settings tile (`sysui_qs_tiles` lists `flashlight`), which is a SystemUI
     * control and not something a launcher can start. So it cannot be a [TileKind.PACKAGE]
     * tile however much it looks like one; it is this app calling
     * `CameraManager.setTorchMode`. See [Torch].
     */
    const val TORCH = Torch.TILE_ID

    /**
     * ★ The hub's address lives in exactly one place, and this is not it.
     *
     * It is configured once in `build.gradle` (`roam.hub.host` / `roam.hub.port`, both
     * overridable from local.properties or the environment) and reaches every link tile
     * through here. Change it there, rebuild, and all three tiles follow — there is no
     * second copy of the tailnet address to hunt down. No trailing slash: the paths
     * below supply their own.
     */
    val HUB_BASE: String = "http://${BuildConfig.HUB_HOST}:${BuildConfig.HUB_PORT}"

    /**
     * ⚠️ Verified on sailfish 2026-08-12, do not re-diagnose: the HA companion app is
     * installed, doze-exempt and pointed at a server that answers — and it still paints
     * a blank white page. WebView and Chrome on this phone are pinned at 74.0.3729.186
     * (2019) because Play Store is gone, and the HA frontend needs a far newer engine.
     * Loading the same URL in Chrome directly is equally blank, so it is not the app.
     * The WebView provider is signature-pinned; there is no sideload around it.
     */
    private val COMPANION_NOTE = TileNote(
        chip = "BLANK SCREEN",
        detail = "needs a newer WebView than this phone can get — use the native tile",
    )

    /**
     * ⚠️ Chrome is not broken, and this note is not a broken one — it is the same
     * "say it before the tap" rule applied to a working tile with a sharp edge.
     *
     * Same root cause as [COMPANION_NOTE]: no Play Store, so Chrome is frozen at
     * 74.0.3729.186 from 2019 and cannot be updated (the WebView provider is
     * signature-pinned). Simple pages are fine — the hub's own pages are built for it —
     * but a 2019 engine white-screens on plenty of modern sites, and he should read that
     * on the tile instead of concluding the phone's network is down.
     */
    private val CHROME_NOTE = TileNote(
        chip = "2019 ENGINE",
        detail = "Chrome is stuck at v74 (2019) — modern sites may not render",
        broken = false,
    )

    private data class Candidate(
        val packages: List<String>,
        val label: String? = null,
        val subtitle: String? = null,
        val note: TileNote? = null,
    )

    private val CANDIDATES = listOf(
        // ★ First, with the torch, because this is worn in a workshop and outdoors and
        // both are reached for without thinking. Everything below is a tool you go
        // looking for; these two are reflexes.
        //
        // ⚠️ The Pixel camera is `com.google.android.GoogleCamera`, which is not the
        // package name anything else on the phone uses, and it is absent from the API 29
        // emulator image. That is the shelf working: the tile resolves at runtime, so it
        // simply does not appear on a device without it. Do not "fix" that by hard-coding
        // the tile in.
        Candidate(listOf("com.google.android.GoogleCamera"), subtitle = "photos"),
        Candidate(listOf("com.termux"), subtitle = "shell"),
        Candidate(listOf("com.tailscale.ipn"), subtitle = "tailnet"),
        Candidate(listOf("com.android.settings"), subtitle = "system"),
        // Last of the packages so it sits next to the link tiles it opens.
        Candidate(listOf("com.android.chrome"), subtitle = "search", note = CHROME_NOTE),
        Candidate(
            // The system label is "Home Assistant", which would read as a duplicate of
            // the native tile directly above it. This is the only forced rename.
            listOf(
                "io.homeassistant.companion.android",
                "io.homeassistant.companion.android.minimal",
            ),
            label = "HA Companion",
            subtitle = "official app",
            note = COMPANION_NOTE,
        ),
    )

    /**
     * The hub's file browser, as three tiles.
     *
     * ⚠️⚠️ **The folder is in the FRAGMENT, not the path, and that is a fact about the
     * hub rather than a style choice.** `GET /browse` is the only browse route the hub
     * has; `web/browse.html` then keeps the whole of its navigation state in
     * `window.location.hash` ("the hash is the whole state, so back and forward work and a
     * folder can be bookmarked"). The folder names are the keys of `files.DEFAULT_ROOTS`
     * and are case-sensitive.
     *
     * These tiles used to say `/browse/photos` and `/browse/cad`. Verified against the
     * live hub 2026-08-14: **both are 404** — there is no such route and there never was,
     * so two of the three tiles could not have worked even with the auth fixed. The
     * fragment form is what the page's own breadcrumbs and folder cards emit.
     *
     * ⚠️ These name a path, never a browser: the tap opens [HubBrowserScreen] inside this
     * app. That is what lets the token travel as a header — see [TileKind.HUB] — and it is
     * still a 2019 WebView underneath, which is why the hub's pages are written for one.
     *
     * They are always present, even if the hub is not up. An unreachable hub is a page
     * saying so; a tile that vanishes when the hub is down is a shelf that changes shape
     * under him, which is worse on the only screen he can reach from Home.
     */
    private val LINKS = listOf(
        AppTile("$HUB_BASE/browse", "Files", "network drive", kind = TileKind.HUB),
        AppTile("$HUB_BASE/browse#Photos", "Photos", "shared album", kind = TileKind.HUB),
        AppTile("$HUB_BASE/browse#CAD", "CAD", "models", kind = TileKind.HUB),
    )

    /** The native Home Assistant screen. Always present; it needs no package. */
    private val NATIVE_HA = AppTile(
        id = HOME_ASSISTANT,
        label = "Home Assistant",
        subtitle = "native — no browser",
        kind = TileKind.INTERNAL,
    )

    /**
     * ★ The torch. A switch, not a launch — the only tile that is already doing something
     * when he looks at it.
     *
     * Present only where there is a flash to drive, which the caller answers from
     * `PackageManager.hasSystemFeature(FEATURE_CAMERA_FLASH)`. Same rule as an uninstalled
     * package: a capability the device does not have is a tile that is simply not there,
     * never a tile that fails when pressed.
     */
    private val TORCH_TILE = AppTile(
        id = TORCH,
        label = "Flashlight",
        subtitle = "torch — tap to toggle",
        kind = TileKind.INTERNAL,
    )

    /**
     * Build the shelf from whatever is actually installed, and whatever this device can
     * actually do.
     *
     * Order is fixed and meaningful: the native HA screen first because it is the one
     * that works and the device is a smart-home controller, then the torch beside it
     * because both are instant and neither leaves the app; then the installed tools in
     * declaration order; then the hub links; then anything known-broken, last, so a tile
     * that cannot do its job never sits above one that can. A caution note ([CHROME_NOTE])
     * does not sink a tile — only `broken` does.
     *
     * @param hasTorch whether the device reports a camera flash. The default is the
     *   convenient answer for tests; the real caller ([AppCatalog.shelf]) always asks
     *   PackageManager rather than assuming.
     */
    fun build(installed: List<InstalledApp>, hasTorch: Boolean = true): List<AppTile> {
        val byPackage = installed.associateBy { it.packageId }
        val resolved = CANDIDATES.mapNotNull { candidate ->
            val app = candidate.packages.firstNotNullOfOrNull { byPackage[it] } ?: return@mapNotNull null
            AppTile(
                id = app.packageId,
                label = candidate.label ?: app.label,
                subtitle = candidate.subtitle,
                note = candidate.note,
            )
        }
        val (broken, working) = (resolved + LINKS).partition { it.broken }
        val native = listOfNotNull(NATIVE_HA, TORCH_TILE.takeIf { hasTorch })
        return native + working + broken
    }
}
