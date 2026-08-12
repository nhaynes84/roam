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
     * ★★ **Play is demand, and demand is the whole message.**
     *
     * This used to speak `event.summary`, which the hub caps at 280 characters — so the
     * voice stopped at the same sentence the screen did, and the owner reasonably read
     * the pair as one "message capping thing". It was: *"the TTS also cuts off there."*
     * `API.md` calls the summary "always safe to speak", and that is a statement about
     * a **glance** — the notification, the strip — not a limit on what he is allowed to
     * hear once he has tapped play on one specific message. His standing rule is summary
     * first, full detail on demand; this is the demand path, so it gets the full detail.
     *
     * ⚠️ [body] is passed in rather than read off [event] because the caller may have
     * had to fetch it: a bulk payload is trimmed to 4 KiB, and speaking that tail as if
     * it were the whole answer is the same lie as printing it. See `ChannelsViewModel`.
     *
     * The channel label still goes first, so he knows who is talking without looking at
     * the screen he is deliberately not looking at.
     */
    fun of(channelLabel: String, event: Event, body: String = event.body): String {
        val what = spoken(event, body).take(MAX_CHARS)
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
     * The words themselves, before the label is put in front of them.
     *
     * ⚠️ The summary is the *fallback*, not the source: some kinds carry a summary and
     * an empty body, and a control byte is an action whose spoken form is its label —
     * `` has no pronunciation.
     */
    private fun spoken(event: Event, body: String): String {
        event.controlKey?.let { return it.label }
        return Speech.plain(body)
            .ifBlank { Speech.plain(event.body) }
            .ifBlank { event.summary.trim() }
    }

    /**
     * tmux pane titles start with the agent's status glyph (`✳`, `◑`). Piper says nothing
     * for those but does pause on them, so they come out as a stumble before the name.
     */
    fun speakableLabel(label: String): String =
        label.filter { it.isLetterOrDigit() || it.isWhitespace() || it in "-_.:," }
            .trim()
            .take(60)

    /**
     * A guard against a pathological payload, **not** a message cap.
     *
     * ⚠️ It used to be 400 — "any hub summary plus a label" — which is precisely how the
     * voice came to stop six lines in. Real answers run 300–6000 characters; the hub's
     * own storage cap is 256 KiB. This sits far above anything he would ever ask to hear
     * and exists only so a runaway body cannot commit the speaker to an hour of audio.
     */
    const val MAX_CHARS = 20_000
}
