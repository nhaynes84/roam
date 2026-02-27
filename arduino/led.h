// Roam — Non-blocking LED status patterns
// PWM-driven LED on GP16 via 100Ω resistor

#pragma once

#include "config.h"

enum LEDPattern : uint8_t {
    LED_OFF = 0,
    LED_SOLID,       // BLE connected
    LED_SLOW_BLINK,  // Advertising (1 Hz)
    LED_FAST_BLINK,  // Pairing (4 Hz)
    LED_DIM_PULSE,   // Low battery breathing
};

class StatusLED {
public:
    void begin();
    void setPattern(LEDPattern pattern);
    void off();
    void update();  // Call every loop iteration

private:
    LEDPattern _pattern = LED_OFF;
    uint32_t _cycleStart = 0;
    bool _state = false;

    void _setBrightness(uint8_t pct);
};
