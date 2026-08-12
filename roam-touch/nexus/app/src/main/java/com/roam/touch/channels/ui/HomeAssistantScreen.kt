package com.roam.touch.channels.ui

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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.roam.touch.ha.HaEntities
import com.roam.touch.ha.HaHome
import com.roam.touch.ha.HaLink
import com.roam.touch.ha.HaState
import kotlinx.coroutines.delay

/**
 * ★★ Home Assistant without a browser.
 *
 * The companion app renders a blank white page on this phone and always will: WebView
 * and Chrome are frozen at 74.0.3729.186 (2019) because Play Store was removed, and the
 * HA frontend needs a far newer engine. That is a dead end, not a bug to fix.
 *
 * So the panel talks to HA's REST API and draws its own tiles. It suits the device
 * better anyway — this is a voice-first appliance on a forearm, and a responsive web
 * dashboard shrunk onto it was never the right answer. Entities in, tiles out; a tap is
 * one service call.
 *
 * ⚠️ **Untested against the real server.** Everything below was built and verified
 * against recorded HA payloads and a mock server, because creating a long-lived access
 * token requires his password and nobody else can do it. The wire shapes come from HA's
 * documented REST contract; the first real call happens when he pastes a token in.
 */
@Composable
fun HomeAssistantScreen(
    home: HaHome,
    onBack: () -> Unit,
    onRefresh: () -> Unit,
    onTap: (HaState) -> Unit,
) {
    // Poll while he is looking at it, and only while he is looking at it. HA has a
    // WebSocket for live updates; that is the right upgrade once this is proven, and
    // pointless before it — this screen is off far more than it is on.
    LaunchedEffect(home.link.isReady) {
        while (true) {
            delay(20_000)
            onRefresh()
        }
    }

    Column(
        Modifier
            .fillMaxSize()
            .background(RoamColors.Background)
    ) {
        BackToChannelsBar(
            title = "HOME ASSISTANT",
            onBack = onBack,
            trailing = {
                if (home.link !is HaLink.Unconfigured) {
                    ActionChip("REFRESH", RoamColors.Attention, onClick = onRefresh)
                }
            },
        )

        when (val link = home.link) {
            is HaLink.Unconfigured -> TokenSetup(reason = null)

            is HaLink.Failed ->
                if (link.unauthorised) TokenSetup(reason = link.reason)
                else {
                    HaFailureBanner(link.reason, onRefresh)
                    EntityGrid(home, onTap)
                }

            is HaLink.Loading -> if (home.tiles.isEmpty()) {
                Row(
                    Modifier.fillMaxWidth().padding(20.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    TypingEllipsis(color = RoamColors.Attention, dot = 6.dp)
                    Text(
                        "asking home assistant",
                        style = MaterialTheme.typography.bodyLarge,
                        color = RoamColors.TextSecondary,
                    )
                }
            } else EntityGrid(home, onTap)

            is HaLink.Ready -> if (home.tiles.isEmpty()) {
                Text(
                    "connected, but nothing to show — no lights, switches or locks came back",
                    style = MaterialTheme.typography.bodyLarge,
                    color = RoamColors.TextSecondary,
                    modifier = Modifier.padding(20.dp),
                )
            } else EntityGrid(home, onTap)
        }
    }
}

@Composable
private fun HaFailureBanner(reason: String, onRefresh: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .background(RoamColors.Alarm)
            .padding(horizontal = 14.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                "HOME ASSISTANT UNREACHABLE",
                style = MaterialTheme.typography.labelLarge,
                color = Color.White,
            )
            Text(
                reason,
                style = MaterialTheme.typography.bodySmall,
                color = Color.White.copy(alpha = 0.92f),
            )
        }
        ActionChip("RETRY", Color.White, onClick = onRefresh)
    }
}

/**
 * ★ The one thing only he can do, written where he will be standing when he needs it.
 *
 * HA long-lived tokens are minted from his profile page behind his password; there is no
 * API for it and no way for an agent to create one. So this screen is not an error — it
 * is the instruction, on the device, with the exact path and the exact file.
 */
@Composable
private fun TokenSetup(reason: String?) {
    val scroll = rememberScrollState()
    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(scroll)
            .padding(horizontal = 16.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        StateChip(
            text = if (reason == null) "NEEDS A TOKEN" else "TOKEN REJECTED",
            color = if (reason == null) RoamColors.Quiet else RoamColors.Alarm,
            filled = true,
        )
        Text(
            if (reason == null)
                "The native tiles are built and wired. They need one long-lived access token, and only you can make one."
            else
                "Home Assistant refused the token in this build ($reason). Same fix — make a new one and rebuild.",
            style = MaterialTheme.typography.bodyLarge,
            color = RoamColors.TextPrimary,
        )

        SetupStep(1, "In Home Assistant: your avatar → Security → Long-lived access tokens → Create token.")
        SetupStep(2, "On talos, add it to nexus/local.properties:\n\nroam.ha.token=<paste>")
        SetupStep(3, "Rebuild and install:\n\ncd ~/Projects/roam/roam-touch/nexus\n./gradlew installDebug")

        Text(
            "Optional — pin exactly which entities become tiles, in order:\n" +
                "roam.ha.entities=light.kitchen,lock.front_door,switch.desk\n\n" +
                "Left empty, the panel picks the actionable ones automatically (lights, " +
                "switches, fans, covers, locks, scenes, scripts) and caps the grid at 12.",
            style = MaterialTheme.typography.bodySmall,
            color = RoamColors.TextSecondary,
        )
        Text(
            "Server: ${com.roam.touch.BuildConfig.HA_URL}",
            style = MaterialTheme.typography.bodySmall,
            color = RoamColors.TextSecondary.copy(alpha = 0.7f),
        )
        Spacer(Modifier.height(6.dp))
    }
}

@Composable
private fun SetupStep(n: Int, text: String) {
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(RoamColors.Surface)
            .padding(12.dp),
        horizontalArrangement = Arrangement.spacedBy(11.dp),
    ) {
        Box(
            Modifier
                .size(26.dp)
                .background(RoamColors.Attention, RoundedCornerShape(13.dp)),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                "$n",
                style = MaterialTheme.typography.labelLarge,
                color = RoamColors.Background,
            )
        }
        Text(
            text,
            style = MaterialTheme.typography.bodyMedium,
            color = RoamColors.TextPrimary,
        )
    }
}

@Composable
private fun EntityGrid(home: HaHome, onTap: (HaState) -> Unit) {
    LazyVerticalGrid(
        columns = GridCells.Fixed(2),
        contentPadding = PaddingValues(12.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        modifier = Modifier.fillMaxSize(),
    ) {
        items(home.tiles, key = { it.entityId }) { entity ->
            EntityTile(
                entity = entity,
                busy = entity.entityId in home.busy,
                onTap = { onTap(entity) },
            )
        }
    }
}

/**
 * One entity.
 *
 * ★ On/off is carried by the whole tile, not by a small indicator: an "on" tile is
 * filled and bright, an "off" tile is flat. That is the read-at-arm's-length rule the
 * channel rows follow, applied here — you should be able to see that a light is on from
 * across the room without focusing on the panel.
 */
@Composable
private fun EntityTile(entity: HaState, busy: Boolean, onTap: () -> Unit) {
    val on = HaEntities.isOn(entity.state)
    val unavailable = HaEntities.isUnavailable(entity.state)
    val actionable = HaEntities.isActionable(entity)

    val accent = when {
        unavailable -> RoamColors.Dead
        on -> RoamColors.Working
        actionable -> RoamColors.TextSecondary
        else -> RoamColors.Attention
    }

    Column(
        Modifier
            .fillMaxWidth()
            .heightIn(min = 108.dp)
            .clip(RoundedCornerShape(12.dp))
            .background(if (on) accent.copy(alpha = 0.16f) else RoamColors.Surface)
            .border(
                width = if (on) 1.dp else 0.dp,
                color = if (on) accent.copy(alpha = 0.5f) else Color.Transparent,
                shape = RoundedCornerShape(12.dp),
            )
            // ⚠️ Taps are swallowed while a service call is in flight. Double-tapping a
            // light because the first tap looked like nothing happened is how you end up
            // with it back off, and the round trip over the tailnet is not instant.
            .clickable(enabled = actionable && !busy, onClick = onTap)
            .padding(12.dp),
    ) {
        Dimmed(unavailable) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (busy) TypingEllipsis(color = accent, dot = 6.dp)
                else StatusDot(accent, if (on) 12.dp else 10.dp)
            }
        }
        Spacer(Modifier.height(9.dp))
        Text(
            entity.friendlyName,
            style = MaterialTheme.typography.titleMedium,
            color = if (unavailable) RoamColors.Dead else RoamColors.TextPrimary,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
        Spacer(Modifier.height(4.dp))
        Text(
            if (busy) "sending…" else HaEntities.stateText(entity),
            style = MaterialTheme.typography.bodyMedium,
            color = accent,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        Spacer(Modifier.height(3.dp))
        Text(
            entity.domain,
            style = MaterialTheme.typography.bodySmall,
            color = RoamColors.TextSecondary.copy(alpha = 0.55f),
            maxLines = 1,
        )
    }
}
