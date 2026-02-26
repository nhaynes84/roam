"""BLE HID keyboard + consumer control service for Roam.

Uses aioble to register a composite HID device with:
  - HID Service (0x1812): keyboard (Report ID 1) + consumer control (Report ID 2)
  - Battery Service (0x180F)
  - Device Information Service (0x180A)

Designed for macOS compatibility — the HID Report Map descriptor must be
byte-perfect or macOS will reject the device.
"""

import asyncio
import struct

import aioble
import bluetooth

from hid_report import (
    REPORT_MAP,
    KEYBOARD_REPORT_ID,
    CONSUMER_REPORT_ID,
    KEYBOARD_REPORT_SIZE,
    CONSUMER_REPORT_SIZE,
)

# BLE UUIDs
_HID_SERVICE_UUID = bluetooth.UUID(0x1812)
_HID_INFO_UUID = bluetooth.UUID(0x2A4A)
_HID_REPORT_MAP_UUID = bluetooth.UUID(0x2A4B)
_HID_CONTROL_POINT_UUID = bluetooth.UUID(0x2A4C)
_HID_REPORT_UUID = bluetooth.UUID(0x2A4D)
_HID_PROTOCOL_MODE_UUID = bluetooth.UUID(0x2A4E)

_BATTERY_SERVICE_UUID = bluetooth.UUID(0x180F)
_BATTERY_LEVEL_UUID = bluetooth.UUID(0x2A19)

_DEVICE_INFO_SERVICE_UUID = bluetooth.UUID(0x180A)
_MANUFACTURER_NAME_UUID = bluetooth.UUID(0x2A29)
_MODEL_NUMBER_UUID = bluetooth.UUID(0x2A24)
_PNP_ID_UUID = bluetooth.UUID(0x2A50)

# Report Reference Descriptor UUID
_REPORT_REFERENCE_UUID = bluetooth.UUID(0x2908)

# HID appearance: keyboard
_HID_APPEARANCE = const(961)  # 0x03C1

# Advertising interval (ms)
_ADV_INTERVAL_MS = const(30_000)


class BleHID:
    """BLE HID composite device (keyboard + consumer control).

    Registers GATT services and handles connection lifecycle,
    report sending, and battery level updates.
    """

    def __init__(self, device_name="Roam"):
        self._device_name = device_name
        self._connection = None
        self._connected = False
        self._keyboard_report_char = None
        self._consumer_report_char = None
        self._battery_char = None
        self._should_advertise = True

        self._register_services()

    def _register_services(self):
        """Register HID, Battery, and Device Information GATT services."""

        # --- HID Service ---
        hid_service = aioble.Service(_HID_SERVICE_UUID)

        # HID Information: version 1.11, country=0, flags=0x02 (normally connectable)
        hid_info = aioble.Characteristic(
            hid_service, _HID_INFO_UUID,
            read=True,
            initial=struct.pack("<BBbB", 0x11, 0x01, 0x00, 0x02),
        )

        # Report Map: the composite HID descriptor
        report_map = aioble.Characteristic(
            hid_service, _HID_REPORT_MAP_UUID,
            read=True,
            initial=REPORT_MAP,
        )

        # HID Control Point: host writes to suspend/resume
        control_point = aioble.Characteristic(
            hid_service, _HID_CONTROL_POINT_UUID,
            write=True,
        )

        # Protocol Mode: Report Protocol (1)
        protocol_mode = aioble.Characteristic(
            hid_service, _HID_PROTOCOL_MODE_UUID,
            read=True, write=True,
            initial=struct.pack("B", 1),
        )

        # Keyboard Input Report (Report ID 1)
        self._keyboard_report_char = aioble.Characteristic(
            hid_service, _HID_REPORT_UUID,
            read=True, notify=True,
            initial=bytes(KEYBOARD_REPORT_SIZE),
        )
        # Report Reference descriptor: Report ID 1, Input (1)
        aioble.Descriptor(
            self._keyboard_report_char, _REPORT_REFERENCE_UUID,
            read=True,
            initial=struct.pack("BB", KEYBOARD_REPORT_ID, 0x01),
        )

        # Consumer Input Report (Report ID 2)
        self._consumer_report_char = aioble.Characteristic(
            hid_service, _HID_REPORT_UUID,
            read=True, notify=True,
            initial=bytes(CONSUMER_REPORT_SIZE),
        )
        # Report Reference descriptor: Report ID 2, Input (1)
        aioble.Descriptor(
            self._consumer_report_char, _REPORT_REFERENCE_UUID,
            read=True,
            initial=struct.pack("BB", CONSUMER_REPORT_ID, 0x01),
        )

        # LED Output Report (Report ID 1) — host writes LED state
        led_output_char = aioble.Characteristic(
            hid_service, _HID_REPORT_UUID,
            read=True, write=True,
            initial=bytes(1),
        )
        # Report Reference descriptor: Report ID 1, Output (2)
        aioble.Descriptor(
            led_output_char, _REPORT_REFERENCE_UUID,
            read=True,
            initial=struct.pack("BB", KEYBOARD_REPORT_ID, 0x02),
        )

        # --- Battery Service ---
        battery_service = aioble.Service(_BATTERY_SERVICE_UUID)
        self._battery_char = aioble.Characteristic(
            battery_service, _BATTERY_LEVEL_UUID,
            read=True, notify=True,
            initial=struct.pack("B", 100),
        )

        # --- Device Information Service ---
        device_info_service = aioble.Service(_DEVICE_INFO_SERVICE_UUID)

        aioble.Characteristic(
            device_info_service, _MANUFACTURER_NAME_UUID,
            read=True,
            initial="Roam",
        )
        aioble.Characteristic(
            device_info_service, _MODEL_NUMBER_UUID,
            read=True,
            initial="Roam v1",
        )
        # PnP ID: vendor source=0x02 (USB), vendor=0x05AC (placeholder),
        # product=0x0001, version=0x0001
        aioble.Characteristic(
            device_info_service, _PNP_ID_UUID,
            read=True,
            initial=struct.pack("<BHHH", 0x02, 0x05AC, 0x0001, 0x0001),
        )

        # Register all services
        aioble.register_services(hid_service, battery_service, device_info_service)

    def is_connected(self):
        """Check if a host is currently connected."""
        return self._connected and self._connection is not None

    async def start_advertising(self):
        """Start BLE advertising as an HID keyboard."""
        self._should_advertise = True

    async def stop_advertising(self):
        """Stop advertising."""
        self._should_advertise = False

    async def disconnect(self):
        """Disconnect the current connection."""
        if self._connection:
            try:
                await self._connection.disconnect()
            except Exception:
                pass
            self._connection = None
            self._connected = False

    async def send_keyboard_report(self, modifiers=0, keys=None):
        """Send a keyboard HID report.

        Args:
            modifiers: Modifier bitmask (MOD_CTRL, MOD_SHIFT, etc.).
            keys: List of up to 6 HID keycodes (ints), or None for no keys.
        """
        if not self.is_connected():
            return

        report = bytearray(KEYBOARD_REPORT_SIZE)
        report[0] = modifiers
        report[1] = 0  # Reserved
        if keys:
            for i, key in enumerate(keys[:6]):
                report[2 + i] = key

        self._keyboard_report_char.write(report)
        self._keyboard_report_char.notify(self._connection, report)

    async def send_consumer_report(self, usage_code):
        """Send a consumer control HID report.

        Args:
            usage_code: 16-bit consumer usage code (e.g., 0x00CF for dictation).
        """
        if not self.is_connected():
            return

        report = struct.pack("<H", usage_code)
        self._consumer_report_char.write(report)
        self._consumer_report_char.notify(self._connection, report)

    async def release_all(self):
        """Send empty reports to release all keys."""
        if not self.is_connected():
            return

        # Release keyboard
        empty_kb = bytes(KEYBOARD_REPORT_SIZE)
        self._keyboard_report_char.write(empty_kb)
        self._keyboard_report_char.notify(self._connection, empty_kb)

        # Release consumer
        empty_cc = bytes(CONSUMER_REPORT_SIZE)
        self._consumer_report_char.write(empty_cc)
        self._consumer_report_char.notify(self._connection, empty_cc)

    def update_battery(self, percent):
        """Update the battery level characteristic.

        Args:
            percent: Battery level 0-100.
        """
        data = struct.pack("B", min(100, max(0, percent)))
        self._battery_char.write(data)
        if self.is_connected():
            self._battery_char.notify(self._connection, data)

    async def run(self, on_connect=None, on_disconnect=None):
        """Main BLE connection loop. Advertises and waits for connections.

        Args:
            on_connect: Optional async callback when a host connects.
            on_disconnect: Optional async callback when a host disconnects.
        """
        while True:
            if not self._should_advertise:
                await asyncio.sleep_ms(500)
                continue

            try:
                connection = await aioble.advertise(
                    _ADV_INTERVAL_MS * 1000,  # aioble uses microseconds
                    name=self._device_name,
                    services=[_HID_SERVICE_UUID],
                    appearance=_HID_APPEARANCE,
                )

                self._connection = connection
                self._connected = True

                if on_connect:
                    await on_connect()

                # Wait for disconnect
                await connection.disconnected(timeout_ms=None)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                print("ble_hid: connection error:", e)

            finally:
                self._connected = False
                self._connection = None
                if on_disconnect:
                    await on_disconnect()

            # Brief delay before re-advertising
            await asyncio.sleep_ms(500)
