"""OLED display manager for Roam.

Drives an SH1106 128x64 OLED over I2C (GP4=SDA, GP5=SCL) with a
4-line status UI. Uses a dirty flag to only redraw on state changes,
targeting ~10Hz render loop.
"""

import asyncio
import machine
import time

from lib.sh1106 import SH1106_I2C


# Display layout constants
SCREEN_WIDTH = 128
SCREEN_HEIGHT = 64
LINE_HEIGHT = 16  # 8px font + 8px padding
FONT_WIDTH = 8    # Built-in font is 8x8

# Battery bar dimensions
BAR_X = 90
BAR_Y = 34
BAR_W = 30
BAR_H = 8


class Display:
    """SH1106 OLED status display with dirty-flag rendering.

    Shows 4 lines:
      1. Current mode name
      2. BLE status + connected device name
      3. Battery bar + percentage
      4. Last action (fades after 3s)
    """

    def __init__(self, sda_pin=4, scl_pin=5, i2c_freq=400_000):
        i2c = machine.I2C(0, sda=machine.Pin(sda_pin), scl=machine.Pin(scl_pin),
                          freq=i2c_freq)
        self._oled = SH1106_I2C(SCREEN_WIDTH, SCREEN_HEIGHT, i2c)
        self._dirty = True
        self._dimmed = False

        # State
        self._mode = "Roam"
        self._ble_status = "Advertising"
        self._device_name = ""
        self._battery_pct = 0
        self._last_action = ""
        self._action_time = 0

    @property
    def mode(self):
        return self._mode

    @mode.setter
    def mode(self, value):
        if value != self._mode:
            self._mode = value
            self._dirty = True

    @property
    def ble_status(self):
        return self._ble_status

    @ble_status.setter
    def ble_status(self, value):
        if value != self._ble_status:
            self._ble_status = value
            self._dirty = True

    @property
    def device_name(self):
        return self._device_name

    @device_name.setter
    def device_name(self, value):
        if value != self._device_name:
            self._device_name = value
            self._dirty = True

    @property
    def battery_pct(self):
        return self._battery_pct

    @battery_pct.setter
    def battery_pct(self, value):
        if value != self._battery_pct:
            self._battery_pct = value
            self._dirty = True

    def show_action(self, action_name):
        """Display an action name on line 4, auto-fades after 3 seconds."""
        self._last_action = action_name
        self._action_time = time.ticks_ms()
        self._dirty = True

    def dim(self):
        """Dim the display for idle mode."""
        if not self._dimmed:
            self._oled.contrast(10)
            self._dimmed = True

    def brighten(self):
        """Restore normal brightness."""
        if self._dimmed:
            self._oled.contrast(0x7F)
            self._dimmed = False

    def power_off(self):
        """Turn off the OLED."""
        self._oled.poweroff()

    def power_on(self):
        """Turn on the OLED and mark for redraw."""
        self._oled.poweron()
        self._dirty = True

    def _render(self):
        """Redraw all 4 status lines to the framebuffer."""
        oled = self._oled
        oled.fill(0)

        # Line 1: Mode name (bold-ish via double draw)
        oled.text(self._mode, 0, 0, 1)

        # Line 2: BLE status
        ble_text = self._ble_status
        if self._device_name:
            ble_text += " " + self._device_name
        # Truncate to fit screen
        max_chars = SCREEN_WIDTH // FONT_WIDTH
        if len(ble_text) > max_chars:
            ble_text = ble_text[:max_chars - 1] + ">"
        oled.text(ble_text, 0, LINE_HEIGHT, 1)

        # Line 3: Battery
        self._draw_battery(oled)

        # Line 4: Last action (with 3s fade)
        action_text = ""
        if self._last_action:
            elapsed = time.ticks_diff(time.ticks_ms(), self._action_time)
            if elapsed < 3000:
                action_text = self._last_action
            else:
                self._last_action = ""
        oled.text(action_text, 0, LINE_HEIGHT * 3, 1)

        oled.show()

    def _draw_battery(self, oled):
        """Draw battery percentage text and fill bar."""
        # Text: "Batt: XX%"
        oled.text("Batt:{}%".format(self._battery_pct), 0, LINE_HEIGHT * 2, 1)

        # Bar outline
        oled.rect(BAR_X, BAR_Y, BAR_W, BAR_H, 1)
        # Bar nub (terminal)
        oled.fill_rect(BAR_X + BAR_W, BAR_Y + 2, 2, BAR_H - 4, 1)
        # Fill
        fill_w = int((BAR_W - 2) * self._battery_pct / 100)
        if fill_w > 0:
            oled.fill_rect(BAR_X + 1, BAR_Y + 1, fill_w, BAR_H - 2, 1)

    async def render_loop(self):
        """Main render loop, ~10Hz. Only redraws when dirty."""
        while True:
            # Check if action text should fade
            if self._last_action:
                elapsed = time.ticks_diff(time.ticks_ms(), self._action_time)
                if elapsed >= 3000:
                    self._last_action = ""
                    self._dirty = True

            if self._dirty:
                self._render()
                self._dirty = False

            await asyncio.sleep_ms(100)
