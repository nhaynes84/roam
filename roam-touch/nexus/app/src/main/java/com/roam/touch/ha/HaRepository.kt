package com.roam.touch.ha

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.io.IOException

/**
 * Whether Home Assistant is usable, and if not, why — in that order of importance.
 *
 * ★ [Unconfigured] is separate from [Failed] on purpose. "You have not made a token yet"
 * and "your token was refused" are different situations with different fixes, and
 * collapsing them into one red banner is how a five-minute job becomes an evening.
 */
sealed interface HaLink {
    /** No token in the build. The only state the panel can be in tonight. */
    data object Unconfigured : HaLink

    data object Loading : HaLink

    data class Ready(val atMs: Long) : HaLink

    data class Failed(val reason: String, val unauthorised: Boolean) : HaLink

    val isReady: Boolean get() = this is Ready
}

/** Everything the Home Assistant screen renders. */
data class HaHome(
    val link: HaLink = HaLink.Loading,
    val tiles: List<HaState> = emptyList(),
    /** Entity ids with a service call in flight — the tile shows it, and ignores taps. */
    val busy: Set<String> = emptySet(),
    val lastError: String? = null,
)

/**
 * The one piece of Home Assistant state in the process.
 *
 * Deliberately dumber than [com.roam.touch.channels.HubRepository]: there is no socket,
 * no cursor and no unread model, because a light does not have history worth keeping on
 * a wrist. Refresh happens when the screen opens, after a tap, and on a slow tick while
 * he is looking at it.
 */
class HaRepository(
    private val api: HaApi,
    private val config: HaConfig,
    private val nowMs: () -> Long = System::currentTimeMillis,
) {
    private val _home = MutableStateFlow(
        HaHome(link = if (config.configured) HaLink.Loading else HaLink.Unconfigured)
    )
    val home: StateFlow<HaHome> = _home.asStateFlow()

    val configured: Boolean get() = config.configured

    /** Pull every state and rebuild the tiles. Safe to call repeatedly. */
    suspend fun refresh() {
        if (!config.configured) {
            _home.value = _home.value.copy(link = HaLink.Unconfigured)
            return
        }
        // Keep the old tiles on screen while refreshing: a panel that blanks on every
        // poll is unreadable while walking, and stale-but-labelled beats empty.
        if (!_home.value.link.isReady) _home.value = _home.value.copy(link = HaLink.Loading)
        try {
            val states = api.states()
            _home.value = HaHome(
                link = HaLink.Ready(nowMs()),
                tiles = HaEntities.tiles(states, config.pinned),
                busy = emptySet(),
            )
        } catch (e: Throwable) {
            _home.value = _home.value.copy(link = failure(e), busy = emptySet())
        }
    }

    /**
     * Act on a tile.
     *
     * The returned states from HA are folded back in rather than assuming the tap
     * worked — see [HaApi.callService]. If HA reports nothing changed (scripts and
     * scenes often do), a follow-up read of that one entity keeps the tile honest.
     */
    suspend fun act(entity: HaState): String? {
        val action = HaEntities.actionFor(entity) ?: return null
        if (!config.configured) return "no token"
        _home.value = _home.value.copy(busy = _home.value.busy + entity.entityId, lastError = null)
        return try {
            val changed = api.callService(action.domain, action.service, entity.entityId)
            val settled = changed.ifEmpty { runCatching { listOf(api.state(entity.entityId)) }.getOrDefault(emptyList()) }
            _home.value = _home.value.copy(
                tiles = merge(_home.value.tiles, settled),
                busy = _home.value.busy - entity.entityId,
                link = HaLink.Ready(nowMs()),
            )
            null
        } catch (e: Throwable) {
            val link = failure(e)
            val reason = (link as? HaLink.Failed)?.reason ?: "failed"
            _home.value = _home.value.copy(
                busy = _home.value.busy - entity.entityId,
                lastError = reason,
                link = link,
            )
            reason
        }
    }

    private fun failure(e: Throwable): HaLink.Failed = when (e) {
        is HaHttpException -> HaLink.Failed(e.shortReason(), e.isUnauthorised)
        // No route, no DNS, tailnet down. Same words the hub banner uses, so the two
        // screens do not describe the same failure two different ways.
        is IOException -> HaLink.Failed("unreachable — check Tailscale", false)
        else -> HaLink.Failed(e.message ?: "failed", false)
    }

    companion object {
        /** Replace by entity id, preserving tile order. Unknown ids are ignored. */
        fun merge(tiles: List<HaState>, updates: List<HaState>): List<HaState> {
            if (updates.isEmpty()) return tiles
            val byId = updates.associateBy { it.entityId }
            return tiles.map { byId[it.entityId] ?: it }
        }
    }
}
