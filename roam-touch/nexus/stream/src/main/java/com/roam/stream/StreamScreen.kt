package com.roam.stream

import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

private val Live = Color(0xFFE5484D)
private val Listening = Color(0xFF3E9B4F)
private val Idle = Color(0xFF6B7280)

/**
 * ★ OPT-IN, ALWAYS. Owner: *"opt in, I have to open it on any device."* The role
 * starts at OFF on every launch and nothing captures until he picks a role here.
 * A phone that reboots and comes back with a hot microphone is the outcome this
 * screen exists to make impossible.
 */
@Composable
fun StreamScreen(
    ui: StreamUi,
    onRole: (Role) -> Unit,
    onPress: () -> Unit,
    onRelease: () -> Unit,
) {
    Column(
        Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Stream", fontSize = 28.sp, fontWeight = FontWeight.Bold,
             color = MaterialTheme.colorScheme.onBackground)

        StatusCard(ui)

        Text("This device", fontSize = 14.sp, color = Idle)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            RoleChip("Off", ui.role == Role.OFF) { onRole(Role.OFF) }
            RoleChip("Open channel", ui.role == Role.SENDER) { onRole(Role.SENDER) }
            RoleChip("Receiver", ui.role == Role.RECEIVER) { onRole(Role.RECEIVER) }
        }

        ui.notice?.let {
            Text(it, fontSize = 14.sp, color = Live)
        }

        Spacer(Modifier.height(8.dp))

        if (ui.role == Role.RECEIVER) {
            TalkButton(ui, onPress, onRelease)
        }
    }
}

@Composable
private fun StatusCard(ui: StreamUi) {
    val (dot, line) = when {
        ui.role == Role.OFF -> Idle to "Off — nothing is being sent or received"
        !ui.connected -> Idle to "Connecting…"
        ui.role == Role.SENDER && ui.talkingNow != null ->
            Listening to "${ui.talkingNow} is talking — your mic is muted"
        ui.role == Role.SENDER -> Live to "Live — this device is the open mic"
        ui.talkingNow != null && ui.floor?.micLive("") == false && ui.talkingNow != null ->
            Listening to "${ui.talkingNow} is talking"
        ui.channelOpen -> Listening to "Listening to ${ui.floor?.sender}"
        else -> Idle to "No open channel yet"
    }
    Card(
        Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = dot.copy(alpha = 0.14f)),
    ) {
        Row(
            Modifier.padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Box(Modifier.size(12.dp).clip(CircleShape).background(dot))
            Text(line, fontSize = 16.sp, color = MaterialTheme.colorScheme.onBackground)
        }
    }
}

@Composable
private fun RoleChip(label: String, selected: Boolean, onClick: () -> Unit) {
    FilterChip(selected = selected, onClick = onClick, label = { Text(label) })
}

/**
 * Hold to talk. ⚠️ Release is wired to BOTH the natural finger-up and the gesture
 * being cancelled — a drag off the button, a notification shade pulled down mid-press,
 * a call arriving. Without the cancel path the floor stays seized until the hub's
 * 30 s timeout, and the monitor is silent for those 30 seconds with no explanation.
 */
@Composable
private fun TalkButton(ui: StreamUi, onPress: () -> Unit, onRelease: () -> Unit) {
    var down by remember { mutableStateOf(false) }
    val mine = ui.floor?.talker != null && ui.floor.talker == ui.floor.holder && down
    val enabled = ui.channelOpen

    Box(
        Modifier
            .fillMaxWidth()
            .height(180.dp)
            .clip(RoundedCornerShape(24.dp))
            .background(
                when {
                    !enabled -> Idle.copy(alpha = 0.18f)
                    mine -> Live
                    else -> MaterialTheme.colorScheme.primary.copy(alpha = 0.22f)
                }
            )
            .pointerInput(enabled) {
                if (!enabled) return@pointerInput
                detectTapGestures(
                    onPress = {
                        down = true
                        onPress()
                        // returns when the finger lifts OR the gesture is cancelled
                        tryAwaitRelease()
                        down = false
                        onRelease()
                    }
                )
            },
        contentAlignment = Alignment.Center,
    ) {
        Text(
            when {
                !enabled -> "No open channel"
                mine -> "TALKING — release to listen"
                else -> "HOLD TO TALK"
            },
            fontSize = 20.sp,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onBackground,
        )
    }
}
