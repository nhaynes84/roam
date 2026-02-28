// Roam — BLE GATT text service
// Adds a writable characteristic (UUID 0xFF01) alongside the HID service.
// Mac writes text → firmware displays it on the OLED.
//
// Service UUID: 0xFF00 (vendor-specific)
// Characteristic UUID: 0xFF01 (write without response, read)
// ATT handles: 0x003F-0x0041 (appended after HID DB)

#pragma once

#include <Arduino.h>

// Max text length for BLE writes (MTU-limited, ~20 bytes default, up to 128 with negotiation)
#define BLE_TEXT_MAX_LEN 128

class BLETextService {
public:
    // Call AFTER KeyboardBLE.begin() — extends ATT DB and registers handler
    void begin();

    // Check for new text from BLE (non-blocking)
    bool hasNewText() const;

    // Get received text and clear the flag
    const char* getText();

    // Current text buffer (may be read without clearing flag)
    const char* peek() const { return _textBuf; }

private:
    char _textBuf[BLE_TEXT_MAX_LEN] = {0};
    volatile bool _newText = false;
    bool _handlerRegistered = false;
};

extern BLETextService bleText;
