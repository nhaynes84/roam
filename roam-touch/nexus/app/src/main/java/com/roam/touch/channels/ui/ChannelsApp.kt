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
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
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
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.saveable.SaveableStateHolder
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.roam.touch.apps.AppShelf
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
 * [BackToChannelsBar] and [NavRail]. There is no nav stack and no navigation library,
 * because there are three destinations and a wearer who must never be lost in one of them.
 */
enum class Screen {
    Channels,
    Apps,
    HomeAssistant,
    Controls,

    /**
     * ★ The hub's own pages, drawn in-app — see [HubBrowserScreen].
     *
     * ⚠️ Not on the rail, and that is deliberate: it is not a destination, it is what a
     * shelf tile opens. It is reached from [Apps] and returns there, which is why it is the
     * one screen [Nav.back] treats separately.
     */
    HubBrowser,
}

/**
 * ★★ The panel: a nav rail, and beside it the thing he is reading.
 *
 * The layout law, from the owner: *"that stuff should be all left nav bar so height of
 * channels isn't being eaten by that stuff."* So this is a [Row] — [NavRail] first, then
 * everything else — and nothing but the hub-down banner is ever allowed to stack above
 * the content again.
 */
@Composable
fun ChannelsApp(vm: ChannelsViewModel = viewModel()) {
    val state by vm.state.collectAsStateWithLifecycle()
    val link by vm.link.collectAsStateWithLifecycle()
    val battery by Roam.device.battery.collectAsStateWithLifecycle()
    val speakingEventId by vm.speakingEventId.collectAsStateWithLifecycle()
    val haHome by vm.haHome.collectAsStateWithLifecycle()
    val pttState by vm.pttState.collectAsStateWithLifecycle()
    val draft by vm.draft.collectAsStateWithLifecycle()
    val outbox by vm.outbox.collectAsStateWithLifecycle()
    val nowMs = rememberTicker()
    val requestMic = rememberMicPermission(vm)
    val shell = rememberShell()

    // ★★ Saveable, not merely remembered — and that is a landscape requirement, not a
    // nicety. Rotating the device destroys and recreates the activity, so with plain
    // `remember` the wrist he just turned over threw away the thread he was reading and
    // dumped him back on the list. An orientation the app claims to support cannot cost
    // him his place in the conversation.
    var screen by rememberSaveable { mutableStateOf(Screen.Channels) }
    var openPane by rememberSaveable { mutableStateOf<String?>(null) }
    var toast by remember { mutableStateOf<Toast?>(null) }

    // ★ Which hub page the browser is showing, as a URL and a label.
    //
    // ⚠️ Saveable, for the same reason `screen` is: a configuration change must not drop
    // him out of a folder he is reading. Only the address is kept — the token is never
    // part of it, so nothing here can end up in a saved instance state bundle.
    var hubPage by rememberSaveable { mutableStateOf<Pair<String, String>?>(null) }

    // ★★ The message he is reading in full, by id.
    //
    // ⚠️ It lives **here**, above the thread list, and that placement is the fix rather
    // than an implementation detail: the old in-place expansion kept its state inside a
    // `LazyColumn` item, so scrolling the card off screen disposed it and silently
    // collapsed the answer. Nothing in the list can reach this.
    var readingEventId by rememberSaveable { mutableStateOf<Long?>(null) }

    // ★ Where he was in each open thread. See [rememberThreadPlaces].
    val threadPlaces = rememberThreadPlaces(openPane)

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
            learningFor?.let { action ->
                // ⚠️⚠️ **A gesture does one thing, so teaching it a new one ends the old
                // one — and that must be said, not discovered.** This is how his
                // push-to-talk disappeared: SEND landed on the tap that held it, and
                // nothing on screen or off it mentioned the swap. Owner: *"it unset my
                // push to talk, so the mappings are a little buggy."*
                controls.bind(gesture, action)?.let { lost ->
                    vm.notify("${gesture.label} was ${lost.label} — now ${action.label}")
                }
            }
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

    // ★★ **What the hub is told he can see — one line, derived, never set by hand.**
    //
    // ⚠️⚠️ This is the buzz. Presence is what stops a message he is already reading from
    // interrupting him, and claiming too much of it is what silenced his arm entirely.
    // Every place below that moves `openPane` or `screen` feeds this automatically, so a
    // new navigation path cannot forget to keep presence honest. See [Nav.covered].
    val covered = Nav.covered(readingEventId != null, screen, openPane, channel != null)
    LaunchedEffect(covered) { vm.covering(covered) }

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
        // ⚠️ The reader unwinds to the thread it came from, not to Channels: he opened it
        // from a conversation he is still in the middle of. Speech is deliberately left
        // running — walking away from the text while still listening to it is the point
        // of having both. The precedence itself lives in [Nav.back].
        when (Nav.back(readingEventId != null, screen, openPane != null)) {
            Back.CloseReader -> readingEventId = null
            // ⚠️ Back to the shelf he tapped the tile on, not to Channels. In practice
            // [HubBrowserScreen] installs its own handler and walks the page's history
            // first, so this fires only once there is nowhere left to go back to — or if
            // the WebView never came up at all, which is exactly when a way out matters.
            Back.CloseHubBrowser -> { hubPage = null; screen = Screen.Apps }
            Back.CloseDetour -> screen = Screen.Channels
            Back.CloseThread -> { openPane = null; vm.stopSpeaking(); vm.pttCancel() }
            null -> Unit
        }
    }

    // ⚠️⚠️ Installed once, keyed on Unit, and reads everything it needs through
    // rememberUpdatedState. Re-installing it on every state change would drop a gesture
    // that arrived mid-recomposition — the same class of bug as re-keying the PTT
    // gesture detector, which is how a five-second hold became 240 ms.
    val currentPane by rememberUpdatedState(openPane)
    val currentState by rememberUpdatedState(state)
    val currentPtt by rememberUpdatedState(pttState)

    // ★★ One rule, two triggers: a headset tap and the rail's TALK door both land here.
    //
    // The list reorders itself live, so "the top one" is not a destination — a voice press
    // with nowhere to send takes him to the top live channel and **says so** rather than
    // guessing. See [VoiceEntry]. ⚠️ It navigates only; the microphone stays in the
    // thread, where the recording has a channel to go to.
    //
    // Closes over remembered state objects, never over this frame's values, so the copy
    // captured by the DisposableEffect below is still correct on every later frame.
    val openForVoice: () -> Unit = {
        val top = VoiceEntry.target(currentState.channels)
        if (top == null) {
            vm.notify("no channels to talk to")
        } else {
            openPane = top.paneId
            vm.openThread(top.paneId)
            vm.notify("opened ${top.displayLabel} — press again to talk", bad = false)
        }
    }
    val currentVoice by rememberUpdatedState(openForVoice)

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
                    // ⚠️ Not a copy of the rule — *the* rule. When this branch and the
                    // rail's TALK were two pieces of code they were two chances to start
                    // guessing at a destination.
                    currentVoice()
                    return
                }
                // ⚠️ Do NOT branch on `currentPtt` here. That snapshot can be a
                // recomposition behind, and when it was wrong this called press() on an
                // open microphone — the mic stayed on and the tap that was meant to stop
                // it did nothing. Ptt decides, against the state it owns. See Ptt.toggle.
                val label = currentState.channel(pane)?.displayLabel.orEmpty()
                vm.pttToggle(PttTarget(pane, label))
            }

            /**
             * ★ Hold-to-talk from the volume rocker. Same destination rule as the tap —
             * see [VoiceEntry] — so the two controls can never disagree about where a
             * recording is going.
             */
            override fun pushToTalkStart() {
                val pane = currentPane
                if (pane == null) {
                    currentVoice()
                    return
                }
                val label = currentState.channel(pane)?.displayLabel.orEmpty()
                vm.pttPress(PttTarget(pane, label))
            }

            override fun pushToTalkStop() = vm.pttRelease()

            /**
             * ⚠️ The same confirm the SEND button performs — not a bypass of it. The
             * transcript and its destination are on screen either way; this only means he
             * does not have to reach the screen to agree.
             */
            override fun send() = vm.pttConfirm()

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

    Row(Modifier.fillMaxSize()) {
        // ★ The rail is on screen on every screen, in both shapes. It is how he gets
        // anywhere, so it is never the thing that scrolled away.
        NavRail(
            shell = shell,
            state = state,
            battery = battery,
            nowMs = nowMs,
            screen = screen,
            openPane = openPane,
            sending = outbox != null,
            onOpenChannel = {
                readingEventId = null
                openPane = it.paneId
                vm.openThread(it.paneId)
                screen = Screen.Channels
            },
            onHome = {
                readingEventId = null
                if (openPane != null) { openPane = null; vm.stopSpeaking(); vm.pttCancel() }
                screen = Screen.Channels
            },
            onOpenApps = { screen = Screen.Apps },
            onOpenHomeAssistant = { screen = Screen.HomeAssistant },
            onOpenControls = { screen = Screen.Controls },
            onVoice = openForVoice,
            onQuickSend = { reply -> openPane?.let { vm.send(it, reply) } },
        )

        Box(Modifier.weight(1f).fillMaxSize()) {
        Column(Modifier.fillMaxSize()) {
        // ★★ Hub-unreachable must be SEEN, and it is hoisted to exactly one place so it
        // follows him onto every screen — including the ones that are not Channels. It
        // displaces rather than overlays: a red bar that sits on top of the answer is a
        // bar he learns to look past.
        LinkBanner(link, nowMs)
        Box(Modifier.weight(1f).fillMaxSize()) {
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
            // ⚠️⚠️ A detour outranks an open thread, and this order is the whole of it.
            //
            // While the destinations lived on the channel *list*, they were unreachable
            // from inside a thread, so "thread wins" was never wrong. The rail put them on
            // screen everywhere — and then tapping one highlighted it and changed nothing,
            // because `channel != null` was still answered first. Owner: *"the icons don't
            // seem to work."* They worked; the pane never moved.
            //
            // ★ `openPane` is deliberately left set. The detour is drawn *over* the thread,
            // not instead of it, so Back and CHANNELS both land him back in the
            // conversation he left rather than at the list.
        } else if (screen != Screen.Channels) {
            when (screen) {
                Screen.Apps -> AppsScreen(
                    onBack = { screen = Screen.Channels },
                    onOpenHomeAssistant = { screen = Screen.HomeAssistant },
                    onOpenHub = { url, label ->
                        hubPage = url to label
                        screen = Screen.HubBrowser
                    },
                    onMessage = { vm.notify(it) },
                )

                // ★ The hub's pages, in-app, with the token on the request rather than in
                // the URL. `base` and `token` both come from the one hub configuration
                // built in [Roam.init]; there is no second copy of either.
                Screen.HubBrowser -> {
                    val page = hubPage
                    if (page == null) {
                        // Nothing to show means nothing was opened — go back rather than
                        // draw an empty frame he has to work out how to leave.
                        LaunchedEffect(Unit) { screen = Screen.Apps }
                    } else {
                        HubBrowserScreen(
                            url = page.first,
                            title = page.second,
                            token = Roam.hub.token,
                            base = AppShelf.HUB_BASE,
                            onBack = { hubPage = null; screen = Screen.Apps },
                        )
                    }
                }

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
                    shell = shell,
                )

                Screen.Channels -> Unit // unreachable: guarded by the branch condition
            }
        } else if (channel != null) {
            // ★★ **Coming back from the reader must land him where he left, not at the
            // newest message.** The reader is drawn *instead of* the thread, so the
            // thread is disposed and everything it remembered — scroll position, whether
            // it had settled — went with it; on the way back it called itself freshly
            // opened and jumped to the bottom. He walked into the reader from somewhere
            // and got returned somewhere else.
            //
            // ⚠️ Keyed on the pane, and dropped when he leaves it (below), so *opening* a
            // channel still lands on the newest message. That half is his too: *"when i
            // enter and receive messages, it doesn't autoscroll to the latest message,
            // bad experience."* Both halves are the same rule — put him where he was
            // going, and a channel he opens is a channel he opens at the end.
            threadPlaces.SaveableStateProvider(channel.paneId) {
            ThreadScreen(
                shell = shell,
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
                draft = draft,
                outbox = outbox,
                onDraft = vm::draft,
                onSend = { vm.send(channel.paneId, it) },
                onSendDraft = { vm.sendDraft(channel.paneId) },
                onInterrupt = { vm.interrupt(channel.paneId) },
                onKill = { vm.kill(channel.paneId) },
                // ★ The permission check is here, in front of the press, not inside
                // the recorder: a dialog that appears *after* he has already started
                // talking loses the sentence and teaches him the mic is unreliable.
                onPttPress = { target -> requestMic(target, false) },
                onPttRedo = { target -> requestMic(target, true) },
                onPttRelease = vm::pttRelease,
                onPttSend = vm::pttConfirm,
                onPttCancel = vm::pttCancel,
                onPttDismiss = vm::pttDismiss,
            )
            }
        } else {
            // Nothing open and no detour: the list itself, or the prompt to pick from it.
            // ⚠️ In Wide the queue is already in the rail, so re-drawing it here would be
            // the same list twice. The content pane says what to do instead of showing a
            // copy — see [NoChannelOpen].
            if (shell == Shell.Wide) {
                NoChannelOpen(hasChannels = state.channels.isNotEmpty())
            } else ChannelListScreen(
                state = state,
                link = link,
                nowMs = nowMs,
                onOpen = { openPane = it.paneId; vm.openThread(it.paneId) },
            )
        }
        } // end content pane
        } // end column under the link banner

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
                    // Clear of the composer when there is one, and no longer clearing the
                    // root PTT bar that no longer exists.
                    .padding(
                        bottom = if (channel != null) 82.dp else 18.dp,
                        start = 16.dp,
                        end = 16.dp,
                    )
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
        } // end content pane
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
private fun rememberMicPermission(vm: ChannelsViewModel): (PttTarget, Boolean) -> Unit {
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
        { target, redo ->
            val granted = ContextCompat.checkSelfPermission(
                context, Manifest.permission.RECORD_AUDIO
            ) == PackageManager.PERMISSION_GRANTED
            // ⚠️ `redo` is the only press that discards what he already said — see
            // [Ptt.press]. Everything else continues the transcript.
            if (granted) { if (redo) vm.pttRedo(target) else vm.pttPress(target) }
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

/**
 * ★★ **His place in a thread, kept while the thread is covered and released when he
 * leaves it.**
 *
 * Two halves of one rule, and they pull in opposite directions, which is why they live
 * together here rather than being maintained at the places navigation happens:
 *
 * - **Covered** — the reader, or a detour — is still being in the conversation. The
 *   reader is drawn *instead of* the thread, so the thread is disposed and everything it
 *   remembered goes with it; without this he walked into a message and got returned to
 *   the bottom of the thread. A [SaveableStateHolder] hands that state back on the way in.
 * - **Left** is not. Opening a channel lands on the newest message — his own complaint,
 *   from the other direction: *"when i enter and receive messages, it doesn't autoscroll
 *   to the latest message, bad experience."* So the place is dropped when the pane
 *   closes, and the next open is an open.
 *
 * ⚠️ The release runs from a [LaunchedEffect] rather than an `onDispose`, so it happens
 * after the thread has left the composition and written its state into the holder —
 * removing it first would remove nothing and then be overwritten.
 */
@Composable
fun rememberThreadPlaces(openPane: String?): SaveableStateHolder {
    val places = rememberSaveableStateHolder()
    var last by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(openPane) {
        last?.takeIf { it != openPane }?.let(places::removeState)
        last = openPane
    }
    return places
}
