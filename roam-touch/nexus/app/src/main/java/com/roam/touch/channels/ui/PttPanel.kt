package com.roam.touch.channels.ui

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.tween
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.MicOff
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.roam.touch.channels.stt.Pcm
import com.roam.touch.channels.stt.Ptt
import com.roam.touch.channels.stt.PttState
import com.roam.touch.channels.stt.PttTarget
import kotlinx.coroutines.flow.StateFlow

/**
 * ★★ Push to talk — the input half of the product thesis, on screen.
 *
 * Two pieces, and the split is deliberate. [PttButton] is a thumb-sized target in the
 * composer where the hand already is. [PttPanel] sits directly above it and is the only
 * thing that ever *says what is happening*: listening, transcribing, what was heard,
 * where it is going, why it failed.
 *
 * ⚠️ On a device worn on a forearm there is no other channel for that. A control that
 * looked identical while recording, while waiting on a network call, and while broken
 * would leave him unable to tell a dead mic from a slow one — so every state below is
 * visually distinct at a glance, by colour and by shape, before any word is read.
 */

/** dBFS → 0…1 for the meter. −60 is a silent room, 0 is clipping. */
private fun levelFraction(dbfs: Double): Float =
    ((dbfs - METER_FLOOR_DBFS) / -METER_FLOOR_DBFS).coerceIn(0.0, 1.0).toFloat()

private const val METER_FLOOR_DBFS = -60.0

/**
 * The mic. Press and hold to record, release to transcribe.
 *
 * Hold, not tap-to-toggle: a toggle that misses its second tap leaves a microphone open
 * on a worn device, which is precisely the failure the owner's no-auto-audio rule exists
 * to prevent. A held button cannot be left on by accident — let go and it stops.
 */
@Composable
fun PttButton(
    state: PttState,
    target: PttTarget,
    enabled: Boolean,
    onPress: (PttTarget) -> Unit,
    onRelease: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val haptics = LocalHapticFeedback.current
    val listening = state is PttState.Listening
    val connecting = state is PttState.Connecting
    val busy = state is PttState.Transcribing || state is PttState.Sending

    // ★★ The "go" buzz. The headset link costs ~600 ms, so the thumb goes down well
    // before capture starts; without this he has to watch the screen to know when to
    // start talking, on a device whose entire point is not having to look at it.
    // One pulse the instant LISTENING begins — press, feel it, talk.
    LaunchedEffect(listening) {
        if (listening) haptics.performHapticFeedback(HapticFeedbackType.LongPress)
    }

    // ⚠️⚠️ The gesture is keyed on Unit and reads its callbacks through
    // rememberUpdatedState, so no recomposition can ever restart it mid-hold. A press
    // that is torn down and rebuilt while the thumb is still down closes the
    // microphone and reopens it, which is how a five-second hold becomes 240 ms.
    // ⚠️ Do not put `state`, `target` or a fresh lambda into pointerInput's keys.
    val currentTarget by rememberUpdatedState(target)
    val currentPress by rememberUpdatedState(onPress)
    val currentRelease by rememberUpdatedState(onRelease)
    val currentEnabled by rememberUpdatedState(enabled)

    val tint = when {
        !enabled -> RoamColors.Dead
        listening -> RoamColors.Alarm
        // ⚠️ Connecting is deliberately NOT the listening colour. The one thing this
        // control must never do is look like it is recording when it is not.
        connecting -> RoamColors.Working
        busy -> RoamColors.Quiet
        state is PttState.Failed -> RoamColors.Alarm
        else -> RoamColors.Attention
    }

    // A ring that grows while the mic is open. The button is under a thumb, so the
    // signal has to be readable from the edge that is not covered.
    // ⚠️ Read inside graphicsLayer, never with `by` in the composable body: a 60 Hz
    // animation read at composition scope recomposes this button on every frame.
    val pulse = rememberInfiniteTransition(label = "ptt").animateFloat(
        initialValue = 1f,
        targetValue = 1.16f,
        animationSpec = infiniteRepeatable(tween(620), RepeatMode.Reverse),
        label = "pulse",
    )

    Box(
        modifier = modifier
            .size(52.dp)
            .graphicsLayer {
                val s = if (listening || connecting) pulse.value else 1f
                scaleX = s
                scaleY = s
            }
            .background(
                when {
                    listening -> RoamColors.Alarm.copy(alpha = 0.22f)
                    connecting -> RoamColors.Working.copy(alpha = 0.18f)
                    else -> RoamColors.SurfaceRaised
                },
                CircleShape,
            )
            .border(if (listening) 2.dp else 1.dp, tint.copy(alpha = 0.75f), CircleShape)
            .pointerInput(Unit) {
                detectTapGestures(onPress = {
                    if (!currentEnabled) return@detectTapGestures
                    haptics.performHapticFeedback(HapticFeedbackType.LongPress)
                    currentPress(currentTarget)
                    // Returns whether the pointer was lifted rather than cancelled; a
                    // cancel (a scroll stealing the gesture) still has to close the mic,
                    // so both outcomes release.
                    tryAwaitRelease()
                    currentRelease()
                })
            }
            .semantics {
                contentDescription = when {
                    !enabled -> "push to talk unavailable, the pane is dead"
                    listening -> "listening, release to send to transcription"
                    connecting -> "connecting to your headset, keep holding"
                    busy -> "transcribing"
                    else -> "push to talk, hold to record"
                }
            },
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            imageVector = if (enabled) Icons.Filled.Mic else Icons.Filled.MicOff,
            contentDescription = null,
            tint = tint,
            modifier = Modifier.size(25.dp),
        )
    }
}

/**
 * ★★ The confirm step, and every state that leads to it.
 *
 * The architecture is explicit that this is client-side and that **one confirmation
 * covers the words and the routing** — so the transcript and the destination channel are
 * on screen together, above one Send. The hub never sees an unconfirmed send.
 *
 * Returns nothing and renders nothing when there is nothing to say.
 */
@Composable
fun PttPanel(
    state: PttState,
    level: StateFlow<Double>,
    channelLabel: String,
    targetLive: Boolean,
    nowMs: Long,
    onPress: (PttTarget) -> Unit,
    onRelease: () -> Unit,
    onSend: () -> Unit,
    onCancel: () -> Unit,
    onDismiss: () -> Unit,
) {
    if (state is PttState.Idle) return

    val accent = when (state) {
        is PttState.Connecting -> RoamColors.Working
        is PttState.Listening -> RoamColors.Alarm
        is PttState.Transcribing, is PttState.Sending -> RoamColors.Quiet
        is PttState.Confirming -> if (state.error != null) RoamColors.Alarm else RoamColors.Attention
        is PttState.Failed -> RoamColors.Alarm
        is PttState.Idle -> RoamColors.Idle
    }

    Column(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 10.dp, vertical = 6.dp)
            .background(RoamColors.SurfaceRaised, RoundedCornerShape(12.dp))
            .border(1.dp, accent.copy(alpha = 0.55f), RoundedCornerShape(12.dp))
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(9.dp),
    ) {
        when (state) {
            // ★★ The half-second the headset link takes, made visible instead of eaten.
            //
            // ⚠️ It says KEEP HOLDING, not "connecting…", because the only thing he can
            // get wrong here is letting go — and letting go is exactly what a person
            // does when a button appears not to have worked. There is no level meter:
            // nothing is being captured yet, and a meter would say otherwise.
            is PttState.Connecting -> {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    TypingEllipsis(RoamColors.Working)
                    Spacer(Modifier.width(9.dp))
                    Text(
                        "KEEP HOLDING · headset",
                        style = MaterialTheme.typography.labelLarge,
                        color = RoamColors.Working,
                    )
                    Spacer(Modifier.weight(1f))
                    Text(
                        "wait for LISTENING",
                        style = MaterialTheme.typography.bodySmall,
                        color = RoamColors.TextSecondary,
                    )
                }
                Destination(channelLabel, targetLive)
            }

            is PttState.Listening -> {
                val seconds = ((nowMs - state.startedAtMs) / 1_000).coerceAtLeast(0)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    StatusDot(RoamColors.Alarm, 11.dp)
                    Spacer(Modifier.width(8.dp))
                    Text(
                        "LISTENING · ${seconds}s",
                        style = MaterialTheme.typography.labelLarge,
                        color = RoamColors.Alarm,
                    )
                    Spacer(Modifier.weight(1f))
                    Text(
                        "release to send",
                        style = MaterialTheme.typography.bodySmall,
                        color = RoamColors.TextSecondary,
                    )
                }
                LevelMeter(level)
                Destination(channelLabel, targetLive)
            }

            is PttState.Transcribing -> {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    TypingEllipsis(RoamColors.Quiet)
                    Spacer(Modifier.width(9.dp))
                    Text(
                        "TRANSCRIBING",
                        style = MaterialTheme.typography.labelLarge,
                        color = RoamColors.Quiet,
                    )
                    Spacer(Modifier.weight(1f))
                    ActionChip("CANCEL", RoamColors.TextSecondary, onCancel)
                }
            }

            is PttState.Confirming -> {
                // ★ The words, big, before anything else. This is the thing he is
                // actually checking, and he is checking it at arm's length.
                Text(
                    state.transcript,
                    style = MaterialTheme.typography.titleMedium,
                    color = RoamColors.TextPrimary,
                    maxLines = 6,
                    overflow = TextOverflow.Ellipsis,
                )
                Destination(channelLabel, targetLive)
                state.error?.let { error ->
                    Text(
                        error,
                        style = MaterialTheme.typography.bodyMedium,
                        color = RoamColors.Alarm,
                    )
                }
                if (!targetLive) {
                    Text(
                        "that pane is gone — nothing can be sent to it",
                        style = MaterialTheme.typography.bodyMedium,
                        color = RoamColors.Alarm,
                    )
                }
                // SEND gets a row to itself. It is the only filled control on the
                // panel and the only one that reaches the hub, so it is not sharing a
                // row with the two controls that undo it.
                Box(
                    Modifier
                        .fillMaxWidth()
                        .heightIn(min = 50.dp)
                        .clip(RoundedCornerShape(9.dp))
                        .background(
                            if (targetLive) RoamColors.Attention
                            else RoamColors.Attention.copy(alpha = 0.25f)
                        )
                        .clickable(enabled = targetLive, onClick = onSend),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        "SEND",
                        style = MaterialTheme.typography.labelLarge,
                        color = RoamColors.Background,
                    )
                }
                Row(horizontalArrangement = Arrangement.spacedBy(9.dp)) {
                    // ⚠️ Redo is a hold, like the mic — holding it records again
                    // without a trip back to the composer. A stray tap is safe: the
                    // controller hands the old transcript back with the complaint on
                    // it rather than deleting a sentence he already said.
                    PttHoldChip(
                        text = "HOLD TO REDO",
                        color = RoamColors.Quiet,
                        target = state.target,
                        onPress = onPress,
                        onRelease = onRelease,
                        modifier = Modifier.weight(1f),
                    )
                    ActionChip(
                        "CANCEL",
                        RoamColors.TextSecondary,
                        onCancel,
                        Modifier.heightIn(min = 46.dp),
                    )
                }
            }

            is PttState.Sending -> {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    TypingEllipsis(RoamColors.Quiet)
                    Spacer(Modifier.width(9.dp))
                    Text(
                        "SENDING",
                        style = MaterialTheme.typography.labelLarge,
                        color = RoamColors.Quiet,
                    )
                }
                Text(
                    state.transcript,
                    style = MaterialTheme.typography.bodyMedium,
                    color = RoamColors.TextSecondary,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }

            is PttState.Failed -> {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        Icons.Filled.MicOff,
                        contentDescription = null,
                        tint = RoamColors.Alarm,
                        modifier = Modifier.size(20.dp),
                    )
                    Spacer(Modifier.width(9.dp))
                    Text(
                        state.reason,
                        style = MaterialTheme.typography.bodyMedium,
                        color = RoamColors.Alarm,
                        modifier = Modifier.weight(1f),
                    )
                    Spacer(Modifier.width(8.dp))
                    ActionChip("OK", RoamColors.TextSecondary, onDismiss)
                }
            }

            // Unreachable — the whole panel returns early when idle. Kept explicit so
            // adding a state to PttState fails to compile here rather than silently
            // rendering nothing, which is how a state stops being visible.
            is PttState.Idle -> Unit
        }
    }
}

/**
 * ★ Where it is going, in the same place in every state.
 *
 * Not decoration: the confirmation is over the words *and* the routing, and a
 * destination that only appears on the final screen is a routing check he can skip.
 */
@Composable
private fun Destination(channelLabel: String, live: Boolean) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(
            "to",
            style = MaterialTheme.typography.bodySmall,
            color = RoamColors.TextSecondary,
        )
        Spacer(Modifier.width(7.dp))
        StateChip(
            text = channelLabel.ifBlank { "this channel" },
            color = if (live) RoamColors.Attention else RoamColors.Dead,
        )
    }
}

/**
 * A live input meter. Moving = the mic is genuinely open and hearing something.
 *
 * ★ It subscribes to the level itself rather than being handed a value from above, so
 * an 8 Hz signal invalidates one 8 dp bar instead of the whole thread screen.
 */
@Composable
private fun LevelMeter(levels: StateFlow<Double>) {
    val dbfs by levels.collectAsState()
    val fraction = levelFraction(dbfs)
    val quiet = dbfs < Ptt.MIN_RMS_DBFS
    Box(
        Modifier
            .fillMaxWidth()
            .height(8.dp)
            .background(RoamColors.Surface, RoundedCornerShape(4.dp))
    ) {
        Box(
            Modifier
                .fillMaxWidth(fraction)
                .height(8.dp)
                .background(
                    if (quiet) RoamColors.Dead else RoamColors.Working,
                    RoundedCornerShape(4.dp),
                )
        )
    }
}

/** A chip that records while it is held — same gesture as the mic, second location. */
@Composable
private fun PttHoldChip(
    text: String,
    color: Color,
    target: PttTarget,
    onPress: (PttTarget) -> Unit,
    onRelease: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val haptics = LocalHapticFeedback.current
    // Same rule as PttButton: keyed on Unit, callbacks read through updated state.
    val currentTarget by rememberUpdatedState(target)
    val currentPress by rememberUpdatedState(onPress)
    val currentRelease by rememberUpdatedState(onRelease)
    StateChip(
        text = text,
        color = color,
        modifier = modifier
            .heightIn(min = 46.dp)
            .clip(RoundedCornerShape(7.dp))
            .pointerInput(Unit) {
                detectTapGestures(onPress = {
                    haptics.performHapticFeedback(HapticFeedbackType.LongPress)
                    currentPress(currentTarget)
                    tryAwaitRelease()
                    currentRelease()
                })
            },
    )
}
