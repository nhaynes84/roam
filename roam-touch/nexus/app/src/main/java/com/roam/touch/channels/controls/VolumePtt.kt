package com.roam.touch.channels.controls

/**
 * ★★ The volume-down key, doing two jobs: **tap for volume, hold to talk.**
 *
 * ⚠️⚠️ This exists because it is the only push-to-talk control on this device that
 * actually works, and it took a long detour to find that out:
 *
 * - **The earbud cannot hold.** Its firmware collapses a gesture into one discrete event
 *   and sends that; measured on the owner's Pixel Buds, every press arrives as a DOWN and
 *   an UP 2–5 ms apart however long he holds it. There is no held state on the wire.
 * - **A wired inline button cannot hold either**, and this one is counter-intuitive: on a
 *   TRRS headset the microphone and the button share one conductor, and the button *is* a
 *   short across it. Hold the button and you have shorted out the microphone — so a wired
 *   hook gives a tap and can never give a hold with audio behind it.
 * - **The phone's own rocker is a real switch on a real GPIO.** It reports a true
 *   ACTION_DOWN, repeat counts while held, and a true ACTION_UP. It is the only input on
 *   this device that can express "while I am holding this."
 *
 * ⚠️ And it must not cost him volume — *"then how do i adjust volume, lol"* — so the tap
 * still adjusts, and the app performs that adjustment itself rather than passing the key
 * back, because by the time it knows the press was a tap the moment to pass it has gone.
 *
 * ★ The consequence, stated plainly so nobody "fixes" it later: **volume changes on
 * release, not on press.** Until he lets go there is no way to know which gesture he
 * meant. One step, one beat late, and invisible on the PTT side.
 */
enum class VolumeGesture {
    /** Held past [VolumePtt.HOLD_REPEATS] — start talking. */
    StartTalking,

    /** Let go while talking — stop, and go to the confirm step. */
    StopTalking,

    /** A tap: one step of volume down, performed by us. */
    VolumeDown,

    /** Nothing to do — the down edge before we know which gesture it is. */
    Nothing,
}

/**
 * Pure, so the decision is testable without a device. One instance per key, holding only
 * whether this particular press has already become a hold.
 */
class VolumePtt {

    private var talking = false

    /**
     * @param repeat Android's repeat count on the down edge; > 0 means the key is held.
     * @param micOpen whether a recording is actually running, read from [Ptt], not
     *   inferred — the same rule as everywhere else in this file's history.
     */
    fun onDown(repeat: Int, micOpen: Boolean): VolumeGesture {
        if (repeat < HOLD_REPEATS) return VolumeGesture.Nothing
        if (talking || micOpen) return VolumeGesture.Nothing
        talking = true
        return VolumeGesture.StartTalking
    }

    fun onUp(micOpen: Boolean): VolumeGesture {
        val wasTalking = talking
        talking = false
        // ⚠️ `micOpen` as well as `wasTalking`: a recording started some other way (the
        // on-screen mic, a headset tap) must still be closable with this key. A control
        // that can only stop what it personally started is half a control.
        return if (wasTalking || micOpen) VolumeGesture.StopTalking else VolumeGesture.VolumeDown
    }

    /** ⚠️ The key was taken away mid-press — treat it as a release, never as still held. */
    fun reset() {
        talking = false
    }

    companion object {
        /**
         * ★ One repeat, not a millisecond timer. Android's own long-press threshold is
         * what produces the first repeat, so this inherits the platform's idea of a hold
         * and stays consistent with every other button he uses.
         */
        const val HOLD_REPEATS = 1
    }
}
