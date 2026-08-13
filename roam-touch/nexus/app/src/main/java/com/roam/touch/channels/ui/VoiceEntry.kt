package com.roam.touch.channels.ui

import com.roam.touch.channels.model.Channel

/**
 * ★★ Where a voice press with nowhere to go actually goes.
 *
 * There are two ways to reach for the mic without a channel open — a headset tap, and the
 * TALK door in the nav rail — and they must not disagree. The rule, from the headset
 * surface that had it first: **open the top LIVE channel and say so, never guess.**
 *
 * ⚠️ "The top one" is not a destination. The queue re-sorts on every hub frame, so a
 * control that silently recorded into whatever was at the top would send his words to a
 * pane that moved under him — the same class of failure as keying channels on tmux
 * indices instead of pane ids. So this resolves a channel to *navigate to*; recording
 * still only ever happens inside the thread, against a channel he is looking at.
 *
 * Pure and separate from the composable on purpose: this is the rule that has to be
 * right, and a rule that lives in a `@Composable` can only be checked by looking at a
 * phone.
 */
object VoiceEntry {

    /**
     * The channel a voice press should open, or `null` when there is nothing to talk to
     * — in which case the caller must say *that* rather than opening something.
     *
     * ⚠️ Live first, and only then the most recent: a dead pane cannot be typed into, so
     * landing him in one would cost him a whole sentence before the panel admitted it.
     */
    fun target(channels: List<Channel>): Channel? =
        channels.firstOrNull { it.live } ?: channels.firstOrNull()
}
