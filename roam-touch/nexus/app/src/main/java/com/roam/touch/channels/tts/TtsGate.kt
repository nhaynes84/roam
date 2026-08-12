package com.roam.touch.channels.tts

import com.roam.touch.channels.model.Event

/**
 * ★★ **Nothing is ever spoken unless he asks for it.**
 *
 * There is no gate here any more, because there is nothing to gate. An earlier version
 * decided for itself when to read outcomes aloud — screen off, app backgrounded, hub
 * presence, and so on — and the owner's verdict on it, live on the device, was:
 *
 * > *"I'm talking to you on my laptop, I'm not on the phone at all, and I should have the
 * > option to just 'play' a message, I don't want it non stop blabbering at me."*
 *
 * So the automatic path is deleted rather than defaulted off. The only way audio happens
 * is a tap on a play control next to a specific message. ⚠️ **Do not reintroduce an
 * automatic mode, not even behind a setting that starts enabled.** If auto-play ever
 * earns its place it is a per-channel thing he switches on deliberately, and he has not
 * asked for it.
 *
 * What survives is the wording: given a message he chose, this decides what Piper says.
 */
object Utterance {

    /**
     * What Piper is handed.
     *
     * The hub already computed a speakable summary — markdown stripped, code blocks and
     * tables reduced to `[code, 12 lines]`, decorative glyphs dropped — and `API.md` is
     * explicit that the client must not re-derive it: one implementation, so the panel
     * and the voice say the same thing. The channel label goes first so he knows who is
     * talking without looking at the screen he deliberately is not looking at.
     */
    fun of(channelLabel: String, event: Event): String {
        val what = event.summary.ifBlank { event.body }.trim().take(MAX_CHARS)
        if (what.isEmpty()) return ""
        val who = speakableLabel(channelLabel)
        if (who.isEmpty()) return what
        val prefix = if (event.kindEnum == com.roam.touch.channels.model.EventKind.ERROR) {
            "Error in $who"
        } else {
            who
        }
        return "$prefix. $what"
    }

    /**
     * tmux pane titles start with the agent's status glyph (`✳`, `◑`). Piper says nothing
     * for those but does pause on them, so they come out as a stumble before the name.
     */
    fun speakableLabel(label: String): String =
        label.filter { it.isLetterOrDigit() || it.isWhitespace() || it in "-_.:," }
            .trim()
            .take(60)

    /** Long enough for any hub summary (280) plus a label, short enough to not ramble. */
    const val MAX_CHARS = 400
}
