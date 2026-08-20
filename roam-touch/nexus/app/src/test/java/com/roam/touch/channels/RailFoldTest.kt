package com.roam.touch.channels

import androidx.test.core.app.ApplicationProvider
import com.roam.touch.channels.model.Event
import com.roam.touch.channels.net.HubApi
import com.roam.touch.channels.net.HubConfig
import com.roam.touch.channels.net.HubSocket
import com.roam.touch.channels.tts.Speaker
import com.roam.touch.channels.ui.ChannelsViewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * ★★ The rail's fold, and the one thing that makes it a setting rather than a gesture:
 * it is still folded when the process comes back.
 *
 * ⚠️ **Not `rememberSaveable`.** Saved instance state survives a rotation; it does not
 * survive the process being killed, and this is a launcher on a 12-year-old phone — being
 * killed is its normal life. A fold that quietly undid itself overnight would be a
 * preference he has to set again every morning, which is the same class of bug as the read
 * cursors resetting to "12 unread". So it goes where they go: [Settings], on disk.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [29])
class RailFoldTest {

    private val context = ApplicationProvider.getApplicationContext<android.app.Application>()

    @Before
    fun setUp() {
        // The view model writes on `viewModelScope`, which is Main.
        Dispatchers.setMain(Dispatchers.Unconfined)
    }

    @After
    fun tearDown() = Dispatchers.resetMain()

    @Test
    fun `the rail starts expanded, because that is the shape with the list in it`() = runBlocking {
        assertFalse(Settings(context).railCollapsed.first())
    }

    /**
     * ★ The round trip through DataStore, read back through a *different* [Settings] — the
     * point is that nothing about the fold is held in the instance that wrote it.
     */
    @Test
    fun `a folded rail is still folded after the object that folded it is gone`() = runBlocking {
        Settings(context).setRailCollapsed(true)
        assertTrue(Settings(context).railCollapsed.first())

        Settings(context).setRailCollapsed(false)
        assertFalse(Settings(context).railCollapsed.first())
    }

    /** ⚠️ Two keys, one store: folding the rail must not disturb what he has read. */
    @Test
    fun `folding the rail does not touch the read cursors`() = runBlocking {
        val settings = Settings(context)
        settings.saveReadCursors(mapOf("%0" to 41L))
        settings.setRailCollapsed(true)
        assertEquals(mapOf("%0" to 41L), settings.loadReadCursors())
    }

    /**
     * The panel's copy: [ChannelsViewModel] exposes the stored flow as state and writes
     * through to it. Against a fake, so this stays a test of the wiring rather than of
     * DataStore.
     */
    @Test
    fun `the panel reads the stored fold and writes back to it`() {
        val store = FakeRailStore(initial = true)
        // ⚠️ Never connected. The repository is a constructor argument this test has no
        // opinion about; nothing here starts a socket.
        val config = HubConfig("127.0.0.1", 1, "t")
        val vm = ChannelsViewModel(
            repo = HubRepository(HubApi(config), HubSocket(config), FakeCursorStore()),
            speaker = SilentSpeaker(),
            railProvider = { store },
        )

        assertTrue("the panel ignored a rail that was already folded", vm.railCollapsed.value)

        vm.setRailCollapsed(false)
        assertFalse(store.collapsed.value)
        assertFalse(vm.railCollapsed.value)
    }
}

/** Nothing in this file makes a sound. */
private class SilentSpeaker : Speaker {
    override val speakingEventId: StateFlow<Long?> = MutableStateFlow(null)
    override fun play(event: Event, channelLabel: String, body: String) = Unit
    override fun stop() = Unit
}

/** A fold on nothing, so the wiring can be tested without DataStore or a Context. */
private class FakeRailStore(initial: Boolean = false) : RailCollapseStore {
    val collapsed = MutableStateFlow(initial)
    override val railCollapsed = collapsed
    override suspend fun setRailCollapsed(collapsed: Boolean) {
        this.collapsed.value = collapsed
    }
}
