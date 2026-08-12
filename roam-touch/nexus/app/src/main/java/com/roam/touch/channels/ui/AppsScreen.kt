package com.roam.touch.channels.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Home
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.graphics.drawable.toBitmap
import com.roam.touch.apps.AppCatalog
import com.roam.touch.apps.AppShelf
import com.roam.touch.apps.AppTile

/**
 * ★ The only route off the home screen.
 *
 * Nexus is the pinned home activity, so before this screen existed there was no way to
 * reach anything else on the phone: press Home, get Channels, forever. Four tiles fix
 * that. It is not an app drawer and must not become one — see [AppShelf].
 */
@Composable
fun AppsScreen(
    onBack: () -> Unit,
    onOpenHomeAssistant: () -> Unit,
    onMessage: (String) -> Unit,
) {
    val context = LocalContext.current
    // Resolved once per entry to the screen. Installing something is rare and always
    // involves adb, which restarts nothing here — a stale shelf costs one Back press.
    val tiles = remember { AppCatalog.shelf(context) }

    Column(
        Modifier
            .fillMaxSize()
            .background(RoamColors.Background)
    ) {
        BackToChannelsBar(title = "APPS", onBack = onBack)

        LazyVerticalGrid(
            columns = GridCells.Fixed(2),
            contentPadding = PaddingValues(12.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
            modifier = Modifier.weight(1f),
        ) {
            items(tiles, key = { it.id }) { tile ->
                LauncherTile(
                    tile = tile,
                    onClick = {
                        if (tile.id == AppShelf.HOME_ASSISTANT) {
                            onOpenHomeAssistant()
                        } else if (!AppCatalog.launch(context, tile.id)) {
                            onMessage("could not start ${tile.label}")
                        }
                    },
                )
            }
        }

        Text(
            "installed apps only — this is an appliance, not a phone",
            style = MaterialTheme.typography.bodySmall,
            color = RoamColors.TextSecondary.copy(alpha = 0.6f),
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
        )
    }
}

/**
 * One tile.
 *
 * ⚠️ A known-broken tile is still tappable. It is dimmed and it carries a red chip and
 * the reason, but it is not disabled: the failure is environmental and he may well want
 * to see it with his own eyes, or to try it again after changing something. Blocking the
 * tap would just mean he goes looking for the app another way and hits the same wall
 * with none of the explanation.
 */
@Composable
private fun LauncherTile(tile: AppTile, onClick: () -> Unit) {
    val context = LocalContext.current
    val icon = remember(tile.id) {
        if (tile.internal) null
        else runCatching {
            AppCatalog.icon(context, tile.id)?.toBitmap(96, 96)?.asImageBitmap()
        }.getOrNull()
    }
    val accent = if (tile.broken) RoamColors.Alarm else RoamColors.TextPrimary

    Column(
        Modifier
            .fillMaxWidth()
            .heightIn(min = 132.dp)
            .clip(RoundedCornerShape(12.dp))
            .background(RoamColors.Surface)
            .then(
                if (tile.internal)
                    Modifier.border(1.dp, RoamColors.Attention.copy(alpha = 0.55f), RoundedCornerShape(12.dp))
                else Modifier
            )
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 12.dp),
    ) {
        Dimmed(tile.broken) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(40.dp), contentAlignment = Alignment.Center) {
                    if (icon != null) {
                        Image(icon, contentDescription = null, modifier = Modifier.size(38.dp))
                    } else {
                        Icon(
                            Icons.Filled.Home,
                            contentDescription = null,
                            tint = RoamColors.Attention,
                            modifier = Modifier.size(30.dp),
                        )
                    }
                }
            }
        }
        Spacer(Modifier.height(9.dp))
        Text(
            tile.label,
            style = MaterialTheme.typography.titleMedium,
            color = if (tile.broken) RoamColors.TextSecondary else RoamColors.TextPrimary,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
        tile.subtitle?.let {
            Spacer(Modifier.height(2.dp))
            Text(
                it,
                style = MaterialTheme.typography.bodySmall,
                color = accent.copy(alpha = 0.6f),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        tile.note?.let { note ->
            Spacer(Modifier.height(8.dp))
            StateChip(note.chip, RoamColors.Alarm, filled = true)
            Spacer(Modifier.height(5.dp))
            Text(
                note.detail,
                style = MaterialTheme.typography.bodySmall,
                color = RoamColors.TextSecondary,
            )
        }
    }
}
