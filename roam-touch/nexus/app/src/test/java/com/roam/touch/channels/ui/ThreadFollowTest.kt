package com.roam.touch.channels.ui

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
}
