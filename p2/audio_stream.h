// Roam P2 — PDM mic audio streaming over the Roam relay BLE service.

#pragma once

#include <Arduino.h>
#include "ble_text.h"

class AudioStream {
public:
    bool begin();
    bool start();
    void stop();
    void poll(BLETextService& relay);

    bool active() const { return _active; }

private:
    bool _active = false;
    uint16_t _sequence = 0;
    int16_t _predictor = 0;
    uint8_t _stepIndex = 0;
    uint8_t _payload[BLE_AUDIO_PAYLOAD_MAX_LEN] = {0};
    uint16_t _payloadLen = 0;
    uint8_t _pendingNibble = 0;
    bool _hasPendingNibble = false;
    uint32_t _frameStartMs = 0;
    int16_t _framePredictor = 0;
    uint8_t _frameStepIndex = 0;

    void resetEncoder();
    uint8_t encodeNibble(int16_t sample);
    void beginFrameIfNeeded();
    void appendSample(int16_t sample);
    void flushFrame(BLETextService& relay, bool force);
};

extern AudioStream audioStream;
