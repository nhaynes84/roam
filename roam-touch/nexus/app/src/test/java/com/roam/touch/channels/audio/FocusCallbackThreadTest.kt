package com.roam.touch.channels.audio

import android.content.Context
import android.media.AudioFocusRequest
import android.os.Handler
import android.os.Looper
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.util.ReflectionHelpers

/**
 * ★★ **Where a focus callback lands is a thread decision, and it was being made by
 * accident.**
 *
 * ⚠️⚠️ [android.media.AudioFocusRequest.Builder.setOnAudioFocusChangeListener] has two
 * forms, and the one-argument form does not mean "any thread" — it means **the thread that
 * made the request**. [SystemAudioFocus.request] is called from several:
 *
 * | caller | thread |
 * |---|---|
 * | the PTT panel | main |
 * | `Ptt` / TTS coroutines | `Dispatchers.Default` |
 *
 * A listener pinned to a caller's thread is a listener that blocks whatever that thread was
 * for, and this device stalls its audio HAL: a focus callback that waits is a coroutine
 * dispatcher thread that waits with it, in the middle of a press.
 *
 * One looper, always the same one, chosen explicitly. Robolectric because the subject is
 * what the framework object was actually built with.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [29])
class FocusCallbackThreadTest {

    private val context: Context = ApplicationProvider.getApplicationContext()
    private val audio = context.getSystemService(Context.AUDIO_SERVICE) as android.media.AudioManager

    /** The request the shadow captured, as the framework object it really is. */
    private fun requestFor(kind: FocusKind): AudioFocusRequest {
        SystemAudioFocus(context).request(kind) {}
        return requireNotNull(shadowOf(audio).lastAudioFocusRequest?.audioFocusRequest) {
            "no AudioFocusRequest reached AudioManager"
        }
    }

    /** What the framework was handed, dug out of the request the shadow captured. */
    private fun handlerFor(kind: FocusKind): Handler? =
        // ⚠️ There is no getter for this in API 29 — the field is the only place the
        // answer exists, and the answer is the whole fix.
        ReflectionHelpers.getField(requestFor(kind), "mListenerHandler")

    @Test
    fun `every focus request names the thread its callbacks arrive on`() {
        for (kind in FocusKind.values()) {
            val handler = handlerFor(kind)
            assertNotNull(
                "$kind focus would deliver on whichever thread happened to ask",
                handler,
            )
        }
    }

    /**
     * ★★ And that thread is the main looper — never the JavaBridge thread, whatever the
     * request was made from.
     */
    @Test
    fun `focus callbacks are delivered on the main looper`() {
        for (kind in FocusKind.values()) {
            assertEquals(
                "$kind focus must call back on the main looper",
                Looper.getMainLooper(),
                handlerFor(kind)?.looper,
            )
        }
    }

    /**
     * ⚠️ The case the fix is for: the request is made off the main thread, exactly as the
     * PTT and TTS coroutines make it, and the callbacks still come back to the main looper.
     */
    @Test
    fun `a request made off the main thread still calls back on main`() {
        var handler: Handler? = null
        val worker = Thread({ handler = handlerFor(FocusKind.CAPTURE) }, "DefaultDispatcher")
        worker.start()
        worker.join()

        assertEquals(
            "whichever thread happened to press the button must not become the audio " +
                "callback thread",
            Looper.getMainLooper(),
            handler?.looper,
        )
    }

    /**
     * ★★ **Nothing this app asks for is a durable media `GAIN`** — the request that a media
     * app takes to own the audio until it is done.
     *
     * ⚠️⚠️ The radio is an `<audio>` element in a WebView and Chromium takes that request
     * for it, from inside this process. A second one from us revoked the first, our own loss
     * callback read it as another app taking over, and the station was paused a heartbeat
     * after it started — on the device, every time, so nothing ever played. Both kinds left
     * here are borrows that are given back: the microphone and Piper's voice. See
     * `WebViewOwnsMediaFocusTest`.
     */
    @Test
    fun `no request this app makes claims the audio durably`() {
        for (kind in FocusKind.values()) {
            val gain = requestFor(kind).focusGain
            assertEquals(
                "$kind must not take AUDIOFOCUS_GAIN — the page's Chromium owns media focus",
                false,
                gain == android.media.AudioManager.AUDIOFOCUS_GAIN,
            )
        }
    }
}
