package com.roam.touch.channels.wyoming

import com.roam.touch.channels.model.HubJson
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import java.io.BufferedInputStream
import java.io.ByteArrayOutputStream
import java.io.EOFException
import java.io.InputStream
import java.io.OutputStream

/**
 * One Wyoming event: a JSON header line, optional out-of-line JSON data, optional
 * binary payload.
 *
 * ★ **The framing is the hard part of this protocol, and this file is the only place it
 * is implemented.** The header is a *line*, the payload is *raw bytes*, and they share
 * one stream — so it cannot be read with a Reader, which would happily swallow PCM into
 * a decoder. Hence the hand-rolled [WyomingReader.readLine] over a byte stream.
 *
 * ⚠️ PCM contains `0x0A` constantly (any sample whose low byte is 10). A reader that
 * scanned for newlines outside of the header, or a writer that assumed the payload was
 * text, would work on quiet audio and corrupt loud audio. [WyomingFramingTest] pins
 * exactly that case.
 *
 * Verified against wyoming-piper 1.10.0 (`talos:10200`) and wyoming-faster-whisper
 * 3.5.0 / `small-int8` (`talos:10300`), 2026-08-12.
 */
data class WyomingEvent(
    val type: String,
    val data: JsonObject = JsonObject(emptyMap()),
    val payload: ByteArray = NO_PAYLOAD,
) {
    // A data class over a ByteArray needs these spelled out; identity equality on the
    // payload would make every test comparison a coin toss.
    override fun equals(other: Any?): Boolean =
        this === other || (other is WyomingEvent && type == other.type && data == other.data &&
                payload.contentEquals(other.payload))

    override fun hashCode(): Int =
        (type.hashCode() * 31 + data.hashCode()) * 31 + payload.contentHashCode()

    companion object {
        /** Shared, because most events have no payload and all of them mean the same. */
        val NO_PAYLOAD: ByteArray = ByteArray(0)
    }
}

/** Reads [WyomingEvent]s off a socket. Not thread-safe; one per connection. */
class WyomingReader(input: InputStream) {
    private val stream = BufferedInputStream(input, 16 * 1024)

    private fun readLine(): String {
        val out = ByteArrayOutputStream(256)
        while (true) {
            val b = stream.read()
            if (b == -1) {
                if (out.size() == 0) throw EOFException("wyoming stream closed")
                break
            }
            if (b == '\n'.code) break
            out.write(b)
        }
        return out.toString("UTF-8")
    }

    private fun readExactly(n: Int): ByteArray {
        val buf = ByteArray(n)
        var off = 0
        while (off < n) {
            val r = stream.read(buf, off, n - off)
            if (r < 0) throw EOFException("wyoming payload truncated")
            off += r
        }
        return buf
    }

    /** The next event, or throws [EOFException] when the peer hangs up. */
    fun next(): WyomingEvent {
        val header = HubJson.parseToJsonElement(readLine()) as JsonObject
        val type = (header["type"] as? JsonPrimitive)?.content
            ?: throw IllegalStateException("wyoming event with no type")

        // Both forms are legal and both are seen in the wild: `data` inline in the
        // header, or `data_length` bytes of JSON following it.
        var data = header["data"] as? JsonObject ?: JsonObject(emptyMap())
        (header["data_length"] as? JsonPrimitive)?.content?.toIntOrNull()?.let { len ->
            data = HubJson.parseToJsonElement(
                String(readExactly(len), Charsets.UTF_8)
            ) as JsonObject
        }
        val payload = (header["payload_length"] as? JsonPrimitive)?.content?.toIntOrNull()
            ?.let { readExactly(it) } ?: WyomingEvent.NO_PAYLOAD

        return WyomingEvent(type, data, payload)
    }
}

/**
 * Writes [WyomingEvent]s to a socket.
 *
 * `data` goes inline in the header — one line, one write — and only the binary payload
 * is framed by length. Confirmed accepted by both services above; the alternative
 * (`data_length`) is read correctly by [WyomingReader] but never produced here, because
 * one wire format is easier to debug at 2 a.m. than two.
 */
class WyomingWriter(private val out: OutputStream) {

    fun write(type: String, data: JsonObject? = null, payload: ByteArray? = null) {
        val header = buildJsonObject {
            put("type", JsonPrimitive(type))
            if (data != null) put("data", data)
            if (payload != null) put("payload_length", JsonPrimitive(payload.size))
        }
        out.write((header.toString() + "\n").toByteArray(Charsets.UTF_8))
        payload?.let { out.write(it) }
        out.flush()
    }
}
