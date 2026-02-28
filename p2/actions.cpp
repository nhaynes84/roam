// Roam P2 — HID action implementation (Bluefruit BLEHidAdafruit)

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

void executeAction(ActionType action) {
    switch (action) {

    case ACTION_DICTATION:
        // macOS dictation consumer key 0x00CF
        blehid.consumerKeyPress(0, 0x00CF);
        delay(50);
        blehid.consumerKeyRelease(0);
        break;

    case ACTION_TMUX_PANE:
        // Ctrl+B then 'o' — tmux next pane
        blehid.keyPress(0, HID_KEY_B, KEYBOARD_MODIFIER_LEFTCTRL);
        keystrokeDelay();
        blehid.keyRelease(0);
        delay(50);
        blehid.keyPress(0, HID_KEY_O);
        keystrokeDelay();
        blehid.keyRelease(0);
        break;

    case ACTION_CYCLE_MODE:
        // Shift+Tab — cycle mode
        blehid.keyPress(0, HID_KEY_TAB, KEYBOARD_MODIFIER_LEFTSHIFT);
        delay(50);
        blehid.keyRelease(0);
        break;

    case ACTION_BLE_SWITCH:
        // Disconnect BLE — Bluefruit will re-advertise
        Bluefruit.disconnect(Bluefruit.connHandle());
        delay(200);
        Bluefruit.Advertising.start(0);
        break;

    case ACTION_APPROVE_YES:
        // 'y' then Enter
        blehid.keyPress(0, HID_KEY_Y);
        keystrokeDelay();
        blehid.keyRelease(0);
        keystrokeDelay();
        blehid.keyPress(0, HID_KEY_ENTER);
        keystrokeDelay();
        blehid.keyRelease(0);
        break;

    case ACTION_APPROVE_ALWAYS:
        // Tab then Enter — select "Always allow"
        blehid.keyPress(0, HID_KEY_TAB);
        keystrokeDelay();
        blehid.keyRelease(0);
        keystrokeDelay();
        blehid.keyPress(0, HID_KEY_ENTER);
        keystrokeDelay();
        blehid.keyRelease(0);
        break;

    case ACTION_REJECT_ESCAPE:
        // Escape
        blehid.keyPress(0, HID_KEY_ESCAPE);
        delay(50);
        blehid.keyRelease(0);
        break;

    case ACTION_KILL_PROCESS:
        // Ctrl+C
        blehid.keyPress(0, HID_KEY_C, KEYBOARD_MODIFIER_LEFTCTRL);
        delay(50);
        blehid.keyRelease(0);
        break;

    case ACTION_ENTER:
        blehid.keyPress(0, HID_KEY_ENTER);
        delay(50);
        blehid.keyRelease(0);
        break;

    case ACTION_NONE:
    default:
        break;
    }
}
