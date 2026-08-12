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
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.roam.touch.channels.ChannelsState
import com.roam.touch.channels.Liveliness
import com.roam.touch.channels.Liveness
import com.roam.touch.channels.ThreadEntry
import com.roam.touch.channels.model.Channel
import com.roam.touch.channels.model.Event
import com.roam.touch.channels.model.EventKind
import com.roam.touch.channels.stt.PttState
import com.roam.touch.channels.stt.PttTarget
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/**
 * One channel's thread.
 *
 * ★ Summary first, full body on demand — the house rule, and it applies to every kind,
 * not just outcomes. Nothing is a wall of text, nothing is truncated so hard it is
 * useless: the hub's own `summary` is always shown, and anything with more behind it
 * gets an explicit affordance saying how much more.
 *
 * ⚠️ **The list shows summaries and nothing else.** "On demand" is [ReaderScreen], a
 * screen of its own — never a card that grows into a wall of text where a glanceable
 * list used to be.
 */
@Composable
fun ThreadScreen(
    state: ChannelsState,
    channel: Channel,
    nowMs: Long,
    speakingEventId: Long?,
    pttState: PttState,
    pttLevel: StateFlow<Double>,
    onBack: () -> Unit,
    onRead: (Event) -> Unit,
    onPlay: (Event) -> Unit,
    onStopPlaying: () -> Unit,
    draft: String,
    outbox: Outbox?,
    onDraft: (String) -> Unit,
    onSend: (String) -> Unit,
    onSendDraft: () -> Unit,
    onInterrupt: () -> Unit,
    onKill: () -> Unit,
    onPttPress: (PttTarget) -> Unit,
    onPttRelease: () -> Unit,
    onPttSend: () -> Unit,
    onPttCancel: () -> Unit,
    onPttDismiss: () -> Unit,
) {
    // ★ Entries, not events: the echo of a message he sent from here is folded into
    // the entry it confirms, so one thing he said is one row. See [ThreadEntries].
    val entries = state.entries(channel.paneId)
    val listState = rememberLazyListState()
    val scope = rememberCoroutineScope()
    var stopDialog by remember { mutableStateOf(false) }

    // ★ See [ThreadFollow]. Follow the tail only from the tail; otherwise the list would
    // snap to the bottom under his thumb every time the agent emitted anything.
    val atTail by remember {
        derivedStateOf {
            val info = listState.layoutInfo
            val last = info.visibleItemsInfo.lastOrNull()
            ThreadFollow.isAtTail(
                lastVisibleIndex = last?.index ?: -1,
                lastVisibleBottomPx = last?.let { it.offset + it.size } ?: 0,
                lastIndex = info.totalItemsCount - 1,
                viewportBottomPx = info.viewportEndOffset,
            )
        }
    }

    // Something landed while he was reading further up. Not silent — see the chip below.
    var newBelow by remember(channel.paneId) { mutableStateOf(false) }

    // ⚠️ Opening a thread is not "an event arrived": a `LazyColumn` starts at index 0, so
    // without this the very first frame looks like he had scrolled away from the tail and
    // the panel greeted him with "NEW BELOW" over the newest answer. Jump, don't animate —
    // he asked for this channel, not for a tour of it.
    var settled by remember(channel.paneId) { mutableStateOf(false) }
    LaunchedEffect(channel.paneId, entries.isNotEmpty()) {
        if (entries.isNotEmpty() && !settled) {
            listState.scrollToItem(entries.lastIndex)
            settled = true
        }
    }

    LaunchedEffect(entries.lastOrNull()?.id) {
        if (entries.isEmpty() || !settled) return@LaunchedEffect
        // `atTail` is read before the scroll happens, so it describes where he was when
        // the event arrived rather than where this effect is about to put him.
        if (atTail) listState.animateScrollToItem(entries.lastIndex) else newBelow = true
    }
    LaunchedEffect(atTail) { if (atTail) newBelow = false }

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

        if (entries.isEmpty()) {
            Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                Text(
                    "no history",
                    style = MaterialTheme.typography.bodyLarge,
                    color = RoamColors.TextSecondary,
                )
            }
        } else {
            Box(Modifier.weight(1f)) {
                LazyColumn(
                    state = listState,
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(
                        start = 12.dp, end = 12.dp, top = 10.dp, bottom = 10.dp
                    ),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    items(entries, key = { it.id }) { entry ->
                        EventCard(
                            entry = entry,
                            speaking = speakingEventId == entry.id,
                            onRead = { onRead(entry.event) },
                            onPlay = { onPlay(entry.event) },
                            onStopPlaying = onStopPlaying,
                        )
                    }
                }

                // ⚠️ An answer that arrives while he is reading history must not move the
                // page, and must not be silent either. A chip, with the way to it.
                if (newBelow) {
                    StateChip(
                        text = "NEW BELOW ↓",
                        color = RoamColors.Attention,
                        filled = true,
                        modifier = Modifier
                            .align(Alignment.BottomCenter)
                            .padding(bottom = 10.dp)
                            .clip(RoundedCornerShape(7.dp))
                            .clickable {
                                scope.launch { listState.animateScrollToItem(entries.lastIndex) }
                            }
                            .heightIn(min = 40.dp),
                    )
                }
            }
        }

        // ★ The voice panel sits between the thread and the composer: directly above
        // the thumb that opened the mic, and never covering the answer he is reading.
        // ⚠️ `targetLive` reads the channel's live flag *now*, not the one captured at
        // press time — a pane that died while he was talking must say so before Send.
        PttPanel(
            state = pttState,
            level = pttLevel,
            channelLabel = channel.displayLabel,
            targetLive = channel.live,
            nowMs = nowMs,
            onPress = onPttPress,
            onRelease = onPttRelease,
            onSend = onPttSend,
            onCancel = onPttCancel,
            onDismiss = onPttDismiss,
        )

        Composer(
            enabled = channel.live,
            pttState = pttState,
            target = PttTarget(channel.paneId, channel.displayLabel),
            draft = draft,
            outbox = outbox,
            nowMs = nowMs,
            onDraft = onDraft,
            onSend = onSend,
            onSendDraft = onSendDraft,
            onPttPress = onPttPress,
            onPttRelease = onPttRelease,
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
 * One event, as a summary. The body lives in [ReaderScreen].
 *
 * The affordance carries the size (`4.1k chars`) so he can decide whether to open it
 * *before* committing to it — which is the difference between summary-first and
 * summary-then-surprise.
 *
 * ⚠️ There is deliberately no `expanded` state here any more. It used to be a
 * `remember` inside the lazy item, which meant the `LazyColumn` destroyed it whenever
 * the card scrolled out of the viewport: he would open a long answer, look up at the
 * question, come back, and find it collapsed with no sign it had ever opened.
 */
@Composable
private fun EventCard(
    entry: ThreadEntry,
    speaking: Boolean,
    onRead: () -> Unit,
    onPlay: () -> Unit,
    onStopPlaying: () -> Unit,
) {
    val event = entry.event
    val kind = event.kindEnum
    val mine = kind == EventKind.SENT
    val accent = accentFor(entry)

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
            .clickable(enabled = event.hasMore(), onClick = onRead)
            .padding(12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            StateChip(statusLabel(entry), accent)
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
            text = event.displaySummary(),
            style = MaterialTheme.typography.bodyLarge,
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

        // ★ The only affordance, and it is a verb: this opens the message. Filled rather
        // than outlined because it is the one thing on the card he is meant to press, and
        // it carries the size so "how much am I committing to" is answered before the tap.
        if (event.hasMore()) {
            Spacer(Modifier.height(9.dp))
            StateChip(
                text = "READ ALL · ${Format.chars(event.bodyChars)}",
                color = RoamColors.Attention,
                filled = true,
                modifier = Modifier
                    .clip(RoundedCornerShape(7.dp))
                    .clickable(onClick = onRead)
                    .heightIn(min = 40.dp),
            )
        }
    }
}

/**
 * ★★ **A message is one thing with a lifecycle, not a pile of events that share text.**
 *
 * The owner, on seeing his first voice message drawn twice: *"just change the 'status'
 * from 'YOU' to 'PROMPT' on receival — same message, multiple states."* So the entry he
 * sent is `YOU` while it is only in the hub, and becomes `PROMPT` the moment the echo
 * says the agent has it. One row, whose status advances.
 *
 * Deliberately not inside the composable: this is the string on the card that has to be
 * right, and a rule that lives in a `@Composable` can only be checked by looking at a
 * phone.
 */
internal fun statusLabel(entry: ThreadEntry): String =
    // ⚠️ A control byte is an action, not something he said; it keeps its own word.
    if (entry.advanced) "PROMPT" else kindLabel(entry.event)

/** The chip colour follows the status, so `PROMPT` looks the same however it got there. */
internal fun accentFor(entry: ThreadEntry): Color =
    if (entry.advanced) RoamColors.Quiet else accentFor(entry.event.kindEnum)

private val ThreadEntry.advanced: Boolean
    get() = delivered && event.controlKey == null

internal fun kindLabel(event: Event): String =
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

internal fun accentFor(kind: EventKind): Color = when (kind) {
    EventKind.OUTCOME -> RoamColors.Working
    EventKind.ERROR, EventKind.CLOSED -> RoamColors.Alarm
    EventKind.SENT -> RoamColors.Attention
    EventKind.RECEIPT -> RoamColors.Quiet
    else -> RoamColors.Idle
}

/**
 * Send: voice, canned replies, and free text — in that order of importance.
 *
 * ★ The mic is first because the thesis says so: *voice is the input, the screen reads
 * output and confirms input.* The canned row exists because the four things he actually
 * types from a corridor are one word long. The keyboard is last, and stays, because
 * ⚠️ **you cannot voice-type a password**.
 */
@Composable
private fun Composer(
    enabled: Boolean,
    pttState: PttState,
    target: PttTarget,
    draft: String,
    outbox: Outbox?,
    nowMs: Long,
    onDraft: (String) -> Unit,
    onSend: (String) -> Unit,
    onSendDraft: () -> Unit,
    onPttPress: (PttTarget) -> Unit,
    onPttRelease: () -> Unit,
) {
    // ⚠️ The words live above this composable — see [ChannelsViewModel.draft]. A `remember`
    // here is what let a failed send delete a sentence he had just typed.
    val inFlight = outbox != null
    val canSend = enabled && !inFlight

    Column(
        Modifier
            .fillMaxWidth()
            .background(RoamColors.Surface)
    ) {
        Box(Modifier.fillMaxWidth().height(1.dp).background(dividerColor()))

        // ★★ A send in flight is *shown*, with a clock on it.
        //
        // ⚠️ This row is the whole of the fix for the typed half of the freeze. Tapping
        // a canned chip used to produce nothing visible whatsoever until the hub
        // answered, so a hub that never answered was indistinguishable from a dead app.
        // Measured against a wedged hub on the emulator: 105 s, blank screen, no error.
        if (outbox != null) {
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                TypingEllipsis(RoamColors.Quiet)
                Spacer(Modifier.width(9.dp))
                Text(
                    "SENDING · ${((nowMs - outbox.startedAtMs) / 1_000).coerceAtLeast(0)}s",
                    style = MaterialTheme.typography.labelMedium,
                    color = RoamColors.Quiet,
                )
                Spacer(Modifier.width(9.dp))
                Text(
                    outbox.text,
                    style = MaterialTheme.typography.bodySmall,
                    color = RoamColors.TextSecondary,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }

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
                    color = if (canSend) RoamColors.Attention else RoamColors.Dead,
                    modifier = Modifier
                        .heightIn(min = 38.dp)
                        .clickable(enabled = canSend) { onSend(reply) },
                )
            }
        }
        Row(
            Modifier.padding(start = 12.dp, end = 8.dp, bottom = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // PTT sits where the thumb lands. Hold it and talk.
            PttButton(
                state = pttState,
                target = target,
                enabled = enabled,
                onPress = onPttPress,
                onRelease = onPttRelease,
            )
            Spacer(Modifier.width(8.dp))
            OutlinedTextField(
                value = draft,
                onValueChange = onDraft,
                modifier = Modifier.weight(1f),
                enabled = canSend,
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
                    if (canSend && draft.isNotBlank()) onSendDraft()
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
                onClick = onSendDraft,
                enabled = canSend && draft.isNotBlank(),
            ) {
                Icon(
                    Icons.AutoMirrored.Filled.Send,
                    contentDescription = "send",
                    tint = if (canSend && draft.isNotBlank()) RoamColors.Attention
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
