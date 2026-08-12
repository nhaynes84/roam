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
) {
    Column(
        Modifier
            .fillMaxSize()
            .background(RoamColors.Background)
    ) {
        ListTopBar(state, battery)
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
        PttBar()
    }
}

@Composable
private fun ListTopBar(
    state: ChannelsState,
    battery: BatteryState,
) {
    Row(
        Modifier
            .fillMaxWidth()
            .background(RoamColors.Surface)
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            "CHANNELS",
            style = MaterialTheme.typography.labelLarge,
            color = RoamColors.TextSecondary,
        )
        val unread = state.totalUnread()
        if (unread > 0) {
            Spacer(Modifier.width(9.dp))
            UnreadBadge(unread)
        }
        Spacer(Modifier.weight(1f))
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

/**
 * The push-to-talk affordance, present and honestly dead.
 *
 * Voice is the primary input in the product thesis, so its control gets the bottom of
 * the screen where a thumb lands — but speech-to-text is explicitly out of V1, and a
 * button that looks alive and does nothing is worse than one that says so.
 */
@Composable
fun PttBar(modifier: Modifier = Modifier) {
    Row(
        modifier
            .fillMaxWidth()
            .background(RoamColors.Surface)
            .heightIn(min = 62.dp)
            .padding(horizontal = 14.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(
            Modifier
                .size(42.dp)
                .background(RoamColors.SurfaceRaised, RoundedCornerShape(21.dp)),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                imageVector = Icons.Filled.MicOff,
                contentDescription = "push to talk, disabled",
                tint = RoamColors.Dead,
                modifier = Modifier.size(22.dp),
            )
        }
        Column {
            Text(
                "PUSH TO TALK",
                style = MaterialTheme.typography.labelMedium,
                color = RoamColors.Dead,
            )
            Text(
                "not in V1 — no speech-to-text yet",
                style = MaterialTheme.typography.bodySmall,
                color = RoamColors.TextSecondary.copy(alpha = 0.65f),
            )
        }
        Spacer(Modifier.weight(1f))
        StateChip("V2", RoamColors.Dead)
    }
}
