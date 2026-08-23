package com.roam.nexus

import android.graphics.BitmapFactory
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.URL

/**
 * Bytes for images posted into channels.
 *
 * ★ Safe to cache forever and never invalidate: the hub's ids are the sha256 of the
 * bytes, so one id can only ever mean one image. That is the whole reason the store is
 * content-addressed.
 */
object ImageCache {
    private val memory = mutableMapOf<String, ImageBitmap>()

    suspend fun load(id: String): ImageBitmap? = withContext(Dispatchers.IO) {
        memory[id]?.let { return@withContext it }
        runCatching {
            val url = URL("${BuildConfig.HUB_HOST.let { "http://$it:${BuildConfig.HUB_PORT}" }}/images/$id")
            val conn = (url.openConnection() as HttpURLConnection).apply {
                setRequestProperty("Authorization", "Bearer ${BuildConfig.HUB_TOKEN}")
                connectTimeout = 10_000
                readTimeout = 30_000
            }
            conn.inputStream.use { it.readBytes() }
        }.getOrNull()?.let { bytes ->
            BitmapFactory.decodeByteArray(bytes, 0, bytes.size)?.asImageBitmap()
                ?.also { memory[id] = it }
        }
    }
}
