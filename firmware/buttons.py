"""Button handler for Roam.

Manages 4 buttons on GP10-GP13 with debouncing and long press detection.
Active low with internal pull-ups. Short press fires on release if held
less than the long press threshold. Long press fires at threshold crossing
without waiting for release.
"""

import asyncio
import machine
import time


class Button:
    """Single debounced button with short/long press detection.

    Args:
        pin_num: GPIO pin number.
        index: Button index (0-3) for action mapping.
        long_press_ms: Long press threshold in milliseconds.
        debounce_ms: Debounce window in milliseconds.
    """

    def __init__(self, pin_num, index, long_press_ms=600, debounce_ms=50):
        self.pin = machine.Pin(pin_num, machine.Pin.IN, machine.Pin.PULL_UP)
        self.index = index
        self.long_press_ms = long_press_ms
        self.debounce_ms = debounce_ms

        self._pressed = False
        self._press_start = 0
        self._long_fired = False
        self._last_state = 1  # Pull-up: 1 = released

        # Callbacks: (index, press_type) where press_type is 'short' or 'long'
        self.on_short = None
        self.on_long = None

    @property
    def is_pressed(self):
        """True if button is currently held down."""
        return self._pressed

    def poll(self):
        """Poll the button state. Call at ~100Hz.

        Returns:
            Tuple of (event_type, index) or None.
            event_type is 'short', 'long', or None.
        """
        current = self.pin.value()
        now = time.ticks_ms()
        event = None

        if current == 0 and self._last_state == 1:
            # Button just pressed (active low)
            self._pressed = True
            self._press_start = now
            self._long_fired = False

        elif current == 0 and self._pressed and not self._long_fired:
            # Button still held — check for long press threshold
            held = time.ticks_diff(now, self._press_start)
            if held >= self.long_press_ms:
                self._long_fired = True
                event = 'long'

        elif current == 1 and self._last_state == 0:
            # Button just released
            if self._pressed:
                held = time.ticks_diff(now, self._press_start)
                if held >= self.debounce_ms and not self._long_fired:
                    event = 'short'
                self._pressed = False

        self._last_state = current
        return event


class ButtonManager:
    """Manages multiple buttons with async polling.

    Args:
        pin_nums: List of GPIO pin numbers (default GP10-GP13).
        long_press_ms: Long press threshold in milliseconds.
    """

    def __init__(self, pin_nums=None, long_press_ms=600):
        if pin_nums is None:
            pin_nums = [10, 11, 12, 13]

        self.buttons = [
            Button(pin, i, long_press_ms=long_press_ms)
            for i, pin in enumerate(pin_nums)
        ]
        self._callback = None

    def set_callback(self, callback):
        """Set the event callback.

        Args:
            callback: Async function(button_index, press_type) where
                      press_type is 'short' or 'long'.
        """
        self._callback = callback

    @property
    def any_pressed(self):
        """True if any button is currently held."""
        return any(b.is_pressed for b in self.buttons)

    def get_wake_pins(self):
        """Return Pin objects for wake-from-sleep interrupts."""
        return [b.pin for b in self.buttons]

    async def poll_loop(self):
        """Main polling loop at ~100Hz. Dispatches events via callback."""
        while True:
            for button in self.buttons:
                event = button.poll()
                if event and self._callback:
                    await self._callback(button.index, event)
            await asyncio.sleep_ms(10)
