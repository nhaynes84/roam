package com.roam.touch.channels.ui

import com.roam.touch.apps.AppShelf
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The two string decisions behind the in-app hub browser: which request carries the
 * token, and which URL is allowed to load at all.
 *
 * ★ Both were bugs. The Files tile answered *"bearer token required"* because an
 * `ACTION_VIEW` at Chrome cannot carry a header, and the only fix available to an external
 * browser — `?token=` in the URL — writes a token that opens every hub endpoint into
 * another app's history. These are plain JVM tests because that is where a rule about a
 * secret belongs: not behind a `WebViewClient` that only a device can run.
 */
class HubBrowserTest {

    private val base = "http://100.67.237.109:8787"
    private val token = "s3cr3t-token"

    // ---- the token -------------------------------------------------------------------

    @Test
    fun `the token travels as an Authorization header`() {
        assertEquals(
            mapOf("Authorization" to "Bearer $token"),
            HubBrowser.authHeaders(token),
        )
    }

    @Test
    fun `the token is never put in the url`() {
        // ★★ The rule the whole screen exists for. If a future change starts appending
        // `?token=`, the header map is the only place it could come from, and this fails.
        val headers = HubBrowser.authHeaders(token)
        assertEquals(1, headers.size)
        assertTrue(headers.values.single().endsWith(token))
        assertFalse(headers.keys.single().contains("?"))
    }

    @Test
    fun `a missing token sends no header at all, rather than an empty bearer`() {
        // ⚠️ `Bearer ` with nothing after it reads as a malformed request; no header at
        // all gets the hub's own 401 page — "bearer token required" — which is the
        // diagnosable answer. Same choice build.gradle makes when roam.hub.token is unset.
        assertTrue(HubBrowser.authHeaders("").isEmpty())
        assertTrue(HubBrowser.authHeaders("   ").isEmpty())
    }

    // ---- what may load ---------------------------------------------------------------

    @Test
    fun `every shelf tile is recognised as a hub url`() {
        // ★ The tiles and the browser must agree, or a tile opens a screen that then
        // refuses to load it.
        AppShelf.build(emptyList())
            .filter { it.kind == com.roam.touch.apps.TileKind.HUB }
            .forEach {
                assertTrue("not a hub url: ${it.id}", HubBrowser.isHubUrl(it.id, AppShelf.HUB_BASE))
            }
    }

    @Test
    fun `the hub's own pages load`() {
        assertTrue(HubBrowser.isHubUrl(base, base))
        assertTrue(HubBrowser.isHubUrl("$base/browse", base))
        assertTrue(HubBrowser.isHubUrl("$base/browse#CAD", base))
        assertTrue(HubBrowser.isHubUrl("$base/browse#CAD/estack", base))
        // The links browse.html emits for a file and for the STL viewer. They carry their
        // own `?token=` — that is the hub's design for things a browser fetches, and it is
        // why no header has to be re-attached to a link click.
        assertTrue(HubBrowser.isHubUrl("$base/files/raw?token=x&path=CAD/a.stl", base))
        assertTrue(HubBrowser.isHubUrl("$base/view/stl?token=x&path=CAD/a.stl", base))
        assertTrue(HubBrowser.isHubUrl("$base/web/vendor/three.js", base))
    }

    @Test
    fun `a host that merely starts with the hub's address is not the hub`() {
        // ⚠️⚠️ The suffix check, and the reason it exists. A bare startsWith would hand a
        // page carrying the token to an entirely different server.
        assertFalse(HubBrowser.isHubUrl("http://100.67.237.109:8787.example.org/", base))
        assertFalse(HubBrowser.isHubUrl("http://100.67.237.109:87878/browse", base))
        assertFalse(HubBrowser.isHubUrl("http://100.67.237.109:8787evil/browse", base))
    }

    @Test
    fun `anything off the hub is refused`() {
        assertFalse(HubBrowser.isHubUrl("https://example.org", base))
        assertFalse(HubBrowser.isHubUrl("http://100.67.114.94:8123/", base))
        // A different scheme to the same host is a different origin and stays out.
        assertFalse(HubBrowser.isHubUrl("https://100.67.237.109:8787/browse", base))
        // The classic WebView escapes.
        assertFalse(HubBrowser.isHubUrl("file:///data/data/com.roam.touch/", base))
        assertFalse(HubBrowser.isHubUrl("intent://evil#Intent;end", base))
        assertFalse(HubBrowser.isHubUrl("javascript:alert(1)", base))
        assertFalse(HubBrowser.isHubUrl("", base))
    }

    // ---- the 401 retry ---------------------------------------------------------------

    @Test
    fun `a main-frame 401 on a hub page is retried with the token`() {
        // ⚠️ The gap a single loadUrl(url, headers) leaves: headers are not replayed for a
        // *back* navigation, and the hub serves `Cache-Control: no-store`, so pressing
        // Back out of the STL viewer refetches /browse bare — the exact "bearer token
        // required" this screen exists to remove.
        assertTrue(
            HubBrowser.shouldRetryWithAuth(401, true, "$base/browse", base, alreadyTried = false)
        )
    }

    @Test
    fun `it retries once and then lets the 401 stand`() {
        // ★ A token the hub genuinely rejects must show its 401, not spin forever on the
        // one screen that can leave the home screen.
        assertFalse(
            HubBrowser.shouldRetryWithAuth(401, true, "$base/browse", base, alreadyTried = true)
        )
    }

    @Test
    fun `nothing else is retried`() {
        // Not another status — a 404 or a 500 is the hub's answer and he should read it.
        assertFalse(
            HubBrowser.shouldRetryWithAuth(404, true, "$base/browse", base, alreadyTried = false)
        )
        assertFalse(
            HubBrowser.shouldRetryWithAuth(500, true, "$base/browse", base, alreadyTried = false)
        )
        // Not a subresource: the page's own fetches carry the token themselves, and the
        // vendored three.js under /web/vendor is unauthenticated on purpose.
        assertFalse(
            HubBrowser.shouldRetryWithAuth(401, false, "$base/files", base, alreadyTried = false)
        )
        // ★★ And never off the hub. Retrying there would send the hub's token to whatever
        // answered 401 — which is precisely how a token gets stolen by a 401 challenge.
        assertFalse(
            HubBrowser.shouldRetryWithAuth(401, true, "https://evil.example/", base, false)
        )
    }
}
