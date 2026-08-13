package com.roam.touch.channels.controls

import android.view.KeyEvent

/**
 * ★★ The headset as a **control surface**, not just a microphone.
 *
 * The owner's framing: *"my pixel earbuds have smart / gesture / tap controls, we could
 * easily tie those to PTT or channel switching so i could even control this without being
 * directly at it, a proxy for my proxy."* The arm display becomes output and confirmation;
 * the thing already in his ear becomes the input.
 *
 * ⚠️⚠️ **There is no standard gesture set, so nothing here may assume one.** Measured
 * against his own kit: the Pixel Buds bind long-press to Assistant, his Jabras bind it to
 * volume, and **the Jabras fire an independent action set per ear**. The event a gesture
 * produces is a property of the *headset*, not of Android — so bindings are captured from
 * what actually arrives, stored per device, and editable. Anything hard-coded here would
 * be right for one headset and silently wrong for the next.
 */

/**
 * One gesture, as the phone saw it.
 *
 * ★ Deliberately just a key code and whether it was held. Headset firmware already
 * collapses "two taps" into `MEDIA_NEXT` and "three taps" into `MEDIA_PREVIOUS` before
 * anything reaches Android, so trying to count taps here would be inventing a layer the
 * hardware has already decided.
 */
data class HeadsetGesture(val keyCode: Int, val longPress: Boolean = false) {

    /** What to call it on screen, for a man who is not reading key codes. */
    val label: String
        get() = (KEY_NAMES[keyCode] ?: "key $keyCode") + if (longPress) ", held" else ""

    companion object {

        /**
         * ★★ One logical tap, whatever Android decided to call it this time.
         *
         * ⚠️⚠️ **The keycode a headset tap arrives as is not a property of the headset.**
         * `MediaSessionService` rewrites `MEDIA_PLAY_PAUSE` into `MEDIA_PLAY` or
         * `MEDIA_PAUSE` according to the playback state *our own session* reports, before
         * it ever reaches us. So the same physical tap on the same earbud arrives as 85
         * when the session is idle and 127 when it is playing.
         *
         * That broke it in the field, and silently. The owner bound a tap while the
         * session was idle, so `85~0=PUSH_TO_TALK` went into the store; by the time he
         * used it the session was reporting `state=3` and every tap arrived as 127,
         * matched nothing, and passed through. Owner: *"earbud tap set to ptt but it
         * doesn't work."* Both his headsets had the same binding and neither worked.
         *
         * Canonicalising at the boundary means a gesture learned in one playback state
         * still matches in the other — and `HEADSETHOOK`, which older wired headsets send
         * for the same press, folds in with it.
         */
        fun canonical(keyCode: Int): Int = when (keyCode) {
            KeyEvent.KEYCODE_MEDIA_PLAY,
            KeyEvent.KEYCODE_MEDIA_PAUSE,
            KeyEvent.KEYCODE_HEADSETHOOK -> KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE
            else -> keyCode
        }

        private val KEY_NAMES = mapOf(
            KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE to "tap",
            KeyEvent.KEYCODE_HEADSETHOOK to "tap (hook)",
            KeyEvent.KEYCODE_MEDIA_PLAY to "play",
            KeyEvent.KEYCODE_MEDIA_PAUSE to "pause",
            KeyEvent.KEYCODE_MEDIA_NEXT to "next / double tap",
            KeyEvent.KEYCODE_MEDIA_PREVIOUS to "previous / triple tap",
            KeyEvent.KEYCODE_MEDIA_STOP to "stop",
            KeyEvent.KEYCODE_VOICE_ASSIST to "assistant",
            KeyEvent.KEYCODE_VOLUME_UP to "volume up",
            KeyEvent.KEYCODE_VOLUME_DOWN to "volume down",
        )

        /**
         * ⚠️ Volume is bindable but special: capturing it means taking it away from the
         * system, so it is only ever armed for a gesture he has explicitly bound.
         */
        val VOLUME_KEYS = setOf(KeyEvent.KEYCODE_VOLUME_UP, KeyEvent.KEYCODE_VOLUME_DOWN)
    }
}

/** What a gesture can be made to do. Short list on purpose — this is a worn device. */
enum class ControlAction(val label: String) {
    /**
     * ⚠️⚠️ A **toggle**, unlike the on-screen button, because a headset tap has no "hold".
     * Start talking, tap again to send. The sixty-second cap in `Ptt` is what stops a
     * missed second tap from leaving a microphone open, and the panel plus the buzz on
     * entering LISTENING are what stop it from being open *unnoticed*.
     */
    PUSH_TO_TALK("push to talk"),

    /**
     * ★★ **Send the transcript, without touching the phone.**
     *
     * Owner: *"I need a push-to-talk mapping option for send. So when I'm using earbuds,
     * I don't have to click the phone. I could just do, like, double or triple tap."*
     * Bind it to a double tap and the whole loop — talk, stop, send — happens on the
     * earbud, which is the entire point of a device you are not sitting in front of.
     *
     * ⚠️ Does nothing unless there is a transcript waiting. It is the confirm step, not a
     * shortcut past it: the words and their destination are still shown and still have to
     * be agreed to, they just get agreed to from an earbud.
     */
    SEND("send"),
    NEXT_CHANNEL("next channel"),
    PREVIOUS_CHANNEL("previous channel"),
    CANCEL("cancel"),
}

/**
 * Everything known about one headset.
 *
 * ⚠️ Keyed on the Bluetooth address, so swapping earbuds cannot silently rebind PTT to
 * whatever the other set happens to send.
 */
data class HeadsetProfile(
    val address: String,
    val name: String,
    val bindings: Map<HeadsetGesture, ControlAction> = emptyMap(),
    /**
     * True once he has seen this headset's setup once — whether he mapped anything or
     * waved it away. A known headset connecting is silent.
     */
    val introduced: Boolean = false,
) {
    /**
     * ★★ Bind [gesture] to [action] — and it is a **move**, in both directions.
     *
     * ⚠️⚠️ One gesture does one thing, and one action lives on one gesture. The map can
     * express neither of those wrong states usefully, and both of them bit:
     *
     * - Binding onto an occupied gesture **silently displaced** what was there. The owner
     *   taught SEND to his double tap; the stray play/pause behind it (see [ControlRouter])
     *   meant the tap was what actually got captured, and the tap was push-to-talk.
     *   Owner: *"it unset my push to talk, so the mappings are a little buggy."* The echo
     *   fix stops that happening by accident, but he can still do it deliberately, so the
     *   displacement is now **returned** and said out loud rather than being a silence.
     * - Moving an action to a new gesture used to leave the old gesture bound to it as
     *   well, so two gestures fired one action while the screen — [boundTo] takes the
     *   first match — could only ever show one of them.
     */
    fun bind(gesture: HeadsetGesture, action: ControlAction) =
        copy(bindings = bindings.filterValues { it != action } + (gesture to action))

    /**
     * ⚠️ What binding [gesture] to [action] would take away from him, if anything. Null
     * when the gesture is free, or already does this. See [bind].
     */
    fun displacedBy(gesture: HeadsetGesture, action: ControlAction): ControlAction? =
        bindings[gesture]?.takeIf { it != action }

    /** Release a gesture back to the headset and the system. */
    fun unbind(gesture: HeadsetGesture) = copy(bindings = bindings - gesture)

    fun boundTo(action: ControlAction): HeadsetGesture? =
        bindings.entries.firstOrNull { it.value == action }?.key

    /** True if any bound gesture is a volume key — see [HeadsetGesture.VOLUME_KEYS]. */
    val capturesVolume: Boolean
        get() = bindings.keys.any { it.keyCode in HeadsetGesture.VOLUME_KEYS }

    companion object {
        /**
         * ★ A sensible default where the convention actually holds: nearly every headset
         * sends `MEDIA_PLAY_PAUSE` for a single tap.
         *
         * ⚠️ A **default**, not an assumption — it is offered on first connect, named in
         * plain words so he knows a tap will open a microphone, and can be changed or
         * unbound. Nothing else is guessed at.
         */
        fun forNewHeadset(address: String, name: String) = HeadsetProfile(
            address = address,
            name = name,
            bindings = mapOf(
                HeadsetGesture(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE) to ControlAction.PUSH_TO_TALK,
            ),
        )
    }
}

/** One key edge, reduced to what a binding can depend on. */
data class KeyRecord(val keyCode: Int, val down: Boolean, val repeat: Int = 0) {
    /** Android reports a held key as repeats on the down edge. */
    val longPress: Boolean get() = repeat > 0
}

/** What the router decided about a key. */
sealed interface ControlDecision {

    /**
     * ⚠️ **The default, and it matters.** An unbound key is not ours: it goes back to the
     * system so volume stays volume and track-skip stays track-skip. Only gestures he has
     * explicitly bound are ever swallowed.
     */
    data object PassThrough : ControlDecision

    /** Bound, and this edge is consumed — but nothing happens until the key comes up. */
    data object Consumed : ControlDecision

    /** Bound, key released: do this. */
    data class Perform(val action: ControlAction) : ControlDecision

    /** Learn mode: this is the gesture he just made. */
    data class Learned(val gesture: HeadsetGesture) : ControlDecision
}

/**
 * ★★ The whole decision, as a pure function of the profile and the key.
 *
 * Lives apart from the `MediaSession` so every rule below is testable without a device —
 * which matters more than usual here, because the devices that would exercise it are two
 * sets of earbuds that behave differently from each other and from the phone's idea of a
 * headset.
 */
class ControlRouter(private val clock: () -> Long = System::currentTimeMillis) {

    /**
     * ⚠️⚠️ When a multi-tap last arrived — because **a multi-tap does not arrive alone.**
     *
     * Measured on the owner's Pixel Buds, one double tap produces:
     * ```
     * MEDIA_PREVIOUS DOWN   .469
     * MEDIA_PREVIOUS UP     .475
     * MEDIA_PLAY     UP     .577   <- 102 ms later, tail of the same physical gesture
     * MEDIA_PLAY     DOWN   .585   <- and an orphaned down edge after it
     * ```
     * The firmware sends its multi-tap event *and* a stray play/pause behind it. Since a
     * tap is canonicalised (see [HeadsetGesture.canonical]) that tail is indistinguishable
     * from a single tap — so binding "send" to a double tap captured the tail instead, and
     * every double tap started a recording. Owner: *"the double tap does not work right.
     * It kept trying to record."*
     *
     * So a play/pause inside [TAIL_MS] of a multi-tap is discarded as the echo it is.
     * ⚠️ The window is deliberately short: two deliberate presses that close together are
     * not something a thumb does, and a longer window would start eating real taps.
     */
    private var lastMultiTapAt = 0L

    /** The headset that is connected right now, with its bindings. Null when none is. */
    @Volatile
    var profile: HeadsetProfile? = null

    /**
     * When set, the next gesture is *captured* rather than acted on.
     *
     * ⚠️ In learn mode every key is consumed, including unbound ones — he is being asked
     * to make a gesture, and having it skip a track while he does would be absurd. It is
     * a short, explicit, user-initiated mode; [stopLearning] always ends it.
     */
    @Volatile
    private var learning = false

    fun startLearning() {
        learning = true
    }

    fun stopLearning() {
        learning = false
    }

    val isLearning: Boolean get() = learning

    /** Held between the down and up edges so a long press is known when it is released. */
    private var heldLong = false

    companion object {
        /** Firmware collapses two and three taps into these before Android sees them. */
        private val MULTI_TAP_KEYS = setOf(
            KeyEvent.KEYCODE_MEDIA_NEXT,
            KeyEvent.KEYCODE_MEDIA_PREVIOUS,
        )

        /** Measured tails were 16 ms and 102 ms; this is generous without being greedy. */
        const val TAIL_MS = 300L
    }

    /**
     * ★★ **Is this edge the stray play/pause behind a multi-tap?**
     *
     * ⚠️⚠️ Public and **pure** — no state is changed, so it is safe to ask twice — because
     * [HeadsetControls] has a rule that runs *before* [onKey]: while the microphone is
     * open, any headset key stops it. That rule would otherwise act on the echo, and
     * acting on it means toggling push-to-talk a second time, which **re-opens the
     * microphone he just closed**. Every path that can act on a key asks this first.
     */
    fun isEchoOfMultiTap(key: KeyRecord): Boolean =
        key.keyCode !in MULTI_TAP_KEYS &&
                HeadsetGesture.canonical(key.keyCode) == KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE &&
                clock() - lastMultiTapAt < TAIL_MS

    /**
     * ⚠️ Tell the router a multi-tap happened even when something else claimed the edge
     * before [onKey] could see it — otherwise the tail that follows has no multi-tap to
     * belong to and arrives looking like a deliberate single tap.
     */
    fun noteMultiTap(key: KeyRecord) {
        if (key.keyCode in MULTI_TAP_KEYS) lastMultiTapAt = clock()
    }

    fun onKey(key: KeyRecord): ControlDecision {
        // ⚠️ Canonical from here down — see [HeadsetGesture.canonical]. Learning and
        // matching MUST agree on this or a gesture bound in one playback state cannot be
        // recognised in the other, which is exactly the bug this fixes.
        val code = HeadsetGesture.canonical(key.keyCode)

        if (isEchoOfMultiTap(key)) {
            // The echo of a multi-tap, not a tap. Consumed rather than passed through:
            // an echo is not a gesture, it is one physical press arriving twice, and
            // handing the second copy to the system would toggle his music.
            return ControlDecision.Consumed
        }
        noteMultiTap(key)
        if (learning) {
            if (key.down) {
                if (key.longPress) heldLong = true
                return ControlDecision.Consumed
            }
            val gesture = HeadsetGesture(code, heldLong)
            heldLong = false
            learning = false
            return ControlDecision.Learned(gesture)
        }

        val bindings = profile?.bindings.orEmpty()
        // ⚠️ Consume the down edge only if *either* variant of this key is bound: at the
        // moment of the press we cannot yet know whether he is going to hold it, and
        // letting the down edge through would let the system act on a key we are about
        // to claim.
        val claimed = bindings.keys.any { it.keyCode == code }
        if (!claimed) {
            heldLong = false
            return ControlDecision.PassThrough
        }
        if (key.down) {
            if (key.longPress) heldLong = true
            return ControlDecision.Consumed
        }
        val gesture = HeadsetGesture(code, heldLong)
        heldLong = false
        // ★ A held key with only a short binding still performs the short one. Some
        // headsets never report a repeat, and refusing to act would read as a dead
        // button rather than as a distinction he never asked for.
        val action = bindings[gesture] ?: bindings[HeadsetGesture(code, false)]
        return action?.let { ControlDecision.Perform(it) } ?: ControlDecision.Consumed
    }
}
