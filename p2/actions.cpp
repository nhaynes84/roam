// Roam P2 — HID action implementation (Bluefruit BLEHidAdafruit)
// API: keyPress(char) for ASCII, keyboardReport(modifier, keycodes[6]) for combos

#include "actions.h"
#include "ble_text.h"

// BLEHidAdafruit instance — declared in p2.ino
extern BLEHidAdafruit blehid;

void actionsBegin() {
    // BLE HID initialized in p2.ino — nothing extra needed here
}

// Small delay between keystrokes in a sequence
static void keystrokeDelay() {
    delay(30);
}

// Helper: send a single keycode with modifier via raw HID report
static void sendKey(uint8_t modifier, uint8_t keycode) {
    uint8_t keys[6] = { keycode, 0, 0, 0, 0, 0 };
    blehid.keyboardReport(modifier, keys);
}

// Helper: release all keys
static void releaseKeys() {
    blehid.keyRelease();
}

void executeAction(ActionType action) {
    switch (action) {

    case ACTION_DICTATION:
        // macOS dictation consumer key 0x00CF
        blehid.consumerKeyPress(0x00CF);
        delay(50);
        blehid.consumerKeyRelease();
        break;

    case ACTION_DICTATION_ANDROID:
        // Android inline voice input 0x00D8
        blehid.consumerKeyPress(0x00D8);
        delay(50);
        blehid.consumerKeyRelease();
        break;

    case ACTION_TMUX_PANE:
        // Ctrl+B then 'o' — tmux next pane
        sendKey(KEYBOARD_MODIFIER_LEFTCTRL, HID_KEY_B);
        keystrokeDelay();
        releaseKeys();
        delay(50);
        blehid.keyPress('o');
        keystrokeDelay();
        releaseKeys();
        break;

    case ACTION_CYCLE_MODE:
        // Shift+Tab — cycle mode
        sendKey(KEYBOARD_MODIFIER_LEFTSHIFT, HID_KEY_TAB);
        delay(50);
        releaseKeys();
        break;

    case ACTION_BLE_SWITCH:
        // Disconnect + reject reconnections from current device
        bleSwitch();
        break;

    case ACTION_APPROVE_YES:
        // 'y' then Enter
        blehid.keyPress('y');
        keystrokeDelay();
        releaseKeys();
        keystrokeDelay();
        sendKey(0, HID_KEY_ENTER);
        keystrokeDelay();
        releaseKeys();
        break;

    case ACTION_APPROVE_ALWAYS:
        // Tab then Enter — select "Always allow"
        sendKey(0, HID_KEY_TAB);
        keystrokeDelay();
        releaseKeys();
        keystrokeDelay();
        sendKey(0, HID_KEY_ENTER);
        keystrokeDelay();
        releaseKeys();
        break;

    case ACTION_REJECT_ESCAPE:
        // Escape
        sendKey(0, HID_KEY_ESCAPE);
        delay(50);
        releaseKeys();
        break;

    case ACTION_KILL_PROCESS:
        // Ctrl+C
        sendKey(KEYBOARD_MODIFIER_LEFTCTRL, HID_KEY_C);
        delay(50);
        releaseKeys();
        break;

    case ACTION_ENTER:
        sendKey(0, HID_KEY_ENTER);
        delay(50);
        releaseKeys();
        break;

    case ACTION_HOME_ANDROID:
        // Meta+H — Android home
        sendKey(KEYBOARD_MODIFIER_LEFTGUI, HID_KEY_H);
        delay(50);
        releaseKeys();
        break;

    case ACTION_RECENTS_ANDROID:
        // Android app switcher consumer key 0x029F
        blehid.consumerKeyPress(0x029F);
        delay(50);
        blehid.consumerKeyRelease();
        break;

    case ACTION_PROFILE_TOGGLE:
        // Toggle between Mac ↔ Android profile
        activeProfile = (activeProfile == PROFILE_MAC) ? PROFILE_ANDROID : PROFILE_MAC;
        break;

    case ACTION_NONE:
    default:
        break;
    }
}
