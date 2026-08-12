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
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import com.roam.touch.channels.controls.ControlAction
import com.roam.touch.channels.controls.HeadsetGesture
import com.roam.touch.channels.controls.HeadsetProfile

/**
 * ★★ What each gesture on the connected headset does, and how to change one.
 *
 * ⚠️ The owner's constraints, all of which shaped this screen:
 * - *"but make it 'editable'"* — one binding can be changed **in place**. Nothing here
 *   makes him walk a wizard to move a single gesture.
 * - Gestures are **releasable**: unbinding hands the key back to the headset and the
 *   system, so volume goes back to being volume.
 * - It is reachable from the app, not only when a headset connects — he will want to
 *   change this sitting down.
 * - The raw key log is on screen, because his two headsets disagree with each other and
 *   the only trustworthy mapping is the one captured from what actually arrived.
 */
@Composable
fun ControlsScreen(
    profile: HeadsetProfile?,
    seen: List<String>,
    learningFor: ControlAction?,
    onBack: () -> Unit,
    onLearn: (ControlAction) -> Unit,
    onCancelLearn: () -> Unit,
    onUnbind: (HeadsetGesture) -> Unit,
) {
    Column(
        Modifier
            .fillMaxSize()
            .background(RoamColors.Background)
    ) {
        BackToChannelsBar("HEADSET CONTROLS", onBack)

        if (profile == null) {
            // ⚠️ Honest and specific, like every other empty state in this app: there is
            // nothing to configure because there is nothing connected, and it says which.
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text(
                    "no headset connected — connect one and its buttons will show up here",
                    style = MaterialTheme.typography.bodyMedium,
                    color = RoamColors.TextSecondary,
                    modifier = Modifier.padding(28.dp),
                )
            }
            return@Column
        }

        Column(
            Modifier
                .weight(1f)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 12.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(9.dp),
        ) {
            Text(
                profile.name,
                style = MaterialTheme.typography.titleMedium,
                color = RoamColors.TextPrimary,
            )

            if (learningFor != null) {
                LearnCard(learningFor, onCancelLearn)
            }

            // ★ One row per action, always all of them, so an *unbound* action is as
            // visible as a bound one. A missing binding he cannot see is a control he
            // will think is broken.
            ControlAction.entries.forEach { action ->
                BindingRow(
                    action = action,
                    gesture = profile.boundTo(action),
                    learning = learningFor == action,
                    onLearn = { onLearn(action) },
                    onUnbind = onUnbind,
                )
            }

            if (profile.capturesVolume) {
                // ⚠️ Named where he can see it. Capturing volume takes the rocker away
                // from the system for as long as it is bound, and he should never have
                // to work out why volume stopped working.
                Note(
                    "a volume gesture is bound, so volume keys go to this app instead of " +
                            "changing the volume. Unbind it to give them back."
                )
            }

            Note(
                "a tap on the headset starts and stops recording — it is a toggle, not a " +
                        "hold. The panel says LISTENING and the phone buzzes when the mic " +
                        "actually opens."
            )

            if (seen.isNotEmpty()) {
                Text(
                    "WHAT THIS HEADSET SENDS",
                    style = MaterialTheme.typography.labelLarge,
                    color = RoamColors.TextSecondary,
                    modifier = Modifier.padding(top = 6.dp),
                )
                seen.forEach { line ->
                    Text(
                        line,
                        style = MaterialTheme.typography.bodySmall,
                        color = RoamColors.TextSecondary,
                    )
                }
            }
        }
    }
}

/**
 * ★★ The first-connect prompt. Short, because he is putting earbuds in, not sitting down.
 *
 * ⚠️ A prompt, never a gate — the owner was explicit. Dismissing it leaves the headset
 * working as a microphone with PTT on the on-screen button, and it is never asked again
 * for that headset.
 */
@Composable
fun HeadsetIntroCard(
    profile: HeadsetProfile,
    onMap: () -> Unit,
    onDismiss: () -> Unit,
) {
    Column(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 10.dp, vertical = 6.dp)
            .background(RoamColors.SurfaceRaised, RoundedCornerShape(12.dp))
            .border(1.dp, RoamColors.Attention.copy(alpha = 0.55f), RoundedCornerShape(12.dp))
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(
            "${profile.name} — new headset",
            style = MaterialTheme.typography.titleMedium,
            color = RoamColors.TextPrimary,
        )
        // ★ It says out loud that a tap will open a microphone. A default binding he was
        // not told about is the same surprise as a hot mic.
        Text(
            "a single tap is set to push-to-talk. Map its buttons, or leave it — " +
                    "the mic button on screen works either way.",
            style = MaterialTheme.typography.bodyMedium,
            color = RoamColors.TextSecondary,
        )
        Row(horizontalArrangement = Arrangement.spacedBy(9.dp)) {
            ActionChip("MAP BUTTONS", RoamColors.Attention, onMap, Modifier.heightIn(min = 44.dp))
            ActionChip("NOT NOW", RoamColors.TextSecondary, onDismiss, Modifier.heightIn(min = 44.dp))
        }
    }
}

@Composable
private fun BindingRow(
    action: ControlAction,
    gesture: HeadsetGesture?,
    learning: Boolean,
    onLearn: () -> Unit,
    onUnbind: (HeadsetGesture) -> Unit,
) {
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(9.dp))
            .background(RoamColors.SurfaceRaised)
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                action.label,
                style = MaterialTheme.typography.bodyMedium,
                color = RoamColors.TextPrimary,
            )
            Text(
                gesture?.label ?: "not bound",
                style = MaterialTheme.typography.bodySmall,
                color = if (gesture == null) RoamColors.Dead else RoamColors.Attention,
            )
        }
        Spacer(Modifier.width(8.dp))
        // ★ Change one binding in place — this is the whole of "make it editable".
        ActionChip(
            if (learning) "PRESS IT" else if (gesture == null) "SET" else "CHANGE",
            if (learning) RoamColors.Working else RoamColors.TextSecondary,
            onLearn,
            Modifier.heightIn(min = 42.dp),
        )
        if (gesture != null) {
            Spacer(Modifier.width(7.dp))
            // ⚠️ Releases the key back to the headset and the system.
            ActionChip("UNBIND", RoamColors.Dead, { onUnbind(gesture) }, Modifier.heightIn(min = 42.dp))
        }
    }
}

@Composable
private fun LearnCard(action: ControlAction, onCancel: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .background(RoamColors.Working.copy(alpha = 0.18f), RoundedCornerShape(9.dp))
            .border(1.dp, RoamColors.Working.copy(alpha = 0.6f), RoundedCornerShape(9.dp))
            .padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            "press the button you want for “${action.label}”",
            style = MaterialTheme.typography.bodyMedium,
            color = RoamColors.Working,
            modifier = Modifier.weight(1f),
        )
        ActionChip("CANCEL", RoamColors.TextSecondary, onCancel, Modifier.heightIn(min = 42.dp))
    }
}

@Composable
private fun Note(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.bodySmall,
        color = RoamColors.TextSecondary,
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(RoamColors.Surface)
            .padding(10.dp),
    )
}
