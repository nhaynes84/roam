package com.roam.touch.channels.ui

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
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
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.roam.touch.channels.Roam
import com.roam.touch.channels.controls.ControlAction
import com.roam.touch.channels.controls.ControlSurface
import com.roam.touch.channels.stt.PttState
import com.roam.touch.channels.stt.PttTarget
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
enum class Screen { Channels, Apps, HomeAssistant, Controls }

@Composable
fun ChannelsApp(vm: ChannelsViewModel = viewModel()) {
    val state by vm.state.collectAsStateWithLifecycle()
    val link by vm.link.collectAsStateWithLifecycle()
    val battery by Roam.device.battery.collectAsStateWithLifecycle()
    val speakingEventId by vm.speakingEventId.collectAsStateWithLifecycle()
    val haHome by vm.haHome.collectAsStateWithLifecycle()
    val pttState by vm.pttState.collectAsStateWithLifecycle()
    val nowMs = rememberTicker()
    val requestMic = rememberMicPermission(vm)

    var screen by remember { mutableStateOf(Screen.Channels) }
    var openPane by remember { mutableStateOf<String?>(null) }
    var toast by remember { mutableStateOf<Toast?>(null) }

    // ★★ The message he is reading in full, by id.
    //
    // ⚠️ It lives **here**, above the thread list, and that placement is the fix rather
    // than an implementation detail: the old in-place expansion kept its state inside a
    // `LazyColumn` item, so scrolling the card off screen disposed it and silently
    // collapsed the answer. Nothing in the list can reach this.
    var readingEventId by remember { mutableStateOf<Long?>(null) }

    // --- the headset as a control surface ---------------------------------
    val controls = Roam.controls
    val headset by controls.active.collectAsStateWithLifecycle()
    val headsetIntro by controls.intro.collectAsStateWithLifecycle()
    val seenKeys by controls.seen.collectAsStateWithLifecycle()
    var learningFor by remember { mutableStateOf<ControlAction?>(null) }

    // ★ A captured gesture binds the action he asked for, and nothing else. The router
    // has already stopped learning by the time this lands.
    LaunchedEffect(Unit) {
        controls.learned.collect { gesture ->
            learningFor?.let { controls.bind(gesture, it) }
            learningFor = null
        }
    }

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
    // ⚠️ Leaving a thread cancels any recording or pending confirmation with it: an
    // open mic must not survive the screen that opened it, and a transcript confirmed
    // against a channel he has walked away from is exactly the mis-routing the confirm
    // step exists to prevent.
    BackHandler(enabled = readingEventId != null || openPane != null || screen != Screen.Channels) {
        when {
            // ⚠️ The reader unwinds to the thread it came from, not to Channels: he
            // opened it from a conversation he is still in the middle of. Speech is
            // deliberately left running — walking away from the text while still
            // listening to it is the point of having both.
            readingEventId != null -> readingEventId = null
            openPane != null -> { openPane = null; vm.stopSpeaking(); vm.pttCancel() }
            else -> screen = Screen.Channels
        }
    }

    // ⚠️⚠️ Installed once, keyed on Unit, and reads everything it needs through
    // rememberUpdatedState. Re-installing it on every state change would drop a gesture
    // that arrived mid-recomposition — the same class of bug as re-keying the PTT
    // gesture detector, which is how a five-second hold became 240 ms.
    val currentPane by rememberUpdatedState(openPane)
    val currentState by rememberUpdatedState(state)
    val currentPtt by rememberUpdatedState(pttState)
    DisposableEffect(Unit) {
        controls.surface = object : ControlSurface {

            /**
             * ⚠️⚠️ A toggle, because a headset tap has no hold — and it only ever records
             * into a channel he has actually opened. The list reorders itself live, so
             * "the top one" is not a destination; a gesture with nowhere to send takes
             * him to the top live channel and says so rather than guessing.
             */
            override fun pushToTalkToggle() {
                val pane = currentPane
                if (pane == null) {
                    val top = currentState.channels.firstOrNull { it.live }
                        ?: currentState.channels.firstOrNull()
                    if (top == null) {
                        vm.notify("no channels to talk to")
                        return
                    }
                    openPane = top.paneId
                    vm.openThread(top.paneId)
                    vm.notify("opened ${top.displayLabel} — press again to talk", bad = false)
                    return
                }
                when (currentPtt) {
                    is PttState.Connecting, is PttState.Listening -> vm.pttRelease()
                    else -> {
                        val label = currentState.channel(pane)?.displayLabel.orEmpty()
                        vm.pttPress(PttTarget(pane, label))
                    }
                }
            }

            override fun nextChannel() = step(+1)
            override fun previousChannel() = step(-1)

            override fun cancel() = vm.pttCancel()

            private fun step(by: Int) {
                val ordered = currentState.channels
                if (ordered.isEmpty()) return
                val at = ordered.indexOfFirst { it.paneId == currentPane }
                val next = ordered[((if (at < 0) 0 else at) + by).mod(ordered.size)]
                openPane = next.paneId
                vm.openThread(next.paneId)
            }
        }
        onDispose { controls.surface = null }
    }

    // The event being read, resolved fresh each frame so the expanded body landing from
    // `GET /events/{id}` reaches the open reader.
    val reading = readingEventId?.let { id ->
        state.thread(openPane.orEmpty()).firstOrNull { it.id == id }
    }

    Box(Modifier.fillMaxSize()) {
        if (channel != null && reading != null) {
            ReaderScreen(
                state = state,
                channel = channel,
                event = reading,
                speaking = speakingEventId == reading.id,
                onBack = { readingEventId = null },
                onPlay = { vm.play(reading) },
                onStopPlaying = vm::stopSpeaking,
            )
        } else if (channel != null) {
            ThreadScreen(
                state = state,
                channel = channel,
                nowMs = nowMs,
                speakingEventId = speakingEventId,
                pttState = pttState,
                pttLevel = vm.pttLevel,
                onBack = { openPane = null; vm.stopSpeaking(); vm.pttCancel() },
                // ⚠️ The fetch is kicked off with the navigation, not after it: a body
                // trimmed to 4 KiB in transit must be made whole before he can mistake
                // its tail for the end of the answer. `expand` is a no-op otherwise.
                onRead = { event -> vm.expand(event); readingEventId = event.id },
                onPlay = vm::play,
                onStopPlaying = vm::stopSpeaking,
                onSend = { vm.send(channel.paneId, it) },
                onInterrupt = { vm.interrupt(channel.paneId) },
                onKill = { vm.kill(channel.paneId) },
                // ★ The permission check is here, in front of the press, not inside
                // the recorder: a dialog that appears *after* he has already started
                // talking loses the sentence and teaches him the mic is unreliable.
                onPttPress = { target -> requestMic(target) },
                onPttRelease = vm::pttRelease,
                onPttSend = vm::pttConfirm,
                onPttCancel = vm::pttCancel,
                onPttDismiss = vm::pttDismiss,
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
                onOpenControls = { screen = Screen.Controls },
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

            Screen.Controls -> ControlsScreen(
                profile = headset,
                seen = seenKeys,
                learningFor = learningFor,
                onBack = { screen = Screen.Channels },
                onLearn = { action -> learningFor = action; controls.learnNext() },
                onCancelLearn = { learningFor = null; controls.cancelLearning() },
                onUnbind = controls::unbind,
            )
        }

        // ★ An unfamiliar headset, once. It sits over the panel rather than replacing
        // it, and NOT NOW leaves everything working — the mic button is still the mic
        // button. Nothing waits on this.
        headsetIntro?.let { profile ->
            Box(Modifier.align(Alignment.TopCenter)) {
                HeadsetIntroCard(
                    profile = profile,
                    onMap = { controls.dismissIntro(); screen = Screen.Controls; openPane = null },
                    onDismiss = controls::dismissIntro,
                )
            }
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
 * ★ The microphone gate: check the permission, then press — never the other way round.
 *
 * ⚠️ **The result of the dialog never starts a recording.** By the time he has answered
 * it his thumb is off the button, and a mic that opens on a dialog dismissal is a mic
 * that opened without anyone pressing anything. He is told to hold it again instead.
 * That is one wasted press the first time, and no hot mic ever — the same rule that got
 * automatic speech deleted, applied to the input side where it matters more.
 */
@Composable
private fun rememberMicPermission(vm: ChannelsViewModel): (PttTarget) -> Unit {
    val context = androidx.compose.ui.platform.LocalContext.current
    val launcher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        vm.notify(
            if (granted) "microphone granted — hold the mic and talk"
            else "microphone denied — voice input is off",
            bad = !granted,
        )
    }
    return remember(context, launcher) {
        { target ->
            val granted = ContextCompat.checkSelfPermission(
                context, Manifest.permission.RECORD_AUDIO
            ) == PackageManager.PERMISSION_GRANTED
            if (granted) vm.pttPress(target)
            else launcher.launch(Manifest.permission.RECORD_AUDIO)
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
