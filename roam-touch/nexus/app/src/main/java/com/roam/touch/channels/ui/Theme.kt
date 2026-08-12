package com.roam.touch.channels.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/**
 * A palette for a forearm in daylight, not a phone in a dim room.
 *
 * Every state colour has to survive being glanced at for under a second while walking,
 * so the set is small and the meanings do not overlap: green is producing output, amber
 * is *not* producing output, grey is gone, blue is news for you, red is broken.
 */
object RoamColors {
    val Background = Color(0xFF06070A)
    val Surface = Color(0xFF14171D)
    val SurfaceRaised = Color(0xFF1D222B)
    val Divider = Color(0xFF2A313D)

    val TextPrimary = Color(0xFFF2F5F9)
    val TextSecondary = Color(0xFFA9B4C4)

    /** Output is moving. */
    val Working = Color(0xFF4ADE80)

    /** Still "working", but nothing has come out. The kill-it-or-not colour. */
    val Quiet = Color(0xFFFBBF24)

    /** The pane is gone. History stays; the channel must look dead. */
    val Dead = Color(0xFF6B7280)

    /** Unread — something is waiting for him. */
    val Attention = Color(0xFF38BDF8)

    /** Broken: a failed send, a refused token, a hub that is not there. */
    val Alarm = Color(0xFFEF4444)

    val Idle = Color(0xFF64748B)
}

/**
 * ⚠️ Nothing below 14sp, ever. 14sp is the floor for timestamps and chip text only;
 * anything he actually reads is 16sp or larger.
 */
private val RoamTypography = Typography(
    titleLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 22.sp,
        lineHeight = 28.sp,
    ),
    titleMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 18.sp,
        lineHeight = 24.sp,
    ),
    bodyLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontSize = 17.sp,
        lineHeight = 24.sp,
    ),
    bodyMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontSize = 16.sp,
        lineHeight = 22.sp,
    ),
    labelLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Bold,
        fontSize = 15.sp,
        letterSpacing = 0.6.sp,
    ),
    labelMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Bold,
        fontSize = 14.sp,
        letterSpacing = 0.5.sp,
    ),
    bodySmall = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontSize = 14.sp,
        lineHeight = 19.sp,
    ),
)

private val RoamScheme = darkColorScheme(
    primary = RoamColors.Attention,
    onPrimary = Color(0xFF04202D),
    background = RoamColors.Background,
    onBackground = RoamColors.TextPrimary,
    surface = RoamColors.Surface,
    onSurface = RoamColors.TextPrimary,
    surfaceVariant = RoamColors.SurfaceRaised,
    onSurfaceVariant = RoamColors.TextSecondary,
    error = RoamColors.Alarm,
    outline = RoamColors.Divider,
)

@Composable
fun RoamTheme(content: @Composable () -> Unit) {
    // Always dark, regardless of the system setting. This is a worn device; a light
    // panel on a forearm at night is a torch pointed at your own face.
    MaterialTheme(
        colorScheme = RoamScheme,
        typography = RoamTypography,
        content = content,
    )
}
