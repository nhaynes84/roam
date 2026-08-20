package com.roam.touch.channels.ui

import android.annotation.SuppressLint
import android.util.Log
import android.view.ViewGroup
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import com.roam.touch.channels.Roam
import com.roam.touch.channels.audio.PlaybackFocus
import com.roam.touch.channels.audio.RadioBridge
import com.roam.touch.channels.audio.WebViewPlayback

/** Same tag the rest of Nexus logs under, so `roam-emu logcat` catches it unchanged. */
private const val TAG = "RoamNexus"

/**
 * ★★ How the hub's own pages are addressed and authenticated — as decisions, not as an
 * `if` chain inside a `WebViewClient` that no JVM test can reach.
 *
 * Everything here is a pure function of strings, because the two things that were wrong
 * are both string decisions: which URL gets the token, and which URL is allowed to load
 * at all.
 */
object HubBrowser {

    /**
     * ★★ **The token goes here and nowhere else.**
     *
     * ⚠️⚠️ Not `?token=` on the URL. The hub accepts either — `require_auth_flex` takes a
     * query token precisely so a browser can fetch an `<img src>` — but a URL is written
     * into history, into the omnibox's suggestions and into every log that records a
     * request line, and **this one token authenticates every endpoint on the hub**,
     * including `POST /channels/{pane}/send`. A header is sent, used and gone. The page
     * that comes back carries its own copy of the token in its JavaScript for the fetches
     * it makes after that, so exactly one request has to be authenticated this way.
     *
     * A blank token yields no header at all rather than `Bearer `, so the failure is the
     * hub's own 401 page — "bearer token required", diagnosable — instead of a malformed
     * header that reads as a network fault. That is the same choice `build.gradle` makes
     * when `roam.hub.token` is unset.
     */
    fun authHeaders(token: String): Map<String, String> =
        if (token.isBlank()) emptyMap() else mapOf("Authorization" to "Bearer $token")

    /**
     * ★ Whether a URL belongs to the hub, and may therefore be loaded.
     *
     * ⚠️ The suffix check is load-bearing: a bare `startsWith(base)` would also accept
     * `http://100.67.237.109:8787.example.com/`, which is a different host that would be
     * handed a page carrying the token. Only a URL that continues with a path, a query, a
     * fragment or nothing at all is the same origin.
     */
    fun isHubUrl(url: String, base: String): Boolean {
        if (!url.startsWith(base)) return false
        val rest = url.substring(base.length)
        return rest.isEmpty() || rest.startsWith("/") ||
            rest.startsWith("?") || rest.startsWith("#")
    }

    /**
     * ★★ Whether a failed load should be retried with the token on it.
     *
     * ⚠️ This is the gap that a single `loadUrl(url, headers)` leaves open, and it is a
     * real path rather than a hypothetical one. Headers passed to `loadUrl` apply to that
     * one main-frame request; they are not replayed for a *back* navigation. The hub
     * serves its pages `Cache-Control: no-store`, so pressing Back out of the STL viewer
     * refetches `/browse` — with no header, and therefore a 401 reading "bearer token
     * required", which is the exact symptom this whole screen exists to remove.
     *
     * Retried once per URL and only on 401, so a token the hub genuinely rejects shows its
     * 401 rather than spinning. Subresources are left alone: the page's own fetches carry
     * the token themselves, and the vendored three.js under `/web/vendor` is
     * unauthenticated on purpose.
     */
    fun shouldRetryWithAuth(
        status: Int,
        isMainFrame: Boolean,
        url: String,
        base: String,
        alreadyTried: Boolean,
    ): Boolean = status == 401 && isMainFrame && !alreadyTried && isHubUrl(url, base)
}

/**
 * ★★ The hub's file browser, drawn inside Nexus.
 *
 * Two reasons it is here rather than an `ACTION_VIEW` at Chrome, and the first is the one
 * that made it necessary:
 *
 * 1. **The token can be a header.** Handing the URL to another app means the only way to
 *    authenticate it is `?token=` in the URL — see [HubBrowser.authHeaders].
 * 2. **He does not leave the app.** The phone is strapped to a forearm; the way back is a
 *    named button in the top-left and the hardware key, both landing on the shelf he came
 *    from rather than dumping him at another app's idea of home.
 *
 * ⚠️ The engine underneath is Chrome 74 from 2019 and cannot be updated — there is no
 * Play Store on this phone and the WebView provider is signature-pinned. Nothing modern
 * may be assumed here or in the hub's pages; `web/browse.html` is already written for it
 * (`var`, `XMLHttpRequest`-era `fetch`, no template literals, no arrow functions).
 */
@Composable
fun HubBrowserScreen(
    url: String,
    title: String,
    token: String,
    base: String,
    onBack: () -> Unit,
    /**
     * ★★ The referee for the earbud — see [PlaybackFocus].
     *
     * ⚠️ Null when the process graph has not been built (a preview, a screen test). The
     * page then still loads and still plays; it is only the arbitration that is absent,
     * which is the right failure for a test harness and the wrong one for the device — so
     * the real caller always has it.
     */
    playback: PlaybackFocus? = if (Roam.isReady()) Roam.playback else null,
) {
    val headers = remember(token) { HubBrowser.authHeaders(token) }
    // Held so Back can ask the live WebView whether it has anywhere to go, at the moment
    // it is pressed rather than at the moment it was composed.
    val web = remember { mutableStateOf<WebView?>(null) }

    /**
     * ★★ **The radio stops when this screen does.**
     *
     * ⚠️ Both halves matter. The JS pause is for the WebView itself: Compose detaches the
     * view but nothing guarantees the media element inside it stops, and a stream that
     * keeps playing from a screen he has left is unreachable — there is no control on any
     * other screen that can stop it. [PlaybackFocus.onSurfaceGone] is for the app's own
     * memory of it: a page that has gone must not be resumed by the next PTT release.
     */
    DisposableEffect(playback) {
        onDispose {
            Roam.radio?.pause()
            Roam.radio = null
            playback?.onSurfaceGone()
        }
    }

    // ★ Back walks the page's own history first, and only then leaves.
    //
    // ⚠️ Composed *after* the app-wide handler in [ChannelsApp], so it wins: Compose
    // dispatches Back to the most recently registered enabled handler. Folder navigation
    // in browse.html is `location.hash`, so each folder he opened is a history entry and
    // Back walks back up the tree exactly the way he walked down it. When there is nowhere
    // left to go, it hands him to the shelf — never out of the app.
    BackHandler {
        val view = web.value
        if (view != null && view.canGoBack()) view.goBack() else onBack()
    }

    Column(Modifier.fillMaxSize().background(RoamColors.Background)) {
        // Named APPS rather than CHANNELS: this screen was opened from the shelf and
        // returns to the shelf, and a button that names the wrong destination on a worn
        // device is worse than no button.
        BackToChannelsBar(title = title, backLabel = "APPS", onBack = onBack)

        AndroidView(
            modifier = Modifier.fillMaxWidth().weight(1f),
            factory = { context ->
                WebView(context).apply {
                    layoutParams = ViewGroup.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT,
                        ViewGroup.LayoutParams.MATCH_PARENT,
                    )
                    // True black behind the page, so the hub's dark pages do not flash
                    // white on every navigation on an OLED strapped to an arm.
                    setBackgroundColor(android.graphics.Color.BLACK)
                    configure()
                    webViewClient = hubClient(base, headers)
                    // ★★ The radio, wired to the referee. Installed on every hub page
                    // rather than only on the radio one: a page that never calls
                    // `RoamAudio` is unaffected, and there is no way to know from a URL
                    // which hub page has an <audio> element on it today.
                    //
                    // ⚠️ Safe because this WebView cannot navigate off the hub — see
                    // `hubClient` — and because the bridge exposes two no-argument
                    // methods and nothing else. See [RadioBridge].
                    if (playback != null) {
                        addJavascriptInterface(RadioBridge(playback), RadioBridge.NAME)
                        Roam.radio = WebViewPlayback(this)
                    }
                    // ★ The one request that has to carry the token as a header. Every
                    // fetch the page makes afterwards uses the copy the hub baked into
                    // its JavaScript, and its folder navigation never leaves this
                    // document at all.
                    loadUrl(url, headers)
                    web.value = this
                }
            },
            // ⚠️ Nothing is reloaded on recomposition. `update` firing a second loadUrl
            // would throw away his scroll position and his place in the folder tree every
            // time an unrelated piece of app state changed.
            update = { },
        )
    }
}

/**
 * ⚠️ JavaScript is on because the hub's pages are *entirely* JavaScript — `browse.html`
 * renders nothing server-side, it fetches `/files` and builds the grid. This is the app's
 * own server on its own tailnet, serving pages from this repository.
 *
 * File and content access are off: this WebView never has a reason to read the device's
 * storage or its content providers, and leaving them on is what turns a hub page bug into
 * a way to read the phone.
 */
@SuppressLint("SetJavaScriptEnabled")
private fun WebView.configure() {
    settings.javaScriptEnabled = true
    settings.domStorageEnabled = true
    // ★★ **False, or the music never comes back after PTT.**
    //
    // ⚠️ The default is true, and it does not mean "the first play needs a tap" — it means
    // *every* `play()` that is not inside a touch handler is refused. The resume after a
    // press is issued from a focus callback, which is not a gesture by any definition the
    // engine has, so with the default the radio would stop at the first PTT press and stay
    // stopped until he found the page and pressed play again. That is the exact failure
    // this whole file exists to remove.
    //
    // ⚠️ The cost is that a hub page *could* autoplay on load. Accepted: this WebView
    // loads nothing but pages from his own hub, out of this repository, and it refuses to
    // navigate anywhere else.
    settings.mediaPlaybackRequiresUserGesture = false
    settings.allowFileAccess = false
    settings.allowContentAccess = false
    // A forearm screen is small and the hub's pages are already laid out for it; pinch
    // zoom here only ever means an accidentally zoomed page he then has to fix.
    settings.setSupportZoom(false)
    settings.builtInZoomControls = false
    settings.displayZoomControls = false
}

/**
 * ★ What this WebView is allowed to load, and what it does when the hub says no.
 *
 * ⚠️ Off-hub navigation is refused outright rather than passed to Chrome. This is an
 * appliance showing his own files: there is no legitimate link out of `browse.html`, so
 * anything pointing elsewhere is either a bug or a filename doing something clever, and
 * the safe answer on the only screen that can leave the home screen is "no".
 */
private fun hubClient(base: String, headers: Map<String, String>): WebViewClient =
    object : WebViewClient() {

        /** Retried at most once per URL — see [HubBrowser.shouldRetryWithAuth]. */
        private var retried: String? = null

        override fun shouldOverrideUrlLoading(
            view: WebView,
            request: WebResourceRequest,
        ): Boolean {
            val target = request.url.toString()
            if (HubBrowser.isHubUrl(target, base)) {
                // ⚠️ Return false — let the WebView load it itself. Calling loadUrl here
                // to re-attach the header would cancel and restart every navigation, and
                // the links the hub emits (`/view/stl`, `/files/raw`) already carry their
                // own `?token=`; that is the hub's design for things a browser fetches,
                // not something added here.
                return false
            }
            Log.w(TAG, "refusing off-hub navigation from the shelf browser")
            return true
        }

        override fun onReceivedHttpError(
            view: WebView,
            request: WebResourceRequest,
            errorResponse: WebResourceResponse,
        ) {
            val target = request.url.toString()
            if (
                HubBrowser.shouldRetryWithAuth(
                    status = errorResponse.statusCode,
                    isMainFrame = request.isForMainFrame,
                    url = target,
                    base = base,
                    alreadyTried = retried == target,
                )
            ) {
                retried = target
                Log.i(TAG, "hub asked for auth on a back navigation — reloading with the header")
                view.loadUrl(target, headers)
                return
            }
            super.onReceivedHttpError(view, request, errorResponse)
        }
    }
