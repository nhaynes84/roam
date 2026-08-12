package com.roam.touch.channels

import com.roam.touch.channels.tts.Speech
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * ⚠️ **This strips; it never chooses.**
 *
 * `API.md` forbids re-deriving the summary client-side, and that rule stands — the whole
 * reason play was broken is that something upstream decided what he was allowed to hear.
 * So every test here asserts on what *survives*. The only assertions about removal are
 * about syntax that has no spoken form at all.
 */
class SpeechTest {

    @Test
    fun `emphasis markers go, the emphasised words stay`() {
        assertEquals("Andy is now in.", Speech.plain("**Andy is now in.**"))
        assertEquals("the orgTrainers doc", Speech.plain("the `orgTrainers` doc"))
    }

    @Test
    fun `a heading is read as its words`() {
        assertEquals("What changed", Speech.plain("## What changed"))
    }

    /** ★ A code block is content. Dropping it would be the same silent loss, renamed. */
    @Test
    fun `a fenced block keeps its code`() {
        val out = Speech.plain("Run:\n```bash\nmake p2-flash\n```\ndone.")
        assertEquals("Run:\nmake p2-flash\ndone.", out)
    }

    /** A table row should read as a row, not as a fence of pipes. */
    @Test
    fun `a table reads as rows`() {
        val out = Speech.plain(
            """
            | pane | status |
            |------|--------|
            | %0   | working |
            """.trimIndent()
        )
        assertEquals("pane, status\n%0, working", out)
    }

    @Test
    fun `a link keeps its text and loses its url`() {
        val out = Speech.plain("see [the contract](http://talos:8787/docs) for detail")
        assertEquals("see the contract for detail", out)
        assertFalse(out.contains("http"))
    }

    @Test
    fun `bullets become plain lines`() {
        assertEquals("first\nsecond", Speech.plain("- first\n- second"))
        assertEquals("first\nsecond", Speech.plain("1. first\n2. second"))
    }

    /**
     * ⚠️ A lone underscore is far more likely to be inside `body_truncated` than to be
     * emphasis, and mangling an identifier he is listening for is worse than an
     * asterisk Piper says nothing for anyway.
     */
    @Test
    fun `an identifier is not mistaken for emphasis`() {
        assertEquals("check body_truncated first", Speech.plain("check body_truncated first"))
    }

    @Test
    fun `nothing in, nothing out`() {
        assertEquals("", Speech.plain(""))
        assertEquals("", Speech.plain("   \n\n  "))
    }

    /** The load-bearing property: no words are lost. */
    @Test
    fun `every word survives a realistic answer`() {
        val markdown = """
            ## Done — Andy resolves now

            **You were already in the org.** `orgTrainers/demo-ot-nick`, active.

            ```
            users/vb7 -> membership
            ```

            - Nothing was wrong on your side.
            - Only Andy was missing.
        """.trimIndent()
        val out = Speech.plain(markdown)
        listOf(
            "Done", "Andy", "resolves", "now", "You", "were", "already", "in", "the", "org",
            "orgTrainers/demo-ot-nick", "active", "users/vb7", "membership",
            "Nothing", "wrong", "your", "side", "Only", "missing",
        ).forEach { word ->
            assertTrue("'$word' must survive", out.contains(word))
        }
        assertFalse(out.contains("```"))
        assertFalse(out.contains("**"))
        assertFalse(out.contains("##"))
    }
}
