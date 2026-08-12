package com.roam.touch.channels

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore("roam-channels")

/**
 * What the repository actually needs from settings.
 *
 * Split out so the connection logic can be tested against a fake instead of dragging
 * DataStore — and therefore a Context, and therefore Robolectric — into every test of
 * the reconnect path. The repository has no business knowing where the cursors live.
 */
interface ReadCursorStore {
    suspend fun loadReadCursors(): Map<String, Long>
    suspend fun saveReadCursors(cursors: Map<String, Long>)
}

/**
 * The two things that must survive a kill: how loud he wants it, and what he has
 * already read.
 *
 * Read state is persisted because Android will kill this process — routinely, this is a
 * normal app under doze — and a badge that resets to "12 unread" every time the launcher
 * is rebuilt trains him to ignore badges, which breaks the one job the queue has.
 */
class Settings(context: Context) : ReadCursorStore {
    private val store = context.applicationContext.dataStore

    /** pane id -> highest event id read, flattened to `%0=41;%1=7`. */
    val readCursors: Flow<Map<String, Long>> = store.data.map { decode(it[KEY_READ]) }

    override suspend fun loadReadCursors(): Map<String, Long> = readCursors.first()

    override suspend fun saveReadCursors(cursors: Map<String, Long>) {
        store.edit { it[KEY_READ] = encode(cursors) }
    }

    companion object {
        private val KEY_READ = stringPreferencesKey("read_cursors")

        fun encode(cursors: Map<String, Long>): String =
            cursors.entries.joinToString(";") { "${it.key}=${it.value}" }

        fun decode(raw: String?): Map<String, Long> =
            raw.orEmpty().split(";").mapNotNull { entry ->
                val i = entry.lastIndexOf('=')
                if (i <= 0) return@mapNotNull null
                val id = entry.substring(i + 1).toLongOrNull() ?: return@mapNotNull null
                entry.substring(0, i) to id
            }.toMap()
    }
}
