package com.roam.touch.channels.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.GridView
import androidx.compose.material.icons.filled.Headphones
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.RecordVoiceOver
import androidx.compose.material3.Icon
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.roam.touch.channels.BatteryState
import com.roam.touch.channels.ChannelsState
import com.roam.touch.channels.Liveliness
import com.roam.touch.channels.Liveness
import com.roam.touch.channels.Queue
import com.roam.touch.channels.model.Channel

/**
 * ★★ The nav rail — every piece of chrome that used to sit on top of the messages.
 *
 * The owner, on the portrait-native layout: *"we're eating vertical space with channels
 * and PTT... that stuff should be all left nav bar so height of channels isn't being
 * eaten by that stuff; gives us back like 30% of the vertical space."*
 *
 * So the title bar, the channel list, the destinations, the battery, the canned replies
 * and the door to voice all live here, on the axis there is spare of. What is left in the
 * content pane is the thing he is actually reading, top to bottom.
 *
 * ⚠️ **There is no microphone in this rail.** The root-level PTT bar this replaces could
 * not record — it only ever opened a channel — and a control that cannot act where it is
 * shown is a bug in either orientation. [RailTalk] is a door, labelled as one, and it
 * obeys [VoiceEntry]: no open channel means open the top *live* one and **say so**.
 */
@Composable
fun NavRail(
    shell: Shell,
    state: ChannelsState,
    battery: BatteryState,
    nowMs: Long,
    screen: Screen,
    openPane: String?,
    /**
     * ⚠️ True while a send is still outstanding. The rail's canned chips are a *second copy*
     * of the composer's, so they need the composer's rule too: a chip left live during a send
     * is a duplicate prompt one tap away. The Wide shell is the only place both exist, which
     * is exactly where the merge of the nav rail and the send deadlines could have lost it.
     */
    sending: Boolean,
    onOpenChannel: (Channel) -> Unit,
    onHome: () -> Unit,
    onOpenApps: () -> Unit,
    onOpenHomeAssistant: () -> Unit,
    onOpenControls: () -> Unit,
    onVoice: () -> Unit,
    onQuickSend: (String) -> Unit,
) {
    val open = openPane?.let { state.channel(it) }
    Column(
        Modifier
            .testTag(RAIL)
            .width(if (shell == Shell.Wide) WIDE_DP else NARROW_DP)
            .fillMaxHeight()
            .background(RoamColors.Surface)
            .padding(vertical = 4.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        // ⚠️ 5, not 6. Seven children means six gaps, so a dp of air here costs six dp of
        // channel list — and the list is the only thing in the rail he reads rather than
        // presses. `the rail spends width, never height` is the test that says so.
        verticalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        RailHome(shell, state.totalUnread(), atHome = screen == Screen.Channels, onHome)

        // ★ The list itself, in the rail, only where there is width for it. In Narrow it
        // stays in the content pane — collapsing the rail rather than forking the tree is
        // what keeps portrait working while landscape gets a layout of its own.
        if (shell == Shell.Wide) {
            // ⚠️ The tag is on the *pane*, not on the LazyColumn inside it. A LazyColumn
            // wraps its content, so measuring the list would have reported a healthy
            // height for a single channel while the pane holding it was 0 dp tall — which
            // is exactly the bug `the rail spends width, never height` exists to catch.
            Box(Modifier.testTag(RAIL_QUEUE).weight(1f).fillMaxWidth()) {
                val ordered = Queue.order(state, nowMs)
                if (ordered.isEmpty()) {
                    Text(
                        "no channels",
                        style = MaterialTheme.typography.bodySmall,
                        color = RoamColors.TextSecondary,
                        modifier = Modifier.align(Alignment.TopCenter).padding(top = 12.dp),
                    )
                } else {
                    LazyColumn(
                        Modifier.fillMaxWidth(),
                        verticalArrangement = Arrangement.spacedBy(3.dp),
                    ) {
                        items(ordered, key = { it.paneId }) { channel ->
                            RailChannelRow(
                                state = state,
                                channel = channel,
                                nowMs = nowMs,
                                selected = channel.paneId == openPane,
                                onClick = { onOpenChannel(channel) },
                            )
                        }
                    }
                }
            }
        } else {
            Spacer(Modifier.weight(1f))
        }

        // ★ The canned replies come left in Wide, off the composer row and out of the
        // messages' way. They act on the channel that is open, so they exist only while
        // one is — the same rule the mic is being held to one file over.
        if (shell == Shell.Wide && open != null) {
            RailDivider()
            // ⚠️ Capped and scrollable, not "as tall as five chips". Five stacked chips
            // are 170 dp — 41 % of a landscape window — and they would take it out of the
            // queue above, which is the one thing the rail exists to hold. It scrolls
            // either way, so the cap is purely how much of the list it is worth costing.
            Column(
                Modifier
                    .fillMaxWidth()
                    .heightIn(max = 76.dp)
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 8.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                val canSend = open.live && !sending
                CANNED.forEach { reply ->
                    StateChip(
                        text = reply.uppercase(),
                        color = if (canSend) RoamColors.Attention else RoamColors.Dead,
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(7.dp))
                            .clickable(enabled = canSend) { onQuickSend(reply) }
                            .heightIn(min = 34.dp),
                    )
                }
            }
        }

        RailDivider()

        // ⚠️ Only while there is no channel open. With one open the real microphone is on
        // screen already, in the composer, and a second voice control next to it is the
        // exact confusion the root PTT bar used to cause.
        if (open == null) RailTalk(shell, VoiceEntry.target(state.channels), onVoice)

        val destinations = @Composable { m: Modifier ->
            RailDestination(m, Icons.Filled.Home, "home assistant", RoamColors.Attention,
                selected = screen == Screen.HomeAssistant, onClick = onOpenHomeAssistant)
            RailDestination(m, Icons.Filled.GridView, "apps", RoamColors.TextPrimary,
                selected = screen == Screen.Apps, onClick = onOpenApps)
            // ⚠️ Reachable without a headset connected, on purpose: he will want to change
            // a binding sitting down, not while putting earbuds in.
            RailDestination(m, Icons.Filled.Headphones, "headset buttons", RoamColors.TextPrimary,
                selected = screen == Screen.Controls, onClick = onOpenControls)
        }
        if (shell == Shell.Wide) {
            // One row, three doors: 46 dp instead of 138. In a 411 dp window those 92 dp
            // are two more channels in the list.
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(3.dp),
            ) { destinations(Modifier.weight(1f)) }
        } else {
            destinations(Modifier.fillMaxWidth().padding(horizontal = 6.dp))
        }

        RailStatus(shell, battery, nowMs)
    }
}

/**
 * Home, and the unread count, in the same place in both shapes.
 *
 * The badge is on the rail rather than over the list because in Wide the list is *in* the
 * rail: one glance at the left edge answers "is anything waiting for me" whatever screen
 * he is on, including the ones that are not Channels at all.
 */
@Composable
private fun RailHome(
    shell: Shell,
    unread: Int,
    atHome: Boolean,
    onHome: () -> Unit,
) {
    val label = @Composable {
        Text(
            text = if (shell == Shell.Wide) "CHANNELS" else "CH",
            style = MaterialTheme.typography.labelLarge,
            color = if (atHome) RoamColors.TextPrimary else RoamColors.TextSecondary,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            textAlign = TextAlign.Center,
        )
    }
    Row(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        val home = Modifier
            .weight(1f)
            .clip(RoundedCornerShape(8.dp))
            .background(if (atHome) RoamColors.SurfaceRaised else Color.Transparent)
            .clickable(onClick = onHome)
            .defaultMinSize(minHeight = 38.dp)
            .padding(horizontal = 6.dp, vertical = 5.dp)

        if (shell == Shell.Wide) {
            Row(
                home,
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(5.dp),
            ) {
                label()
                UnreadBadge(unread)
            }
        } else {
            // ⚠️ Stacked, not side by side. A 62 dp rail cannot hold "CH" *and* a badge on
            // one line, and side by side it rendered as ". (3)" on the device — the word
            // ellipsised down to a full stop while the count kept its width.
            Column(
                home,
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(3.dp),
            ) {
                label()
                UnreadBadge(unread)
            }
        }
    }
}

/**
 * ★★ The two facts the system status bar used to carry, now carried by the app.
 *
 * The stock bar is gone — see `SystemBars`, and the owner: *"i don't need to see the
 * battery charge unless you're going to hide the notification bar that's always on,
 * which i'm not opposed to."* He is right that a chip beside a bar showing the same
 * number is amateur duplication. Hiding the bar makes the chip the only copy instead of
 * the second one, and it buys back 24 dp of a 411 dp window.
 *
 * ⚠️ **The clock came with it, and it is not optional on a worn device.** The bar was
 * where the time lived; a screen on a forearm that cannot tell you the time is worse than
 * the 24 dp it saved. So this row is time *and* charge, and it is the same row in both
 * shapes rather than two arrangements that can drift apart.
 *
 * It sits at the foot of the rail, below the doors: it is the thing you look at
 * deliberately, never the thing you navigate with.
 */
@Composable
private fun RailStatus(shell: Shell, battery: BatteryState, nowMs: Long) {
    val clock = @Composable {
        Text(
            text = Format.clock(nowMs),
            style = MaterialTheme.typography.labelMedium,
            color = RoamColors.TextSecondary,
            maxLines = 1,
        )
    }
    if (shell == Shell.Wide) {
        Row(
            Modifier
                .testTag(RAIL_STATUS)
                .fillMaxWidth()
                .padding(horizontal = 8.dp, vertical = 1.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            clock()
            BatteryChip(battery)
        }
    } else {
        // 62 dp cannot hold both on one line, and the rail has height to spare in
        // portrait — the same trade the header makes one composable up.
        Column(
            Modifier.testTag(RAIL_STATUS).fillMaxWidth().padding(top = 2.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(3.dp),
        ) {
            clock()
            BatteryChip(battery)
        }
    }
}

/**
 * One channel, rail-sized.
 *
 * ★ It keeps the two things the queue is sorted by — liveness and unread — and drops the
 * preview text. The preview belongs to a row he is deciding *from*; here the thread
 * itself is open beside it, so a second copy of the last line would cost height on the
 * only screen that has none to spare.
 */
@Composable
private fun RailChannelRow(
    state: ChannelsState,
    channel: Channel,
    nowMs: Long,
    selected: Boolean,
    onClick: () -> Unit,
) {
    val liveness = Liveliness.of(state, channel, nowMs)
    val unread = state.unreadCount(channel.paneId)
    val dead = liveness is Liveness.Dead

    Dimmed(dead) {
        Row(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 6.dp)
                .clip(RoundedCornerShape(8.dp))
                .background(
                    when {
                        selected -> RoamColors.SurfaceRaised
                        unread > 0 -> RoamColors.Attention.copy(alpha = 0.10f)
                        else -> Color.Transparent
                    }
                )
                .clickable(onClick = onClick)
                .heightIn(min = 46.dp)
                .padding(horizontal = 7.dp, vertical = 5.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // The animated part survives the move: if it is moving, output is moving.
            Box(Modifier.size(width = 20.dp, height = 12.dp), contentAlignment = Alignment.CenterStart) {
                when (liveness) {
                    is Liveness.Working -> TypingEllipsis(RoamColors.Working, dot = 5.dp)
                    is Liveness.Quiet -> StatusDot(RoamColors.Quiet, 8.dp)
                    is Liveness.Idle -> StatusDot(RoamColors.Idle, 8.dp)
                    Liveness.Dead -> StatusDot(RoamColors.Dead, 8.dp)
                    Liveness.Unknown -> StatusDot(RoamColors.Idle, 7.dp)
                }
            }
            Spacer(Modifier.width(7.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    text = channel.displayLabel,
                    style = MaterialTheme.typography.bodyMedium,
                    color = when {
                        dead -> RoamColors.Dead
                        selected -> RoamColors.TextPrimary
                        else -> RoamColors.TextPrimary
                    },
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                // ⚠️ QUIET keeps its number here too — "nothing has come out for 4m" is
                // the input to "should I kill it", and hiding it in the rail would take
                // that decision away from the only screen that is always on show.
                Text(
                    text = com.roam.touch.channels.LivenessLabel.text(liveness),
                    style = MaterialTheme.typography.bodySmall,
                    color = when (liveness) {
                        is Liveness.Working -> RoamColors.Working
                        is Liveness.Quiet -> RoamColors.Quiet
                        Liveness.Dead -> RoamColors.Dead
                        else -> RoamColors.TextSecondary.copy(alpha = 0.75f)
                    },
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            if (unread > 0) {
                Spacer(Modifier.width(5.dp))
                UnreadBadge(unread)
            }
        }
    }
}

/**
 * ★★ TALK — the device's voice front door, and the one control that says where it goes.
 *
 * The owner asked what it did, which was the finding: *"what does 'TALK' do in that side
 * nav, if nothing, it doesn't need to be there."* It did do something — it opened the top
 * live channel — but a button whose destination is invisible is a button you have to press
 * to learn. So the destination is printed on it. Nothing changed about what it does.
 *
 * ★ It stays because he then gave it a bigger job: *"i'm not opposed to the top level talk
 * doing 'other things', taking HA commands and piping them in, answering general questions
 * or other stuff, i dunno, a OS level talk feature."* That is not built and is not assumed
 * here — but it is why this is shaped as **the root voice control** rather than as a
 * shortcut into the list beside it. When the interpreter lands, the second line stops
 * saying which channel it will open and starts saying what it understood; the control
 * itself does not move.
 *
 * ⚠️ **It is not a microphone and must never become one.** The glyph is deliberately not
 * [Icons.Filled.Mic] — the mic capsule belongs to the in-thread PTT button, which is the
 * only control on this device that captures into a channel (`MicPolicyTest`). This one is
 * a head speaking: you address the device with it, you do not record through it.
 *
 * See [VoiceEntry] for the rule it carries out, and note what it is *not*: a hold. A hold
 * here would have to guess a destination, and the destination it would guess moves.
 */
@Composable
private fun RailTalk(shell: Shell, target: Channel?, onVoice: () -> Unit) {
    val enabled = target != null
    val color = if (enabled) RoamColors.Attention else RoamColors.Dead
    Row(
        Modifier
            .testTag(RAIL_TALK)
            .fillMaxWidth()
            .padding(horizontal = 6.dp)
            .clip(RoundedCornerShape(8.dp))
            .background(RoamColors.SurfaceRaised)
            .clickable(enabled = enabled, onClick = onVoice)
            .heightIn(min = 46.dp)
            .padding(horizontal = 7.dp, vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(7.dp),
    ) {
        Icon(
            imageVector = Icons.Filled.RecordVoiceOver,
            contentDescription = if (enabled) "talk, opens ${target?.displayLabel}"
            else "talk, no channels to talk to yet",
            tint = color,
            modifier = Modifier.size(24.dp),
        )
        if (shell == Shell.Wide) {
            Column(Modifier.weight(1f)) {
                Text(
                    "TALK",
                    style = MaterialTheme.typography.labelMedium,
                    color = color,
                    maxLines = 1,
                )
                // ★ The answer to "what does this do", in the place he was looking when
                // he asked. It is resolved through [VoiceEntry], not re-derived here, so
                // the label and the press can never name different channels.
                Text(
                    text = if (enabled) "→ ${target?.displayLabel}" else "no channels yet",
                    style = MaterialTheme.typography.bodySmall,
                    color = RoamColors.TextSecondary,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

/**
 * One destination, as a glyph.
 *
 * ⚠️ **This used to be the words HA / APPS / BUDS, and that was the wrong call.** Owner,
 * 2026-08-12: *"HA / BUDS / APPS, let's do icons instead, looks amateurish."* The comment
 * that was here argued a glyph is a puzzle he has to remember the meaning of; the reply is
 * that three shouted abbreviations are a puzzle too, and an uglier one. A house, a grid and
 * a pair of headphones are not conventions he has to learn.
 *
 * ⚠️ The target is read on a forearm, in motion, outdoors, so this is tuned for that and
 * not for a phone in the hand: 26 dp glyphs (Material's own default is 24), full-strength
 * [RoamColors.TextPrimary] rather than the secondary grey the words used, and a 46 dp row —
 * *taller* than the 40 dp the labels had, never smaller. The name survives as the
 * content description, which is what the tests assert against.
 */
@Composable
private fun RailDestination(
    modifier: Modifier,
    icon: ImageVector,
    name: String,
    color: Color,
    selected: Boolean,
    onClick: () -> Unit,
) {
    Box(
        modifier
            .clip(RoundedCornerShape(8.dp))
            .background(if (selected) color.copy(alpha = 0.22f) else Color.Transparent)
            .clickable(onClick = onClick)
            .heightIn(min = 46.dp)
            .padding(horizontal = 5.dp, vertical = 4.dp),
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            imageVector = icon,
            contentDescription = name,
            tint = if (selected) RoamColors.TextPrimary else color,
            modifier = Modifier.size(26.dp),
        )
    }
}

@Composable
private fun RailDivider() {
    Box(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 6.dp)
            .height(1.dp)
            .background(dividerColor())
    )
}

/**
 * ★ The empty half of the two-pane layout, and it is not blank.
 *
 * In Wide the rail holds the list, so the content pane has nothing to show until a
 * channel is picked. It says which of the two things to do rather than sitting empty —
 * and it names the same door the rail does, so there is one story about how voice starts.
 */
@Composable
fun NoChannelOpen(hasChannels: Boolean) {
    Box(
        Modifier
            .testTag(NO_CHANNEL_OPEN)
            .fillMaxWidth()
            .fillMaxHeight()
            .padding(24.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = if (hasChannels) "pick a channel — or press TALK for the top live one"
            else "no channels — open a pane on talos",
            style = MaterialTheme.typography.bodyLarge,
            color = RoamColors.TextSecondary,
            textAlign = TextAlign.Center,
        )
    }
}

/**
 * Rail widths. Wide holds a channel name; Narrow holds a word and a thumb.
 *
 * ⚠️ 224, not 196: at 196 the header rendered as "CHANNE… (3) 100%" on the device. The
 * title is the one word in the rail that must never be abbreviated — it is the way home.
 * The battery has since moved out of the header into [RailStatus], so the header has slack
 * again; the width stays because it is also what lets [RailTalk] print a channel name.
 */
private val WIDE_DP = 224.dp
private val NARROW_DP = 62.dp

const val RAIL = "nav-rail"
const val RAIL_QUEUE = "rail-queue"
const val RAIL_TALK = "rail-talk"
const val RAIL_STATUS = "rail-status"
const val NO_CHANNEL_OPEN = "no-channel-open"
