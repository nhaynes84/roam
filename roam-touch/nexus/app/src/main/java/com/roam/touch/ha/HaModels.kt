package com.roam.touch.ha

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull

/**
 * Home Assistant's REST surface, decoded leniently.
 *
 * ⚠️ `ignoreUnknownKeys` is not optional here. `attributes` is a free-form bag that
 * differs per integration and grows with every HA release; a strict decoder would turn
 * a routine HA upgrade into a blank panel on his arm.
 */
@OptIn(kotlinx.serialization.ExperimentalSerializationApi::class)
val HaJson: Json = Json {
    ignoreUnknownKeys = true
    isLenient = true
    explicitNulls = false
    coerceInputValues = true
}

/**
 * One entity as `GET /api/states` returns it.
 *
 * HA models *everything* as an entity with a string `state`, so this single type covers
 * lights, locks, sensors and scripts alike. The meaning of the string is the domain's
 * business — see [HaEntities].
 */
@Serializable
data class HaState(
    @SerialName("entity_id") val entityId: String,
    val state: String = HaEntities.UNKNOWN,
    val attributes: JsonObject = JsonObject(emptyMap()),
    @SerialName("last_changed") val lastChanged: String? = null,
) {
    /** The domain, i.e. everything before the dot: `light.kitchen` -> `light`. */
    val domain: String get() = entityId.substringBefore('.', "")

    private fun attr(name: String): JsonPrimitive? = attributes[name] as? JsonPrimitive

    /** What HA calls it, falling back to a de-slugged object id. */
    val friendlyName: String
        get() = attr("friendly_name")?.contentOrNull?.takeIf { it.isNotBlank() }
            ?: entityId.substringAfter('.', entityId).replace('_', ' ')
                .split(' ').joinToString(" ") { w ->
                    w.replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
                }

    /** e.g. `°C`, `%`. Present on sensors, absent everywhere else. */
    val unit: String? get() = attr("unit_of_measurement")?.contentOrNull

    /** 0..255 for lights that support it; null when off or unsupported. */
    val brightness: Int? get() = attr("brightness")?.doubleOrNull?.toInt()
}

/**
 * `GET /api/` — the cheapest proof that both the URL and the token are right.
 *
 * `POST /api/services/…` needs no type of its own: it answers with a bare JSON array of
 * the states it changed, decoded straight into `List<HaState>`.
 */
@Serializable
data class HaPing(val message: String = "")
