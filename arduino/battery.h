// Roam — Battery voltage monitor
// Reads VSYS/3 via ADC3 (GPIO29), with GP25 coordination for CYW43

#pragma once

#include "config.h"

class Battery {
public:
    void begin();
    void read();           // Take a reading (averages 3 samples)
    bool shouldRead();     // True if interval has elapsed

    float voltage() const { return _voltage; }
    uint8_t percent() const { return _percent; }
    bool isLow() const { return _percent <= 10; }

private:
    float _voltage = 0.0f;
    uint8_t _percent = 0;
    uint32_t _lastRead = 0;

    uint8_t _voltageToPercent(float v);
};
