"""Power management for Roam.

Tracks idle time and progressively saves power:
  - 5 min idle: dim OLED
  - 15 min idle: enter light sleep (wake on button press)

Button presses reset the idle timer and restore full brightness.
"""

import asyncio
import machine
import time


# Idle thresholds (milliseconds)
DIM_TIMEOUT_MS = const(5 * 60 * 1000)    # 5 minutes
SLEEP_TIMEOUT_MS = const(15 * 60 * 1000)  # 15 minutes


class PowerManager:
    """Manages idle timeouts and sleep modes.

    Args:
        display: Display instance for dimming/power control.
        led: StatusLED instance for power control.
        button_pins: List of Pin objects that trigger wake from sleep.
    """

    def __init__(self, display, led, button_pins):
        self._display = display
        self._led = led
        self._button_pins = button_pins
        self._last_activity = time.ticks_ms()
        self._dimmed = False
        self._sleeping = False

    def activity(self):
        """Signal user activity — resets idle timer and restores display."""
        self._last_activity = time.ticks_ms()
        if self._dimmed:
            self._display.brighten()
            self._dimmed = False
        if self._sleeping:
            self._sleeping = False
            self._display.power_on()

    @property
    def idle_ms(self):
        """Milliseconds since last activity."""
        return time.ticks_diff(time.ticks_ms(), self._last_activity)

    async def monitor_loop(self):
        """Main power monitoring loop. Checks idle time every 5 seconds."""
        while True:
            idle = self.idle_ms

            if idle >= SLEEP_TIMEOUT_MS and not self._sleeping:
                self._enter_sleep()
            elif idle >= DIM_TIMEOUT_MS and not self._dimmed:
                self._display.dim()
                self._dimmed = True

            await asyncio.sleep_ms(5000)

    def _enter_sleep(self):
        """Enter light sleep mode. Wakes on any button pin interrupt."""
        self._sleeping = True
        self._display.power_off()
        self._led.off()

        # Configure wake interrupts on button pins
        for pin in self._button_pins:
            pin.irq(trigger=machine.Pin.IRQ_FALLING, handler=self._wake_handler)

        # Light sleep — CPU stops, peripherals retain state
        machine.lightsleep()

        # Execution resumes here after wake
        self._sleeping = False
        self._last_activity = time.ticks_ms()
        self._display.power_on()
        self._display.brighten()
        self._dimmed = False

    def _wake_handler(self, pin):
        """IRQ handler for button wake — just needs to exist to trigger wake."""
        pass
