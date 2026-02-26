"""Haptic feedback driver for Roam.

Controls a vibration motor on GP15 via an NPN transistor. Provides
named vibration patterns for different UI events.
"""

import asyncio
import machine


class Haptic:
    """Drives a vibration motor with predefined feedback patterns."""

    def __init__(self, pin_num=15):
        self._pin = machine.Pin(pin_num, machine.Pin.OUT, value=0)
        self._running = False

    def _on(self):
        self._pin.value(1)

    def _off(self):
        self._pin.value(0)

    async def _pulse(self, on_ms):
        """Single vibration pulse."""
        self._on()
        await asyncio.sleep_ms(on_ms)
        self._off()

    async def short_buzz(self):
        """Short tactile click — button press feedback."""
        await self._pulse(80)

    async def long_confirm(self):
        """Longer buzz — long press threshold reached."""
        await self._pulse(150)

    async def double_tap(self):
        """Double tap — mode change or toggle."""
        await self._pulse(50)
        await asyncio.sleep_ms(50)
        await self._pulse(50)

    async def error(self):
        """Error pattern — action failed."""
        await self._pulse(200)
        await asyncio.sleep_ms(100)
        await self._pulse(200)

    async def connected(self):
        """Triple tap — BLE connection established."""
        for i in range(3):
            await self._pulse(50)
            if i < 2:
                await asyncio.sleep_ms(60)

    async def play(self, pattern_name):
        """Play a named pattern. Ignores unknown names.

        Args:
            pattern_name: One of 'short_buzz', 'long_confirm', 'double_tap',
                          'error', 'connected'.
        """
        fn = getattr(self, pattern_name, None)
        if fn and callable(fn) and pattern_name != "play":
            await fn()

    def stop(self):
        """Immediately stop any vibration."""
        self._off()
