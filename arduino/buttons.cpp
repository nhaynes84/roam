// Roam — Button implementation

#include "buttons.h"

void Button::begin(uint8_t pin, uint8_t index) {
    _pin = pin;
    _index = index;
    pinMode(_pin, INPUT_PULLUP);
    _lastState = digitalRead(_pin);
}

ButtonEvent Button::poll() {
    uint8_t current = digitalRead(_pin);
    uint32_t now = millis();
    ButtonEvent event = BTN_EVENT_NONE;

    if (current == 0 && _lastState == 1) {
        // Just pressed
        _pressed = true;
        _pressStart = now;
        _longFired = false;
    } else if (current == 0 && _pressed && !_longFired) {
        // Still held — check long press
        if ((now - _pressStart) >= LONG_PRESS_MS) {
            _longFired = true;
            event = BTN_EVENT_LONG;
        }
    } else if (current == 1 && _lastState == 0) {
        // Just released
        if (_pressed) {
            uint32_t held = now - _pressStart;
            if (held >= DEBOUNCE_MS && !_longFired) {
                event = BTN_EVENT_SHORT;
            }
            _pressed = false;
        }
    }

    _lastState = current;
    return event;
}

// --- ButtonManager ---

void ButtonManager::begin() {
    for (uint8_t i = 0; i < NUM_BUTTONS; i++) {
        _buttons[i].begin(BUTTON_PINS[i], i);
    }
}

void ButtonManager::poll(ActionType &outAction) {
    outAction = ACTION_NONE;
    for (uint8_t i = 0; i < NUM_BUTTONS; i++) {
        ButtonEvent evt = _buttons[i].poll();
        if (evt == BTN_EVENT_SHORT) {
            outAction = BUTTON_MAP[i].shortPress;
            return;
        } else if (evt == BTN_EVENT_LONG) {
            outAction = BUTTON_MAP[i].longPress;
            return;
        }
    }
}

bool ButtonManager::anyPressed() const {
    for (uint8_t i = 0; i < NUM_BUTTONS; i++) {
        if (_buttons[i].isPressed()) return true;
    }
    return false;
}
