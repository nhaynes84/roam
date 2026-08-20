package com.roam.touch.channels.stt

import android.content.Context
import android.media.AudioManager
import androidx.test.core.app.ApplicationProvider
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * ★★ **The Back button must not reach into the audio HAL.**
 *
 * ⚠️⚠️ The failure this file exists for is not a wrong transcript — it is a **frozen
 * launcher on his forearm**. `Ptt.cancel()` tears the headset link down from *Idle*, and
 * cancel is wired to every Back press and every thread close (three call sites in
 * `ChannelsApp`), all on the main thread. [BluetoothHeadsetLink.close] used to run
 * unconditionally, so every one of those presses issued `stopBluetoothSco()` and
 * `setMode(MODE_NORMAL)` — a **global** audio-HAL operation — on a device whose capture
 * HAL is documented broken in [HeadsetLink] and which has already wedged with the audio
 * HAL stuck in D state. A blocked main thread there is a UI that does not come back.
 *
 * So the rule pinned below has two halves and both matter:
 *
 * 1. **Nothing we did not start gets stopped.** A close with no press behind it touches
 *    the audio stack not at all.
 * 2. **Anything we did start still gets stopped** — including a press abandoned halfway,
 *    which has already issued `startBluetoothSco()` and would otherwise leave the headset
 *    pinned in mono narrowband call mode.
 *
 * Robolectric because the subject is [AudioManager]'s own state: with `returnDefaultValues`
 * the android.jar stub would swallow every mode change and the assertions would pass
 * against code that still called it.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [29])
class BluetoothHeadsetLinkTest {

    private val context: Context = ApplicationProvider.getApplicationContext()
    private val audio = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager

    private fun link() = BluetoothHeadsetLink(context)

    // ---- 1. the Back press ------------------------------------------------------------

    /**
     * ⚠️⚠️ **The behavioural fix.** Idle → cancel → close, which is what every Back press
     * does. The audio mode is left exactly where the rest of the system put it.
     */
    @Test
    fun `a close with no press behind it never touches the audio mode`() {
        // Stand in for whatever else on the phone owns the audio at that moment — a call,
        // a navigation prompt. Resetting this to MODE_NORMAL from a Back press is both a
        // global HAL call and a lie about the device's state.
        audio.mode = AudioManager.MODE_IN_COMMUNICATION

        link().close()

        assertEquals(
            "Back must not reset the global audio mode",
            AudioManager.MODE_IN_COMMUNICATION,
            audio.mode,
        )
    }

    /** ⚠️ And it must not un-route SCO that something else has up, either. */
    @Test
    fun `a close with no press behind it leaves SCO routing alone`() {
        @Suppress("DEPRECATION")
        audio.setBluetoothScoOn(true)

        link().close()

        @Suppress("DEPRECATION")
        assertTrue("Back must not tear down someone else's SCO route", audio.isBluetoothScoOn)
    }

    /**
     * ★ Cancel fires on *every* Back press, not the first — the flag has to stay down, not
     * merely start down.
     */
    @Test
    fun `repeated closes stay a no-op`() {
        audio.mode = AudioManager.MODE_IN_COMMUNICATION
        val link = link()

        repeat(10) { link.close() }

        assertEquals(AudioManager.MODE_IN_COMMUNICATION, audio.mode)
    }

    /** Each press gets its own object in practice, but a shared one must behave too. */
    @Test
    fun `a close is still a no-op on a link that has been used and released`() =
        runTest {
            val link = link()
            runCatching { link.open() }
            link.close()
            assertEquals(AudioManager.MODE_NORMAL, audio.mode)

            // Something else takes the audio afterwards. The stale link must not reclaim it.
            audio.mode = AudioManager.MODE_IN_COMMUNICATION
            link.close()
            assertEquals(AudioManager.MODE_IN_COMMUNICATION, audio.mode)
        }

    // ---- 2. what we did start, we still stop ------------------------------------------

    /**
     * ⚠️⚠️ The other half. A press that reaches [BluetoothHeadsetLink.open] has already
     * moved the device into MODE_IN_COMMUNICATION and asked for SCO; abandoning it — the
     * link never comes up, he lets go early — must still hand the audio mode back. The
     * guard is on "did we touch it", never on "did it work".
     */
    @OptIn(ExperimentalCoroutinesApi::class)
    @Test
    fun `an open that never connects is still torn down`() = runTest {
        val link = link()

        // No SCO_AUDIO_STATE_CONNECTED broadcast ever arrives, so this is the timeout
        // path — the abandoned press. Virtual time, so the 4 s budget costs nothing.
        runCatching { link.open() }
        assertEquals(
            "open must have taken the device into call mode",
            AudioManager.MODE_IN_COMMUNICATION,
            audio.mode,
        )

        link.close()
        assertEquals(
            "a press we started must always be handed back",
            AudioManager.MODE_NORMAL,
            audio.mode,
        )
    }
}
