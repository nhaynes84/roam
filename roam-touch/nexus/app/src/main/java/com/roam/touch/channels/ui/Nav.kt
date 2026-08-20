package com.roam.touch.channels.ui

/**
 * ★ What the content pane shows, and what Back unwinds — as a decision, not as an `if`
 * chain buried in [ChannelsApp].
 *
 * ⚠️⚠️ This exists because the precedence was wrong and nothing could catch it. The
 * destinations used to live on the channel *list*, so they were unreachable from inside a
 * thread and "an open thread wins" was never tested against a competing screen. The nav
 * rail put them on screen everywhere — and then tapping one highlighted the icon and
 * changed nothing, because the open thread was still answered first. Owner: *"the icons
 * don't seem to work."* They worked. The pane never moved.
 *
 * The same ordering has to hold in both directions, which is the other half of the bug:
 * if a detour outranks the thread on the way in, Back must unwind the detour *before* the
 * thread on the way out, or he lands on Home Assistant with the conversation silently
 * closed behind it.
 */
enum class Pane {
    /** Reading one message in full. Unwinds to the thread it was opened from. */
    Reader,

    /** Home Assistant, Apps, Controls — drawn *over* an open thread, not instead of it. */
    Detour,

    /** A channel is open and nothing is covering it. */
    Thread,

    /** Nothing open: the list, or the prompt to pick from it. */
    List,
}

/** What a Back press should do next. `null` means nothing is stacked — leave it to the system. */
enum class Back {
    CloseReader,

    /**
     * ★ A screen opened *from another screen* unwinds to its parent, not to Channels.
     *
     * ⚠️ The general rule would put him two steps back in one press — he tapped Files on
     * the shelf and would land in Channels with no sign the shelf was ever there.
     * Everything else is reached from the rail, which is on screen everywhere, so for
     * those one step out *is* the way he came in.
     *
     * ⚠️⚠️ This used to be `CloseHubBrowser`, singular, above a comment claiming the
     * browser was *"the one detour opened from another detour"*. It is not any more:
     * headset controls moved off the rail and into Settings, so it is now reached the same
     * way the browser is. The exception was generalised rather than duplicated — see
     * [Nav.parentOf], which is the only place the parent of a screen is written down.
     */
    CloseSubScreen,
    CloseDetour,
    CloseThread,
}

object Nav {

    /**
     * ★ Order is the whole of this function. Reader over detour over thread over list.
     *
     * [hasChannel] rather than a pane id: a pane can be open while the channel behind it
     * has gone away, and then there is nothing to draw.
     */
    fun pane(reading: Boolean, screen: Screen, hasChannel: Boolean): Pane = when {
        reading -> Pane.Reader
        screen != Screen.Channels -> Pane.Detour
        hasChannel -> Pane.Thread
        else -> Pane.List
    }

    /**
     * ⚠️ The mirror of [pane], and it must stay the mirror. Each press closes exactly the
     * topmost thing, so Back walks back out the way he walked in.
     *
     * ★ `openPane` is not cleared when a detour opens, so closing the detour returns him to
     * the conversation rather than to the list — the reason [pane] is written in terms of
     * what is *covering* the thread rather than what replaced it.
     */
    fun back(reading: Boolean, screen: Screen, hasOpenPane: Boolean): Back? = when {
        reading -> Back.CloseReader
        // ⚠️ Above the general detour rule, not folded into it: a screen with a parent is
        // one he reached *through* something, so its one step back is that something and
        // not Channels. See [Back.CloseSubScreen].
        parentOf(screen) != null -> Back.CloseSubScreen
        screen != Screen.Channels -> Back.CloseDetour
        hasOpenPane -> Back.CloseThread
        else -> null
    }

    /**
     * ★★ Which screen a screen was opened from, or null for the ones the rail reaches
     * directly. **The only statement of that fact in the app** — [back] asks it, and so
     * does the handler that carries the answer out.
     *
     * ⚠️ [Screen.Controls] is here because the headset moved. Owner, 2026-08-15: *"honestly
     * the headphones setup is a Setting, we'll need our own settings so might as well just
     * start making widgets there, of which headphones is one setting."* It is no longer a
     * rail destination, so Back out of it must land on the Settings screen he opened it
     * from — the same rule the hub browser has always had.
     */
    fun parentOf(screen: Screen): Screen? = when (screen) {
        Screen.HubBrowser -> Screen.Apps
        Screen.Controls -> Screen.Settings
        else -> null
    }

    /**
     * ★★ **Which channel his eyes are on** — the one that must not buzz his arm, and the
     * only one. Reported to the hub as presence; see `PresenceRequest`.
     *
     * Owner's rule, verbatim: *"haptic and buzz when I'm actually on that device, and I'm
     * not in the active channel at the time, that's it."*
     *
     * ⚠️⚠️ **It is [pane], deliberately, and that is the point of it existing.** The app
     * used to claim `covers_all` — eyes on every channel at once — so the hub correctly
     * decided nothing was worth interrupting him for and his arm went silent all evening.
     * The buzz path was never broken; it was never asked to run. The replacement must
     * never drift from what is *drawn*, so it is derived from the same function that
     * decides what to draw rather than set by hand at each place navigation happens —
     * there were four of those, and the fifth would have been the one that got missed.
     *
     * - [Pane.Thread] and [Pane.Reader] — he is in that conversation. Covered.
     * - [Pane.Detour] — Home Assistant, Apps or Controls is drawn *over* the thread. The
     *   pane stays open so Back returns to it, but he is not reading it, so it may buzz.
     * - [Pane.List] — nothing is covered. Anything at all may reach him.
     */
    fun covered(
        reading: Boolean,
        screen: Screen,
        openPane: String?,
        hasChannel: Boolean,
    ): String? = when (pane(reading, screen, hasChannel)) {
        Pane.Thread, Pane.Reader -> openPane
        Pane.Detour, Pane.List -> null
    }
}
