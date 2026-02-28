// Roam P2 — Battery monitor implementation (nRF52840)
// XIAO nRF52840 Sense reads VBAT via internal ADC with voltage divider.
// LiPo discharge curve: 4.2V=100%, 3.7V=50%, 3.3V=10%, 3.0V=0%

#include "battery.h"

static const float VOLTAGE_FULL    = 4.2f;
static const float VOLTAGE_NOMINAL = 3.7f;
static const float VOLTAGE_LOW     = 3.3f;
static const float VOLTAGE_EMPTY   = 3.0f;

// nRF52840 ADC reference voltage and resolution
static const float ADC_VREF    = 3.6f;    // nRF52840 internal reference
static const float ADC_RES     = 4096.0f; // 12-bit ADC
static const float VBAT_DIVIDER = 2.0f;   // On-board voltage divider ratio

void Battery::begin() {
    // nRF52840 ADC configured automatically by analogRead
    analogReference(AR_INTERNAL_3_6);
    analogReadResolution(12);
}

void Battery::read() {
    // Average 3 samples for stability
    uint32_t total = 0;
    for (int i = 0; i < 3; i++) {
        total += analogRead(PIN_VBAT);
        delayMicroseconds(1000);
    }
    uint16_t raw = total / 3;

    // Convert: nRF52840 12-bit ADC, 3.6V reference, 2:1 divider
    float adcVoltage = (float)raw / ADC_RES * ADC_VREF;
    _voltage = adcVoltage * VBAT_DIVIDER;

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
