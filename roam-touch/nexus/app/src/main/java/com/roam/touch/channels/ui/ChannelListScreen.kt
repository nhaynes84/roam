package com.roam.touch.channels.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.MicOff
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.roam.touch.channels.BatteryState
import com.roam.touch.channels.ChannelsState
import com.roam.touch.channels.HubLink
import com.roam.touch.channels.Liveliness
import com.roam.touch.channels.Liveness
import com.roam.touch.channels.LivenessLabel
import com.roam.touch.channels.OfflineReason
import com.roam.touch.channels.Queue
import com.roam.touch.channels.model.Channel

/**
 * ★ The queue. Not a feed.
 *
 * Rows are ordered by *what needs him*, top down: unread first, then a session that has
 * gone quiet mid-work (the kill decision), then work in progress, then idle, then dead.
 * Chronology is a tiebreak, never the sort.
 */
@Composable
fun ChannelListScreen(
    state: ChannelsState,
    link: HubLink,
    battery: BatteryState,
    nowMs: Long,
    onOpen: (Channel) -> Unit,
    onOpenApps: () -> Unit,
    onOpenHomeAssistant: () -> Unit,
    onOpenControls: () -> Unit,
) {
    Column(
        Modifier
            .fillMaxSize()
            .background(RoamColors.Background)
    ) {
        ListTopBar(state, battery, onOpenApps, onOpenHomeAssistant, onOpenControls)
        LinkBanner(link, nowMs)

        val ordered = Queue.order(state, nowMs)
        if (ordered.isEmpty()) {
            EmptyState(link)
        } else {
            LazyColumn(Modifier.weight(1f)) {
                items(ordered, key = { it.paneId }) { channel ->
                    ChannelRow(
                        state = state,
                        channel = channel,
                        nowMs = nowMs,
                        onClick = { onOpen(channel) },
                    )
                }
            }
        }
        PttBar(
            // ⚠️ Deliberately not "hold here and I will guess the channel". The list is
            // ordered live-first, most-recent-next, so its top row moves under him —
            // the same class of failure as keying channels on tmux indices instead of
            // pane ids. Voice routes from a channel he is looking at, never from a
            // position in a list. This takes him there; the mic is one screen in.
            top = state.channels.firstOrNull { it.live } ?: state.channels.firstOrNull(),
            onOpen = onOpen,
        )
    }
}

/**
 * ★ Channels keeps the title; the two doors off it are chips, and they are small.
 *
 * HA gets its own chip rather than living one level down under APPS because it is the
 * thing he reaches for while walking past a light switch — two taps to turn a lamp off
 * is one tap too many. Everything else is behind APPS, where it belongs.
 */
@Composable
private fun ListTopBar(
    state: ChannelsState,
    battery: BatteryState,
    onOpenApps: () -> Unit,
    onOpenHomeAssistant: () -> Unit,
    onOpenControls: () -> Unit,
) {
    Row(
        Modifier
            .fillMaxWidth()
            .background(RoamColors.Surface)
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(7.dp),
    ) {
        Text(
            "CHANNELS",
            style = MaterialTheme.typography.labelLarge,
            color = RoamColors.TextSecondary,
        )
        val unread = state.totalUnread()
        if (unread > 0) {
            Spacer(Modifier.width(2.dp))
            UnreadBadge(unread)
        }
        Spacer(Modifier.weight(1f))
        ActionChip("HA", RoamColors.Attention, onClick = onOpenHomeAssistant)
        ActionChip("APPS", RoamColors.TextSecondary, onClick = onOpenApps)
        // ⚠️ Reachable without a headset connected, on purpose: he will want to change a
        // binding sitting down, not while putting earbuds in.
        ActionChip("BUDS", RoamColors.TextSecondary, onClick = onOpenControls)
        // No voice-mode control here. The app never speaks unless he taps play on a
        // specific message, so there is no mode to be in.
        BatteryChip(battery)
    }
}

@Composable
fun BatteryChip(battery: BatteryState) {
    if (!battery.known) {
        StateChip("BATT ?", RoamColors.Dead)
        return
    }
    val color = when {
        battery.charging -> RoamColors.Working
        battery.low -> RoamColors.Alarm
        battery.percent <= 40 -> RoamColors.Quiet
        else -> RoamColors.TextSecondary
    }
    // A worn device with no charge is a brick on your arm; the number is always shown,
    // never hidden behind an icon that only turns red at the end.
    StateChip(
        text = if (battery.charging) "${battery.percent}% CHG" else "${battery.percent}%",
        color = color,
        filled = battery.low,
    )
}

/**
 * ★★ Hub-unreachable must be SEEN.
 *
 * Owner's failure mode, stated: trusting silence that actually means "nothing is
 * arriving". So this is a full-width red bar that displaces content, carries how long
 * the link has been down and when the next attempt is — never a toast, never a small
 * grey dot.
 */
@Composable
fun LinkBanner(link: HubLink, nowMs: Long) {
    when (link) {
        is HubLink.Online -> Unit

        is HubLink.Connecting -> Row(
            Modifier
                .fillMaxWidth()
                .background(RoamColors.SurfaceRaised)
                .padding(horizontal = 14.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            TypingEllipsis(color = RoamColors.Attention, dot = 5.dp)
            Text(
                "connecting to hub",
                style = MaterialTheme.typography.bodySmall,
                color = RoamColors.TextSecondary,
            )
        }

        is HubLink.Offline -> {
            val headline = when (link.reason) {
                OfflineReason.UNAUTHORISED -> "HUB REFUSED TOKEN"
                OfflineReason.DESYNC -> "RESYNCING"
                OfflineReason.UNREACHABLE -> "HUB UNREACHABLE"
            }
            val fatal = link.reason == OfflineReason.UNAUTHORISED
            Column(
                Modifier
                    .fillMaxWidth()
                    .background(if (fatal) RoamColors.Alarm else RoamColors.Alarm.copy(alpha = 0.92f))
                    .padding(horizontal = 14.dp, vertical = 10.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        headline,
                        style = MaterialTheme.typography.labelLarge,
                        color = Color.White,
                    )
                    Spacer(Modifier.weight(1f))
                    val retryIn = (link.nextRetryAtMs - nowMs).coerceAtLeast(0)
                    Text(
                        if (fatal) "check token" else "retry ${Format.duration(retryIn)}",
                        style = MaterialTheme.typography.bodySmall,
                        color = Color.White.copy(alpha = 0.9f),
                    )
                }
                Spacer(Modifier.height(3.dp))
                Text(
                    text = link.lastContactMs
                        ?.let { "nothing since ${Format.ago(nowMs - it)} — this is NOT silence" }
                        ?: "never reached the hub — check Tailscale",
                    style = MaterialTheme.typography.bodySmall,
                    color = Color.White.copy(alpha = 0.92f),
                )
            }
        }
    }
}

@Composable
private fun ChannelRow(
    state: ChannelsState,
    channel: Channel,
    nowMs: Long,
    onClick: () -> Unit,
) {
    val liveness = Liveliness.of(state, channel, nowMs)
    val unread = state.unreadCount(channel.paneId)
    val dead = liveness is Liveness.Dead

    // A dead channel keeps its history and must LOOK dead — dimming the whole row
    // rather than restyling each child means it reads as gone at a glance, from the
    // same distance the working rows read as alive.
    Dimmed(dead) {
    Column(
        Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .background(if (unread > 0) RoamColors.Surface else RoamColors.Background)
            .heightIn(min = 84.dp)
            .padding(horizontal = 14.dp, vertical = 10.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            LivenessGlyph(liveness)
            Spacer(Modifier.width(11.dp))
            Text(
                text = channel.displayLabel,
                style = MaterialTheme.typography.titleMedium,
                color = if (dead) RoamColors.Dead else RoamColors.TextPrimary,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f),
            )
            Spacer(Modifier.width(8.dp))
            UnreadBadge(unread)
        }

        Spacer(Modifier.height(5.dp))
        Row(
            horizontalArrangement = Arrangement.spacedBy(7.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            LivenessChip(liveness)
            Text(
                text = channel.paneId,
                style = MaterialTheme.typography.bodySmall,
                color = RoamColors.TextSecondary.copy(alpha = 0.7f),
            )
        }

        channel.lastEvent?.let { last ->
            Spacer(Modifier.height(6.dp))
            Text(
                text = last.displaySummary(),
                style = MaterialTheme.typography.bodyMedium,
                color = if (dead) RoamColors.TextSecondary.copy(alpha = 0.75f)
                else RoamColors.TextSecondary,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
        }

        Spacer(Modifier.height(6.dp))
        Text(
            text = buildString {
                append(channel.eventCount)
                append(if (channel.eventCount == 1) " event" else " events")
                channel.lastEvent?.let { append(" · ${Format.clock(it.tsMillis)}") }
            },
            style = MaterialTheme.typography.bodySmall,
            color = RoamColors.TextSecondary.copy(alpha = 0.6f),
        )
        Spacer(Modifier.height(3.dp))
        Box(
            Modifier
                .fillMaxWidth()
                .height(1.dp)
                .background(dividerColor())
        )
    }
    }
}

/** The animated part: moving dots mean output is moving, right now. */
@Composable
private fun LivenessGlyph(liveness: Liveness) {
    Box(Modifier.size(width = 26.dp, height = 12.dp), contentAlignment = Alignment.CenterStart) {
        when (liveness) {
            is Liveness.Working -> TypingEllipsis(RoamColors.Working)
            is Liveness.Quiet -> StatusDot(RoamColors.Quiet)
            is Liveness.Idle -> StatusDot(RoamColors.Idle)
            Liveness.Dead -> StatusDot(RoamColors.Dead, 9.dp)
            Liveness.Unknown -> StatusDot(RoamColors.Idle, 8.dp)
        }
    }
}

@Composable
fun LivenessChip(liveness: Liveness) {
    // The words come from LivenessLabel, which is pure and covered by
    // LivenessLabelTest — including the regression where WORKING flickered 0s/1s/2s.
    val text = LivenessLabel.text(liveness)
    when (liveness) {
        is Liveness.Working -> StateChip(text, RoamColors.Working)

        // ★ Filled amber, and always with the number: "nothing has come out for 4m" is
        // the input to "should I kill it", which is the thing he cannot answer from a
        // phone today.
        is Liveness.Quiet -> StateChip(text, RoamColors.Quiet, filled = true)

        is Liveness.Idle -> StateChip(text, RoamColors.Idle)

        // A dead pane keeps its history and must look dead — API.md is explicit that it
        // stays in the list, because its last words may be what you were waiting for.
        Liveness.Dead -> StateChip(text, RoamColors.Dead, filled = true)
        Liveness.Unknown -> StateChip(text, RoamColors.Idle)
    }
}

@Composable
private fun EmptyState(link: HubLink) {
    Box(
        Modifier
            .fillMaxWidth()
            .padding(24.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = if (link.isOnline) "no channels — open a pane on talos"
            else "no channels yet",
            style = MaterialTheme.typography.bodyLarge,
            color = RoamColors.TextSecondary,
        )
    }
}

/** A chip-sized channel name: cut on a word, and marked when it was cut. */
private fun shortLabel(label: String, max: Int = 16): String {
    val clean = label.trimStart { !it.isLetterOrDigit() }.trim()
    if (clean.length <= max) return clean
    val cut = clean.take(max).substringBeforeLast(' ', clean.take(max))
    return "$cut…"
}

/**
 * ★ The door to voice, at the bottom of the screen where a thumb lands.
 *
 * The architecture's loop starts **"pick channel → PTT"**, in that order, and this bar
 * is the first half of it. It carries the mic to the channel rather than the channel to
 * the mic: one tap opens [top] and the live PTT control is waiting there, named, with
 * the confirm step behind it.
 *
 * ⚠️ It does **not** record here. A hold on a list would have to guess a destination,
 * and the destination it would guess moves — the list re-sorts on every hub frame.
 * Voice always routes from a channel he is looking at.
 */
@Composable
fun PttBar(
    top: Channel?,
    onOpen: (Channel) -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier
            .fillMaxWidth()
            .background(RoamColors.Surface)
            .heightIn(min = 62.dp)
            .then(if (top != null) Modifier.clickable { onOpen(top) } else Modifier)
            .padding(horizontal = 14.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        val enabled = top != null
        Box(
            Modifier
                .size(42.dp)
                .background(RoamColors.SurfaceRaised, RoundedCornerShape(21.dp)),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                imageVector = if (enabled) Icons.Filled.Mic else Icons.Filled.MicOff,
                contentDescription = if (enabled) "push to talk, open a channel to talk"
                else "push to talk, no channels yet",
                tint = if (enabled) RoamColors.Attention else RoamColors.Dead,
                modifier = Modifier.size(22.dp),
            )
        }
        Column(Modifier.weight(1f)) {
            Text(
                "PUSH TO TALK",
                style = MaterialTheme.typography.labelMedium,
                color = if (enabled) RoamColors.Attention else RoamColors.Dead,
            )
            Text(
                if (top != null) "open a channel to talk"
                else "no channels to talk to yet",
                style = MaterialTheme.typography.bodySmall,
                color = RoamColors.TextSecondary.copy(alpha = 0.75f),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        // Where the tap goes, named — so the door says which room it opens.
        if (top != null) StateChip(shortLabel(top.displayLabel), RoamColors.Idle)
    }
}
