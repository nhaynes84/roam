// Roam P2 — Battery monitor implementation (nRF52840)
// XIAO nRF52840 Sense reads VBAT via internal ADC with voltage divider.
// LiPo discharge curve: 4.2V=100%, 3.7V=50%, 3.3V=10%, 3.0V=0%

#include "battery.h"

static const float VOLTAGE_FULL    = 4.2f;
static const float VOLTAGE_NOMINAL = 3.7f;
static const float VOLTAGE_LOW     = 3.3f;
static const float VOLTAGE_EMPTY   = 3.0f;

// nRF52840 ADC: AR_INTERNAL = 0.6V ref with 1/6 gain -> 3.6V max input
static const float ADC_VREF    = 3.6f;    // effective max input voltage
static const float ADC_RES     = 4095.0f; // 12-bit ADC max value
static const float VBAT_DIVIDER = 1510.0f / 510.0f;  // On-board 1M + 510k divider

void Battery::begin() {
    // Enable VBAT voltage divider (VBAT_ENABLE must be LOW to read)
    pinMode(VBAT_ENABLE, OUTPUT);
    digitalWrite(VBAT_ENABLE, LOW);

    // nRF52840 ADC: internal reference with 3.6V effective input range.
    analogReference(AR_INTERNAL);
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

    // Convert: nRF52840 12-bit ADC, 3.6V reference, on-board VBAT divider.
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
    Serial.printf("battery: raw=%u adc=%.3fV voltage=%.2fV pct=%d%%\n",
                  raw, adcVoltage, _voltage, _percent);
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
