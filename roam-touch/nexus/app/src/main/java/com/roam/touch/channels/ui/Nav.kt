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
}
