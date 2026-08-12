package com.roam.touch.ha

/**
 * ★ Every decision about what a Home Assistant entity *means* lives here, and it is all
 * pure. The screen renders what this returns; the client only moves bytes.
 *
 * This exists because none of it could be verified against the real server tonight — no
 * token — so the part that can be tested exhaustively is separated from the part that
 * cannot be tested at all until he creates one.
 */
object HaEntities {

    const val ON = "on"
    const val OFF = "off"
    const val UNKNOWN = "unknown"
    const val UNAVAILABLE = "unavailable"

    /**
     * Domains that get a tile, in the order a smart-home controller wants them.
     *
     * ⚠️ Deliberately short. A default HA install exposes hundreds of entities — device
     * trackers, update sensors, sun position — and putting all of them on a forearm
     * makes the panel useless. Anything missing here is one config line away.
     */
    val ACTIONABLE = listOf("light", "switch", "fan", "cover", "lock", "input_boolean", "scene", "script")

    /** Read-only domains worth showing when he pins them explicitly. Never auto-picked. */
    val READABLE = listOf("sensor", "binary_sensor", "climate", "media_player", "person")

    /** What a tap does, or null when the entity is read-only. */
    data class Action(val domain: String, val service: String)

    fun domainOf(entityId: String): String = entityId.substringBefore('.', "")

    fun isOn(state: String): Boolean = state.equals(ON, ignoreCase = true)

    fun isUnavailable(state: String): Boolean =
        state.equals(UNAVAILABLE, ignoreCase = true) || state.equals(UNKNOWN, ignoreCase = true)

    /**
     * The service call for a tap on [entity].
     *
     * ⚠️ `homeassistant.toggle` would cover most of this in one line and is wrong for
     * two domains: a cover toggles between `open`/`close`, and a lock between
     * `lock`/`unlock`. Getting those two generic would either no-op or, worse, unlock a
     * door because the generic toggle read `locked` as "on".
     */
    fun actionFor(entity: HaState): Action? {
        val on = isOn(entity.state)
        return when (val d = entity.domain) {
            "light", "switch", "fan", "input_boolean" ->
                Action(d, if (on) "turn_off" else "turn_on")

            // Scenes and scripts are momentary: there is nothing to turn off.
            "scene", "script" -> Action(d, "turn_on")

            "cover" -> Action(d, if (entity.state.equals("open", true)) "close_cover" else "open_cover")

            // ⚠️ A lock's "on" is `locked`. Tapping an unlocked lock locks it; tapping a
            // locked one unlocks it — the same direction as every other tile.
            "lock" -> Action(d, if (entity.state.equals("locked", true)) "unlock" else "lock")

            else -> null
        }
    }

    /** True when a tap on this entity does something. */
    fun isActionable(entity: HaState): Boolean =
        actionFor(entity) != null && !isUnavailable(entity.state)

    /**
     * The line under the label. Short, because it is read while walking.
     *
     * Lights carry their brightness as a percentage — "on" and "on at 4%" are different
     * facts and the second one explains a dark room.
     */
    fun stateText(entity: HaState): String {
        if (isUnavailable(entity.state)) return entity.state.lowercase()
        return when (entity.domain) {
            "light" -> {
                val pct = entity.brightness?.let { (it * 100f / 255f).toInt().coerceIn(1, 100) }
                if (isOn(entity.state) && pct != null) "on · $pct%" else entity.state.lowercase()
            }

            "scene", "script" -> "tap to run"
            "sensor", "binary_sensor" ->
                entity.unit?.let { "${entity.state} $it" } ?: entity.state.lowercase()

            else -> entity.state.lowercase()
        }
    }

    /**
     * Which entities become tiles.
     *
     * [pinned] is the owner's explicit list (`roam.ha.entities`) and wins outright,
     * including its order and including read-only domains — if he pins a temperature
     * sensor he wants to see the temperature. With nothing pinned, fall back to the
     * actionable domains, ordered by [ACTIONABLE] then by name, capped at [limit] so a
     * fresh HA install cannot bury the panel.
     */
    fun tiles(states: List<HaState>, pinned: List<String> = emptyList(), limit: Int = 12): List<HaState> {
        if (pinned.isNotEmpty()) {
            val byId = states.associateBy { it.entityId }
            return pinned.mapNotNull { byId[it.trim()] }
        }
        return states
            .filter { it.domain in ACTIONABLE }
            .sortedWith(
                compareBy(
                    { ACTIONABLE.indexOf(it.domain) },
                    { it.friendlyName.lowercase() },
                )
            )
            .take(limit)
    }

    /** Split a config string like `light.kitchen, lock.front` into ids. */
    fun parsePinned(raw: String?): List<String> =
        raw.orEmpty().split(',', ';', '\n')
            .map { it.trim() }
            .filter { it.isNotEmpty() && it.contains('.') }
}
