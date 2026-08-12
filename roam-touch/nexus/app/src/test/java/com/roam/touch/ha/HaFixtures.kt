package com.roam.touch.ha

/**
 * Recorded Home Assistant payloads.
 *
 * ⚠️ These are the documented `GET /api/states` shapes, not invented ones — attribute
 * bags trimmed to what the panel reads, keys and value types left exactly as HA emits
 * them (`brightness` an int 0..255, `state` always a string, `unit_of_measurement`
 * present only on sensors). They stand in for the live server, which could not be
 * called tonight: minting a long-lived token needs the owner's password.
 *
 * ★ When the real server is first reached, re-capture this from it. A fixture that
 * drifts from the wire is worse than none — see the hub's `Fx`.
 */
object HaFx {

    fun state(json: String): HaState = HaJson.decodeFromString(json)

    fun states(json: String): List<HaState> = HaJson.decodeFromString(json)

    const val LIGHT_ON = """
        {"entity_id":"light.kitchen","state":"on",
         "attributes":{"friendly_name":"Kitchen","brightness":128,
                       "supported_color_modes":["brightness"]},
         "last_changed":"2026-08-12T04:02:11.101Z"}
    """

    const val LIGHT_OFF = """
        {"entity_id":"light.desk_lamp","state":"off",
         "attributes":{"friendly_name":"Desk Lamp"},
         "last_changed":"2026-08-11T22:40:00.000Z"}
    """

    const val SWITCH_ON = """
        {"entity_id":"switch.roaster","state":"on",
         "attributes":{"friendly_name":"Roaster"}}
    """

    const val LOCK_LOCKED = """
        {"entity_id":"lock.front_door","state":"locked",
         "attributes":{"friendly_name":"Front Door"}}
    """

    const val COVER_OPEN = """
        {"entity_id":"cover.garage","state":"open",
         "attributes":{"friendly_name":"Garage","device_class":"garage"}}
    """

    const val SCENE = """
        {"entity_id":"scene.goodnight","state":"2026-08-11T23:00:00.000Z",
         "attributes":{"friendly_name":"Goodnight"}}
    """

    /** No `friendly_name` at all — the de-slug path. */
    const val UNNAMED_FAN = """
        {"entity_id":"fan.office_ceiling","state":"off","attributes":{}}
    """

    const val UNAVAILABLE_LIGHT = """
        {"entity_id":"light.porch","state":"unavailable",
         "attributes":{"friendly_name":"Porch","restored":true}}
    """

    const val SENSOR = """
        {"entity_id":"sensor.office_temperature","state":"21.4",
         "attributes":{"friendly_name":"Office Temperature",
                       "unit_of_measurement":"°C","device_class":"temperature"}}
    """

    /** Noise a real install is full of and the panel must not show by default. */
    const val NOISE = """
        {"entity_id":"device_tracker.pixel","state":"home","attributes":{}}
    """

    const val SUN = """
        {"entity_id":"sun.sun","state":"below_horizon",
         "attributes":{"friendly_name":"Sun","elevation":-31.2}}
    """

    /** A whole `GET /api/states` body, in the order HA returns it (alphabetical-ish). */
    val ALL: String = "[$COVER_OPEN,$NOISE,$UNNAMED_FAN,$LIGHT_ON,$LIGHT_OFF," +
        "$UNAVAILABLE_LIGHT,$LOCK_LOCKED,$SCENE,$SENSOR,$SUN,$SWITCH_ON]"
}
