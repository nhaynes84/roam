package com.roam.touch.channels.ui

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.getUnclippedBoundsInRoot
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.unit.height
import androidx.compose.ui.unit.width
import com.roam.touch.channels.BatteryState
import com.roam.touch.channels.ChannelReducer
import com.roam.touch.channels.ChannelsState
import com.roam.touch.channels.Fx
import com.roam.touch.channels.stt.PttState
import kotlinx.coroutines.flow.MutableStateFlow
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * ★★ **The number.** Vertical is the scarce axis, because vertical is where he reads.
 *
 * The brief was quantitative — moving the chrome left *"gives us back like 30 % of the
 * vertical space"* — so this measures the reading surface against sailfish's real window,
 * 411 × 731 dp, in both orientations. The layout it replaced spent 252 dp of chrome
 * whatever the orientation, which on a 411 dp-tall landscape window left 159 dp — under
 * two message cards — for the only thing on screen he is actually there to read.
 *
 * ⚠️ These are floors, not targets: set below what the layout achieves today so ordinary
 * tuning does not break the build, and far enough above the old layout that no amount of
 * tuning can drift back to it.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [29])
class LandscapeLayoutTest {

    @get:Rule
    val compose = createComposeRule()

    private val channel = Fx.channel(pane = "%0", label = "◑ Roam Touch rebuild", live = true)

    private val state = (1L..12L).fold(ChannelsState(channels = listOf(channel))) { acc, i ->
        ChannelReducer.applyEvent(acc, Fx.event(id = i, pane = "%0", body = "answer $i"))
    }

    /** The whole panel, laid out exactly as [ChannelsApp] lays it out. */
    private fun renderThread(shell: Shell) {
        compose.setContent {
            RoamTheme {
                Row(Modifier.fillMaxSize()) {
                    NavRail(
                        shell = shell,
                        state = state,
                        battery = BatteryState(percent = 72),
                        nowMs = Fx.NOW_MS,
                        screen = Screen.Channels,
                        openPane = "%0",
                        sending = false,
                        onOpenChannel = {},
                        onHome = {},
                        onOpenApps = {},
                        onOpenHomeAssistant = {},
                        onOpenControls = {},
                        onVoice = {},
                        onQuickSend = {},
                    )
                    ThreadScreen(
                        shell = shell,
                        state = state,
                        channel = channel,
                        nowMs = Fx.NOW_MS,
                        speakingEventId = null,
                        pttState = PttState.Idle,
                        pttLevel = MutableStateFlow(-120.0),
                        // ⚠️ An idle composer on purpose: this test measures the *height*
                        // the layout gives back, and an in-flight send adds a row.
                        draft = "",
                        outbox = null,
                        onDraft = {},
                        onSendDraft = {},
                        onBack = {},
                        onRead = {},
                        onPlay = {},
                        onStopPlaying = {},
                        onSend = {},
                        onInterrupt = {},
                        onKill = {},
                        onPttPress = {},
                        onPttRelease = {},
                        onPttSend = {},
                        onPttCancel = {},
                        onPttDismiss = {},
                    )
                }
            }
        }
    }

    private fun heightDp(tag: String) =
        compose.onNodeWithTag(tag).getUnclippedBoundsInRoot().height.value

    private fun rootHeightDp() = compose.onRoot().getUnclippedBoundsInRoot().height.value

    private fun report(which: String): Triple<Float, Float, Float> {
        val root = rootHeightDp()
        val top = heightDp(THREAD_TOP_BAR)
        val composer = heightDp(COMPOSER)
        val messages = heightDp(MESSAGES)
        println(
            "$which root=${root}dp topbar=${top}dp composer=${composer}dp " +
                "chrome=${top + composer}dp messages=${messages}dp " +
                "(${(100 * messages / root).toInt()}% reading)"
        )
        return Triple(root, top + composer, messages)
    }

    /**
     * ★ Landscape, the orientation the housing is going to.
     *
     * The old layout's 252 dp of chrome left 159 dp of a 411 dp window — 39 %. The floor
     * here is 60 %, which no rearrangement of the old two-row header and two-row composer
     * can reach.
     */
    @Test
    @Config(qualifiers = "w731dp-h411dp-land")
    fun `landscape gives most of a short window to the messages`() {
        renderThread(Shell.Wide)
        val (root, chrome, messages) = report("LANDSCAPE")
        assertTrue("chrome ate ${chrome}dp of a ${root}dp window", chrome <= root * 0.36f)
        assertTrue("messages only got ${messages}dp of ${root}dp", messages >= root * 0.60f)
    }

    /**
     * ⚠️ Portrait must keep working — the housing decision is still open, so this is not
     * a fork with a dead branch in it.
     */
    @Test
    @Config(qualifiers = "w411dp-h731dp-port")
    fun `portrait still works and still reads`() {
        renderThread(Shell.Narrow)
        val (root, _, messages) = report("PORTRAIT")
        assertTrue("messages only got ${messages}dp of ${root}dp", messages >= root * 0.60f)
    }

    /**
     * ★★ The fold, as a rule rather than as two numbers: the same thread, on the same
     * content, must spend strictly less height on chrome in landscape than in portrait.
     * **That is what "built for landscape" means here** — a layout, not a rotation. If
     * this ever passes trivially, the Wide branch has stopped folding anything.
     */
    @Test
    @Config(qualifiers = "w731dp-h411dp-land")
    fun `landscape chrome is strictly shorter than portrait chrome`() {
        renderThread(Shell.Wide)
        val land = heightDp(THREAD_TOP_BAR) + heightDp(COMPOSER)
        // Portrait's chrome is a fixed stack — two header rows and two composer rows —
        // and does not depend on the window it is in, which is exactly the complaint.
        val portraitChrome = PORTRAIT_CHROME_DP
        println("CHROME portrait=${portraitChrome}dp landscape=${land}dp " +
            "saved=${portraitChrome - land}dp")
        assertTrue(
            "landscape chrome ${land}dp is not meaningfully shorter than portrait " +
                "${portraitChrome}dp",
            land <= portraitChrome * 0.75f,
        )
    }

    /**
     * The rail is width, and width is what there is spare of. It must never grow into the
     * reading surface's axis by, say, stacking a header above the whole [Row].
     *
     * ⚠️⚠️ And the rail has a height budget of its own. The first version of this test
     * reported `queue=0.0dp`: five stacked canned chips plus three stacked destinations
     * plus a battery row had squeezed the channel list — **the reason the rail exists** —
     * out of existence whenever a thread was open. Nothing about that was visible in the
     * shape of the code. The floor below is what keeps it visible.
     */
    @Test
    @Config(qualifiers = "w731dp-h411dp-land")
    fun `the rail spends width, never height`() {
        renderThread(Shell.Wide)
        val root = compose.onRoot().getUnclippedBoundsInRoot()
        val rail = compose.onNodeWithTag(RAIL).getUnclippedBoundsInRoot()
        val queue = heightDp(RAIL_QUEUE)
        println("RAIL width=${rail.width.value}dp height=${rail.height.value}dp queue=${queue}dp")
        assertTrue("the rail does not start at the top edge", rail.top.value == 0f)
        assertTrue("the rail is not full height", rail.height == root.height)
        assertTrue("the rail is too wide for a 731dp window", rail.width.value <= 240f)
        assertTrue(
            "the rail footer starved the channel list down to ${queue}dp",
            queue >= 3 * RAIL_ROW_MIN_DP,
        )
    }

    private companion object {
        /**
         * Measured, not guessed: `portrait still works and still reads` prints it, and it
         * is the same number the pre-rail layout carried in *both* orientations.
         */
        const val PORTRAIT_CHROME_DP = 252f

        /** `RailChannelRow`'s `heightIn(min = 46.dp)`. Three rows is a usable list. */
        const val RAIL_ROW_MIN_DP = 46f
    }
}
