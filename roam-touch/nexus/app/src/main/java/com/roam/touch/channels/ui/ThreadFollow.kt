package com.roam.touch.channels.ui

/**
 * Whether an arriving event is allowed to move the thread under him.
 *
 * ★ The intent behind following the tail is right — he is on this screen *because* he is
 * waiting for an answer, so an outcome that lands should come into view. The old rule
 * just had no exception: every new event called `animateScrollToItem(lastIndex)`
 * unconditionally, and on a live channel that is every few seconds. Scroll back through
 * the conversation and it snaps to the bottom under your thumb, which is what
 * *"doesn't scroll"* feels like from the wearer's seat.
 *
 * So: follow only when he is already at the tail, which is the same as saying *follow
 * only when following costs him nothing*. When he is not, the arrival becomes a chip he
 * can press — ⚠️ never a silent non-event, because a message that lands and says nothing
 * is the failure mode this whole change exists to remove.
 *
 * Deliberately pure and outside the composable, for the reason this codebase already
 * states elsewhere: a rule that lives in a `@Composable` can only be checked by looking
 * at a phone.
 */
object ThreadFollow {

    /**
     * How close to the bottom still counts as "at the bottom", in pixels.
     *
     * Not zero: a fling settles a pixel or two short, and a thread that stopped following
     * because it was 1 px out would look broken in exactly the way that is hardest to
     * report. Roughly a line of body text.
     */
    const val SLACK_PX = 64

    /**
     * @param lastVisibleIndex index of the last item with any pixels on screen, or -1.
     * @param lastVisibleBottomPx that item's bottom edge, relative to the viewport top.
     * @param lastIndex index of the final entry in the thread, or -1 when empty.
     * @param viewportBottomPx the bottom edge of the list's viewport.
     */
    fun isAtTail(
        lastVisibleIndex: Int,
        lastVisibleBottomPx: Int,
        lastIndex: Int,
        viewportBottomPx: Int,
    ): Boolean {
        // An empty or not-yet-measured list is trivially at its own end; the first
        // event to arrive should scroll into view rather than announce itself.
        if (lastIndex < 0) return true
        if (lastVisibleIndex < lastIndex) return false
        return lastVisibleBottomPx <= viewportBottomPx + SLACK_PX
    }

    /**
     * ★★ Whether the panel is still following the tail.
     *
     * ⚠️ [isAtTail] alone was the bug the owner hit: *"when i enter and receive messages,
     * it doesn't autoscroll to the latest message, bad experience."* Opening a thread
     * lands on the newest entry — and the newest entry is routinely **taller than the
     * window**, which is the whole reason this device has a reader. So the geometry said
     * "not at the end of the last card", the panel dutifully stopped following, and every
     * answer after that announced itself as NEW BELOW instead of arriving. He never
     * scrolled anywhere; the layout decided for him that he had.
     *
     * ★ So the question is not *where is he* but **has he taken over**. A finger on the
     * list is the only thing that can stop the panel following, and reaching the end is
     * the only thing that starts it again. Both halves of the owner's brief fall out of
     * that: he never touched it, so a message arriving moves the view; he scrolled up to
     * read something, so nothing moves under him until he comes back down.
     *
     * @param dragged has he put a finger on this list at all since it opened.
     * @param atTail [isAtTail], the geometry.
     */
    fun isFollowing(dragged: Boolean, atTail: Boolean): Boolean = !dragged || atTail

    /** What the thread should do about a change to its entries. */
    enum class Move {
        /** Nothing moves and nothing is announced. */
        None,

        /** Put the newest entry on screen now, with no animation. */
        Jump,

        /** Bring the newest entry into view, visibly, so the movement is explained. */
        Animate,

        /** Do not move; raise NEW BELOW instead. */
        Announce,
    }

    /**
     * ★★ The whole scroll decision, in one place, with no `LazyListState` in sight.
     *
     * @param empty nothing to scroll to.
     * @param opening this is the first time entries have existed for this channel — he
     *   asked for this channel, so he gets the bottom of it, and he gets it without a
     *   forty-item tour.
     * @param following [isFollowing].
     * @param arrived the newest entry is genuinely *new*. ⚠️ Distinguishing this from
     *   "the list changed" is load-bearing twice over: history hydrating **underneath**
     *   him (the hub returns the backlog after the socket has already delivered the tail,
     *   so entries get *prepended* and his index silently stops meaning what it meant)
     *   must keep him where he is without ever raising NEW BELOW — nothing arrived, so
     *   announcing an arrival would be a lie he has to walk to the bottom to disprove.
     */
    fun move(empty: Boolean, opening: Boolean, following: Boolean, arrived: Boolean): Move = when {
        empty -> Move.None
        opening -> Move.Jump
        !following -> if (arrived) Move.Announce else Move.None
        arrived -> Move.Animate
        // Following, and the list grew somewhere that is not the end: stay pinned to the
        // tail, silently. This is the prepend case, and animating it would be a tour.
        else -> Move.Jump
    }
}
