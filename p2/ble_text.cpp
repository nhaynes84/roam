// Roam P2 — BLE text service implementation (Bluefruit native API)
// Much simpler than P1's btstack ATT DB hack — Bluefruit exposes
// BLEService and BLECharacteristic as first-class objects.

#include "ble_text.h"
#include <bluefruit.h>

// Custom GATT service and characteristic — same UUIDs as P1
static BLEService   _svc(0xFF00);
static BLECharacteristic _chr(0xFF01);
static BLECharacteristic _eventChr(0xFF02);
static BLECharacteristic _audioChr(0xFF03);
static BLECharacteristic _controlChr(0xFF04);

// Shared state between callback and BLETextService. The main loop can spend
// ~200 ms on message haptics, so text writes need a real queue instead of one
// overwrite-prone slot.
static char _sharedTextQueue[BLE_TEXT_QUEUE_SIZE][BLE_TEXT_MAX_LEN];
static volatile uint8_t _sharedTextHead = 0;
static volatile uint8_t _sharedTextTail = 0;
static volatile uint8_t _sharedTextCount = 0;
static volatile bool _sharedNewControl = false;
static uint8_t _sharedControlCommand = RELAY_CONTROL_NONE;

// Write callback — triggered when Mac writes to characteristic
static void text_write_callback(uint16_t conn_hdl, BLECharacteristic* chr,
                                 uint8_t* data, uint16_t len) {
    (void)conn_hdl;
    (void)chr;
    uint16_t n = len < (BLE_TEXT_MAX_LEN - 1) ? len : (BLE_TEXT_MAX_LEN - 1);

    if (_sharedTextCount >= BLE_TEXT_QUEUE_SIZE) {
        _sharedTextTail = (_sharedTextTail + 1) % BLE_TEXT_QUEUE_SIZE;
        _sharedTextCount--;
    }

    uint8_t slot = _sharedTextHead;
    memcpy(_sharedTextQueue[slot], data, n);
    _sharedTextQueue[slot][n] = '\0';
    _sharedTextHead = (_sharedTextHead + 1) % BLE_TEXT_QUEUE_SIZE;
    _sharedTextCount++;
}

static void control_write_callback(uint16_t conn_hdl, BLECharacteristic* chr,
                                   uint8_t* data, uint16_t len) {
    (void)conn_hdl;
    (void)chr;
    if (len < 2 || data[0] != 1) return;
    _sharedControlCommand = data[1];
    _sharedNewControl = true;
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

    _eventChr.setProperties(CHR_PROPS_READ | CHR_PROPS_NOTIFY);
    _eventChr.setPermission(SECMODE_OPEN, SECMODE_NO_ACCESS);
    _eventChr.setFixedLen(BLE_RELAY_EVENT_LEN);
    _eventChr.begin();

    _audioChr.setProperties(CHR_PROPS_READ | CHR_PROPS_NOTIFY);
    _audioChr.setPermission(SECMODE_OPEN, SECMODE_NO_ACCESS);
    _audioChr.setMaxLen(BLE_AUDIO_FRAME_MAX_LEN);
    _audioChr.begin();

    _controlChr.setProperties(CHR_PROPS_WRITE | CHR_PROPS_WRITE_WO_RESP);
    _controlChr.setPermission(SECMODE_NO_ACCESS, SECMODE_OPEN);
    _controlChr.setMaxLen(16);
    _controlChr.setWriteCallback(control_write_callback);
    _controlChr.begin();

    Serial.println("ble_text: service registered (UUID 0xFF00/0xFF01-0xFF04)");
}

bool BLETextService::addToAdvertising() {
    return Bluefruit.Advertising.addService(_svc);
}

bool BLETextService::notifyEvent(uint8_t eventType, uint8_t actionId, uint8_t profileId, uint32_t timestampMs) {
    if (!Bluefruit.connected()) return false;

    uint8_t packet[BLE_RELAY_EVENT_LEN] = {
        1,
        eventType,
        actionId,
        profileId,
        (uint8_t)(timestampMs & 0xff),
        (uint8_t)((timestampMs >> 8) & 0xff),
        (uint8_t)((timestampMs >> 16) & 0xff),
        (uint8_t)((timestampMs >> 24) & 0xff),
    };

    _eventChr.write(packet, sizeof(packet));
    return _eventChr.notify(packet, sizeof(packet));
}

bool BLETextService::notifyAudioFrame(uint8_t codecId, uint16_t sequence, uint32_t timestampMs,
                                      int16_t predictor, uint8_t stepIndex,
                                      const uint8_t* payload, uint16_t payloadLen) {
    if (!Bluefruit.connected() || payload == nullptr) return false;
    if (payloadLen > BLE_AUDIO_PAYLOAD_MAX_LEN) return false;

    uint8_t packet[BLE_AUDIO_FRAME_MAX_LEN];
    packet[0] = 1;
    packet[1] = codecId;
    packet[2] = (uint8_t)(sequence & 0xff);
    packet[3] = (uint8_t)((sequence >> 8) & 0xff);
    packet[4] = (uint8_t)(timestampMs & 0xff);
    packet[5] = (uint8_t)((timestampMs >> 8) & 0xff);
    packet[6] = (uint8_t)((timestampMs >> 16) & 0xff);
    packet[7] = (uint8_t)((timestampMs >> 24) & 0xff);
    packet[8] = (uint8_t)(predictor & 0xff);
    packet[9] = (uint8_t)((predictor >> 8) & 0xff);
    packet[10] = stepIndex;
    packet[11] = 0;
    memcpy(packet + BLE_AUDIO_HEADER_LEN, payload, payloadLen);

    return _audioChr.notify(packet, payloadLen + BLE_AUDIO_HEADER_LEN);
}

bool BLETextService::hasControlCommand() const {
    return _sharedNewControl;
}

uint8_t BLETextService::getControlCommand() {
    if (!_sharedNewControl) return RELAY_CONTROL_NONE;
    uint8_t cmd = _sharedControlCommand;
    _sharedControlCommand = RELAY_CONTROL_NONE;
    _sharedNewControl = false;
    return cmd;
}

bool BLETextService::hasNewText() const {
    return _sharedTextCount > 0;
}

const char* BLETextService::getText() {
    if (_sharedTextCount > 0) {
        uint8_t slot = _sharedTextTail;
        memcpy(_textBuf, _sharedTextQueue[slot], BLE_TEXT_MAX_LEN);
        _sharedTextTail = (_sharedTextTail + 1) % BLE_TEXT_QUEUE_SIZE;
        _sharedTextCount--;
        _newText = _sharedTextCount > 0;
        return _textBuf;
    }
    return _textBuf;
}
