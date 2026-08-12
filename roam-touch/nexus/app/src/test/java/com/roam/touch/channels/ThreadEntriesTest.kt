package com.roam.touch.channels

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * One entry per thing he actually said.
 *
 * The bug, from the live ledger of 2026-08-12 — his first push-to-talk message arrived
 * in the session and the thread drew it twice, a second apart:
 *
 * ```
 * 340  sent     13:43:04  "Not done yet. Ba-ba-ba-ba-ba-ba-wee-wee."   → YOU
 * 341  receipt  13:43:04  "Not done yet. Ba-ba-ba-ba-ba-ba-wee-wee."   → PROMPT
 * ```
 *
 * ⚠️ The other half of this is what must **not** happen: a receipt for a prompt he
 * typed at the keyboard is the only record that message exists.
 */
class ThreadEntriesTest {

    private fun sent(id: Long, text: String = "deploy it") =
        Fx.event(id = id, kind = "sent", body = text)

    private fun receipt(id: Long, text: String = "deploy it", echoOf: Long? = null) =
        Fx.event(id = id, kind = "receipt", body = text, echoOf = echoOf)

    @Test
    fun `a message sent from the app is one entry, not two`() {
        val entries = ThreadEntries.of(
            listOf(sent(340, "Not done yet."), receipt(341, "Not done yet.", echoOf = 340))
        )
        assertEquals(1, entries.size)
        assertEquals(340L, entries.single().id)
        assertEquals("sent", entries.single().event.kind)
    }

    @Test
    fun `the echo becomes the delivered state of the message it confirms`() {
        val entry = ThreadEntries.of(listOf(sent(340), receipt(341, echoOf = 340))).single()
        assertTrue(entry.delivered)
        assertEquals(341L, entry.deliveredBy?.id)
    }

    @Test
    fun `a message not yet echoed is shown, undelivered`() {
        // The half-second between POST /send and the hook firing. He must see what he
        // said immediately; the tick arrives when it arrives.
        val entry = ThreadEntries.of(listOf(sent(340))).single()
        assertFalse(entry.delivered)
        assertNull(entry.deliveredBy)
    }

    @Test
    fun `a prompt he typed at the keyboard is still a message`() {
        // ⚠️ The regression that would make this fix worse than the bug.
        val entries = ThreadEntries.of(listOf(receipt(341, "run the tests")))
        assertEquals(1, entries.size)
        assertEquals("receipt", entries.single().event.kind)
        assertFalse(entries.single().delivered)
    }

    @Test
    fun `an echo whose original is outside the loaded window renders on its own`() {
        // Shown twice is a nuisance; shown zero times is a lie.
        val entries = ThreadEntries.of(listOf(receipt(341, echoOf = 340)))
        assertEquals(listOf(341L), entries.map { it.id })
    }

    @Test
    fun `everything else in the thread is untouched and in order`() {
        val entries = ThreadEntries.of(
            listOf(
                Fx.event(id = 338, kind = "opened", body = "%0"),
                sent(340),
                receipt(341, echoOf = 340),
                Fx.event(id = 342, kind = "outcome", body = "done"),
            )
        )
        assertEquals(listOf(338L, 340L, 342L), entries.map { it.id })
    }

    @Test
    fun `two echoes of one message still collapse into one entry`() {
        // Belt and braces: a hook that fired twice must not resurrect the duplicate.
        val entries = ThreadEntries.of(
            listOf(sent(340), receipt(341, echoOf = 340), receipt(342, echoOf = 340))
        )
        assertEquals(listOf(340L), entries.map { it.id })
        assertEquals(341L, entries.single().deliveredBy?.id)
    }

    @Test
    fun `the thread screen reads entries off the state`() {
        var state = Fx.stateWith(Fx.channel())
        state = ChannelReducer.applyEvent(state, sent(340))
        state = ChannelReducer.applyEvent(state, receipt(341, echoOf = 340))
        assertEquals(2, state.thread("%0").size)   // the ledger keeps both, always
        assertEquals(1, state.entries("%0").size)  // the screen draws one
    }
}
