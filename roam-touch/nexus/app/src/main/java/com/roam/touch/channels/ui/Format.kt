package com.roam.touch.channels.ui

import java.util.Locale
import java.util.concurrent.TimeUnit

/**
 * Durations for a glance, not a report. Pure, so the awkward boundaries (59 s, 90 s,
 * 24 h) are unit tests rather than something noticed on a wrist a week later.
 */
object Format {

    /** "2s", "45s", "4m", "1h12m", "3d". Never wider than six characters. */
    fun duration(ms: Long): String {
        val s = TimeUnit.MILLISECONDS.toSeconds(ms.coerceAtLeast(0))
        if (s < 60) return "${s}s"
        val m = s / 60
        if (m < 60) return "${m}m"
        val h = m / 60
        if (h < 24) {
            val rem = m % 60
            return if (rem == 0L) "${h}h" else "${h}h${rem}m"
        }
        val d = h / 24
        return "${d}d"
    }

    /** "active 2s ago" reads better than a timestamp when you are walking. */
    fun ago(ms: Long): String = "${duration(ms)} ago"

    /** Clock time, for the one place a thread needs an absolute anchor. */
    fun clock(epochMs: Long): String {
        val cal = java.util.Calendar.getInstance()
        cal.timeInMillis = epochMs
        return String.format(
            Locale.US, "%02d:%02d",
            cal.get(java.util.Calendar.HOUR_OF_DAY),
            cal.get(java.util.Calendar.MINUTE),
        )
    }

    /** "4.1k chars" — how much is hiding behind a summary. */
    fun chars(n: Int): String = when {
        n < 1000 -> "$n chars"
        else -> String.format(Locale.US, "%.1fk chars", n / 1000.0)
    }
}
