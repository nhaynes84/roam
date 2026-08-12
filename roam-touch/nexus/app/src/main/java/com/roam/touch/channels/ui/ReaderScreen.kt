package com.roam.touch.channels.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.roam.touch.channels.ChannelsState
import com.roam.touch.channels.model.Channel
import com.roam.touch.channels.model.Event

/**
 * ★★ One message, all of it, on a screen of its own.
 *
 * ### Why a screen and not an in-place expander
 *
 * The old design expanded the card inside the thread list, and on a forearm that is the
 * wrong shape in three separate ways:
 *
 * 1. **One gesture, two meanings.** A vertical swipe had to serve both "move through the
 *    conversation" and "read this answer". Walking, one-handed, that is a coin toss.
 * 2. **The read was not durable.** `expanded` lived in a `LazyColumn` item, so the state
 *    died with the item the moment it scrolled out of the viewport — expand a 2.3k answer,
 *    glance up at what he asked, come back, collapsed. Reproduced on the emulator before
 *    this change.
 * 3. **The thread moved under him.** A live channel emits events every few seconds and the
 *    tail-follow yanked the list to the bottom mid-sentence.
 *
 * A dedicated screen fixes all three by construction: its scroll means exactly one thing,
 * its state lives above the list where nothing can dispose it, and no arriving event can
 * move it. Getting out is the same tile-sized target he already knows from every other
 * secondary screen.
 *
 * ⚠️ The thread list keeps showing **summaries only**. That is the rule that makes the
 * list glanceable — *"always a summary first, with expandable details if I need them"* —
 * and this screen is the "if I need them", not a reason to abandon it.
 */
@Composable
fun ReaderScreen(
    state: ChannelsState,
    channel: Channel,
    event: Event,
    speaking: Boolean,
    onBack: () -> Unit,
    onPlay: () -> Unit,
    onStopPlaying: () -> Unit,
) {
    val scroll = rememberScrollState()
    val body = state.bodyOf(event).trim().ifBlank { event.displaySummary() }

    // ⚠️ True while the untrimmed body is still in flight. `API.md`: a bulk payload is
    // cut to 4 KiB, and showing that tail as though it were the answer is exactly the
    // silent truncation this whole change exists to kill. So it is announced, never
    // implied — and the number says how much is still missing.
    val awaitingFull = state.needsExpansion(event)

    val more by remember {
        derivedStateOf { scroll.maxValue > 0 && scroll.value < scroll.maxValue - MORE_SLACK_PX }
    }

    Column(
        Modifier
            .fillMaxSize()
            .background(RoamColors.Background)
    ) {
        ReaderTopBar(
            channel = channel,
            event = event,
            speaking = speaking,
            onBack = onBack,
            onPlay = onPlay,
            onStopPlaying = onStopPlaying,
        )

        if (awaitingFull) {
            Row(
                Modifier
                    .fillMaxWidth()
                    .background(RoamColors.Quiet.copy(alpha = 0.16f))
                    .padding(horizontal = 14.dp, vertical = 9.dp)
            ) {
                Text(
                    "fetching the rest — ${Format.chars(event.bodyChars)} in full",
                    style = MaterialTheme.typography.bodySmall,
                    color = RoamColors.Quiet,
                )
            }
        }

        Box(Modifier.weight(1f)) {
            Column(
                Modifier
                    .fillMaxSize()
                    .verticalScroll(scroll)
                    .padding(horizontal = 14.dp, vertical = 12.dp)
            ) {
                Text(
                    text = body,
                    // 17sp. He reads this at arm's length, sometimes moving.
                    style = MaterialTheme.typography.bodyLarge,
                    color = if (event.kindEnum == com.roam.touch.channels.model.EventKind.ERROR) {
                        RoamColors.Alarm
                    } else {
                        RoamColors.TextPrimary
                    },
                    modifier = Modifier.testTag(BODY_TAG),
                )
                // Room to scroll the last line clear of the "MORE" chip.
                Spacer(Modifier.height(56.dp))
            }

            // ★ "It must be obvious there is more to read." A silent stop is what caused
            // the original complaint, so the end of the text is stated rather than left
            // to be discovered — a chip, not a sentence, and it is also the way down.
            if (more) {
                StateChip(
                    text = "MORE ↓",
                    color = RoamColors.Attention,
                    filled = true,
                    // Bottom-*end*, not centre: prose is ragged on the right, so this is
                    // the one corner where a floating chip covers the fewest words.
                    modifier = Modifier
                        .align(Alignment.BottomEnd)
                        .padding(end = 12.dp, bottom = 12.dp)
                        .defaultMinSize(minHeight = 40.dp),
                )
            }
        }
    }
}

/**
 * Who said it, when, and the one control worth having here.
 *
 * ★ Play is on this screen deliberately. The honest answer to "a 6000-character answer on
 * a wrist" is often not to read it at all — it is to press play and keep walking, which is
 * the product thesis working as intended rather than a consolation prize.
 */
@Composable
private fun ReaderTopBar(
    channel: Channel,
    event: Event,
    speaking: Boolean,
    onBack: () -> Unit,
    onPlay: () -> Unit,
    onStopPlaying: () -> Unit,
) {
    Column(
        Modifier
            .fillMaxWidth()
            .background(RoamColors.Surface)
    ) {
        Row(
            Modifier.padding(start = 10.dp, end = 10.dp, top = 8.dp, bottom = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            // Same shape and same corner as every other way back in this app.
            Row(
                Modifier
                    .clip(RoundedCornerShape(9.dp))
                    .clickable(onClick = onBack)
                    .background(RoamColors.SurfaceRaised)
                    .defaultMinSize(minHeight = 44.dp)
                    .padding(horizontal = 12.dp, vertical = 9.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(7.dp),
            ) {
                Icon(
                    Icons.AutoMirrored.Filled.ArrowBack,
                    contentDescription = "back to the thread",
                    tint = RoamColors.Attention,
                    modifier = Modifier.size(19.dp),
                )
                Text(
                    "THREAD",
                    style = MaterialTheme.typography.labelMedium,
                    color = RoamColors.Attention,
                )
            }
            Text(
                channel.displayLabel,
                style = MaterialTheme.typography.labelLarge,
                color = RoamColors.TextSecondary,
                modifier = Modifier.weight(1f),
            )
            IconButton(
                onClick = { if (speaking) onStopPlaying() else onPlay() },
                modifier = Modifier.size(44.dp),
            ) {
                Icon(
                    imageVector = if (speaking) Icons.Filled.Stop else Icons.Filled.PlayArrow,
                    contentDescription = if (speaking) "stop speaking" else "read this aloud",
                    tint = if (speaking) RoamColors.Alarm else RoamColors.Attention,
                    modifier = Modifier.size(28.dp),
                )
            }
        }
        Row(
            Modifier.padding(start = 14.dp, end = 14.dp, bottom = 10.dp),
            horizontalArrangement = Arrangement.spacedBy(7.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            StateChip(kindLabel(event), accentFor(event.kindEnum))
            StateChip(Format.chars(event.bodyChars), RoamColors.TextSecondary)
            Spacer(Modifier.weight(1f))
            Text(
                Format.clock(event.tsMillis),
                style = MaterialTheme.typography.bodySmall,
                color = RoamColors.TextSecondary.copy(alpha = 0.7f),
            )
        }
        Box(Modifier.fillMaxWidth().height(1.dp).background(dividerColor()))
    }
}

/** Below this many pixels from the end, "more" is a rounding error rather than content. */
private const val MORE_SLACK_PX = 24

/** So a test can assert on the body text without matching a whole screen of prose. */
const val BODY_TAG = "reader-body"
