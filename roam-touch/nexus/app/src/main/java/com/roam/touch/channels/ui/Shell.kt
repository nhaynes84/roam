package com.roam.touch.channels.ui

import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalConfiguration

/**
 * ★★ How much room the panel has, and therefore what shape it takes.
 *
 * The owner's constraint, verbatim: *"landscape is a more reasonable use of a forearm...
 * the app needs to be built for landscape as well, it currently isn't."* Rotating the
 * portrait layout is not the work. So this is the one place that decides which of the two
 * real layouts is on screen, and every composable that differs takes it as a parameter
 * rather than reaching for the configuration itself — which is what makes both shapes
 * testable without a device.
 *
 * ⚠️ **Vertical is the scarce axis, because vertical is where he reads.** Both shapes
 * therefore spend width to buy height: [Wide] puts the whole channel list in a left rail,
 * [Narrow] collapses that rail to a strip of destinations. Neither stacks chrome above
 * the messages.
 */
enum class Shell {
    /**
     * Portrait. The rail collapses to a strip barely wider than a thumb: the destinations
     * and the voice door, no channel list. The list gets the content pane to itself.
     */
    Narrow,

    /**
     * Landscape. The rail carries the channel list, the destinations, the voice door and
     * the canned replies — everything that used to sit *above* the messages.
     */
    Wide;

    companion object {
        /**
         * The breakpoint, in dp of window width.
         *
         * sailfish is 411 × 731 dp: 411 portrait, 731 landscape. 560 is the standard
         * compact/medium boundary and sits comfortably between them, so the same number
         * does the right thing on a tablet without a second rule.
         */
        const val WIDE_MIN_WIDTH_DP = 560

        /**
         * ⚠️ Width, not `orientation`. The question this answers is "is there room for a
         * rail *beside* the content", which a landscape flag on a narrow screen would get
         * wrong and a wide portrait window would get wrong in the other direction.
         */
        fun of(widthDp: Int): Shell = if (widthDp >= WIDE_MIN_WIDTH_DP) Wide else Narrow
    }
}

/** The live shell, recomputed when — and only when — the window width changes. */
@Composable
fun rememberShell(): Shell {
    val widthDp = LocalConfiguration.current.screenWidthDp
    return remember(widthDp) { Shell.of(widthDp) }
}
