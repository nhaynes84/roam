package com.roam.touch.channels

import com.roam.touch.channels.model.ControlKeys
import com.roam.touch.channels.model.Coverage
import com.roam.touch.channels.tts.SpeechContext
import com.roam.touch.channels.tts.TtsGate
import com.roam.touch.channels.tts.TtsMode
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Read the summary aloud when the screen is off or the app is not in the foreground;
 * silent when he is looking at it." Every combination, because the wrong half of this
 * behaviour is either a device that mutters at a man reading it or one that stays silent
 * in his pocket.
 */
class TtsGateTest {

    private val outcome = Fx.event(id = 1, kind = "outcome", body = "suite is green")

    private fun ctx(
        mode: TtsMode = TtsMode.AUTO,
        screenOn: Boolean = true,
        foreground: Boolean = true,
        backlog: Boolean = false,
    ) = SpeechContext(mode, screenOn, foreground, backlog)

    // -- the contextual default --------------------------------------------

    @Test
    fun `silent while he is looking at the panel`() {
        assertFalse(TtsGate.shouldSpeak(outcome, ctx(screenOn = true, foreground = true)))
    }

    @Test
    fun `speaks when the screen is off`() {
        assertTrue(TtsGate.shouldSpeak(outcome, ctx(screenOn = false, foreground = true)))
    }

    @Test
    fun `speaks when another app is in front`() {
        assertTrue(TtsGate.shouldSpeak(outcome, ctx(screenOn = true, foreground = false)))
    }

    @Test
    fun `speaks when the screen is off and the app is backgrounded`() {
        assertTrue(TtsGate.shouldSpeak(outcome, ctx(screenOn = false, foreground = false)))
    }

    // -- the manual override ------------------------------------------------

    @Test
    fun `muted never speaks, whatever the context`() {
        for (screen in listOf(true, false)) {
            for (fg in listOf(true, false)) {
                assertFalse(
                    TtsGate.shouldSpeak(outcome, ctx(TtsMode.MUTED, screen, fg))
                )
            }
        }
    }

    @Test
    fun `always speaks even with the panel open in his hand`() {
        assertTrue(
            TtsGate.shouldSpeak(outcome, ctx(TtsMode.ALWAYS, screenOn = true, foreground = true))
        )
    }

    @Test
    fun `mode cycles auto to always to muted and back`() {
        assertEquals(TtsMode.ALWAYS, TtsMode.AUTO.next())
        assertEquals(TtsMode.MUTED, TtsMode.ALWAYS.next())
        assertEquals(TtsMode.AUTO, TtsMode.MUTED.next())
    }

    // -- what is worth saying ----------------------------------------------

    @Test
    fun `only outcomes and errors are spoken`() {
        val speakable = listOf("outcome", "error")
        val silent = listOf("sent", "receipt", "opened", "closed", "note", "weird_new_kind")
        speakable.forEach {
            assertTrue(it, TtsGate.shouldSpeak(Fx.event(1, kind = it), ctx(screenOn = false)))
        }
        silent.forEach {
            assertFalse(it, TtsGate.shouldSpeak(Fx.event(1, kind = it), ctx(screenOn = false)))
        }
    }

    @Test
    fun `a backlog is never recited`() {
        // He has been away; the bridge already buzzed his arm for these. Reading twenty
        // stale outcomes at a walking man is a punishment, not a feature.
        assertFalse(TtsGate.shouldSpeak(outcome, ctx(screenOn = false, backlog = true)))
    }

    @Test
    fun `an unsettled outcome is never read aloud`() {
        // API.md: the body may be an earlier block of the same turn. A plausible wrong
        // answer spoken confidently is indistinguishable from a right one.
        val unsettled = Fx.event(
            id = 2, kind = "outcome",
            meta = mapOf("answer_source" to "transcript", "transcript_settled" to "false"),
        )
        assertTrue(unsettled.unsettled)
        assertFalse(TtsGate.shouldSpeak(unsettled, ctx(screenOn = false)))
    }

    @Test
    fun `a settled transcript-sourced outcome is fine`() {
        val settled = Fx.event(
            id = 2, kind = "outcome",
            meta = mapOf("answer_source" to "transcript", "transcript_settled" to "true"),
        )
        assertFalse(settled.unsettled)
        assertTrue(TtsGate.shouldSpeak(settled, ctx(screenOn = false)))
    }

    @Test
    fun `an event the hub says he is already reading elsewhere stays silent`() {
        val covered = Fx.event(
            id = 3, kind = "outcome",
            coverage = Coverage(known = true, covered = true, by = listOf("tmux-input"),
                lastInput = "tmux"),
        )
        assertFalse(TtsGate.shouldSpeak(covered, ctx(screenOn = false)))
        // ...but the manual override still wins, which is the point of having one.
        assertTrue(TtsGate.shouldSpeak(covered, ctx(TtsMode.ALWAYS, screenOn = false)))
    }

    @Test
    fun `unknown coverage is treated as notify`() {
        // API.md: a missed message is worse than a redundant one.
        val unknown = Fx.event(id = 4, kind = "outcome", coverage = Coverage(known = false))
        assertTrue(TtsGate.shouldSpeak(unknown, ctx(screenOn = false)))
        val absent = Fx.event(id = 5, kind = "outcome", coverage = null)
        assertTrue(TtsGate.shouldSpeak(absent, ctx(screenOn = false)))
    }

    @Test
    fun `an interrupt keystroke is not speech`() {
        val esc = Fx.event(id = 6, kind = "sent", body = ControlKeys.INTERRUPT.bytes)
        assertFalse(TtsGate.shouldSpeak(esc, ctx(screenOn = false)))
    }

    @Test
    fun `an empty event is not spoken`() {
        val empty = Fx.event(id = 7, kind = "outcome", body = "", summary = "")
        assertFalse(TtsGate.shouldSpeak(empty, ctx(screenOn = false)))
    }

    // -- what is said -------------------------------------------------------

    @Test
    fun `the utterance names the channel then the hub's own summary`() {
        val e = Fx.event(id = 8, kind = "outcome", body = "long body here",
            summary = "The suite is green.")
        assertEquals(
            "Augment things. The suite is green.",
            TtsGate.utterance("✳ Augment things", e),
        )
    }

    @Test
    fun `status glyphs are stripped so Piper does not stumble on them`() {
        assertEquals("Roam Touch rebuild discussion",
            TtsGate.speakableLabel("◑ Roam Touch rebuild discussion"))
        assertEquals("Nightly backup job", TtsGate.speakableLabel("✳ Nightly backup job"))
    }

    @Test
    fun `an error announces itself as one`() {
        val e = Fx.event(id = 9, kind = "error", body = "tmux refused the send",
            summary = "tmux refused the send")
        assertTrue(TtsGate.utterance("✳ Augment things", e).startsWith("Error in Augment things"))
    }

    @Test
    fun `the client never re-derives the summary`() {
        // API.md: one implementation, one behaviour, so the panel and the voice agree.
        val e = Fx.event(id = 10, kind = "outcome",
            body = "# Heading\n\nlots and lots of markdown", summary = "hub says this")
        assertTrue(TtsGate.utterance("x", e).endsWith("hub says this"))
    }
}
