package com.roam.touch.channels.stt

import com.roam.touch.channels.wyoming.WyomingReader
import com.roam.touch.channels.wyoming.WyomingWriter
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.EOFException

/**
 * ★★ The Wyoming framing, which is the hard half of both the voice in and the voice out.
 *
 * One JSON header *line* followed by raw bytes, on one stream. The failure mode is not
 * subtle in hindsight and invisible in advance: treat the payload as text and everything
 * works until someone speaks loudly enough to put a `0x0A` in the PCM, at which point
 * the stream desynchronises and every later event is garbage. So the tests below are
 * built around bytes chosen to be hostile — newlines, carriage returns, `0xFF`, and the
 * UTF-8 lead bytes that a decoder would eat.
 */
class WyomingFramingTest {

    private fun roundTrip(vararg write: WyomingWriter.() -> Unit): WyomingReader {
        val buffer = ByteArrayOutputStream()
        val writer = WyomingWriter(buffer)
        write.forEach { it(writer) }
        return WyomingReader(ByteArrayInputStream(buffer.toByteArray()))
    }

    @Test
    fun `an event with no data and no payload survives`() {
        val reader = roundTrip({ write("audio-stop") })
        val event = reader.next()
        assertEquals("audio-stop", event.type)
        assertEquals(0, event.payload.size)
    }

    @Test
    fun `data goes inline and comes back parsed`() {
        val reader = roundTrip({
            write("audio-start", buildJsonObject {
                put("rate", 16_000); put("width", 2); put("channels", 1)
            })
        })
        val event = reader.next()
        assertEquals("audio-start", event.type)
        assertEquals("16000", event.data["rate"]?.jsonPrimitive?.content)
        assertEquals("1", event.data["channels"]?.jsonPrimitive?.content)
    }

    /**
     * ⚠️⚠️ The one that matters. Every byte value 0–255 appears in this payload,
     * including `\n` (0x0A) and `\r` (0x0D), which is exactly what real 16-bit PCM
     * contains within the first few milliseconds of speech.
     */
    @Test
    fun `a payload containing newlines is not treated as text`() {
        val pcm = ByteArray(256) { it.toByte() }
        val reader = roundTrip({
            write("audio-chunk", buildJsonObject { put("rate", 16_000) }, pcm)
        })
        val event = reader.next()
        assertEquals("audio-chunk", event.type)
        assertArrayEquals(pcm, event.payload)
    }

    /** And the stream stays in sync afterwards — the actual symptom of getting it wrong. */
    @Test
    fun `events after a hostile payload still parse`() {
        val pcm = ByteArray(1_024) { (it * 7).toByte() }
        val reader = roundTrip(
            { write("audio-chunk", buildJsonObject { put("rate", 16_000) }, pcm) },
            { write("audio-chunk", buildJsonObject { put("rate", 16_000) }, pcm) },
            { write("audio-stop", buildJsonObject { put("timestamp", 2_000) }) },
        )
        assertArrayEquals(pcm, reader.next().payload)
        assertArrayEquals(pcm, reader.next().payload)
        assertEquals("audio-stop", reader.next().type)
    }

    @Test
    fun `an empty payload is written as zero length, not omitted`() {
        val reader = roundTrip({ write("audio-chunk", null, ByteArray(0)) })
        assertEquals(0, reader.next().payload.size)
    }

    /**
     * The other legal wire form. This client never writes it, but Wyoming servers do,
     * so the reader has to accept `data_length` bytes of JSON after the header.
     */
    @Test
    fun `out-of-line data_length is read`() {
        val data = """{"text":" Run the test suite."}"""
        val raw = """{"type":"transcript","data_length":${data.toByteArray().size}}""" +
                "\n" + data
        val event = WyomingReader(ByteArrayInputStream(raw.toByteArray())).next()
        assertEquals("transcript", event.type)
        assertEquals(" Run the test suite.", event.data["text"]?.jsonPrimitive?.content)
    }

    /** Multi-byte UTF-8 in the header must not be mangled by the byte-wise readLine. */
    @Test
    fun `a header with non-ascii text survives the byte reader`() {
        val reader = roundTrip({
            write("transcript", buildJsonObject { put("text", "café — naïve ✳") })
        })
        assertEquals("café — naïve ✳", reader.next().data["text"]?.jsonPrimitive?.content)
    }

    @Test
    fun `a closed stream is an EOFException, not a hang or a null`() {
        val reader = WyomingReader(ByteArrayInputStream(ByteArray(0)))
        try {
            reader.next()
            throw AssertionError("expected EOFException")
        } catch (e: EOFException) {
            assertTrue(e.message!!.contains("closed"))
        }
    }

    @Test
    fun `a truncated payload is an EOFException rather than short bytes`() {
        val raw = """{"type":"audio-chunk","payload_length":64}""" + "\n" + "only-ten-b"
        try {
            WyomingReader(ByteArrayInputStream(raw.toByteArray())).next()
            throw AssertionError("expected EOFException")
        } catch (e: EOFException) {
            assertTrue(e.message!!.contains("truncated"))
        }
    }
}
