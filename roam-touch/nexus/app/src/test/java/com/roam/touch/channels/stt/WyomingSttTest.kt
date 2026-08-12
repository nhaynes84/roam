package com.roam.touch.channels.stt

import com.roam.touch.channels.wyoming.WyomingEvent
import com.roam.touch.channels.wyoming.WyomingReader
import com.roam.touch.channels.wyoming.WyomingWriter
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.EOFException
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * A Wyoming ASR server, in-process, that records everything the client said to it.
 *
 * It speaks the same wire format the real one does — verified against
 * `wyoming-faster-whisper` 3.5.0 on `talos:10300` — so a client that satisfies this
 * satisfies Whisper, without needing a network or a phone in the loop.
 */
private class FakeWhisper(private val respond: (List<WyomingEvent>) -> Unit = {}) {
    private val server = ServerSocket(0)
    val port: Int get() = server.localPort

    val received = mutableListOf<WyomingEvent>()
    val done = CountDownLatch(1)

    /** What the server sends back once it sees `audio-stop`. */
    var reply: (WyomingWriter) -> Unit = { writer ->
        writer.write("transcript", buildJsonObject { put("text", " run the test suite.") })
    }

    private val thread = Thread({
        runCatching {
            val socket: Socket = server.accept()
            val reader = WyomingReader(socket.getInputStream())
            val writer = WyomingWriter(socket.getOutputStream())
            while (true) {
                val event = try {
                    reader.next()
                } catch (e: EOFException) {
                    break
                }
                synchronized(received) { received += event }
                if (event.type == "audio-stop") {
                    respond(received)
                    reply(writer)
                    break
                }
            }
            socket.close()
        }
        done.countDown()
    }, "fake-whisper").also { it.isDaemon = true; it.start() }

    fun of(type: String) = synchronized(received) { received.filter { it.type == type } }

    fun close() {
        runCatching { server.close() }
        thread.interrupt()
    }
}

/**
 * ★ The Wyoming STT client, against a server that checks what it was told.
 *
 * The exchange being pinned is the one measured against the live service on
 * 2026-08-12 — `transcribe` → `audio-start` → `audio-chunk`×N → `audio-stop` →
 * `transcript` — including the two details that only show up against a real server:
 * the transcript arrives **with a leading space**, and the PCM must survive chunking
 * byte for byte.
 */
class WyomingSttTest {

    private var whisper: FakeWhisper? = null

    @After
    fun tearDown() {
        whisper?.close()
    }

    private fun client(w: FakeWhisper, language: String? = "en") =
        WyomingStt("127.0.0.1", w.port, language)

    @Test
    fun `a recording round-trips to a transcript`() = runBlocking {
        val w = FakeWhisper().also { whisper = it }
        val text = client(w).transcribe(FakeRecorder.speech(ms = 500))
        // ⚠️ Whisper's text always arrives with a leading space; the client trims it.
        assertEquals("run the test suite.", text)
        assertTrue(w.done.await(5, TimeUnit.SECONDS))
    }

    @Test
    fun `the protocol is spoken in the order the service expects`() = runBlocking {
        val w = FakeWhisper().also { whisper = it }
        client(w).transcribe(FakeRecorder.speech(ms = 500))
        w.done.await(5, TimeUnit.SECONDS)

        val types = synchronized(w.received) { w.received.map { it.type } }
        assertEquals("transcribe", types.first())
        assertEquals("audio-start", types[1])
        assertEquals("audio-stop", types.last())
        assertTrue("audio was chunked", types.count { it == "audio-chunk" } > 1)
    }

    @Test
    fun `the format is declared and matches the audio`() = runBlocking {
        val w = FakeWhisper().also { whisper = it }
        client(w).transcribe(FakeRecorder.speech(ms = 500))
        w.done.await(5, TimeUnit.SECONDS)

        val start = w.of("audio-start").single()
        assertEquals("16000", start.data["rate"]?.jsonPrimitive?.content)
        assertEquals("2", start.data["width"]?.jsonPrimitive?.content)
        assertEquals("1", start.data["channels"]?.jsonPrimitive?.content)
    }

    /**
     * ⚠️ The reason the framing exists. Reassembled chunks must equal the captured PCM
     * exactly — one dropped or duplicated byte is a click at best and a desynchronised
     * stream at worst, and neither is visible until someone speaks into it.
     */
    @Test
    fun `every captured byte arrives, in order`() = runBlocking {
        val w = FakeWhisper().also { whisper = it }
        val recording = FakeRecorder.speech(ms = 1_200)
        client(w).transcribe(recording)
        w.done.await(5, TimeUnit.SECONDS)

        val reassembled = w.of("audio-chunk")
            .fold(ByteArray(0)) { acc, event -> acc + event.payload }
        assertArrayEquals(recording.pcm, reassembled)
    }

    @Test
    fun `the language is pinned so a one-word command is not misdetected`() = runBlocking {
        val w = FakeWhisper().also { whisper = it }
        client(w, language = "en").transcribe(FakeRecorder.speech(ms = 400))
        w.done.await(5, TimeUnit.SECONDS)
        assertEquals("en", w.of("transcribe").single().data["language"]?.jsonPrimitive?.content)
    }

    @Test
    fun `an error event becomes an SttException carrying the reason`() = runBlocking {
        val w = FakeWhisper().also { whisper = it }
        w.reply = { writer ->
            writer.write("error", buildJsonObject { put("text", "model not loaded") })
        }
        try {
            client(w).transcribe(FakeRecorder.speech(ms = 400))
            throw AssertionError("expected SttException")
        } catch (e: SttException) {
            assertEquals("model not loaded", e.message)
        }
    }

    @Test
    fun `a server that hangs up mid-exchange is reported, not hung on`() = runBlocking {
        val w = FakeWhisper().also { whisper = it }
        w.reply = { /* say nothing and close */ }
        try {
            client(w).transcribe(FakeRecorder.speech(ms = 400))
            throw AssertionError("expected SttException")
        } catch (e: SttException) {
            assertTrue(e.message!!.contains("closed"))
        }
    }

    @Test
    fun `an empty recording never opens a socket`() = runBlocking {
        // Port 1 is not listening; if this tried to connect it would throw instead.
        assertEquals("", WyomingStt("127.0.0.1", 1).transcribe(Recording.EMPTY))
    }
}
