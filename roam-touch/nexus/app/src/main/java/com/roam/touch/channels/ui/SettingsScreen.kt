package com.roam.touch.channels.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.roam.touch.settings.SettingWidget
import com.roam.touch.settings.SettingsShelf

/**
 * ★★ The device's own settings, as widgets.
 *
 * Owner, 2026-08-15: *"honestly the headphones setup is a Setting, we'll need our own
 * settings so might as well just start making widgets there, of which headphones is one
 * setting."* Two things in that sentence, and this screen is both: a **place** for
 * settings, and the shape they take — **widgets**, not a preference list.
 *
 * ⚠️ It draws [SettingsShelf.WIDGETS] and nothing else. There is no layout here that knows
 * about the headset, so setting #2 is one declaration in that file — the same rule the app
 * shelf follows, and the reason both of them are lists rather than screens full of rows.
 *
 * ⚠️ Same grid as the app shelf, deliberately: [ShelfGrid]. Same device, same forearm, same
 * arm's length — a tile sized right for Termux is sized right for the headset, and one
 * grid means the two shelves cannot drift into different column counts. What is *not*
 * shared is the tile itself: an [com.roam.touch.apps.AppTile] carries a package icon,
 * a broken flag and a lit state, none of which a setting has, so forcing one composable to
 * serve both would be a parameter list with half of it always null.
 */
@Composable
fun SettingsScreen(
    onBack: () -> Unit,
    onOpen: (id: String) -> Unit,
) {
    Column(
        Modifier
            .fillMaxSize()
            .background(RoamColors.Background)
    ) {
        BackToChannelsBar(title = "SETTINGS", onBack = onBack)

        ShelfGrid(Modifier.weight(1f)) {
            items(SettingsShelf.WIDGETS, key = { it.id }) { widget ->
                SettingTile(widget = widget, onClick = { onOpen(widget.id) })
            }
        }

        Text(
            "the panel's own settings — the phone's live in Settings on the app shelf",
            style = MaterialTheme.typography.bodySmall,
            color = RoamColors.TextSecondary.copy(alpha = 0.6f),
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
        )
    }
}

/**
 * One setting, tile-shaped.
 *
 * ⚠️ Built to the shelf's dimensions ([SHELF_TILE_HEIGHT_DP], 12 dp radius, 40 dp glyph
 * box) so the two shelves read as one system. The outline is the app shelf's *internal*
 * tile treatment — these are all screens this app draws, never other people's apps.
 *
 * ⚠️ No note, no chip, no explanation. The app shelf's tiles carried prose until he said
 * *"i don't need debug notes on the widget, lol"*; a settings shelf built the day after
 * that must not reintroduce it. Icon, label, and two or three words of subtitle.
 */
@Composable
private fun SettingTile(widget: SettingWidget, onClick: () -> Unit) {
    Column(
        Modifier
            .testTag(SETTING_TILE)
            .fillMaxWidth()
            .heightIn(min = SHELF_TILE_HEIGHT_DP)
            .clip(RoundedCornerShape(12.dp))
            .background(RoamColors.Surface)
            .border(1.dp, RoamColors.Attention.copy(alpha = 0.55f), RoundedCornerShape(12.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 12.dp),
    ) {
        Box(Modifier.size(40.dp), contentAlignment = Alignment.Center) {
            Icon(
                widget.icon,
                contentDescription = null,
                tint = RoamColors.Attention,
                modifier = Modifier.size(30.dp),
            )
        }
        Spacer(Modifier.height(9.dp))
        Text(
            widget.label,
            style = MaterialTheme.typography.titleMedium,
            color = RoamColors.TextPrimary,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
        Spacer(Modifier.height(2.dp))
        Text(
            widget.subtitle,
            style = MaterialTheme.typography.bodySmall,
            color = RoamColors.TextPrimary.copy(alpha = 0.6f),
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

/** Every widget on the settings shelf, for the tests that count and measure them. */
const val SETTING_TILE = "setting-tile"
