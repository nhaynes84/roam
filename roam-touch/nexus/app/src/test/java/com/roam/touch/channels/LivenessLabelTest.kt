package com.roam.touch.channels

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * ★ Regression: "your 'Working' counter just seems to go 0, 1, 0, 1 — it doesn't count
 * past 1." (owner, on the real device, 2026-08-12)
 *
 * Not a hub bug. Sampled live for 24 s while a Claude pane was working, the hub reported
 * `idle_s` = 0.3, 0.2, 0.1, 0.1, 2.1, 2.0, 1.9, 1.8 … — exactly correct, because a
 * working pane repaints a spinner every second or so and `idle_s` is *"how long since
 * output last changed"*, not elapsed work time. Floored to whole seconds it can only
 * ever read 0s, 1s or 2s, so on screen it looks like a counter that is stuck.
 *
 * The number is meaningless in the state where it never grows, and it is the entire
 * point in the state where it does. So it is rendered only where it means something.
 */
class LivenessLabelTest {

    @Test
    fun `a working channel shows no number at all`() {
        // The moving ellipsis already says "output is moving". A digit that can only be
        // 0, 1 or 2 adds nothing and reads as broken.
        listOf(0L, 300L, 900L, 1_500L, 2_100L, 4_000L).forEach { idle ->
            val label = LivenessLabel.text(Liveness.Working(idle))
            assertEquals("WORKING", label)
            assertFalse("no digits for idle=$idle: $label", label.any { it.isDigit() })
        }
    }

    @Test
    fun `a working channel with no sample yet still just says working`() {
        assertEquals("WORKING", LivenessLabel.text(Liveness.Working(null)))
    }

    @Test
    fun `a quiet channel always shows the number - it is the kill decision`() {
        assertEquals("QUIET 20s", LivenessLabel.text(Liveness.Quiet(20_000)))
        assertEquals("QUIET 4m", LivenessLabel.text(Liveness.Quiet(240_000)))
        assertEquals("QUIET 1h12m", LivenessLabel.text(Liveness.Quiet(72 * 60_000L)))
    }

    @Test
    fun `an idle channel hides the number while it would only flicker`() {
        // Same flicker, same reason: a pane that is idle but repainting reads 0s, 1s, 0s.
        listOf(0L, 900L, 4_900L).forEach {
            assertEquals("IDLE", LivenessLabel.text(Liveness.Idle(it)))
        }
    }

    @Test
    fun `an idle channel shows the number once it means something`() {
        assertEquals("IDLE 5s", LivenessLabel.text(Liveness.Idle(5_000)))
        assertEquals("IDLE 13m", LivenessLabel.text(Liveness.Idle(795_800)))
        assertEquals("IDLE 2h", LivenessLabel.text(Liveness.Idle(7_200_000)))
    }

    @Test
    fun `an unsampled idle channel claims nothing`() {
        assertEquals("IDLE", LivenessLabel.text(Liveness.Idle(null)))
    }

    @Test
    fun `dead and unknown carry no timer`() {
        assertEquals("DEAD", LivenessLabel.text(Liveness.Dead))
        assertEquals("UNKNOWN", LivenessLabel.text(Liveness.Unknown))
    }

    @Test
    fun `the label never grows past a glanceable width`() {
        val worst = listOf(
            Liveness.Working(999_999_999), Liveness.Quiet(999_999_999),
            Liveness.Idle(999_999_999), Liveness.Dead, Liveness.Unknown,
        )
        worst.forEach {
            assertTrue("$it -> ${LivenessLabel.text(it)}", LivenessLabel.text(it).length <= 12)
        }
    }

    /**
     * The observed sequence, replayed. Before the fix this produced
     * `WORKING 0s, WORKING 0s, WORKING 0s, WORKING 0s, WORKING 2s, …` — four distinct
     * labels for one unchanging state.
     */
    @Test
    fun `the real sampled sequence produces one stable label`() {
        val sampledIdleSeconds = listOf(0.3, 0.2, 0.1, 0.1, 2.1, 2.0, 1.9, 1.9, 1.8, 1.7)
        val labels = sampledIdleSeconds
            .map { LivenessLabel.text(Liveness.Working((it * 1000).toLong())) }
            .toSet()
        assertEquals(setOf("WORKING"), labels)
    }
}
