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
        screen != Screen.Channels -> Back.CloseDetour
        hasOpenPane -> Back.CloseThread
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
