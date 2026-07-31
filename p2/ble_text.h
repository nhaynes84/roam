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
#define BLE_TEXT_QUEUE_SIZE 16
#define BLE_RELAY_EVENT_LEN 8
#define BLE_AUDIO_FRAME_MAX_LEN 244
#define BLE_AUDIO_HEADER_LEN 12
#define BLE_AUDIO_PAYLOAD_MAX_LEN (BLE_AUDIO_FRAME_MAX_LEN - BLE_AUDIO_HEADER_LEN)

enum RelayEventType : uint8_t {
    RELAY_EVENT_ACTION = 1,
    RELAY_EVENT_PTT_START = 2,
    RELAY_EVENT_PTT_STOP = 3,
    RELAY_EVENT_STATUS = 4,
};

enum RelayControlCommand : uint8_t {
    RELAY_CONTROL_NONE = 0,
    RELAY_CONTROL_START_AUDIO = 1,
    RELAY_CONTROL_STOP_AUDIO = 2,
    RELAY_CONTROL_STATUS_REQUEST = 3,
};

enum RelayAudioCodec : uint8_t {
    RELAY_AUDIO_CODEC_PCM16_16K = 1,
    RELAY_AUDIO_CODEC_IMA_ADPCM_16K = 2,
};

class BLETextService {
public:
    // Call AFTER Bluefruit.begin() — registers custom GATT service
    void begin();

    // Add the text service UUID to the BLE advertisement.
    bool addToAdvertising();

    // Notify Android relay about control/action/status events.
    bool notifyEvent(uint8_t eventType, uint8_t actionId, uint8_t profileId, uint32_t timestampMs);

    // Notify Android relay with one sequence-numbered audio frame.
    bool notifyAudioFrame(uint8_t codecId, uint16_t sequence, uint32_t timestampMs,
                          int16_t predictor, uint8_t stepIndex,
                          const uint8_t* payload, uint16_t payloadLen);

    // Read control command sent by Android relay.
    bool hasControlCommand() const;
    uint8_t getControlCommand();

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
