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
}
