// Roam P2 — BLE GATT text service
// Custom writable characteristic for Mac → OLED text push.
// Uses Adafruit BLEService + BLECharacteristic (native Bluefruit API).
//
// Service UUID: 0xFF00 (vendor-specific)
// Characteristic UUID: 0xFF01 (write without response, read)

#pragma once

#include <Arduino.h>

// Max text length for BLE writes
#define BLE_TEXT_MAX_LEN 128

class BLETextService {
public:
    // Call AFTER Bluefruit.begin() — registers custom GATT service
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
};

extern BLETextService bleText;
