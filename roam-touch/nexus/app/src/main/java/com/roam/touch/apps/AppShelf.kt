package com.roam.touch.apps

/**
 * What a launchable thing looks like to the panel.
 *
 * [id] is the package name for anything the system launches, or a `roam:` id for a
 * screen this app owns. The UI never branches on the label.
 */
data class AppTile(
    val id: String,
    val label: String,
    val subtitle: String?,
    val note: TileNote? = null,
    val internal: Boolean = false,
) {
    val broken: Boolean get() = note?.broken == true
}

/**
 * ★ A tile that will not work says so *before* the tap.
 *
 * Standing law: stale/dead state is surfaced up front, never discovered by clicking.
 * [chip] is the two-word badge; [detail] is the one-line reason, and it has to be
 * specific enough to stop him debugging it a second time.
 */
data class TileNote(val chip: String, val detail: String, val broken: Boolean = true)

/** A launchable package as the system reports it. Resolved by [AppCatalog] on device. */
data class InstalledApp(val packageId: String, val label: String)

/**
 * ★ The shelf is a short, deliberate list — not an app drawer.
 *
 * Nexus is the home screen, so without this there is literally no route to anything
 * else on the phone: press Home and you are in Channels forever. That is the problem
 * being solved, and it is solved by four or five tiles, not by enumerating 188 packages.
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

    /** The native Home Assistant screen. Always present; it needs no package. */
    private val NATIVE_HA = AppTile(
        id = HOME_ASSISTANT,
        label = "Home Assistant",
        subtitle = "native — no browser",
        internal = true,
    )

    /**
     * Build the shelf from whatever is actually installed.
     *
     * Order is fixed and meaningful: the native HA screen first because it is the one
     * that works and the device is a smart-home controller; then the working tools in
     * declaration order; then anything known-broken, last, so a tile that cannot do its
     * job never sits above one that can.
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
        val (broken, working) = resolved.partition { it.broken }
        return listOf(NATIVE_HA) + working + broken
    }
}
