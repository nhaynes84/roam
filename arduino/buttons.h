// Roam — Debounced 4-button scanner with short/long press detection
// Active low with internal pull-ups. Long press fires at threshold,
// short press fires on release.

#pragma once

#include "config.h"

enum ButtonEvent : uint8_t {
    BTN_EVENT_NONE = 0,
    BTN_EVENT_SHORT,
    BTN_EVENT_LONG,
    BTN_EVENT_DOUBLE,
};

class Button {
public:
    void begin(uint8_t pin, uint8_t index);
    ButtonEvent poll();
    bool isPressed() const { return _pressed; }
    uint8_t index() const { return _index; }

private:
    uint8_t _pin = 0;
    uint8_t _index = 0;
    bool _pressed = false;
    bool _longFired = false;
    bool _waitingForDouble = false;
    uint8_t _lastState = 1;  // pull-up: 1 = released
    uint32_t _pressStart = 0;
    uint32_t _lastReleaseTime = 0;
};

class ButtonManager {
public:
    void begin();
    void poll(ActionType &outAction);
    bool anyPressed() const;

private:
    Button _buttons[NUM_BUTTONS];
};
