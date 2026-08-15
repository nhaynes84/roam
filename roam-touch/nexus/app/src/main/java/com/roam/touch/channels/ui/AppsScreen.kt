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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.FlashOff
import androidx.compose.material.icons.filled.FlashOn
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Link
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.State
import androidx.compose.runtime.mutableStateOf
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
import com.roam.touch.apps.TileKind
import com.roam.touch.apps.Torch

/**
 * ★ The only route off the home screen.
 *
 * Nexus is the pinned home activity, so before this screen existed there was no way to
 * reach anything else on the phone: press Home, get Channels, forever. A handful of
 * tiles fix that. It is not an app drawer and must not become one — see [AppShelf].
 */
@Composable
fun AppsScreen(
    onBack: () -> Unit,
    onOpenHomeAssistant: () -> Unit,
    onOpenHub: (url: String, label: String) -> Unit,
    onMessage: (String) -> Unit,
) {
    val context = LocalContext.current
    // Resolved once per entry to the screen. Installing something is rare and always
    // involves adb, which restarts nothing here — a stale shelf costs one Back press.
    val tiles = remember { AppCatalog.shelf(context) }
    val torchOn = rememberTorchState()

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
                    // ⚠️ Runtime state, so it is a parameter rather than tile data: the
                    // shelf is resolved once on entry and the torch can change under it
                    // at any moment, including from outside this app.
                    lit = tile.id == AppShelf.TORCH && torchOn.value,
                    onClick = {
                        // ★ Dispatch on the *kind*, which is the whole reason the kind
                        // exists. An internal tile is an event inside this app, a hub tile
                        // is a page this app draws, and only a package tile is an intent —
                        // and that one goes through AppCatalog, which never throws back at
                        // the home screen.
                        when (tile.kind) {
                            TileKind.INTERNAL -> when (tile.id) {
                                AppShelf.HOME_ASSISTANT -> onOpenHomeAssistant()
                                AppShelf.TORCH ->
                                    // ⚠️ The switch is asked for, not asserted: the new
                                    // state comes back through the TorchCallback, so a
                                    // refusal leaves the tile showing the truth rather
                                    // than a state we merely requested.
                                    if (!Torch.set(context, !torchOn.value)) {
                                        onMessage("could not switch the torch")
                                    }
                                else -> onMessage("no screen for ${tile.label}")
                            }

                            TileKind.HUB -> onOpenHub(tile.id, tile.label)

                            TileKind.PACKAGE ->
                                if (!AppCatalog.open(context, tile)) {
                                    onMessage("could not start ${tile.label}")
                                }
                        }
                    },
                )
            }
        }

        Text(
            "a curated shelf, not an app drawer — this is an appliance, not a phone",
            style = MaterialTheme.typography.bodySmall,
            color = RoamColors.TextSecondary.copy(alpha = 0.6f),
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
        )
    }
}

/**
 * ★★ The torch, as the device currently reports it — never as we last asked for it.
 *
 * ⚠️ Registered against [Torch.watch] rather than tracked from our own writes, because
 * the quick-settings tile, the camera app and a `setTorchMode` that fails *after*
 * returning can all leave the two disagreeing. On a device worn on an arm the tile is the
 * only place he will notice the torch is still on, so it has to be true.
 */
@Composable
private fun rememberTorchState(): State<Boolean> {
    val context = LocalContext.current
    val on = remember { mutableStateOf(false) }
    DisposableEffect(context) {
        // ⚠️ Registering delivers the current state immediately, which is what seeds it —
        // there is no "read the torch" call to ask first.
        val handle = Torch.watch(context) { on.value = it }
        onDispose { handle?.close() }
    }
    return on
}

/**
 * One tile.
 *
 * ⚠️ A known-broken tile is still tappable. It is dimmed and it carries a red chip and
 * the reason, but it is not disabled: the failure is environmental and he may well want
 * to see it with his own eyes, or to try it again after changing something. Blocking the
 * tap would just mean he goes looking for the app another way and hits the same wall
 * with none of the explanation.
 *
 * [lit] is a tile that is *doing something right now* — the torch, and only the torch so
 * far. It gets the loudest treatment on the screen deliberately: this is the one state on
 * the shelf that costs battery while he is not looking at it.
 */
@Composable
private fun LauncherTile(tile: AppTile, lit: Boolean = false, onClick: () -> Unit) {
    val context = LocalContext.current
    // ⚠️ Only a package tile has a package icon. A hub tile's id is a URL, so asking
    // PackageManager for it would be a guaranteed miss on every recomposition.
    val icon = remember(tile.id) {
        if (tile.kind != TileKind.PACKAGE) null
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
            .background(if (lit) RoamColors.SurfaceRaised else RoamColors.Surface)
            .then(
                when {
                    // A lit torch is readable across a workshop at a glance: full-strength
                    // accent, two pixels of it, against a raised surface.
                    lit -> Modifier.border(2.dp, RoamColors.Attention, RoundedCornerShape(12.dp))
                    tile.internal ->
                        Modifier.border(1.dp, RoamColors.Attention.copy(alpha = 0.55f), RoundedCornerShape(12.dp))
                    else -> Modifier
                }
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
                            when {
                                tile.id == AppShelf.TORCH && lit -> Icons.Filled.FlashOn
                                tile.id == AppShelf.TORCH -> Icons.Filled.FlashOff
                                tile.kind == TileKind.HUB -> Icons.Filled.Link
                                else -> Icons.Filled.Home
                            },
                            contentDescription = null,
                            tint = RoamColors.Attention,
                            modifier = Modifier.size(30.dp),
                        )
                    }
                }
                if (lit) {
                    Spacer(Modifier.width(10.dp))
                    StateChip("ON", RoamColors.Attention, filled = true)
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
            // A caution (note without `broken`) must not wear the broken colour: red and
            // filled is "this will not work", and Chrome's 2019 engine is a warning, not
            // a failure. Amber and outlined reads as "know this first" instead.
            Spacer(Modifier.height(8.dp))
            StateChip(
                note.chip,
                if (note.broken) RoamColors.Alarm else RoamColors.Quiet,
                filled = note.broken,
            )
            Spacer(Modifier.height(5.dp))
            Text(
                note.detail,
                style = MaterialTheme.typography.bodySmall,
                color = RoamColors.TextSecondary,
            )
        }
    }
}
