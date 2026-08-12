package com.roam.touch.channels.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.MicOff
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.roam.touch.channels.ChannelsState
import com.roam.touch.channels.Liveliness
import com.roam.touch.channels.Liveness
import com.roam.touch.channels.model.Channel
import com.roam.touch.channels.model.Event
import com.roam.touch.channels.model.EventKind

/**
 * One channel's thread.
 *
 * ★ Summary first, full body on demand — the house rule, and it applies to every kind,
 * not just outcomes. Nothing is a wall of text, nothing is truncated so hard it is
 * useless: the hub's own `summary` is always shown, and anything with more behind it
 * gets an explicit affordance saying how much more.
 */
@Composable
fun ThreadScreen(
    state: ChannelsState,
    channel: Channel,
    nowMs: Long,
    speakingEventId: Long?,
    onBack: () -> Unit,
    onExpand: (Event) -> Unit,
    onPlay: (Event) -> Unit,
    onStopPlaying: () -> Unit,
    onSend: (String) -> Unit,
    onInterrupt: () -> Unit,
    onKill: () -> Unit,
) {
    val events = state.thread(channel.paneId)
    val listState = rememberLazyListState()
    var stopDialog by remember { mutableStateOf(false) }

    // Follow the tail: an outcome landing while he is reading should scroll into view,
    // because the reason he is on this screen is that he is waiting for it.
    LaunchedEffect(events.lastOrNull()?.id) {
        if (events.isNotEmpty()) listState.animateScrollToItem(events.lastIndex)
    }

    Column(
        Modifier
            .fillMaxSize()
            .background(RoamColors.Background)
    ) {
        ThreadTopBar(
            state = state,
            channel = channel,
            nowMs = nowMs,
            onBack = onBack,
            onStop = { stopDialog = true },
        )

        if (events.isEmpty()) {
            Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                Text(
                    "no history",
                    style = MaterialTheme.typography.bodyLarge,
                    color = RoamColors.TextSecondary,
                )
            }
        } else {
            LazyColumn(
                state = listState,
                modifier = Modifier.weight(1f),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(
                    start = 12.dp, end = 12.dp, top = 10.dp, bottom = 10.dp
                ),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                items(events, key = { it.id }) { event ->
                    EventCard(
                        state = state,
                        event = event,
                        speaking = speakingEventId == event.id,
                        onExpand = { onExpand(event) },
                        onPlay = { onPlay(event) },
                        onStopPlaying = onStopPlaying,
                    )
                }
            }
        }

        Composer(
            enabled = channel.live,
            onSend = onSend,
        )
    }

    if (stopDialog) {
        StopDialog(
            channel = channel,
            onDismiss = { stopDialog = false },
            onInterrupt = { stopDialog = false; onInterrupt() },
            onKill = { stopDialog = false; onKill() },
        )
    }
}

@Composable
private fun ThreadTopBar(
    state: ChannelsState,
    channel: Channel,
    nowMs: Long,
    onBack: () -> Unit,
    onStop: () -> Unit,
) {
    val liveness = Liveliness.of(state, channel, nowMs)
    Column(
        Modifier
            .fillMaxWidth()
            .background(RoamColors.Surface)
    ) {
        Row(
            Modifier.padding(start = 4.dp, end = 10.dp, top = 6.dp, bottom = 2.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onBack) {
                Icon(
                    Icons.AutoMirrored.Filled.ArrowBack,
                    contentDescription = "back to channels",
                    tint = RoamColors.TextPrimary,
                )
            }
            Text(
                text = channel.displayLabel,
                style = MaterialTheme.typography.titleMedium,
                color = RoamColors.TextPrimary,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f),
            )
            Spacer(Modifier.width(8.dp))
            // ★ Interrupt/kill: today this requires walking to a keyboard. Two taps,
            // because "stop" on the wrong session while walking is expensive.
            Box(
                Modifier
                    .background(RoamColors.Alarm.copy(alpha = 0.16f), RoundedCornerShape(8.dp))
                    .border(1.dp, RoamColors.Alarm.copy(alpha = 0.6f), RoundedCornerShape(8.dp))
                    .clickable(enabled = channel.live, onClick = onStop)
                    .padding(horizontal = 12.dp, vertical = 8.dp),
            ) {
                Text(
                    "STOP",
                    style = MaterialTheme.typography.labelMedium,
                    color = if (channel.live) RoamColors.Alarm else RoamColors.Dead,
                )
            }
        }
        Row(
            Modifier.padding(start = 14.dp, end = 14.dp, bottom = 10.dp),
            horizontalArrangement = Arrangement.spacedBy(7.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (liveness is Liveness.Working) TypingEllipsis(RoamColors.Working)
            LivenessChip(liveness)
            channel.lastInputSource?.let { source ->
                // Where the next answer is expected to be read. The hub decides this;
                // showing it stops "why didn't it speak?" being a mystery.
                StateChip(
                    text = if (source == "app") "REPLYING HERE" else "IN TMUX",
                    color = if (source == "app") RoamColors.Attention else RoamColors.Idle,
                )
            }
            Spacer(Modifier.weight(1f))
            Text(
                channel.paneId,
                style = MaterialTheme.typography.bodySmall,
                color = RoamColors.TextSecondary.copy(alpha = 0.7f),
            )
        }
        Box(Modifier.fillMaxWidth().height(1.dp).background(dividerColor()))
    }
}

/**
 * One event. Summary always; body only when asked for.
 *
 * The expand affordance carries the size (`4.1k chars`) so he can decide whether to
 * open it *before* the screen fills with text — which is the difference between
 * summary-first and summary-then-surprise.
 */
@Composable
private fun EventCard(
    state: ChannelsState,
    event: Event,
    speaking: Boolean,
    onExpand: () -> Unit,
    onPlay: () -> Unit,
    onStopPlaying: () -> Unit,
) {
    var expanded by remember(event.id) { mutableStateOf(false) }
    val kind = event.kindEnum
    val mine = kind == EventKind.SENT
    val accent = accentFor(kind)

    Column(
        Modifier
            .fillMaxWidth()
            .background(
                if (mine) RoamColors.SurfaceRaised else RoamColors.Surface,
                RoundedCornerShape(11.dp),
            )
            .border(
                width = 1.dp,
                color = accent.copy(alpha = if (kind == EventKind.ERROR) 0.7f else 0.22f),
                shape = RoundedCornerShape(11.dp),
            )
            .clickable {
                if (!expanded && state.needsExpansion(event)) onExpand()
                if (event.hasMore()) expanded = !expanded
            }
            .padding(12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            StateChip(kindLabel(event), accent)
            Spacer(Modifier.weight(1f))
            Text(
                Format.clock(event.tsMillis),
                style = MaterialTheme.typography.bodySmall,
                color = RoamColors.TextSecondary.copy(alpha = 0.7f),
            )
            // ★★ The only thing in this app that makes a sound. One tap, one message.
            // Nothing plays on its own — see Utterance and SpeechPolicyTest.
            if (event.summary.isNotBlank() || event.body.isNotBlank()) {
                Spacer(Modifier.width(4.dp))
                IconButton(
                    onClick = { if (speaking) onStopPlaying() else onPlay() },
                    modifier = Modifier.size(40.dp),
                ) {
                    Icon(
                        imageVector = if (speaking) Icons.Filled.Stop
                        else Icons.Filled.PlayArrow,
                        contentDescription = if (speaking) "stop speaking"
                        else "play this message",
                        tint = if (speaking) RoamColors.Alarm else RoamColors.Attention,
                        modifier = Modifier.size(26.dp),
                    )
                }
            }
        }

        // ⚠️ API.md: an outcome whose transcript never settled may be an earlier block
        // of the same turn. It is shown — never hidden — but it is labelled, because a
        // plausible wrong answer is the most dangerous thing this screen can display.
        if (event.unsettled) {
            Spacer(Modifier.height(8.dp))
            Row(
                Modifier
                    .fillMaxWidth()
                    .background(RoamColors.Quiet.copy(alpha = 0.16f), RoundedCornerShape(7.dp))
                    .padding(horizontal = 9.dp, vertical = 6.dp)
            ) {
                Text(
                    "unsettled — may be an earlier part of the turn",
                    style = MaterialTheme.typography.bodySmall,
                    color = RoamColors.Quiet,
                )
            }
        }

        Spacer(Modifier.height(8.dp))
        Text(
            text = if (expanded) state.bodyOf(event).trim().ifBlank { event.displaySummary() }
            else event.displaySummary(),
            style = if (expanded) MaterialTheme.typography.bodyMedium.copy(
                fontFamily = FontFamily.SansSerif
            ) else MaterialTheme.typography.bodyLarge,
            color = if (kind == EventKind.ERROR) RoamColors.Alarm else RoamColors.TextPrimary,
        )

        event.attempted?.takeIf { kind == EventKind.ERROR }?.let { attempted ->
            Spacer(Modifier.height(8.dp))
            Text(
                "not typed: $attempted",
                style = MaterialTheme.typography.bodySmall,
                color = RoamColors.TextSecondary,
            )
        }

        if (event.hasMore()) {
            Spacer(Modifier.height(9.dp))
            val loading = expanded && state.needsExpansion(event)
            StateChip(
                text = when {
                    loading -> "loading…"
                    expanded -> "show summary"
                    else -> "full text · ${Format.chars(event.bodyChars)}"
                },
                color = RoamColors.Attention,
                modifier = Modifier.clickable {
                    if (!expanded && state.needsExpansion(event)) onExpand()
                    expanded = !expanded
                },
            )
        }
    }
}

private fun kindLabel(event: Event): String =
    event.controlKey?.label ?: when (event.kindEnum) {
        EventKind.SENT -> "YOU"
        EventKind.RECEIPT -> "PROMPT"
        EventKind.OUTCOME -> "ANSWER"
        EventKind.OPENED -> "OPENED"
        EventKind.CLOSED -> "CLOSED"
        EventKind.NOTE -> "NOTE"
        EventKind.ERROR -> "FAILED"
        // The contract says treat the kind list as open and render an unknown kind as a
        // plain note rather than dropping it. Showing the raw string beats hiding it.
        EventKind.OTHER -> event.kind.uppercase().take(12)
    }

private fun accentFor(kind: EventKind): Color = when (kind) {
    EventKind.OUTCOME -> RoamColors.Working
    EventKind.ERROR, EventKind.CLOSED -> RoamColors.Alarm
    EventKind.SENT -> RoamColors.Attention
    EventKind.RECEIPT -> RoamColors.Quiet
    else -> RoamColors.Idle
}

/**
 * Send: canned replies plus free text.
 *
 * The canned row exists because the four things he actually types from a corridor are
 * one word long, and typing one word on a forearm is absurd. They send on one tap —
 * the whole value is that it is faster than a keyboard.
 */
@Composable
private fun Composer(
    enabled: Boolean,
    onSend: (String) -> Unit,
) {
    var text by remember { mutableStateOf("") }

    Column(
        Modifier
            .fillMaxWidth()
            .background(RoamColors.Surface)
    ) {
        Box(Modifier.fillMaxWidth().height(1.dp).background(dividerColor()))
        Row(
            Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState())
                .padding(horizontal = 12.dp, vertical = 9.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            CANNED.forEach { reply ->
                StateChip(
                    text = reply.uppercase(),
                    color = if (enabled) RoamColors.Attention else RoamColors.Dead,
                    modifier = Modifier
                        .heightIn(min = 38.dp)
                        .clickable(enabled = enabled) { onSend(reply) },
                )
            }
        }
        Row(
            Modifier.padding(start = 12.dp, end = 8.dp, bottom = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // PTT sits where the thumb lands, and says out loud that it is not wired up.
            Box(
                Modifier
                    .size(44.dp)
                    .background(RoamColors.SurfaceRaised, RoundedCornerShape(22.dp)),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    Icons.Filled.MicOff,
                    contentDescription = "push to talk — not in V1",
                    tint = RoamColors.Dead,
                    modifier = Modifier.size(21.dp),
                )
            }
            Spacer(Modifier.width(8.dp))
            OutlinedTextField(
                value = text,
                onValueChange = { text = it },
                modifier = Modifier.weight(1f),
                enabled = enabled,
                placeholder = {
                    Text(
                        if (enabled) "message" else "pane is dead",
                        style = MaterialTheme.typography.bodyMedium,
                        color = RoamColors.TextSecondary.copy(alpha = 0.6f),
                    )
                },
                textStyle = MaterialTheme.typography.bodyMedium,
                singleLine = false,
                maxLines = 4,
                shape = RoundedCornerShape(11.dp),
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                keyboardActions = KeyboardActions(onSend = {
                    if (text.isNotBlank()) { onSend(text); text = "" }
                }),
                colors = TextFieldDefaults.colors(
                    focusedContainerColor = RoamColors.SurfaceRaised,
                    unfocusedContainerColor = RoamColors.SurfaceRaised,
                    disabledContainerColor = RoamColors.SurfaceRaised,
                    focusedTextColor = RoamColors.TextPrimary,
                    unfocusedTextColor = RoamColors.TextPrimary,
                    focusedIndicatorColor = RoamColors.Attention.copy(alpha = 0.6f),
                    unfocusedIndicatorColor = dividerColor(),
                ),
            )
            IconButton(
                onClick = { if (text.isNotBlank()) { onSend(text); text = "" } },
                enabled = enabled && text.isNotBlank(),
            ) {
                Icon(
                    Icons.AutoMirrored.Filled.Send,
                    contentDescription = "send",
                    tint = if (enabled && text.isNotBlank()) RoamColors.Attention
                    else RoamColors.Dead,
                )
            }
        }
    }
}

/**
 * ★ Two different things, and the difference matters.
 *
 * ESC stops the current turn and leaves the session alive — the usual answer when
 * `idle_s` has been climbing. Ctrl-C twice exits Claude Code, and the session with it.
 * A single "kill" button would conflate them and destroy sessions he only wanted to
 * nudge.
 */
@Composable
private fun StopDialog(
    channel: Channel,
    onDismiss: () -> Unit,
    onInterrupt: () -> Unit,
    onKill: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = RoamColors.SurfaceRaised,
        title = {
            Text(
                "Stop ${channel.displayLabel}?",
                style = MaterialTheme.typography.titleMedium,
                color = RoamColors.TextPrimary,
            )
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    "INTERRUPT sends Esc — stops this turn, keeps the session.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = RoamColors.TextSecondary,
                )
                Text(
                    "KILL sends Ctrl-C twice — exits the agent in that pane.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = RoamColors.Alarm,
                )
            }
        },
        confirmButton = {
            TextButton(onClick = onInterrupt) {
                Text("INTERRUPT", style = MaterialTheme.typography.labelLarge,
                    color = RoamColors.Quiet)
            }
        },
        dismissButton = {
            Row {
                TextButton(onClick = onKill) {
                    Text("KILL", style = MaterialTheme.typography.labelLarge,
                        color = RoamColors.Alarm)
                }
                TextButton(onClick = onDismiss) {
                    Text("CANCEL", style = MaterialTheme.typography.labelLarge,
                        color = RoamColors.TextSecondary)
                }
            }
        },
    )
}

/** What he actually says from a corridor. Kept short enough to read at a glance. */
val CANNED = listOf("continue", "yes", "no", "stop", "explain")
