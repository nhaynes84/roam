package com.roam.nexus

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.roam.touch.stream.Role
import com.roam.touch.stream.StreamScreen
import com.roam.touch.stream.StreamUi
import com.roam.touch.channels.model.Channel
import com.roam.touch.channels.model.Event
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.contentOrNull
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.Image
import androidx.compose.foundation.lazy.rememberLazyListState

/**
 * The whole Nexus experience on a phone.
 *
 * ★ Owner: *"i want the whole nexus experience, not just stream on my pixel 11;
 * stream is a stand alone nexus app, nothing we install independently."* So Stream is
 * a TAB in here — one of Nexus's apps, exactly like Files on the Mac — and there is
 * no separate installable. The standalone com.roam.stream build was the wrong shape
 * and has been removed.
 *
 * ⚠️ This is NOT the wrist launcher. That is ../nexus, it claims the HOME category,
 * and it is pinned to targetSdk 29 for sailfish. Two products, two builds, on purpose.
 */
/**
 * ★ Two scopes everywhere, on every client: CHANNELS and APPS.
 *
 * Owner: *"everything should at least have 'Channels' and 'Apps', make 11
 * consistent."* Stream is an APP, not a peer of Channels — the Mac has always had
 * it that way (an APPS rail under the channel list) and the phone having a "Stream"
 * tab beside "Channels" quietly said they were the same kind of thing.
 */
enum class Tab(val label: String) {
    CHANNELS("Channels"),
    APPS("Apps"),
}

/** One app inside Nexus. Files joins this list when the phone gets a browser. */
enum class NexusAppId(val title: String, val subtitle: String) {
    STREAM("Stream", "Open channel, or hold to talk back"),
}

@Composable
fun NexusApp(
    channels: List<Channel>,
    thread: List<Event>,
    openPane: String?,
    connected: Boolean,
    streamUi: StreamUi,
    onOpen: (String?) -> Unit,
    onSend: (String) -> Unit,
    onRole: (Role) -> Unit,
    onPress: () -> Unit,
    onRelease: () -> Unit,
) {
    var tab by remember { mutableStateOf(Tab.CHANNELS) }
    var openApp by remember { mutableStateOf<NexusAppId?>(null) }

    Scaffold(
        bottomBar = {
            NavigationBar {
                Tab.entries.forEach { t ->
                    NavigationBarItem(
                        selected = tab == t,
                        onClick = { tab = t },
                        icon = {
                            // A dot that carries state: Apps turns red while this
                            // device is the live mic, so an open channel is visible
                            // from the tab bar without opening anything.
                            Box(
                                Modifier.size(10.dp).clip(CircleShape).background(
                                    when {
                                        t == Tab.APPS && streamUi.role == Role.SENDER -> Color(0xFFE5484D)
                                        t == Tab.APPS && streamUi.channelOpen -> Color(0xFF3E9B4F)
                                        tab == t -> MaterialTheme.colorScheme.primary
                                        else -> Color(0xFF6B7280)
                                    }
                                )
                            )
                        },
                        label = { Text(t.label) },
                    )
                }
            }
        }
    ) { pad ->
        Box(Modifier.padding(pad)) {
            when (tab) {
                Tab.APPS ->
                    when (openApp) {
                        NexusAppId.STREAM ->
                            StreamScreen(streamUi, onRole, onPress, onRelease)
                        null -> AppsScreen(streamUi) { openApp = it }
                    }
                Tab.CHANNELS ->
                    if (openPane == null) {
                        ChannelList(channels, connected, onOpen)
                    } else {
                        ThreadScreen(
                            label = channels.firstOrNull { it.paneId == openPane }?.label ?: openPane,
                            events = thread,
                            onBack = { onOpen(null) },
                            onSend = onSend,
                        )
                    }
            }
        }
    }
}

@Composable
private fun ChannelList(channels: List<Channel>, connected: Boolean, onOpen: (String) -> Unit) {
    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Channels", fontSize = 26.sp, fontWeight = FontWeight.Bold)
            Box(Modifier.size(9.dp).clip(CircleShape)
                .background(if (connected) Color(0xFF3E9B4F) else Color(0xFF6B7280)))
        }
        if (channels.isEmpty()) {
            Text(
                if (connected) "No channels on the hub yet" else "Connecting to the hub…",
                fontSize = 15.sp, color = Color(0xFF9AA3AF),
                modifier = Modifier.padding(top = 16.dp),
            )
        }
        LazyColumn {
            items(channels, key = { it.paneId }) { ch ->
                Row(
                    Modifier.fillMaxWidth()
                        .clickable { onOpen(ch.paneId) }
                        .padding(vertical = 14.dp),
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Box(
                        Modifier.size(9.dp).clip(CircleShape).background(
                            when {
                                !ch.live -> Color(0xFFE5484D)
                                ch.status == "working" -> Color(0xFF22D3EE)
                                else -> Color(0xFF3E9B4F)
                            }
                        )
                    )
                    Column {
                        Text(ch.label, fontSize = 17.sp, fontWeight = FontWeight.Medium)
                        Text(ch.status, fontSize = 13.sp, color = Color(0xFF9AA3AF))
                    }
                }
            }
        }
    }
}

@Composable
private fun ThreadScreen(
    label: String,
    events: List<Event>,
    onBack: () -> Unit,
    onSend: (String) -> Unit,
) {
    var draft by remember { mutableStateOf("") }
    // ⚠️⚠️ The phone had NO scroll logic at all — not a broken rule, an absent one.
    //    "enter a thread it's somewhere in the middle, i send a message, it doesn't
    //    scroll down". A conversation is read at the BOTTOM.
    val listState = rememberLazyListState()
    LaunchedEffect(events.size, events.lastOrNull()?.id) {
        if (events.isNotEmpty()) listState.scrollToItem(events.lastIndex)
    }
    Column(Modifier.fillMaxSize()) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onBack) {
                Icon(Icons.Default.ArrowBack, contentDescription = "Back")
            }
            Text(label, fontSize = 19.sp, fontWeight = FontWeight.SemiBold)
        }
        LazyColumn(
            state = listState,
            modifier = Modifier.weight(1f).padding(horizontal = 14.dp),
        ) {
            items(events, key = { it.id }) { e -> EventBubble(e) }
        }
        Row(
            Modifier.fillMaxWidth().padding(10.dp),
            verticalAlignment = Alignment.Bottom,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            OutlinedTextField(
                value = draft,
                onValueChange = { draft = it },
                placeholder = { Text("Message this channel") },
                modifier = Modifier.weight(1f),
                maxLines = 6,
            )
            IconButton(onClick = {
                val text = draft.trim()
                if (text.isNotEmpty()) { onSend(text); draft = "" }
            }) {
                Icon(Icons.Default.Send, contentDescription = "Send")
            }
        }
    }
}

/**
 * Mine right, the agent's left — the same reading the Mac client uses, so the two
 * do not disagree about who said what.
 */
@Composable
private fun EventBubble(e: Event) {
    if (e.kind == "image") { InlineImage(e); return }
    val mine = e.kind == "sent" || e.kind == "receipt"
    Row(
        Modifier.fillMaxWidth().padding(vertical = 4.dp),
        horizontalArrangement = if (mine) Arrangement.End else Arrangement.Start,
    ) {
        Box(
            Modifier
                .clip(RoundedCornerShape(14.dp))
                .background(
                    if (mine) Color(0xFF4A8DFF).copy(alpha = 0.30f)
                    else Color(0xFF8066D2).copy(alpha = 0.24f)
                )
                .padding(horizontal = 12.dp, vertical = 9.dp)
        ) {
            Text(
                e.summary.ifBlank { e.body },
                fontSize = 15.sp,
                color = MaterialTheme.colorScheme.onBackground,
            )
        }
    }
}


/**
 * The apps shelf. One entry today; the point is the SHAPE — the phone and the Mac
 * agree about what an app is and where it lives.
 */
@Composable
private fun AppsScreen(streamUi: StreamUi, onOpen: (NexusAppId) -> Unit) {
    Column(Modifier.fillMaxSize().padding(16.dp),
           verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Apps", fontSize = 26.sp, fontWeight = FontWeight.Bold)
        NexusAppId.entries.forEach { app ->
            val live = app == NexusAppId.STREAM && streamUi.role != Role.OFF
            Row(
                Modifier.fillMaxWidth()
                    .clip(RoundedCornerShape(14.dp))
                    .background(
                        if (live) Color(0xFFE5484D).copy(alpha = 0.16f)
                        else Color(0xFF6B7280).copy(alpha = 0.14f)
                    )
                    .clickable { onOpen(app) }
                    .padding(16.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box(Modifier.size(10.dp).clip(CircleShape).background(
                    if (live) Color(0xFFE5484D) else Color(0xFF6B7280)))
                Column {
                    Text(app.title, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                    Text(
                        if (live) streamStatusLine(streamUi) else app.subtitle,
                        fontSize = 13.sp, color = Color(0xFF9AA3AF),
                    )
                }
            }
        }
    }
}

private fun streamStatusLine(ui: StreamUi): String = when {
    ui.role == Role.SENDER -> "LIVE — this device is the open mic"
    ui.talkingNow != null -> "${ui.talkingNow} is talking"
    ui.channelOpen -> "Listening"
    else -> "Waiting for a channel"
}


/**
 * An image drawn IN the thread.
 *
 * ★ "you should be able to dump images into these channel feeds ... don't point me
 * elsewhere." Same event, same place, on the phone as on the Mac.
 *
 * ⚠️ Hand-rolled loader rather than Coil: the hub needs a Bearer token, and adding an
 * image library to carry one header is not worth the dependency. Content-addressed and
 * immutable, so a one-shot in-memory cache keyed by id can never be stale.
 */
@Composable
private fun InlineImage(e: Event) {
    val id = e.meta["image"]?.jsonObject?.get("id")?.jsonPrimitive?.contentOrNull
    val w = e.meta["image"]?.jsonObject?.get("width")?.jsonPrimitive?.intOrNull
    val h = e.meta["image"]?.jsonObject?.get("height")?.jsonPrimitive?.intOrNull
    var bmp by remember(id) { mutableStateOf<ImageBitmap?>(null) }
    var failed by remember(id) { mutableStateOf(false) }

    LaunchedEffect(id) {
        if (id == null) { failed = true; return@LaunchedEffect }
        bmp = ImageCache.load(id)
        if (bmp == null) failed = true
    }

    Column(Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
        Box(
            Modifier
                .fillMaxWidth()
                // ★ Reserve the real aspect ratio before the bytes land, so the thread
                //   does not jump under him while images load.
                .then(if (w != null && h != null && w > 0 && h > 0)
                          Modifier.aspectRatio(w.toFloat() / h.toFloat())
                      else Modifier)
                .clip(RoundedCornerShape(12.dp))
                .background(Color(0xFF8066D2).copy(alpha = 0.14f)),
            contentAlignment = Alignment.Center,
        ) {
            when {
                bmp != null -> Image(
                    bitmap = bmp!!,
                    contentDescription = e.body,
                    modifier = Modifier.fillMaxWidth(),
                    contentScale = ContentScale.Fit,
                )
                failed -> Text("image did not load", fontSize = 14.sp, color = Color(0xFF9AA3AF))
                else -> CircularProgressIndicator(Modifier.size(28.dp))
            }
        }
        if (e.body.isNotBlank()) {
            Text(e.body, fontSize = 14.sp, color = Color(0xFF9AA3AF),
                 modifier = Modifier.padding(top = 6.dp))
        }
    }
}
