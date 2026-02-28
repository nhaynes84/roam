// Roam — Non-blocking haptic feedback patterns
// Vibration motor on GP15 via NPN transistor

#pragma once

#include "config.h"

enum HapticPattern : uint8_t {
    HAPTIC_NONE = 0,
    HAPTIC_SHORT_BUZZ,    // Button press — 80ms
    HAPTIC_LONG_CONFIRM,  // Long press threshold — 150ms
    HAPTIC_DOUBLE_TAP,    // Mode change — 50ms on, 50ms off, 50ms on
    HAPTIC_ERROR,         // Failed action — 200ms on, 100ms off, 200ms on
    HAPTIC_CONNECTED,     // BLE connected — triple tap
};

class Haptic {
public:
    void begin();
    void play(HapticPattern pattern);
    void stop();
    void update();  // Call every loop iteration

private:
    uint32_t _stepStart = 0;
    uint8_t _step = 0;
    HapticPattern _pattern = HAPTIC_NONE;
    bool _active = false;

    void _on();
    void _off();
    void _advance();
};
