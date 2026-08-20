package com.roam.touch.channels.audio

import android.util.Log
import android.webkit.JavascriptInterface
import android.webkit.WebView

/**
 * ★★ **The hub's radio page is the playback surface, so the arbitration has to reach
 * inside a WebView.**
 *
 * There is no MediaPlayer here to pause. The music is an HTML5 media element in a page
 * served by the hub, and the only handle Android gives us on it is JavaScript. So the
 * commands are JavaScript, and — because a 2019 Chrome and a page written by someone else
 * are the two least testable things in this app — every one of them is built by a pure
 * function in [RadioJs] that a JVM test can read.
 *
 * ⚠️ Everything below is ES5. The engine underneath is Chrome 74 and cannot be updated —
 * no Play Store on this phone, WebView provider signature-pinned. No arrow functions, no
 * `let`/`const`, no template literals. Same rule the hub's own pages are written under.
 */
object RadioJs {

    /**
     * ★ The page's own hook, if it has one, is preferred over poking its elements.
     *
     * A radio page that defines `window.RoamRadio = { play: fn, pause: fn, setVolume: fn }`
     * knows things we do not — which of three players is the live one, whether a stream has
     * to be re-opened rather than resumed after a long pause. The element fallback exists
     * so that a page which defines nothing still obeys, which is what makes this safe to
     * ship before the hub page is written.
     */
    const val HOOK = "window.RoamRadio"

    /**
     * Marks the elements *we* paused.
     *
     * ⚠️ Without it, resume would start playing every `<audio>` on the page, including one
     * he had deliberately paused himself, and including a stream that was never playing.
     */
    const val MARK = "data-roam-held"

    /** Pause everything, remembering what was actually playing. */
    fun pause(): String = wrap(
        """
        if ($HOOK && typeof $HOOK.pause === 'function') { $HOOK.pause(); return; }
        var m = document.querySelectorAll('audio,video');
        for (var i = 0; i < m.length; i++) {
          if (!m[i].paused) { m[i].setAttribute('$MARK', '1'); m[i].pause(); }
        }
        """.trimIndent()
    )

    /**
     * Resume at [volume], and only what we paused.
     *
     * ⚠️ `play()` returns a promise on this engine and it rejects when the page has not
     * been interacted with, or when a stream has gone stale. Caught, because an unhandled
     * rejection here would surface as a silent radio with a console message nobody on a
     * forearm can read.
     */
    fun play(volume: Float): String = wrap(
        """
        var v = ${clamp(volume)};
        if ($HOOK && typeof $HOOK.play === 'function') { $HOOK.play(v); return; }
        var m = document.querySelectorAll('audio,video');
        for (var i = 0; i < m.length; i++) {
          m[i].volume = v;
          if (m[i].hasAttribute('$MARK') || m[i].paused) {
            m[i].removeAttribute('$MARK');
            try { var p = m[i].play(); if (p && p['catch']) { p['catch'](function(){}); } }
            catch (e) {}
          }
        }
        """.trimIndent()
    )

    /** Keep playing, at [volume]. Touches nothing else — a duck must not start anything. */
    fun setVolume(volume: Float): String = wrap(
        """
        var v = ${clamp(volume)};
        if ($HOOK && typeof $HOOK.setVolume === 'function') { $HOOK.setVolume(v); return; }
        var m = document.querySelectorAll('audio,video');
        for (var i = 0; i < m.length; i++) { m[i].volume = v; }
        """.trimIndent()
    )

    /**
     * ⚠️⚠️ **The only value that crosses into the page, and it is never interpolated as
     * text.** It is clamped to 0..1 and printed with a fixed format, so there is no input
     * here that could carry a quote, a semicolon or a newline into an eval. The rest of
     * these scripts are constants.
     */
    fun clamp(volume: Float): String {
        val v = when {
            volume.isNaN() -> 0f
            volume < 0f -> 0f
            volume > 1f -> 1f
            else -> volume
        }
        // ⚠️⚠️ [java.util.Locale.ROOT], not the device's. A phone set to French formats
        // this as `0,200`, which is not a number in JavaScript — it is a syntax error that
        // aborts the whole script and leaves the radio wherever it was. The rest of this
        // app can use the default locale; a string being handed to an interpreter cannot.
        return String.format(java.util.Locale.ROOT, "%.3f", v)
    }

    /** An IIFE, so the page's own globals cannot be clobbered by a stray `var`. */
    private fun wrap(body: String): String = "(function(){\n$body\n})();"
}

/**
 * The live radio page, as a [PlaybackSurface].
 *
 * ⚠️ Every call hops to the WebView's own thread. Focus callbacks arrive on a framework
 * thread and PTT's arrive on a coroutine dispatcher; touching a WebView from either is
 * undefined behaviour that shows up as a crash weeks later on the one device that matters.
 */
class WebViewPlayback(private val web: WebView) : PlaybackSurface {

    override fun play(volume: Float) = run(RadioJs.play(volume), "play @ $volume")

    override fun pause() = run(RadioJs.pause(), "pause")

    override fun setVolume(volume: Float) = run(RadioJs.setVolume(volume), "volume $volume")

    private fun run(script: String, what: String) {
        Log.i(TAG, "radio: $what")
        web.post { runCatching { web.evaluateJavascript(script, null) } }
    }

    companion object {
        private const val TAG = "RoamAudio"
    }
}

/**
 * ★ How the radio page tells the app that music is wanted, so a PTT press knows whether
 * there is anything to put back afterwards.
 *
 * The page calls `RoamAudio.onPlay()` / `RoamAudio.onPause()` from its own Play/Stop
 * button — his decisions, not the element's events. Without this the app would have to
 * guess, and both ways of guessing are wrong: assume music is always wanted and every PTT
 * release starts a radio he never asked for, assume it never is and the stream he was
 * listening to does not come back when he lets go of the button.
 *
 * ⚠️⚠️ A `@JavascriptInterface` is a hole from a web page into the app, so this one is as
 * small as it can be: two methods, no arguments, no return values, nothing that names a
 * file, a URL or a token. It is installed only on the hub browser's WebView, which refuses
 * to navigate off the hub at all (see `HubBrowser.isHubUrl`).
 *
 * ⚠️ Calls arrive on a WebView JS thread. [PlaybackFocus] is `@Synchronized` throughout,
 * which is why they may be handed to it directly.
 */
class RadioBridge(private val playback: PlaybackFocus) {

    /**
     * The page started playing.
     *
     * ⚠️ A *report*, not a request, and it is ignored when we already believe music is
     * wanted. That is what breaks the loop: our own resume calls `play()` in the page, the
     * page reports it, and without this guard the report would re-issue the resume — which
     * on this page re-opens the stream — for as long as the process lived.
     */
    @JavascriptInterface
    fun onPlay() {
        if (playback.state.value.wanted) return
        playback.onPlayRequested()
    }

    /**
     * The page stopped, at his hand. Give the audio back to whatever else wants it.
     *
     * ⚠️⚠️ **Guarded on `playing`, not on `wanted`, and the difference is the whole bug.**
     *
     * While PTT is keyed `wanted` is still true and `playing` is false: we *paused* the page
     * and intend to resume it. Two things can echo that pause back at us. A page with an
     * `<audio>` element but no `window.RoamRadio` hook is paused by the element fallback in
     * [RadioJs.pause], which makes the element fire its own `pause` event; and Chromium
     * suspends the element on its own when the `GAIN_TRANSIENT_EXCLUSIVE` we take for the
     * microphone lands on it. On a `wanted` guard either report is indistinguishable from
     * him pressing pause, and **the radio never comes back after the first PTT press.**
     *
     * A pause he actually made always arrives while we believe sound is coming out, so
     * `playing` is the honest test. Today's `radio.html` implements the hook and so never
     * hits the fallback — which is exactly what makes this a trap for the next page rather
     * than a visible fault.
     */
    @JavascriptInterface
    fun onPause() {
        if (!playback.state.value.playing) return
        playback.onPauseRequested()
    }

    companion object {
        /** The name the object takes in the page's JavaScript. */
        const val NAME = "RoamAudio"
    }
}
