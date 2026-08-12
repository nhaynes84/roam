package com.roam.touch.channels.ui

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.keyframes
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
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
