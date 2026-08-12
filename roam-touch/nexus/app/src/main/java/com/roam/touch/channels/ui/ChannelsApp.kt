package com.roam.touch.channels.ui

import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.roam.touch.channels.Roam
import kotlinx.coroutines.delay

/**
 * Attach the Channels UI to the host Activity.
 *
 * Called from `MainActivity`, which stays Java and stays in charge of device-owner
 * policy. Keeping this a one-line seam means the launcher/device-owner behaviour and
 * the app's behaviour never get tangled up in one file.
 */
fun installChannelsUi(activity: ComponentActivity) {
    activity.setContent {
        RoamTheme {
            Box(Modifier.fillMaxSize().background(RoamColors.Background)) {
                ChannelsApp()
            }
        }
    }
}

/**
 * Where the panel is.
 *
 * ★ [Channels] is home and everything else is a detour with one obvious way back — see
 * [BackToChannelsBar]. There is no nav stack and no navigation library, because there
 * are three destinations and a wearer who must never be lost in one of them.
 */
enum class Screen { Channels, Apps, HomeAssistant }

@Composable
fun ChannelsApp(vm: ChannelsViewModel = viewModel()) {
    val state by vm.state.collectAsStateWithLifecycle()
    val link by vm.link.collectAsStateWithLifecycle()
    val battery by Roam.device.battery.collectAsStateWithLifecycle()
    val speakingEventId by vm.speakingEventId.collectAsStateWithLifecycle()
    val haHome by vm.haHome.collectAsStateWithLifecycle()
    val nowMs = rememberTicker()

    var screen by remember { mutableStateOf(Screen.Channels) }
    var openPane by remember { mutableStateOf<String?>(null) }
    var toast by remember { mutableStateOf<Toast?>(null) }

    LaunchedEffect(Unit) {
        vm.messages.collect { toast = it }
    }
    LaunchedEffect(toast) {
        if (toast != null) {
            delay(3_500)
            toast = null
        }
    }

    val channel = openPane?.let { state.channel(it) }

    // While a thread is open, keep marking it read: outcomes land while he is looking
    // at them, and a badge that appears on a screen he is already reading is a lie.
    LaunchedEffect(openPane, state.thread(openPane.orEmpty()).lastOrNull()?.id) {
        openPane?.let { vm.markRead(it) }
    }

    // A reconnect fills gaps via the socket backlog, but a thread opened before the
    // drop can still have holes if it was never hydrated. Re-pull on reconnect.
    LaunchedEffect(link.isOnline, openPane) {
        if (link.isOnline) openPane?.let { vm.refreshThread(it) }
    }

    // Ask HA the moment that screen is opened, not at process start: a token-less or
    // unreachable server must not cost anything on a device whose main job is Channels.
    LaunchedEffect(screen) {
        if (screen == Screen.HomeAssistant) vm.refreshHa()
    }

    // Back always unwinds toward Channels, in one step, from anywhere.
    BackHandler(enabled = openPane != null || screen != Screen.Channels) {
        when {
            openPane != null -> { openPane = null; vm.stopSpeaking() }
            else -> screen = Screen.Channels
        }
    }

    Box(Modifier.fillMaxSize()) {
        if (channel != null) {
            ThreadScreen(
                state = state,
                channel = channel,
                nowMs = nowMs,
                speakingEventId = speakingEventId,
                onBack = { openPane = null; vm.stopSpeaking() },
                onExpand = vm::expand,
                onPlay = vm::play,
                onStopPlaying = vm::stopSpeaking,
                onSend = { vm.send(channel.paneId, it) },
                onInterrupt = { vm.interrupt(channel.paneId) },
                onKill = { vm.kill(channel.paneId) },
            )
            // The link banner follows him into the thread. Nowhere in this app is a
            // dead hub invisible.
            Box(Modifier.fillMaxWidth().align(Alignment.TopCenter)) {
                if (!link.isOnline) LinkBanner(link, nowMs)
            }
        } else when (screen) {
            Screen.Channels -> ChannelListScreen(
                state = state,
                link = link,
                battery = battery,
                nowMs = nowMs,
                onOpen = { openPane = it.paneId; vm.openThread(it.paneId) },
                onOpenApps = { screen = Screen.Apps },
                onOpenHomeAssistant = { screen = Screen.HomeAssistant },
            )

            Screen.Apps -> AppsScreen(
                onBack = { screen = Screen.Channels },
                onOpenHomeAssistant = { screen = Screen.HomeAssistant },
                onMessage = { vm.notify(it) },
            )

            Screen.HomeAssistant -> HomeAssistantScreen(
                home = haHome,
                onBack = { screen = Screen.Channels },
                onRefresh = vm::refreshHa,
                onTap = vm::tapHa,
            )
        }

        toast?.let { t ->
            Box(
                Modifier
                    .align(Alignment.BottomCenter)
                    .padding(bottom = 86.dp, start = 16.dp, end = 16.dp)
                    .background(
                        if (t.bad) RoamColors.Alarm else RoamColors.SurfaceRaised,
                        androidx.compose.foundation.shape.RoundedCornerShape(9.dp),
                    )
                    .padding(horizontal = 14.dp, vertical = 10.dp)
            ) {
                Text(
                    t.text,
                    style = MaterialTheme.typography.bodyMedium,
                    color = if (t.bad) Color.White else RoamColors.TextPrimary,
                )
            }
        }
    }
}

/**
 * A 1 Hz clock, so `idle_s` ages between hub frames.
 *
 * `API.md` asks for exactly this: age locally using `server_time`, and let the
 * `activity` frame reset it. Without it a working pane freezes at "2s ago" and the
 * kill decision loses its only input.
 */
@Composable
fun rememberTicker(periodMs: Long = 1_000): Long {
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    DisposableEffect(Unit) { onDispose { } }
    LaunchedEffect(periodMs) {
        while (true) {
            now = System.currentTimeMillis()
            delay(periodMs)
        }
    }
    return now
}
