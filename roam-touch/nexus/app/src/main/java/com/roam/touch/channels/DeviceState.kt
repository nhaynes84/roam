package com.roam.touch.channels

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.PowerManager
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ProcessLifecycleOwner
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Charge state of a device that is worn, not docked. */
data class BatteryState(
    val percent: Int = -1,
    val charging: Boolean = false,
    val full: Boolean = false,
) {
    val known: Boolean get() = percent in 0..100

    /** Below this the wearer should be told, not left to notice. */
    val low: Boolean get() = known && !charging && percent <= LOW_PERCENT

    companion object {
        const val LOW_PERCENT = 20
    }
}

/**
 * The two facts the TTS gate needs, plus the one the wearer needs.
 *
 * "Is he looking at it" is answered from two independent signals because either alone
 * lies: the app can be resumed under a dark screen in a pocket, and the screen can be
 * on with Settings in front of it.
 */
class DeviceStateMonitor(private val context: Context) {

    private val _screenOn = MutableStateFlow(true)
    val screenOn: StateFlow<Boolean> = _screenOn.asStateFlow()

    private val _appForeground = MutableStateFlow(false)
    val appForeground: StateFlow<Boolean> = _appForeground.asStateFlow()

    private val _battery = MutableStateFlow(BatteryState())
    val battery: StateFlow<BatteryState> = _battery.asStateFlow()

    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(ctx: Context?, intent: Intent?) {
            when (intent?.action) {
                Intent.ACTION_SCREEN_ON -> _screenOn.value = true
                Intent.ACTION_SCREEN_OFF -> _screenOn.value = false
                Intent.ACTION_BATTERY_CHANGED -> _battery.value = intent.toBatteryState()
            }
        }
    }

    private val lifecycleObserver = object : DefaultLifecycleObserver {
        override fun onStart(owner: LifecycleOwner) {
            _appForeground.value = true
        }

        override fun onStop(owner: LifecycleOwner) {
            _appForeground.value = false
        }
    }

    fun start() {
        val pm = context.getSystemService(Context.POWER_SERVICE) as? PowerManager
        _screenOn.value = pm?.isInteractive ?: true

        context.registerReceiver(receiver, IntentFilter().apply {
            addAction(Intent.ACTION_SCREEN_ON)
            addAction(Intent.ACTION_SCREEN_OFF)
        })
        // Sticky: this returns the current charge immediately, no waiting for a change.
        context.registerReceiver(receiver, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
            ?.let { _battery.value = it.toBatteryState() }

        ProcessLifecycleOwner.get().lifecycle.addObserver(lifecycleObserver)
    }

    fun stop() {
        runCatching { context.unregisterReceiver(receiver) }
        ProcessLifecycleOwner.get().lifecycle.removeObserver(lifecycleObserver)
    }

    private fun Intent.toBatteryState(): BatteryState {
        val level = getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
        val scale = getIntExtra(BatteryManager.EXTRA_SCALE, -1)
        val status = getIntExtra(BatteryManager.EXTRA_STATUS, -1)
        val percent = if (level >= 0 && scale > 0) level * 100 / scale else -1
        return BatteryState(
            percent = percent,
            charging = status == BatteryManager.BATTERY_STATUS_CHARGING ||
                    status == BatteryManager.BATTERY_STATUS_FULL,
            full = status == BatteryManager.BATTERY_STATUS_FULL,
        )
    }
}
