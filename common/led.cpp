// Roam — LED status pattern implementation
// Non-blocking state machine driven by millis()

#include "led.h"

void StatusLED::begin() {
    pinMode(ROAM_LED_PIN, OUTPUT);
    analogWriteFreq(1000);
    analogWriteRange(255);
    analogWrite(ROAM_LED_PIN, 0);
}

void StatusLED::_setBrightness(uint8_t pct) {
    uint16_t duty = (uint16_t)pct * 255 / 100;
    analogWrite(ROAM_LED_PIN, duty);
}

void StatusLED::setPattern(LEDPattern pattern) {
    if (pattern == _pattern) return;
    _pattern = pattern;
    _cycleStart = millis();
    _state = false;

    switch (pattern) {
        case LED_SOLID:
            _setBrightness(100);
            break;
        case LED_OFF:
            analogWrite(ROAM_LED_PIN, 0);
            break;
        default:
            break;
    }
}

void StatusLED::off() {
    setPattern(LED_OFF);
}

void StatusLED::update() {
    uint32_t elapsed = millis() - _cycleStart;

    switch (_pattern) {
        case LED_SLOW_BLINK: {
            // 1 Hz: 500ms on, 500ms off
            bool on = (elapsed % 1000) < 500;
            if (on != _state) {
                _state = on;
                _setBrightness(on ? 100 : 0);
            }
            break;
        }
        case LED_FAST_BLINK: {
            // 4 Hz: 125ms on, 125ms off
            bool on = (elapsed % 250) < 125;
            if (on != _state) {
                _state = on;
                _setBrightness(on ? 100 : 0);
            }
            break;
        }
        case LED_DIM_PULSE: {
            // Slow breathing: 1.6s cycle (0.8s up, 0.8s down)
            uint32_t phase = elapsed % 1800;
            uint8_t brightness;
            if (phase < 800) {
                // Ramp up 5% → 30%
                brightness = 5 + (uint8_t)((uint32_t)25 * phase / 800);
            } else if (phase < 1600) {
                // Ramp down 30% → 5%
                brightness = 30 - (uint8_t)((uint32_t)25 * (phase - 800) / 800);
            } else {
                // Brief pause at bottom
                brightness = 5;
            }
            _setBrightness(brightness);
            break;
        }
        case LED_SOLID:
        case LED_OFF:
        default:
            // Static — no update needed
            break;
    }
}
