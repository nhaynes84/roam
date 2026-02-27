// Roam — Haptic feedback implementation
// Non-blocking state machine driven by millis()

#include "haptic.h"

// Pattern definitions: arrays of {duration_ms, motor_on}
// Terminated by duration 0
struct PatternStep {
    uint16_t duration;
    bool on;
};

static const PatternStep PAT_SHORT_BUZZ[] = {
    {80, true}, {0, false}
};
static const PatternStep PAT_LONG_CONFIRM[] = {
    {150, true}, {0, false}
};
static const PatternStep PAT_DOUBLE_TAP[] = {
    {50, true}, {50, false}, {50, true}, {0, false}
};
static const PatternStep PAT_ERROR[] = {
    {200, true}, {100, false}, {200, true}, {0, false}
};
static const PatternStep PAT_CONNECTED[] = {
    {50, true}, {60, false}, {50, true}, {60, false}, {50, true}, {0, false}
};

static const PatternStep* getPattern(HapticPattern p) {
    switch (p) {
        case HAPTIC_SHORT_BUZZ:    return PAT_SHORT_BUZZ;
        case HAPTIC_LONG_CONFIRM:  return PAT_LONG_CONFIRM;
        case HAPTIC_DOUBLE_TAP:    return PAT_DOUBLE_TAP;
        case HAPTIC_ERROR:         return PAT_ERROR;
        case HAPTIC_CONNECTED:     return PAT_CONNECTED;
        default:                   return nullptr;
    }
}

void Haptic::begin() {
    pinMode(PIN_MOTOR, OUTPUT);
    digitalWrite(PIN_MOTOR, LOW);
}

void Haptic::_on() {
    digitalWrite(PIN_MOTOR, HIGH);
}

void Haptic::_off() {
    digitalWrite(PIN_MOTOR, LOW);
}

void Haptic::play(HapticPattern pattern) {
    _pattern = pattern;
    _step = 0;
    _active = true;
    _stepStart = millis();

    const PatternStep* steps = getPattern(pattern);
    if (steps && steps[0].duration > 0) {
        if (steps[0].on) _on(); else _off();
    } else {
        _active = false;
    }
}

void Haptic::stop() {
    _off();
    _active = false;
    _pattern = HAPTIC_NONE;
}

void Haptic::update() {
    if (!_active) return;

    const PatternStep* steps = getPattern(_pattern);
    if (!steps) { stop(); return; }

    uint32_t elapsed = millis() - _stepStart;
    if (elapsed >= steps[_step].duration) {
        _step++;
        if (steps[_step].duration == 0) {
            // Pattern complete
            stop();
            return;
        }
        _stepStart = millis();
        if (steps[_step].on) _on(); else _off();
    }
}
