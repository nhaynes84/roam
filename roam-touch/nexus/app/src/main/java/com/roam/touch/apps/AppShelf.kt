package com.roam.touch.apps

import com.roam.touch.BuildConfig

/**
 * How a tile is opened. The UI dispatches on this and on nothing else.
 *
 * ⚠️ Deliberately about *mechanism*, not about content: [PACKAGE] means "ask the system
 * for this package's launch intent", [URL] means "fire ACTION_VIEW and let the system
 * pick the handler", [INTERNAL] means "a screen this app draws itself". Adding a kind is
 * adding a way to open something, which is why there are only three.
 */
enum class TileKind { PACKAGE, INTERNAL, URL }

/**
 * What a launchable thing looks like to the panel.
 *
 * [id] is the package name for anything the system launches, a `roam:` id for a screen
 * this app owns, or — for a [TileKind.URL] tile — the URL itself. A link tile carries no
 * second `url` field on purpose: one field means there is no such thing as a URL tile
 * with a missing URL, and the grid key stays unique for free. The UI never branches on
 * the label.
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
 * ★ Whether a link tile can be fired at all, decided without touching Android.
 *
 * Kept pure so the "a bad URL returns false instead of throwing" rule is covered by a
 * plain JVM test — the home screen is the one place where an ActivityNotFoundException
 * costs the whole device its UI, so that rule cannot be left to Robolectric.
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
     * ⚠️ These name a path, never a browser. The tap becomes an ACTION_VIEW intent and
     * the system decides who handles it — same reason [AppCatalog] refuses to record a
     * ComponentName. In practice that is Chrome, so read [CHROME_NOTE]: these pages have
     * to render on a 2019 engine.
     *
     * They are always present, even if the endpoint is not up yet. A link that 404s is a
     * page saying so; a tile that vanishes when the hub is down is a shelf that changes
     * shape under him, which is worse on the only screen he can reach from Home.
     */
    private val LINKS = listOf(
        AppTile("$HUB_BASE/browse", "Files", "network drive", kind = TileKind.URL),
        AppTile("$HUB_BASE/browse/photos", "Photos", "shared album", kind = TileKind.URL),
        AppTile("$HUB_BASE/browse/cad", "CAD", "models", kind = TileKind.URL),
    )

    /** The native Home Assistant screen. Always present; it needs no package. */
    private val NATIVE_HA = AppTile(
        id = HOME_ASSISTANT,
        label = "Home Assistant",
        subtitle = "native — no browser",
        kind = TileKind.INTERNAL,
    )

    /**
     * Build the shelf from whatever is actually installed.
     *
     * Order is fixed and meaningful: the native HA screen first because it is the one
     * that works and the device is a smart-home controller; then the installed tools in
     * declaration order; then the hub links; then anything known-broken, last, so a tile
     * that cannot do its job never sits above one that can. A caution note ([CHROME_NOTE])
     * does not sink a tile — only `broken` does.
     */
    fun build(installed: List<InstalledApp>): List<AppTile> {
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
        return listOf(NATIVE_HA) + working + broken
    }
}
