package com.roam.touch.ha

import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test

/**
 * The Home Assistant REST surface against a real HTTP server.
 *
 * ⚠️ This is as far as verification goes tonight. A MockWebServer proves the URLs, the
 * headers, the request bodies and the decoding are right; it cannot prove his HA accepts
 * them, because that needs a long-lived token only he can mint. Read every green tick
 * here as "the client is correct against the documented contract", not "it works".
 */
class HaApiTest {

    private lateinit var server: MockWebServer
    private lateinit var api: HaApi

    @Before
    fun setUp() {
        server = MockWebServer().also { it.start() }
        api = HaApi(
            HaConfig(
                baseUrl = "http://${server.hostName}:${server.port}",
                token = "test-token",
            )
        )
    }

    @After
    fun tearDown() = server.shutdown()

    private fun json(body: String, code: Int = 200) =
        server.enqueue(MockResponse().setResponseCode(code).setBody(body.trimIndent()))

    // -- shape of the requests ----------------------------------------------

    @Test
    fun `every call carries the bearer token`() = runBlocking {
        json("""{"message":"API running."}""")
        api.ping()
        assertEquals("Bearer test-token", server.takeRequest().getHeader("Authorization"))
    }

    @Test
    fun `the api prefix is added once, and a trailing slash on the base url is harmless`() =
        runBlocking {
            val slashed = HaApi(
                HaConfig(baseUrl = "http://${server.hostName}:${server.port}/", token = "t")
            )
            json("[]")
            slashed.states()
            assertEquals("/api/states", server.takeRequest().path)
        }

    @Test
    fun `a service call posts the entity id and nothing else`() = runBlocking {
        json("[$LIGHT_OFF]")
        api.callService("light", "turn_off", "light.kitchen")
        val req = server.takeRequest()
        assertEquals("POST", req.method)
        assertEquals("/api/services/light/turn_off", req.path)
        assertEquals("""{"entity_id":"light.kitchen"}""", req.body.readUtf8())
        assertTrue(req.getHeader("Content-Type")!!.startsWith("application/json"))
    }

    @Test
    fun `a single entity is read from its own path`() = runBlocking {
        json(HaFx.LIGHT_ON)
        api.state("light.kitchen")
        assertEquals("/api/states/light.kitchen", server.takeRequest().path)
    }

    // -- decoding -----------------------------------------------------------

    @Test
    fun `states decode with their attributes`() = runBlocking {
        json(HaFx.ALL)
        val states = api.states()
        assertEquals(11, states.size)
        val kitchen = states.single { it.entityId == "light.kitchen" }
        assertEquals("on", kitchen.state)
        assertEquals("Kitchen", kitchen.friendlyName)
        assertEquals(128, kitchen.brightness)
    }

    @Test
    fun `an unknown attribute cannot break the panel`() = runBlocking {
        // ★ HA ships new attributes every release. A strict decoder would turn a routine
        // `apt upgrade` on argus into a blank screen on his arm.
        json("""[{"entity_id":"light.k","state":"on","attributes":{"a_new_thing":{"deep":[1,2]}},"invented_top_level":7}]""")
        val states = api.states()
        assertEquals("light.k", states.single().entityId)
    }

    @Test
    fun `a service call returns the states HA actually changed`() = runBlocking {
        json("[$LIGHT_OFF]")
        val changed = api.callService("light", "turn_off", "light.kitchen")
        assertEquals("off", changed.single().state)
    }

    @Test
    fun `a service call that changed nothing decodes as an empty list`() = runBlocking {
        json("[]")
        assertTrue(api.callService("scene", "turn_on", "scene.goodnight").isEmpty())
    }

    // -- failure ------------------------------------------------------------

    @Test
    fun `a rejected token is identified as such, not as a generic failure`() = runBlocking {
        // The one failure he can fix, and the fix is specific. 401 must never be
        // flattened into "unreachable" — that would send him to look at Tailscale.
        json("""{"message":"Invalid access token"}""", code = 401)
        try {
            api.states(); fail("expected 401")
        } catch (e: HaHttpException) {
            assertTrue(e.isUnauthorised)
            assertEquals("token rejected", e.shortReason())
        }
    }

    @Test
    fun `403 is treated as a token problem too`() = runBlocking {
        json("""{"message":"forbidden"}""", code = 403)
        try {
            api.ping(); fail("expected 403")
        } catch (e: HaHttpException) {
            assertTrue(e.isUnauthorised)
        }
    }

    @Test
    fun `a wrong url reads as a wrong url`() = runBlocking {
        json("""{"message":"Not Found"}""", code = 404)
        try {
            api.states(); fail("expected 404")
        } catch (e: HaHttpException) {
            assertEquals("not found — check the URL", e.shortReason())
        }
    }

    @Test
    fun `an html error page from a proxy does not crash the decoder`() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(502).setBody("<html>bad gateway</html>"))
        try {
            api.states(); fail("expected 502")
        } catch (e: HaHttpException) {
            assertEquals(502, e.status)
            assertEquals("home assistant error 502", e.shortReason())
        }
    }

    @Test
    fun `a malformed base url fails immediately instead of throwing deep in okhttp`() =
        runBlocking {
            val bad = HaApi(HaConfig(baseUrl = "argus:8123", token = "t"))
            try {
                bad.states(); fail("expected a config error")
            } catch (e: HaHttpException) {
                assertEquals(0, e.status)
            }
        }

    private companion object {
        const val LIGHT_OFF = """{"entity_id":"light.kitchen","state":"off","attributes":{}}"""
    }
}
