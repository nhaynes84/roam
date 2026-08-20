package com.roam.touch.channels.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
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
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ChevronLeft
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.GridView
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.RecordVoiceOver
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.TextButton
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
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
    /**
     * ★★ Folded down to the icon column. Owner: *"make it collapsible into the left side
     * where it becomes some icons."*
     *
     * ⚠️ Hoisted, and persisted in [com.roam.touch.channels.Settings] rather than
     * remembered here — the fold is a preference, and this is a launcher whose process is
     * killed routinely. Wide only: [Shell.Narrow] is already an icon strip, and a fold
     * control there would be a button that changes nothing.
     */
    collapsed: Boolean,
    onToggleCollapse: () -> Unit,
    onOpenChannel: (Channel) -> Unit,
    onNewSession: () -> Unit,
    onHome: () -> Unit,
    onOpenApps: () -> Unit,
    onOpenSettings: () -> Unit,
    onVoice: () -> Unit,
    onQuickSend: (String) -> Unit,
) {
    val open = openPane?.let { state.channel(it) }
    val folded = shell == Shell.Wide && collapsed
    Column(
        Modifier
            .testTag(RAIL)
            .width(
                when {
                    folded -> COLLAPSED_DP
                    shell == Shell.Wide -> WIDE_DP
                    else -> NARROW_DP
                }
            )
            .fillMaxHeight()
            .background(RoamColors.Surface)
            .padding(vertical = 4.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        // ⚠️ 5, not 6. Seven children means six gaps, so a dp of air here costs six dp of
        // channel list — and the list is the only thing in the rail he reads rather than
        // presses. `the rail spends width, never height` is the test that says so.
        verticalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        // ★ Declared once and used by both shapes of the rail. There is no second set of
        // nav targets and there must never be one: a control that exists in only one fold
        // state is a control he cannot find in the other.
        //
        // ⚠️⚠️ **Home Assistant is not here any more, and the house glyph is now Home.**
        // Owner, 2026-08-15: *"no the main feature is channels, Home is channels, HA is an
        // app, has no business being a main tab."* The old first destination was a house
        // that opened [Screen.HomeAssistant] — and with `roam.ha.token` unset that screen
        // is the token-setup wizard, which is the *literal* screen behind *"home … telling
        // me i need a token."* Pressing the house was pressing Home Assistant. HA keeps its
        // screen and its tile on the shelf ([AppShelf] NATIVE_HA, always first); what it
        // loses is a seat in the navigation.
        //
        // ⚠️ [withHome] is not a fourth destination — it is *where* the one Home control is
        // drawn. Expanded, home is the CHANNELS header above the queue, which is bigger and
        // carries the unread count; folded, there is no header, so it is this glyph. Same
        // target, one affordance per shape, never two at once.
        val destinations = @Composable { m: Modifier, withHome: Boolean ->
            if (withHome) {
                RailDestination(m, Icons.Filled.Home, "channels", RoamColors.Attention,
                    selected = screen == Screen.Channels && openPane == null, onClick = onHome)
            }
            RailDestination(m, Icons.Filled.GridView, "apps", RoamColors.TextPrimary,
                selected = screen == Screen.Apps, onClick = onOpenApps)
            // ⚠️⚠️ **Settings, not headphones.** Owner, 2026-08-15: *"honestly the
            // headphones setup is a Setting, we'll need our own settings so might as well
            // just start making widgets there, of which headphones is one setting."* The
            // headset screen is unchanged and one tap further in — [SettingsShelf] —
            // which matters, because with the handset mic dead it is how PTT is bound.
            //
            // ⚠️ Selected for [Screen.Controls] too: he is *inside* settings when he is
            // binding a button, and a rail that unlights while he is two taps deep says he
            // left something he did not leave.
            RailDestination(m, Icons.Filled.Settings, "settings", RoamColors.TextPrimary,
                selected = screen == Screen.Settings || screen == Screen.Controls,
                onClick = onOpenSettings)
        }

        if (folded) {
            FoldedRail(
                unread = state.totalUnread(),
                battery = battery,
                nowMs = nowMs,
                onExpand = onToggleCollapse,
                destinations = destinations,
            )
            return@Column
        }

        RailHome(
            shell = shell,
            unread = state.totalUnread(),
            atHome = screen == Screen.Channels,
            onHome = onHome,
            onCollapse = onToggleCollapse,
        )

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
        if (open == null) {
            RailTalk(shell, VoiceEntry.target(state.channels), onVoice)
            // ★ The door to a NEW session — one tap, one label, and the command is
            // always `claude`. Under TALK's rule and for a harder reason: the rail has
            // a height budget (`the rail spends width, never height`), and with a
            // thread open these 46 dp would come out of the queue, which is the one
            // thing in the rail he reads. At list level the height is there to spend.
            RailNewSession(shell, onNewSession)
        }

        if (shell == Shell.Wide) {
            // One row, three doors: 46 dp instead of 138. In a 411 dp window those 92 dp
            // are two more channels in the list.
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(3.dp),
            ) { destinations(Modifier.weight(1f), false) }
        } else {
            // ⚠️ Narrow has a "CH" header, so home lives there too — see [RailHome].
            destinations(Modifier.fillMaxWidth().padding(horizontal = 6.dp), false)
        }

        RailStatus(shell, battery, nowMs)
    }
}

/**
 * ★★ The rail, folded: a column of icons and nothing that needs reading.
 *
 * The owner's spec, verbatim and in his order: *"show me the home / apps / headphones
 * stacked, with the expand icon at the top of the column, and just unread notification
 * count bubble under that."* So the order below **is** the requirement — expand, count,
 * then the three destinations — and `the folded rail is his column, in his order` is the
 * test that keeps it that way.
 *
 * ⚠️ **No channel list, and no [RailTalk].** Folding is not a narrower list, it is the
 * absence of one: the queue is not clipped or scrolled away here, it is simply not
 * composed, and [ChannelsApp] hands the freed width to the content pane — which draws the
 * full list instead, exactly as it does in portrait. That is what keeps the fold from
 * being a dead end with no way to pick a channel.
 *
 * ⚠️ The clock and the battery stay, at the foot, below the fold he asked for. He did not
 * ask for them and they are not navigation, but the system status bar is hidden app-wide
 * (see `SystemBars`) — this rail is the only clock the device has, and a worn screen that
 * cannot tell the time is a regression whichever shape it is in. Everything above them is
 * his column, untouched.
 */
@Composable
private fun ColumnScope.FoldedRail(
    unread: Int,
    battery: BatteryState,
    nowMs: Long,
    onExpand: () -> Unit,
    destinations: @Composable (Modifier, Boolean) -> Unit,
) {
    RailFold(collapsed = true, onToggle = onExpand)

    // ★ Just the count, as he asked — not a home button wearing a badge. It is the one
    // thing in the folded column that is read rather than pressed, and [UnreadBadge]
    // draws nothing at zero, so a quiet rail stays quiet.
    if (unread > 0) {
        Box(Modifier.testTag(RAIL_COUNT), contentAlignment = Alignment.Center) {
            UnreadBadge(unread)
        }
    }

    // ★ HOME first of the three, and it is the channel list — his order, and now his
    // meaning too. See the note on `destinations`.
    destinations(Modifier.fillMaxWidth().padding(horizontal = 4.dp), true)

    Spacer(Modifier.weight(1f))
    RailStatus(Shell.Narrow, battery, nowMs)
}

/**
 * The fold control, in both directions.
 *
 * ⚠️ It sits at the top of the column in both states — the expand icon at the top of the
 * folded rail is where he asked for it, and putting collapse in the same place means the
 * control does not move when it is used. A toggle that jumps under the finger that pressed
 * it is the one thing a worn device cannot afford.
 *
 * The chevron points where the rail is going, not at what it is: right to open it out,
 * left to put it away.
 */
@Composable
private fun RailFold(collapsed: Boolean, onToggle: () -> Unit) {
    Box(
        Modifier
            .testTag(RAIL_FOLD)
            .then(if (collapsed) Modifier.fillMaxWidth() else Modifier.width(46.dp))
            .clip(RoundedCornerShape(8.dp))
            .clickable(onClick = onToggle)
            // The same 46 dp every pressable row in this rail uses. He does this walking.
            .heightIn(min = 46.dp)
            .padding(horizontal = 4.dp, vertical = 4.dp),
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            imageVector = if (collapsed) Icons.Filled.ChevronRight else Icons.Filled.ChevronLeft,
            contentDescription = if (collapsed) "expand the channel rail" else "collapse the channel rail",
            tint = RoamColors.TextPrimary,
            modifier = Modifier.size(26.dp),
        )
    }
}

/**
 * Home, and the unread count, in the same place in both shapes.
 *
 * The badge is on the rail rather than over the list because in Wide the list is *in* the
 * rail: one glance at the left edge answers "is anything waiting for me" whatever screen
 * he is on, including the ones that are not Channels at all.
 *
 * ⚠️ **There is exactly one unread badge, and this is it while the rail is open.** The
 * folded column's count bubble is the *same* badge in the shape that has no CHANNELS row
 * to hang it off — never a second copy. Two counts of the same number on one screen is how
 * a badge stops meaning anything, and `only one unread badge exists in either fold state`
 * is the test that says so.
 */
@Composable
private fun RailHome(
    shell: Shell,
    unread: Int,
    atHome: Boolean,
    onHome: () -> Unit,
    onCollapse: () -> Unit,
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

        // ★ Only where there is something to fold. Narrow is already the icon column, so
        // it gets no control — see the note on [NavRail]'s `collapsed`.
        if (shell == Shell.Wide) RailFold(collapsed = false, onToggle = onCollapse)
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
 * Rail widths. Wide holds a channel name; Narrow holds a word and a thumb.
 *
 * ⚠️ **This number is the whole of the "channels pane" width.** In Wide the list lives in
 * the rail, so what he sees as the channels pane *is* the rail — there is no second weight
 * splitting the window. [ChannelsApp]'s two `weight(1f)` boxes are nested, one horizontal
 * and one vertical, and neither divides the screen in two.
 *
 * ⚠️⚠️ **224 is deliberate, and narrowing it is the answer that was tried and rejected.**
 * sailfish's landscape window is 731 dp, so 224 dp is 31 % of it — owner: *"the channels
 * takes up like a third of the screen."* It was cut to 184, a true quarter, and he chose
 * differently: *"instead of 1/4 on the channels, let's keep the proportions, but make it
 * collapsible into the left side where it becomes some icons."* So the expanded rail is
 * back to the width that fits a channel name, and the third of the screen is now something
 * he can **put away** rather than something he has to live with. Do not re-narrow this to
 * buy width — [COLLAPSED_DP] is where that width comes from now.
 *
 * ⚠️ 224, not 196: at 196 the header rendered as "CHANNE… (3) 100%" on the device. The
 * title is the one word in the rail that must never be abbreviated — it is the way home.
 *
 * ⚠️ [COLLAPSED_DP] is measured off its contents rather than picked. The widest thing in
 * the icon column is [UnreadBadge] — 30 dp of minimum width plus 9 dp of padding either
 * side, so 48 — and 4 dp of air each side makes 56. That leaves every destination a
 * 48 × 46 dp target, the same 46 dp row the expanded rail uses throughout. **Do not tune
 * this down**: below 56 it is the badge that breaks first, not the layout, and the badge is
 * the only unread signal the collapsed rail has.
 */
private val WIDE_DP = 224.dp
private val COLLAPSED_DP = 56.dp
private val NARROW_DP = 62.dp

/**
 * ★ The one write the rail can start: a new session on talos. A door in the same shape
 * as [RailTalk] — icon plus a word in Wide, the icon alone in Narrow — because it opens
 * a dialog rather than acting on its own; the dialog is where the label is typed.
 */
@Composable
private fun RailNewSession(shell: Shell, onClick: () -> Unit) {
    Row(
        Modifier
            .testTag(RAIL_NEW)
            .fillMaxWidth()
            .padding(horizontal = 6.dp)
            .clip(RoundedCornerShape(8.dp))
            .clickable(onClick = onClick)
            .heightIn(min = 46.dp)
            .padding(horizontal = 7.dp, vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = if (shell == Shell.Wide) Arrangement.spacedBy(7.dp)
        else Arrangement.Center,
    ) {
        Icon(
            imageVector = Icons.Filled.Add,
            contentDescription = "new session",
            tint = RoamColors.Attention,
            modifier = Modifier.size(24.dp),
        )
        if (shell == Shell.Wide) {
            Text(
                "NEW SESSION",
                style = MaterialTheme.typography.labelMedium,
                color = RoamColors.Attention,
                maxLines = 1,
            )
        }
    }
}

/**
 * The agents that exist on this box. The chip row is the whole surface — the shell
 * command is an implementation detail nobody types.
 */
enum class SessionAgent(val label: String, val command: String) {
    CLAUDE("CLAUDE", "claude"),
    CODEX("CODEX", "codex"),
}

/**
 * ★ One label field, an agent chip, one button. The label becomes the pane title —
 * the thing that stops every new pane reading as the hostname — and the agent picks
 * the command under the hood: the dialog offers what he actually spawns, not a
 * terminal.
 *
 * ⚠️ It stays open until the hub answers. START goes dead while the create is in
 * flight ([creating]) and the caller closes the dialog on success — so a refused spawn
 * never silently eats the label he typed.
 */
@Composable
fun NewSessionDialog(
    creating: Boolean,
    onDismiss: () -> Unit,
    onStart: (String, SessionAgent) -> Unit,
) {
    var label by rememberSaveable { mutableStateOf("") }
    var agent by rememberSaveable { mutableStateOf(SessionAgent.CLAUDE) }
    val canStart = !creating && label.isNotBlank()
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = RoamColors.SurfaceRaised,
        title = {
            Text(
                "New session",
                style = MaterialTheme.typography.titleMedium,
                color = RoamColors.TextPrimary,
            )
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                SessionAgent.entries.forEach { a ->
                    val on = agent == a
                    Text(
                        a.label,
                        style = MaterialTheme.typography.labelLarge,
                        color = if (on) RoamColors.Attention else RoamColors.TextSecondary,
                        modifier = Modifier
                            .clip(RoundedCornerShape(11.dp))
                            .background(if (on) RoamColors.Surface else Color.Transparent)
                            .clickable(enabled = !creating) { agent = a }
                            .padding(horizontal = 14.dp, vertical = 8.dp)
                            .testTag("$NEW_SESSION_AGENT-${a.command}"),
                    )
                }
            }
            OutlinedTextField(
                value = label,
                onValueChange = { label = it },
                enabled = !creating,
                placeholder = {
                    Text(
                        "what it is for",
                        style = MaterialTheme.typography.bodyMedium,
                        color = RoamColors.TextSecondary.copy(alpha = 0.6f),
                    )
                },
                textStyle = MaterialTheme.typography.bodyMedium,
                singleLine = true,
                shape = RoundedCornerShape(11.dp),
                colors = TextFieldDefaults.colors(
                    focusedContainerColor = RoamColors.Surface,
                    unfocusedContainerColor = RoamColors.Surface,
                    disabledContainerColor = RoamColors.Surface,
                    focusedTextColor = RoamColors.TextPrimary,
                    unfocusedTextColor = RoamColors.TextPrimary,
                    focusedIndicatorColor = RoamColors.Attention.copy(alpha = 0.6f),
                    unfocusedIndicatorColor = dividerColor(),
                ),
                modifier = Modifier.fillMaxWidth().testTag(NEW_SESSION_LABEL),
            )
            }
        },
        confirmButton = {
            TextButton(onClick = { onStart(label, agent) }, enabled = canStart) {
                Text(
                    if (creating) "STARTING…" else "START",
                    style = MaterialTheme.typography.labelLarge,
                    color = if (canStart) RoamColors.Attention else RoamColors.Dead,
                )
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text(
                    "CANCEL",
                    style = MaterialTheme.typography.labelLarge,
                    color = RoamColors.TextSecondary,
                )
            }
        },
    )
}

const val RAIL = "nav-rail"
const val RAIL_QUEUE = "rail-queue"
const val RAIL_FOLD = "rail-fold"
const val RAIL_COUNT = "rail-count"
const val RAIL_TALK = "rail-talk"
const val RAIL_NEW = "rail-new-session"
const val NEW_SESSION_LABEL = "new-session-label"
const val NEW_SESSION_AGENT = "new-session-agent"
const val RAIL_STATUS = "rail-status"
