"""Roam — BLE macro keyboard firmware for Raspberry Pi Pico 2 W.

Entry point. Launches concurrent async tasks:
  - BLE HID connection management
  - Button polling at ~100Hz
  - OLED display refresh at ~10Hz
  - Battery monitoring every 60s
  - Idle power management
"""

import asyncio

from actions import ActionRegistry
from battery import Battery
from ble_hid import BleHID
from buttons import ButtonManager
from config import Config
from display import Display
from haptic import Haptic
from led import StatusLED
from power import PowerManager


async def main():
    """Initialize all subsystems and run the main event loop."""

    # Load configuration
    config = Config()
    print("roam: config loaded, {} buttons mapped".format(len(config.buttons)))

    # Initialize hardware
    display = Display()
    haptic = Haptic()
    led = StatusLED()
    battery = Battery(read_interval_s=60)
    buttons = ButtonManager(long_press_ms=config.long_press_ms)
    ble = BleHID(device_name="Roam")
    actions = ActionRegistry(ble, haptic=haptic, display=display)
    power = PowerManager(display, led, buttons.get_wake_pins())

    # Initial battery read
    battery.read()
    display.battery_pct = battery.percent
    ble.update_battery(battery.percent)

    # --- BLE connection callbacks ---
    async def on_connect():
        display.ble_status = "Connected"
        led.set_pattern("solid")
        await haptic.connected()
        print("roam: BLE connected")

    async def on_disconnect():
        display.ble_status = "Advertising"
        display.device_name = ""
        led.set_pattern("slow_blink")
        print("roam: BLE disconnected")

    # --- Button event callback ---
    async def on_button(index, press_type):
        """Handle button press events."""
        power.activity()

        # Haptic feedback
        if press_type == "long":
            await haptic.long_confirm()
        else:
            await haptic.short_buzz()

        # Look up and execute action
        action_name = config.get_button_action(index, press_type)
        if action_name:
            if not ble.is_connected() and action_name != "ble_switch":
                display.show_action("No BLE")
                await haptic.error()
                return
            await actions.execute(action_name)
        else:
            print("roam: no action for button {} {}".format(index, press_type))

    buttons.set_callback(on_button)

    # --- Battery monitoring task ---
    async def battery_loop():
        """Read battery voltage periodically and update BLE + display."""
        while True:
            await asyncio.sleep(60)
            battery.read()
            display.battery_pct = battery.percent
            ble.update_battery(battery.percent)

            if battery.is_low:
                led.set_pattern("dim_pulse")

    # Start advertising indicator
    led.set_pattern("slow_blink")
    display.ble_status = "Advertising"
    print("roam: starting — advertising as 'Roam'")

    # Launch all concurrent tasks
    await asyncio.gather(
        ble.run(on_connect=on_connect, on_disconnect=on_disconnect),
        buttons.poll_loop(),
        display.render_loop(),
        battery_loop(),
        power.monitor_loop(),
    )


# MicroPython entry point
try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("roam: stopped")
finally:
    asyncio.new_event_loop()
