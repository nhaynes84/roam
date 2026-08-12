package com.roam.touch.channels.controls

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.controlsStore: DataStore<Preferences> by preferencesDataStore("roam-controls")

/** Where headset bindings live, behind an interface so the router can be tested dry. */
interface ControlBindingStore {
    suspend fun profiles(): Map<String, HeadsetProfile>
    suspend fun save(profile: HeadsetProfile)
    suspend fun forget(address: String)
}

/**
 * Bindings on disk, one line per headset.
 *
 * ⚠️ Hand-rolled encoding rather than JSON only because this app has no serialization
 * dependency and this is four fields; [Codec] is pinned by tests both ways, including the
 * cases that would corrupt it — a headset whose name contains a separator, an address
 * full of colons, an empty binding set.
 */
class ControlStore(context: Context) : ControlBindingStore {
    private val store = context.applicationContext.controlsStore

    val flow: Flow<Map<String, HeadsetProfile>> = store.data.map { Codec.decode(it[KEY]) }

    override suspend fun profiles(): Map<String, HeadsetProfile> = flow.first()

    override suspend fun save(profile: HeadsetProfile) {
        store.edit { prefs ->
            val all = Codec.decode(prefs[KEY]).toMutableMap()
            all[profile.address] = profile
            prefs[KEY] = Codec.encode(all)
        }
    }

    override suspend fun forget(address: String) {
        store.edit { prefs ->
            prefs[KEY] = Codec.encode(Codec.decode(prefs[KEY]) - address)
        }
    }

    private companion object {
        val KEY = stringPreferencesKey("headset_profiles")
    }

    /**
     * `address|name|introduced|keyCode~long=ACTION,keyCode~long=ACTION`, newline separated.
     *
     * ⚠️ Addresses contain colons and names contain spaces and dashes, so neither may be
     * a separator. An unparseable line is **dropped, not guessed at**: a wrong binding is
     * worse than a missing one, because a wrong one can open a microphone.
     */
    object Codec {

        fun encode(profiles: Map<String, HeadsetProfile>): String =
            profiles.values.joinToString("\n") { p ->
                val bindings = p.bindings.entries.joinToString(",") { (g, a) ->
                    "${g.keyCode}~${if (g.longPress) 1 else 0}=${a.name}"
                }
                "${p.address}|${p.name.replace('|', ' ')}|${if (p.introduced) 1 else 0}|$bindings"
            }

        fun decode(raw: String?): Map<String, HeadsetProfile> =
            raw.orEmpty().lineSequence().mapNotNull { line ->
                val parts = line.split('|')
                if (parts.size < 4 || parts[0].isBlank()) return@mapNotNull null
                val bindings = parts[3].split(',').mapNotNull { entry ->
                    if (entry.isBlank()) return@mapNotNull null
                    val (gestureRaw, actionRaw) = entry.split('=', limit = 2)
                        .takeIf { it.size == 2 } ?: return@mapNotNull null
                    val (codeRaw, longRaw) = gestureRaw.split('~', limit = 2)
                        .takeIf { it.size == 2 } ?: return@mapNotNull null
                    val code = codeRaw.toIntOrNull() ?: return@mapNotNull null
                    val action = ControlAction.entries.firstOrNull { it.name == actionRaw }
                        ?: return@mapNotNull null
                    HeadsetGesture(code, longRaw == "1") to action
                }.toMap()
                parts[0] to HeadsetProfile(parts[0], parts[1], bindings, parts[2] == "1")
            }.toMap()
    }
}
