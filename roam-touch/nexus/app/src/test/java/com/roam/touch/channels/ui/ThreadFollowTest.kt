package com.roam.touch.channels.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Whether an arriving event may move the thread under him.
 *
 * ★ The old rule had no exception — every event called `animateScrollToItem(lastIndex)`
 * — so scrolling back through a live channel snapped to the bottom under his thumb every
 * few seconds. That is the *"doesn't scroll"* half of the report.
 */
class ThreadFollowTest {

    /** Viewport 1200 px tall, for all of the below. */
    private val viewport = 1_200

    @Test
    fun `sitting at the bottom, a new answer scrolls into view`() {
        assertTrue(
            ThreadFollow.isAtTail(
                lastVisibleIndex = 9,
                lastVisibleBottomPx = 1_180,
                lastIndex = 9,
                viewportBottomPx = viewport,
            )
        )
    }

    /** ⚠️ Reading history: nothing may move. */
    @Test
    fun `scrolled up through history, nothing pulls him away`() {
        assertFalse(
            ThreadFollow.isAtTail(
                lastVisibleIndex = 4,
                lastVisibleBottomPx = 900,
                lastIndex = 9,
                viewportBottomPx = viewport,
            )
        )
    }

    /**
     * The subtle one: the final card *is* on screen, but only its top — a long entry he
     * has just started reading. Following would throw away his place in it.
     */
    @Test
    fun `the last entry being visible is not the same as being at the end of it`() {
        assertFalse(
            ThreadFollow.isAtTail(
                lastVisibleIndex = 9,
                lastVisibleBottomPx = 4_000,
                lastIndex = 9,
                viewportBottomPx = viewport,
            )
        )
    }

    /** A fling settles a pixel or two short; that must still count as the bottom. */
    @Test
    fun `a hair short of the bottom still counts as the bottom`() {
        assertTrue(
            ThreadFollow.isAtTail(
                lastVisibleIndex = 9,
                lastVisibleBottomPx = viewport + ThreadFollow.SLACK_PX - 1,
                lastIndex = 9,
                viewportBottomPx = viewport,
            )
        )
    }

    /** An empty thread follows, so the first message to land shows itself. */
    @Test
    fun `an empty thread follows`() {
        assertTrue(
            ThreadFollow.isAtTail(
                lastVisibleIndex = -1,
                lastVisibleBottomPx = 0,
                lastIndex = -1,
                viewportBottomPx = viewport,
            )
        )
    }

    // --- who is driving ------------------------------------------------------

    /**
     * ★★ The owner's bug, as a unit test: *"when i enter and receive messages, it doesn't
     * autoscroll to the latest message, bad experience."*
     *
     * ⚠️ Geometry alone produced it. Opening a thread lands on the newest entry, the
     * newest entry is routinely taller than the window, and `the last entry being visible
     * is not the same as being at the end of it` — a rule that is right for a man who has
     * scrolled there and wrong for a man who has just arrived — then declared him
     * scrolled away. He had touched nothing.
     */
    @Test
    fun `a thread he has not touched follows, however tall the last answer is`() {
        assertTrue(ThreadFollow.isFollowing(dragged = false, atTail = false))
    }

    /** ⚠️ And the opposite bug, which is worse: he scrolled up, so nothing moves. */
    @Test
    fun `once he has scrolled, nothing follows until he comes back down`() {
        assertFalse(ThreadFollow.isFollowing(dragged = true, atTail = false))
        assertTrue(ThreadFollow.isFollowing(dragged = true, atTail = true))
    }

    // --- what the thread does about it ---------------------------------------

    private fun move(
        empty: Boolean = false,
        opening: Boolean = false,
        following: Boolean = true,
        arrived: Boolean = false,
    ) = ThreadFollow.move(empty, opening, following, arrived)

    /** ★ Moment one: opening a thread lands on the newest message, with no tour. */
    @Test
    fun `opening a thread jumps to the newest message`() {
        assertEquals(ThreadFollow.Move.Jump, move(opening = true))
        assertEquals(ThreadFollow.Move.Jump, move(opening = true, arrived = true))
    }

    /** ★ Moment two: an answer landing while he is at the tail comes into view. */
    @Test
    fun `an answer arriving while he is following scrolls into view`() {
        assertEquals(ThreadFollow.Move.Animate, move(arrived = true))
    }

    /** ⚠️ And while he is reading history it announces itself instead of moving him. */
    @Test
    fun `an answer arriving while he is reading history only announces itself`() {
        assertEquals(ThreadFollow.Move.Announce, move(following = false, arrived = true))
    }

    /**
     * ⚠️⚠️ The invisible one. The socket delivers the tail and `GET /thread` delivers the
     * backlog, so history lands *underneath* what is on screen: the last id is unchanged
     * and thirty rows appear above it. Following, that must re-pin him to the tail —
     * silently, because animating a thirty-row jump he did not ask for is a tour.
     */
    @Test
    fun `history filling in underneath re-pins him to the tail without animating`() {
        assertEquals(ThreadFollow.Move.Jump, move(arrived = false))
    }

    /**
     * ⚠️ …and if he is reading history when the backlog lands, it must do **nothing**.
     * NEW BELOW would be a lie: nothing arrived, and he would walk to the bottom to find
     * the message he had already read.
     */
    @Test
    fun `history filling in underneath never claims something new arrived`() {
        assertEquals(ThreadFollow.Move.None, move(following = false, arrived = false))
    }

    @Test
    fun `an empty thread has nothing to scroll to`() {
        assertEquals(ThreadFollow.Move.None, move(empty = true, opening = true))
    }
}
