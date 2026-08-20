package com.roam.touch.channels.tts

import com.roam.touch.channels.Fx
import com.roam.touch.channels.audio.AudioHold
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.cancel
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException

/** A voice that says nothing and finishes when the test says so. */
private class FakeVoice : Voice {
    val spoken = mutableListOf<String>()
    var fail: IOException? = null

    /** Completed by the test to end the "speech"; left pending to hold it open. */
    var finish = CompletableDeferred<Unit>()

    override suspend fun speak(text: String) {
        spoken += text
        fail?.let { throw it }
        finish.await()
    }
}

/** Counts the duck the voice took, and whether it was given back. */
private class CountingHold : AudioHold {
    var begins = 0
        private set
    var ends = 0
        private set

    val held: Boolean get() = begins > ends

    override fun begin() {
        begins++
    }

    override fun end() {
        ends++
    }
}

/**
 * ★★ **Piper turns the radio down, and always turns it back up.**
 *
 * The wearer hears the hub's radio, his own PTT and this voice through one Bluetooth
 * earbud. A message he tapped play on is meant to sit *on top of* the music — which is
 * what ducking is — but the half that actually bites is the release: a duck left standing
 * by a cancelled sentence is a radio that plays at 20 % for the rest of the day, with
 * nothing on screen to explain it and no control that fixes it.
 *
 * ⚠️ Tapping play on a second message cancels the first mid-sentence, by design
 * ([TtsSpeaker.play]), so cancellation is the *normal* path here and not an edge case.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class TtsSpeakerAudioTest {

    private val dispatcher = StandardTestDispatcher()
    private val scope = CoroutineScope(dispatcher)
    private val voice = FakeVoice()
    private val audio = CountingHold()
    private val speaker = TtsSpeaker(voice, scope, audio)

    private val event = Fx.event(id = 7, body = "the suite is green")

    @After
    fun tearDown() = scope.cancel()

    @Test
    fun `speaking ducks the radio for exactly as long as it speaks`() = runTest(dispatcher) {
        speaker.play(event, "Augment")
        advanceUntilIdle()
        assertTrue("the duck is taken while Piper talks", audio.held)
        assertEquals(1, voice.spoken.size)

        voice.finish.complete(Unit)
        advanceUntilIdle()
        assertTrue("and given back when it stops", !audio.held)
    }

    @Test
    fun `stopping mid-sentence gives the radio back`() {
        // ★ The stop control next to the message. It cancels the coroutine, and the
        // release rides the `finally` inside it.
        runTest(dispatcher) {
            speaker.play(event, "Augment")
            advanceUntilIdle()
            speaker.stop()
            advanceUntilIdle()
            assertTrue(!audio.held)
        }
    }

    @Test
    fun `playing a second message does not leave the first message's duck behind`() {
        // ⚠️⚠️ The one that would actually have shipped broken. Playing a second message
        // cancels the first, so a naive `begin()`/`end()` pair around the call would leak
        // one duck per interrupted message and drop the radio to 20 % permanently.
        runTest(dispatcher) {
            speaker.play(event, "Augment")
            advanceUntilIdle()
            voice.finish = CompletableDeferred()
            speaker.play(Fx.event(id = 8, body = "and the build is up"), "Roam")
            advanceUntilIdle()
            assertEquals(2, audio.begins)
            assertEquals(1, audio.ends)

            voice.finish.complete(Unit)
            advanceUntilIdle()
            assertTrue(!audio.held)
        }
    }

    @Test
    fun `a Piper that is unreachable does not leave the radio ducked`() = runTest(dispatcher) {
        // ⚠️ The hub is on a tailnet and Piper is a socket on another box. It being down
        // is a Tuesday, not an exception, and it must not cost him his music.
        voice.fail = IOException("connection refused")
        speaker.play(event, "Augment")
        advanceUntilIdle()
        assertTrue(!audio.held)
    }

    @Test
    fun `a message with nothing to say takes nothing at all`() {
        runTest(dispatcher) {
            speaker.play(Fx.event(id = 9, body = "", summary = ""), "Augment")
            advanceUntilIdle()
            assertEquals(0, audio.begins)
        }
    }
}
