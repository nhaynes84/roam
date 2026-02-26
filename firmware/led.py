"""Status LED driver for Roam.

PWM-driven LED on GP16 with named blink/pulse patterns to indicate
device state (connected, advertising, pairing, sleeping, low battery).
"""

import asyncio
import machine


class StatusLED:
    """PWM-controlled status LED with async blink patterns."""

    def __init__(self, pin_num=16):
        self._pwm = machine.PWM(machine.Pin(pin_num))
        self._pwm.freq(1000)
        self._pwm.duty_u16(0)
        self._task = None
        self._pattern = None

    def _set_brightness(self, pct):
        """Set LED brightness as 0-100 percentage."""
        duty = int((pct / 100) * 65535)
        self._pwm.duty_u16(min(duty, 65535))

    def off(self):
        """Turn LED off and cancel any running pattern."""
        self._cancel()
        self._pwm.duty_u16(0)
        self._pattern = None

    def solid(self):
        """Solid on — BLE connected."""
        self._cancel()
        self._set_brightness(100)
        self._pattern = "solid"

    def set_pattern(self, name):
        """Start a named LED pattern.

        Args:
            name: One of 'solid', 'slow_blink', 'fast_blink', 'dim_pulse', 'off'.
        """
        if name == self._pattern:
            return
        self._pattern = name
        self._cancel()
        if name == "solid":
            self._set_brightness(100)
        elif name == "off":
            self._pwm.duty_u16(0)
        elif name in ("slow_blink", "fast_blink", "dim_pulse"):
            self._task = asyncio.create_task(self._run_pattern(name))

    async def _run_pattern(self, name):
        """Run a blink/pulse pattern in a loop."""
        try:
            if name == "slow_blink":
                await self._blink_loop(500)  # 1Hz
            elif name == "fast_blink":
                await self._blink_loop(125)  # 4Hz
            elif name == "dim_pulse":
                await self._pulse_loop()
        except asyncio.CancelledError:
            pass
        finally:
            self._pwm.duty_u16(0)

    async def _blink_loop(self, half_period_ms):
        """Square wave blink at the given half-period."""
        while True:
            self._set_brightness(100)
            await asyncio.sleep_ms(half_period_ms)
            self._pwm.duty_u16(0)
            await asyncio.sleep_ms(half_period_ms)

    async def _pulse_loop(self):
        """Slow sine-ish breathing pulse for low battery."""
        steps = 20
        while True:
            # Ramp up
            for i in range(steps):
                self._set_brightness(int(5 + (i / steps) * 25))
                await asyncio.sleep_ms(40)
            # Ramp down
            for i in range(steps, 0, -1):
                self._set_brightness(int(5 + (i / steps) * 25))
                await asyncio.sleep_ms(40)
            await asyncio.sleep_ms(200)

    def _cancel(self):
        """Cancel any running async pattern."""
        if self._task is not None:
            self._task.cancel()
            self._task = None

    def deinit(self):
        """Release PWM resources."""
        self._cancel()
        self._pwm.deinit()
