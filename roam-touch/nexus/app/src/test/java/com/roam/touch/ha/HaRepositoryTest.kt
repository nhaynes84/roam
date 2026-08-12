package com.roam.touch.ha

import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/**
 * The states the Home Assistant screen can be in, and how it gets between them.
 *
 * ★ The case that matters most tonight is the first test: with no token, the panel must
 * sit in [HaLink.Unconfigured] and make no network calls at all. It is the state the
 * device will actually be in when he picks it up.
 */
class HaRepositoryTest {

    private lateinit var server: MockWebServer

    @Before
    fun setUp() {
        server = MockWebServer().also { it.start() }
    }

    @After
    fun tearDown() = server.shutdown()

    private fun repo(token: String = "test-token", pinned: List<String> = emptyList()): HaRepository {
        val config = HaConfig(
            baseUrl = "http://${server.hostName}:${server.port}",
            token = token,
            pinned = pinned,
        )
        return HaRepository(HaApi(config), config) { 1_786_600_000_000 }
    }

    private fun json(body: String, code: Int = 200) =
        server.enqueue(MockResponse().setResponseCode(code).setBody(body.trimIndent()))

    // -- no token -----------------------------------------------------------

    @Test
    fun `with no token the panel is unconfigured and calls nobody`() = runBlocking {
        val repo = repo(token = "")
        assertEquals(HaLink.Unconfigured, repo.home.value.link)
        assertFalse(repo.configured)

        repo.refresh()

        assertEquals(HaLink.Unconfigured, repo.home.value.link)
        // ⚠️ Zero requests. A token-less build must not sit there retrying against
        // argus and burning battery on a device worn all day.
        assertEquals(0, server.requestCount)
    }

    @Test
    fun `with no token a tap does nothing but say so`() = runBlocking {
        val repo = repo(token = "")
        assertEquals("no token", repo.act(HaFx.state(HaFx.LIGHT_OFF)))
        assertEquals(0, server.requestCount)
    }

    // -- the happy path -----------------------------------------------------

    @Test
    fun `a refresh turns states into tiles`() = runBlocking {
        val repo = repo()
        json(HaFx.ALL)
        repo.refresh()

        val home = repo.home.value
        assertTrue(home.link.isReady)
        assertEquals(8, home.tiles.size)
        assertEquals("light.desk_lamp", home.tiles.first().entityId)
    }

    @Test
    fun `pinned entities are honoured through the repository`() = runBlocking {
        val repo = repo(pinned = listOf("lock.front_door", "light.kitchen"))
        json(HaFx.ALL)
        repo.refresh()
        assertEquals(
            listOf("lock.front_door", "light.kitchen"),
            repo.home.value.tiles.map { it.entityId },
        )
    }

    @Test
    fun `a tap folds back the state HA reports, not the one we hoped for`() = runBlocking {
        val repo = repo()
        json(HaFx.ALL)
        repo.refresh()
        val kitchen = repo.home.value.tiles.single { it.entityId == "light.kitchen" }
        assertEquals("on", kitchen.state)

        // HA says it went off — and at a different brightness than we would have guessed.
        json("""[{"entity_id":"light.kitchen","state":"off","attributes":{"friendly_name":"Kitchen"}}]""")
        assertNull(repo.act(kitchen))

        val after = repo.home.value.tiles.single { it.entityId == "light.kitchen" }
        assertEquals("off", after.state)
        // Tile order is preserved: a grid that reshuffles under his thumb is unusable.
        assertEquals(8, repo.home.value.tiles.size)
        assertEquals("light.desk_lamp", repo.home.value.tiles.first().entityId)
        assertTrue(repo.home.value.busy.isEmpty())
    }

    @Test
    fun `when HA reports no change the entity is re-read rather than assumed`() = runBlocking {
        val repo = repo()
        json(HaFx.ALL)
        repo.refresh()
        val scene = repo.home.value.tiles.single { it.entityId == "scene.goodnight" }

        json("[]")                                  // POST /api/services/scene/turn_on
        json(HaFx.SCENE)                            // GET  /api/states/scene.goodnight
        assertNull(repo.act(scene))

        assertEquals("/api/states", server.takeRequest().path)                 // the refresh
        assertEquals("/api/services/scene/turn_on", server.takeRequest().path) // the tap
        assertEquals("/api/states/scene.goodnight", server.takeRequest().path) // the re-read
    }

    @Test
    fun `a read-only entity is never sent anywhere`() = runBlocking {
        val repo = repo()
        assertNull(repo.act(HaFx.state(HaFx.SENSOR)))
        assertEquals(0, server.requestCount)
    }

    // -- failure ------------------------------------------------------------

    @Test
    fun `a rejected token is reported as a token problem, not a network one`() = runBlocking {
        val repo = repo()
        json("""{"message":"Invalid access token"}""", code = 401)
        repo.refresh()

        val link = repo.home.value.link as HaLink.Failed
        assertTrue(link.unauthorised)
        assertEquals("token rejected", link.reason)
    }

    @Test
    fun `an unreachable server points at Tailscale, the way the hub banner does`() =
        runBlocking {
            val repo = repo()
            server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AT_START))
            repo.refresh()

            val link = repo.home.value.link as HaLink.Failed
            assertFalse(link.unauthorised)
            assertTrue(link.reason.contains("Tailscale"))
        }

    @Test
    fun `a failed refresh keeps the tiles that were already on screen`() = runBlocking {
        val repo = repo()
        json(HaFx.ALL)
        repo.refresh()
        assertEquals(8, repo.home.value.tiles.size)

        server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AT_START))
        repo.refresh()

        // ★ Stale-but-labelled beats empty: the failure is on the banner, and he can
        // still see what the house looked like a moment ago.
        assertEquals(8, repo.home.value.tiles.size)
        assertTrue(repo.home.value.link is HaLink.Failed)
    }

    @Test
    fun `a failed tap clears busy so the tile is not stuck`() = runBlocking {
        val repo = repo()
        json(HaFx.ALL)
        repo.refresh()
        val kitchen = repo.home.value.tiles.single { it.entityId == "light.kitchen" }

        json("""{"message":"nope"}""", code = 500)
        assertEquals("home assistant error 500", repo.act(kitchen))

        assertTrue(repo.home.value.busy.isEmpty())
        assertEquals("home assistant error 500", repo.home.value.lastError)
    }

    // -- the merge ----------------------------------------------------------

    @Test
    fun `merge replaces by id and ignores ids it does not have`() {
        val tiles = HaFx.states("[${HaFx.LIGHT_ON},${HaFx.SWITCH_ON}]")
        val merged = HaRepository.merge(
            tiles,
            HaFx.states("""[{"entity_id":"light.kitchen","state":"off"},{"entity_id":"light.ghost","state":"on"}]"""),
        )
        assertEquals(2, merged.size)
        assertEquals("off", merged[0].state)
        assertEquals("on", merged[1].state)
    }

    @Test
    fun `merging nothing changes nothing`() {
        val tiles = HaFx.states("[${HaFx.LIGHT_ON}]")
        assertEquals(tiles, HaRepository.merge(tiles, emptyList()))
    }
}
