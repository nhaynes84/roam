// Roam — HID action implementation

#include "actions.h"

void actionsBegin() {
    // KeyboardBLE.begin() is called in roam.ino — nothing extra needed here
}

// Small delay between keystrokes in a sequence
static void keystrokeDelay() {
    delay(30);
}

void executeAction(ActionType action) {
    switch (action) {

    case ACTION_DICTATION:
        // macOS dictation consumer key 0x00CF
        KeyboardBLE.consumerPress(0x00CF);
        delay(50);
        KeyboardBLE.consumerRelease();
        break;

    case ACTION_TMUX_PANE:
        // Ctrl+B then 'o' — tmux next pane
        KeyboardBLE.press(KEY_LEFT_CTRL);
        KeyboardBLE.press('b');
        keystrokeDelay();
        KeyboardBLE.releaseAll();
        delay(50);
        KeyboardBLE.press('o');
        keystrokeDelay();
        KeyboardBLE.releaseAll();
        break;

    case ACTION_CYCLE_MODE:
        // Shift+Tab — cycle mode
        KeyboardBLE.press(KEY_LEFT_SHIFT);
        KeyboardBLE.press(KEY_TAB);
        delay(50);
        KeyboardBLE.releaseAll();
        break;

    case ACTION_BLE_SWITCH:
        // Disconnect BLE — btstack will re-advertise automatically
        KeyboardBLE.end();
        delay(200);
        KeyboardBLE.begin("Roam", "Roam");
        break;

    case ACTION_APPROVE_YES:
        // 'y' then Enter
        KeyboardBLE.press('y');
        keystrokeDelay();
        KeyboardBLE.releaseAll();
        keystrokeDelay();
        KeyboardBLE.press(KEY_RETURN);
        keystrokeDelay();
        KeyboardBLE.releaseAll();
        break;

    case ACTION_APPROVE_ALWAYS:
        // Tab then Enter — select "Always allow"
        KeyboardBLE.press(KEY_TAB);
        keystrokeDelay();
        KeyboardBLE.releaseAll();
        keystrokeDelay();
        KeyboardBLE.press(KEY_RETURN);
        keystrokeDelay();
        KeyboardBLE.releaseAll();
        break;

    case ACTION_REJECT_ESCAPE:
        // Escape
        KeyboardBLE.press(KEY_ESC);
        delay(50);
        KeyboardBLE.releaseAll();
        break;

    case ACTION_KILL_PROCESS:
        // Ctrl+C
        KeyboardBLE.press(KEY_LEFT_CTRL);
        KeyboardBLE.press('c');
        delay(50);
        KeyboardBLE.releaseAll();
        break;

    case ACTION_NONE:
    default:
        break;
    }
}
