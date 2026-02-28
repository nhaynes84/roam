// Roam — Battery monitor implementation
// LiPo discharge curve: 4.2V=100%, 3.7V=50%, 3.3V=10%, 3.0V=0%

#include "battery.h"

static const float VOLTAGE_FULL    = 4.2f;
static const float VOLTAGE_NOMINAL = 3.7f;
static const float VOLTAGE_LOW     = 3.3f;
static const float VOLTAGE_EMPTY   = 3.0f;
static const float ADC_VREF        = 3.3f;
static const float VSYS_DIVIDER    = 3.0f;

void Battery::begin() {
    // NOTE: On Pico 2 W, GP25 is used by CYW43 wireless SPI.
    // Do NOT set it as OUTPUT or toggle it — that kills BLE.
    // Battery ADC reads without GP25 coordination; slight noise is acceptable.
}

void Battery::read() {
    // Average 3 samples for stability
    uint32_t total = 0;
    for (int i = 0; i < 3; i++) {
        total += analogRead(PIN_BATTERY);
        delayMicroseconds(1000);
    }
    uint16_t raw = total / 3;

    // Convert: ADC is 12-bit on RP2350 (0-4095)
    float adcVoltage = (float)raw / 4095.0f * ADC_VREF;
    _voltage = adcVoltage * VSYS_DIVIDER;

    // Sanity check: USB ~5V, LiPo 3.0-4.2V
    if (_voltage < 1.0f || _voltage > 6.0f) {
        _voltage = 5.0f;
        _percent = 100;
    } else {
        _percent = _voltageToPercent(_voltage);
    }

    _lastRead = millis();
}

bool Battery::shouldRead() {
    if (_lastRead == 0) return true;
    return (millis() - _lastRead) >= BATTERY_PERIOD_MS;
}

uint8_t Battery::_voltageToPercent(float v) {
    if (v >= VOLTAGE_FULL)    return 100;
    if (v >= VOLTAGE_NOMINAL) return 50 + (uint8_t)((v - VOLTAGE_NOMINAL) / (VOLTAGE_FULL - VOLTAGE_NOMINAL) * 50.0f);
    if (v >= VOLTAGE_LOW)     return 10 + (uint8_t)((v - VOLTAGE_LOW) / (VOLTAGE_NOMINAL - VOLTAGE_LOW) * 40.0f);
    if (v >= VOLTAGE_EMPTY)   return (uint8_t)((v - VOLTAGE_EMPTY) / (VOLTAGE_LOW - VOLTAGE_EMPTY) * 10.0f);
    return 0;
}
