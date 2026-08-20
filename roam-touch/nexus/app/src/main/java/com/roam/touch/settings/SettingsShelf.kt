package com.roam.touch.settings

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Headphones
import androidx.compose.ui.graphics.vector.ImageVector

/**
 * ★★ One setting, as a widget on a shelf.
 *
 * Owner, 2026-08-15: *"honestly the headphones setup is a Setting, we'll need our own
 * settings so might as well just start making widgets there, of which headphones is one
 * setting."* So this is deliberately shaped like [com.roam.touch.apps.AppTile] and not
 * like a preference row: the device is read at arm's length on a forearm, and a wall of
 * 14 sp labels with switches on the right is a phone-in-the-hand pattern.
 *
 * ⚠️ The icon is part of the declaration on purpose. Adding setting #2 must be **one line
 * here** — if the glyph lived in a `when` inside the screen, every new setting would be
 * two edits in two files, and the second one is the one that gets forgotten.
 */
data class SettingWidget(
    val id: String,
    val label: String,
    /** Two or three words. It says what the setting is *for*, never what it currently is. */
    val subtitle: String,
    val icon: ImageVector,
)

/**
 * ★ The settings shelf: what this device lets him change, in the order he sees it.
 *
 * ⚠️ **It is a list, not a layout.** The screen loops over it and knows nothing else, so
 * growth is a declaration rather than a rearrangement — the same rule
 * [com.roam.touch.apps.AppShelf] follows for the app tiles, and for the same reason: the
 * only screen he can reach from Home must never change shape by accident.
 *
 * ★ **Obvious candidates for later, deliberately NOT built yet** — he asked for a place to
 * put settings and one setting in it, and a settings screen full of things nobody asked
 * for is how an appliance turns into a phone:
 *
 *  - **the rail's fold**, already persisted in `Settings.railCollapsed` — but it has a
 *    control on the rail itself, so a second one here would be a duplicate.
 *  - **the hub address and token**, currently `build.gradle` → `BuildConfig`. Making them
 *    editable means a keyboard on a wrist and a token in DataStore rather than in the APK;
 *    that is a real design job, not a widget.
 *  - **the Home Assistant token**, same again — and today its setup screen is reached from
 *    the shelf tile, which is where it belongs while it is a rebuild-to-change value.
 *  - **speech**: voice, rate, whether arrivals ever speak. There is a policy test saying
 *    nothing speaks unprompted; a switch here must not quietly become a way around it.
 *
 * ⚠️ Every widget here opens a screen. An *inline* widget — a switch that acts on the tile
 * itself, like the torch on the app shelf — is the obvious second shape and is not built:
 * it needs a `kind` on [SettingWidget] and a branch in the tile, which is exactly the kind
 * of thing to add when there is a real setting that wants it, not before.
 */
object SettingsShelf {

    /**
     * ⚠️⚠️ **Load-bearing.** This handset's microphone is dead at the HAL, so push-to-talk
     * records through a Bluetooth headset and this screen is how its buttons are bound.
     * It was a top-level rail destination until 2026-08-15; it moved here intact, and it
     * must stay reachable in every shape of the panel.
     */
    const val HEADSET = "roam:headset"

    val WIDGETS = listOf(
        SettingWidget(
            id = HEADSET,
            label = "Headset buttons",
            subtitle = "what each button does",
            icon = Icons.Filled.Headphones,
        ),
    )
}
