package com.roam.touch.channels.tts

/**
 * Markdown scaffolding removed so Piper can read a full body aloud.
 *
 * ⚠️ **This is not a summariser, and must never become one.** `API.md` is emphatic that
 * the summary has exactly one implementation and it lives in the hub — but that rule is
 * about *choosing what to say*, and this chooses nothing. It removes decoration and
 * keeps every word, which is why the tests below assert on what survives rather than on
 * what is dropped.
 *
 * The distinction matters because getting it wrong is how the original bug happened:
 * both the screen and the voice were handed a 280-character summary and neither ever
 * reached the body, so a long answer stopped mid-sentence in two places at once.
 */
object Speech {

    /**
     * [markdown] with the syntax taken out and the content left in.
     *
     * Fence lines go (the code between them stays — he asked to hear the message, and
     * dropping a block because it is code is the same silent loss in a new costume);
     * table pipes become commas so a row reads as a row; `[text](url)` keeps the text,
     * because a spoken URL is noise with no information in it.
     */
    fun plain(markdown: String): String {
        if (markdown.isBlank()) return ""
        val out = StringBuilder()
        for (raw in markdown.lineSequence()) {
            var s = raw.trim()
            if (s.isEmpty()) continue
            if (FENCE.matches(s) || RULE.matches(s) || TABLE_RULE.matches(s)) continue
            s = HEADING.replace(s, "")
            s = QUOTE.replace(s, "")
            s = BULLET.replace(s, "")
            s = LINK.replace(s, "$1")
            if (s.contains('|')) s = s.replace("|", ", ")
            s = DECORATION.replace(s, "")
            s = SPACES.replace(s, " ")
            // Cell padding leaves "pane , status"; Piper pauses on that stray space.
            s = LOOSE_COMMA.replace(s, ", ")
            s = s.trim().trim(',', ' ')
            if (s.isEmpty()) continue
            out.append(s).append('\n')
        }
        return out.toString().trim()
    }

    /** ``` or ~~~, with or without a language tag. */
    private val FENCE = Regex("""^(```|~~~).*$""")

    /** A horizontal rule: three or more of the same marker, nothing else. */
    private val RULE = Regex("""^(-{3,}|\*{3,}|_{3,})$""")

    /** The `|---|:--:|` row under a table header — pure layout, no content. */
    private val TABLE_RULE = Regex("""^\|?[\s|:-]*\|[\s|:-]*$""")

    private val HEADING = Regex("""^#{1,6}\s*""")
    private val QUOTE = Regex("""^>+\s*""")
    private val BULLET = Regex("""^([-*+]|\d{1,3}[.)])\s+""")
    private val LINK = Regex("""\[([^]]*)]\([^)]*\)""")

    /**
     * ⚠️ Only paired markers and backticks. A lone `_` is far more likely to be inside
     * `body_truncated` than to be emphasis, and mangling an identifier he is listening
     * for is worse than an asterisk Piper says nothing for anyway.
     */
    private val DECORATION = Regex("""\*\*|__|`""")

    private val SPACES = Regex("""[ \t]+""")

    /** `pane , status` after a pipe swap, or a run of empty cells. */
    private val LOOSE_COMMA = Regex("""\s*,(\s*,)*\s*""")
}
