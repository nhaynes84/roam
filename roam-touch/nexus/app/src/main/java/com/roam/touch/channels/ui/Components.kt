package com.roam.touch.channels.ui

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.keyframes
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.ui.draw.clip
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp

/**
 * ★ Actionable state is a chip with a count, never a sentence.
 *
 * The whole point of a chip here is that it is legible without being read: shape and
 * colour carry the meaning at arm's length, the two or three words inside confirm it if
 * he looks longer.
 */
@Composable
fun StateChip(
    text: String,
    color: Color,
    modifier: Modifier = Modifier,
    filled: Boolean = false,
    leading: @Composable (() -> Unit)? = null,
) {
    Row(
        modifier = modifier
            .background(
                color = if (filled) color else color.copy(alpha = 0.14f),
                shape = RoundedCornerShape(7.dp),
            )
            .then(
                if (filled) Modifier
                else Modifier.border(1.dp, color.copy(alpha = 0.45f), RoundedCornerShape(7.dp))
            )
            .padding(horizontal = 9.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        leading?.invoke()
        Text(
            text = text,
            color = if (filled) RoamColors.Background else color,
            style = androidx.compose.material3.MaterialTheme.typography.labelMedium,
        )
    }
}

/**
 * The unread count. A number, on the right, always in the same place — so the queue can
 * be read by counting badges rather than reading rows.
 */
@Composable
fun UnreadBadge(count: Int, modifier: Modifier = Modifier) {
    if (count <= 0) return
    Box(
        modifier = modifier
            .defaultMinSize(minWidth = 30.dp, minHeight = 26.dp)
            .background(RoamColors.Attention, RoundedCornerShape(13.dp))
            .padding(horizontal = 9.dp, vertical = 3.dp)
            .semantics { contentDescription = "$count unread" },
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = if (count > 99) "99+" else count.toString(),
            color = RoamColors.Background,
            style = androidx.compose.material3.MaterialTheme.typography.labelLarge,
            textAlign = TextAlign.Center,
        )
    }
}

/**
 * ★★ The typing ellipsis.
 *
 * Owner, verbatim: *"a typing ellipsis while you're in process, otherwise I wouldn't
 * know when to kill."* This animation is the single most load-bearing pixel in the app:
 * if it is moving, output is moving. When it stops moving the row switches to an amber
 * QUIET chip with a climbing number — because "nothing is coming out" is the actual
 * input to the decision, not a guess about whether the process is healthy.
 */
@Composable
fun TypingEllipsis(
    color: Color = RoamColors.Working,
    dot: androidx.compose.ui.unit.Dp = 6.dp,
    modifier: Modifier = Modifier,
) {
    val transition = rememberInfiniteTransition(label = "typing")
    Row(
        modifier = modifier.semantics { contentDescription = "working" },
        horizontalArrangement = Arrangement.spacedBy(3.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        repeat(3) { i ->
            val alpha by transition.animateFloat(
                initialValue = 0.25f,
                targetValue = 1f,
                animationSpec = infiniteRepeatable(
                    animation = keyframes {
                        durationMillis = 1_050
                        0.25f at 0
                        1f at 200
                        0.25f at 500
                        0.25f at 1_050
                    },
                    repeatMode = RepeatMode.Restart,
                    initialStartOffset =
                    androidx.compose.animation.core.StartOffset(i * 180),
                ),
                label = "dot$i",
            )
            Box(
                Modifier
                    .size(dot)
                    .alpha(alpha)
                    .background(color, CircleShape)
            )
        }
    }
}

/**
 * ★ The way back to Channels, in the same place on every secondary screen.
 *
 * Channels is the app; everything else is a detour. The rule from the product thesis is
 * that he must never be lost in a sub-screen on a device strapped to his arm, so the
 * return is a tile-sized target in the top-left with the destination *named* — not a
 * bare chevron he has to remember the meaning of, and not only the hardware Back key.
 */
@Composable
fun BackToChannelsBar(
    title: String,
    onBack: () -> Unit,
    trailing: @Composable (() -> Unit)? = null,
    /**
     * ⚠️ Where Back actually goes, and it must be the truth. Every screen but one returns
     * to Channels, so that is the default; the hub browser is opened from the shelf and
     * returns to the shelf, and a button that names a destination it does not go to is
     * worse than a bare chevron on a device strapped to an arm.
     */
    backLabel: String = "CHANNELS",
) {
    Row(
        Modifier
            .fillMaxWidth()
            .background(RoamColors.Surface)
            .padding(horizontal = 10.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
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
                imageVector = Icons.Filled.ArrowBack,
                contentDescription = "back to ${backLabel.lowercase()}",
                tint = RoamColors.Attention,
                modifier = Modifier.size(19.dp),
            )
            Text(
                backLabel,
                style = androidx.compose.material3.MaterialTheme.typography.labelMedium,
                color = RoamColors.Attention,
            )
        }
        Text(
            title,
            style = androidx.compose.material3.MaterialTheme.typography.labelLarge,
            color = RoamColors.TextSecondary,
            modifier = Modifier.weight(1f),
        )
        trailing?.invoke()
    }
}

/**
 * A chip that is a button. Same shape language as [StateChip] — which is the point: he
 * learns one visual rule, that a rounded outline with a word in it is a thing you press.
 */
@Composable
fun ActionChip(
    text: String,
    color: Color,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    StateChip(
        text = text,
        color = color,
        modifier = modifier
            .clip(RoundedCornerShape(7.dp))
            .clickable(onClick = onClick)
            .defaultMinSize(minHeight = 34.dp),
    )
}

/** A plain status dot for the states that are not animated. */
@Composable
fun StatusDot(color: Color, size: androidx.compose.ui.unit.Dp = 10.dp) {
    Box(Modifier.size(size).background(color, CircleShape))
}

/** Fade a whole row without restyling every child — used to make dead look dead. */
@Composable
fun Dimmed(dimmed: Boolean, content: @Composable () -> Unit) {
    Box(Modifier.alpha(if (dimmed) 0.55f else 1f)) { content() }
}

/** Small helper: alpha-composited divider colour that survives on true black. */
fun dividerColor(): Color = RoamColors.Divider
