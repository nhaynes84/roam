// Roam P2 — BLE text service implementation (Bluefruit native API)
// Much simpler than P1's btstack ATT DB hack — Bluefruit exposes
// BLEService and BLECharacteristic as first-class objects.

#include "ble_text.h"
#include <bluefruit.h>

// Custom GATT service and characteristic — same UUIDs as P1
static BLEService   _svc(0xFF00);
static BLECharacteristic _chr(0xFF01);

// Shared state between callback and BLETextService
static char _sharedTextBuf[BLE_TEXT_MAX_LEN];
static volatile bool _sharedNewText = false;

// Write callback — triggered when Mac writes to characteristic
static void text_write_callback(uint16_t conn_hdl, BLECharacteristic* chr,
                                 uint8_t* data, uint16_t len) {
    (void)conn_hdl;
    (void)chr;
    uint16_t n = len < (BLE_TEXT_MAX_LEN - 1) ? len : (BLE_TEXT_MAX_LEN - 1);
    memcpy(_sharedTextBuf, data, n);
    _sharedTextBuf[n] = '\0';
    _sharedNewText = true;
}

BLETextService bleText;

void BLETextService::begin() {
    // Start the custom service
    _svc.begin();

    // Configure the writable characteristic
    _chr.setProperties(CHR_PROPS_READ | CHR_PROPS_WRITE | CHR_PROPS_WRITE_WO_RESP);
    _chr.setPermission(SECMODE_OPEN, SECMODE_OPEN);
    _chr.setMaxLen(BLE_TEXT_MAX_LEN);
    _chr.setWriteCallback(text_write_callback);
    _chr.begin();

    Serial.println("ble_text: service registered (UUID 0xFF00/0xFF01)");
}

bool BLETextService::hasNewText() const {
    return _sharedNewText;
}

const char* BLETextService::getText() {
    if (_sharedNewText) {
        memcpy(_textBuf, _sharedTextBuf, BLE_TEXT_MAX_LEN);
        _newText = false;
        _sharedNewText = false;
        return _textBuf;
    }
    return _textBuf;
}
