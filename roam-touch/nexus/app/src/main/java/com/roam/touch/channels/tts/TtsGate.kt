package com.roam.touch.channels.tts

import com.roam.touch.channels.model.Event
import com.roam.touch.channels.model.EventKind

/**
 * The manual override. A plain on/off switch is the wrong shape for a worn device — it
 * is always wrong in one of the two situations you are actually in — so the default is
 * contextual and the switch only exists to force the two ends.
 */
enum class TtsMode {
    /** Speak when he is not looking at the screen. The default, and the point. */
    AUTO,

    /** Speak regardless. For hands-full work with the screen deliberately dark. */
    ALWAYS,

    /** Never speak. For a room with other people in it. */
    MUTED;

    fun next(): TtsMode = when (this) {
        AUTO -> ALWAYS
        ALWAYS -> MUTED
        MUTED -> AUTO
    }

    val label: String
        get() = when (this) {
            AUTO -> "AUTO"
            ALWAYS -> "ALWAYS"
            MUTED -> "MUTED"
        }
}

/**
 * Everything the gate is allowed to know. Kept as a value so the decision is a pure
 * function and the awkward combinations are unit tests instead of a phone in a hand.
 */
data class SpeechContext(
    val mode: TtsMode,
    /** Display state. Screen off is the strongest signal that he cannot read it. */
    val screenOn: Boolean,
    /** True only while the Channels UI is actually resumed in front of him. */
    val appForeground: Boolean,
    /**
     * True when this event arrived as replayed catch-up rather than live. A backlog is
     * spoken by nobody: he has been away, the bridge already buzzed his arm for these,
     * and reciting twenty stale outcomes at a walking man is a punishment.
     */
    val fromBacklog: Boolean = false,
)

object TtsGate {

    /** Only what the agent said, and only what actually needs hearing. */
    val SPEAKABLE_KINDS = setOf(EventKind.OUTCOME, EventKind.ERROR)

    fun shouldSpeak(event: Event, ctx: SpeechContext): Boolean {
        if (ctx.mode == TtsMode.MUTED) return false
        if (ctx.fromBacklog) return false
        if (event.kindEnum !in SPEAKABLE_KINDS) return false
        if (event.controlKey != null) return false
        if (event.summary.isBlank() && event.body.isBlank()) return false

        // API.md: an outcome whose transcript never settled "may be an earlier block of
        // the same turn ... show it with a caveat rather than reading it out as the
        // answer". Reading a plausible wrong answer aloud is the worst failure this
        // device has, because it is indistinguishable from a right one.
        if (event.unsettled) return false

        // ★ The hub decides where a reply belongs, not the client. If he typed the
        // prompt in tmux, the answer is already on the screen he is reading and ROAM
        // saying it aloud is pure noise. ALWAYS still overrides — that is what a manual
        // override is for.
        if (event.covered && ctx.mode != TtsMode.ALWAYS) return false

        return when (ctx.mode) {
            TtsMode.ALWAYS -> true
            // He is looking at it — the panel already said it. Anything else is noise.
            TtsMode.AUTO -> !(ctx.screenOn && ctx.appForeground)
            TtsMode.MUTED -> false
        }
    }

    /**
     * What Piper is handed. The hub already computed a speakable summary (emoji and
     * markdown stripped, code blocks reduced) and `API.md` is explicit that the client
     * must not re-derive it — one implementation, so the panel and the voice agree.
     * The channel label is prefixed so he knows *who* is talking without looking.
     */
    fun utterance(channelLabel: String, event: Event): String {
        val what = event.summary.ifBlank { event.body }.trim().take(MAX_UTTERANCE)
        val who = speakableLabel(channelLabel)
        val prefix = if (event.kindEnum == EventKind.ERROR) "Error in $who" else who
        return if (who.isBlank()) what else "$prefix. $what"
    }

    /**
     * tmux pane titles start with the agent's status glyph (`✳`, `◑`). Piper says
     * nothing for those, but it does pause on them; strip them so the label lands
     * cleanly.
     */
    fun speakableLabel(label: String): String =
        label.filter { it.isLetterOrDigit() || it.isWhitespace() || it in "-_.:," }
            .trim()
            .take(60)

    private const val MAX_UTTERANCE = 400
}
