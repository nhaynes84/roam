package com.roam.touch.channels

import com.roam.touch.channels.tts.Utterance
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * ★★ The bug the owner hit, as two failing assertions.
 *
 * > *"any message over 6 lines doesn't scroll or have expandability, i just can't read
 * > it on the phone"* … *"the TTS also cuts off there, so it might just be a message
 * > capping thing"*
 *
 * He was right, and the second half is the diagnosis. **Both consumers were reading
 * `summary` and never reaching `body`**, and `MAX_SUMMARY_CHARS = 280` in the hub is
 * about six lines on a 5" screen — so the screen and the voice stopped in the same
 * place, on the same sentence. Nothing was being clipped by the UI; the rest of the
 * message simply never arrived at either output.
 *
 * ⚠️ These are deliberately written against the *contract*, not the plumbing: whatever
 * the reader screen looks like later, "play says the whole thing" and "a cut summary
 * admits it was cut" must not regress.
 */
class ReadTheWholeMessageTest {

    /** A real shape: the hub cuts at a sentence boundary within 280 and marks it `…`. */
    private val fullBody = """
        Done — Andy resolves now. But the pre-flight caught something that would have
        sunk the demo. You were already in the org, active, with a valid membership doc,
        so nothing was wrong on your side. Only Andy was missing, and he is now in.

        The thing that would have bitten you on stage: the picker only renders when
        there is more than one type. Every seeded demo client has one only, so they all
        auto-select silently and show no picker at all.
    """.trimIndent()

    private val cutSummary = fullBody.replace(Regex("\\s+"), " ").take(279) + "…"

    private val event = Fx.event(
        id = 1,
        kind = "outcome",
        body = fullBody,
        summary = cutSummary,
        chars = fullBody.length,
    )

    /**
     * ★ Play is **demand**, and demand is the whole message.
     *
     * `API.md` calls the summary "always safe to speak" — that is a statement about a
     * glance, not a cap on what he is allowed to hear. Tapping play on one specific
     * message is the most explicit request this app can receive.
     */
    @Test
    fun `play speaks the whole answer, not the 280-char summary`() {
        val spoken = Utterance.of("✳ Augment things", event)
        assertTrue(
            "play must reach the end of the body, not stop where the summary did",
            spoken.contains("auto-select silently and show no picker"),
        )
    }

    /**
     * ⚠️ The silent truncation that started all of this. The hub marks a cut summary
     * with a trailing `…`; a body only ~44 characters longer than its summary fell
     * under `MATERIALLY_LONGER` and was shown with **no affordance at all** — six lines
     * that just stop. Real example: event 365 on `%0`, summary 280, body 324.
     */
    @Test
    fun `a summary the hub had to cut always offers the rest`() {
        val e = Fx.event(
            id = 2,
            kind = "outcome",
            body = "a".repeat(240) + ". And then a final clause that the cut lost.",
            summary = "a".repeat(239) + "…",
        )
        assertTrue("a cut summary must offer the rest", e.hasMore())
    }

    /**
     * The other half of that rule, and the reason it is an ellipsis test rather than a
     * length test: the hub's summary always differs a little (markdown and glyphs are
     * stripped), and offering "full text · 16 chars" on a channel-opened event is the
     * clutter that teaches him to ignore the affordance.
     */
    @Test
    fun `a summary that merely lost its markdown does not claim there is more`() {
        val e = Fx.event(
            id = 3,
            kind = "outcome",
            body = "Merging rather than replacing — your `clip-fetch.sh` hook stays:",
            summary = "Merging rather than replacing — your clip-fetch.sh hook stays:",
        )
        assertFalse("nothing is hidden here, so do not offer more", e.hasMore())
    }
}
