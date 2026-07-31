# Roam P2 Flashing

Roam P2 uses a Seeed XIAO nRF52840 Sense inside a sealed case. Do not ask Nick to double-tap reset; the reset button is not accessible in the current enclosure.

## Preferred Sealed-Case Flow

Use:

```bash
make p2-flash-sealed
```

This target:

1. Compiles the firmware with build intermediates in `/tmp/roam-p2-build`.
2. Exports the DFU package into `/tmp/roam-p2-out`.
3. Uses `adafruit-nrfutil --touch 1200` against the app serial port.
4. Ignores the expected failure after the app port disappears.
5. Waits for the Seeed bootloader PID `0x0045`.
6. Uploads the generated DFU zip to the bootloader port without touching again.

The normal app PID is `0x8045`. During the successful 2026-07-30 flash, the port name stayed `/dev/cu.usbmodem2101`, but the USB product ID changed from `0x8045` to `0x0045` while in bootloader mode.

## Manual Recovery

If `make p2-flash-sealed` fails after the touch step, check the current USB state:

```bash
arduino-cli board list --format json
ioreg -p IOUSB -l -w0 | awk '/XIAO|idProduct|idVendor|USB Product Name|USB Vendor Name/ {print}' | tail -n 20
```

If the board is already at PID `0x0045`, upload directly without another touch:

```bash
~/Library/Arduino15/packages/Seeeduino/hardware/nrf52/1.1.12/tools/adafruit-nrfutil/macos/adafruit-nrfutil --verbose dfu serial \
  -pkg /tmp/roam-p2-out/p2.ino.zip \
  -p /dev/cu.usbmodem2101 \
  -b 115200 \
  --singlebank
```

If the board is at PID `0x8045`, it is running the app firmware, not the bootloader.
