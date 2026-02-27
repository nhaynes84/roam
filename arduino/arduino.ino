// Roam — Arduino-pico BLE HID Firmware
// Pimoroni Pico Plus 2 W (RP2350 + CYW43439)
//
// Dual-core architecture:
//   Core 0: BLE HID + button polling + HID dispatch + haptic trigger
//   Core 1: OLED display + battery monitor + LED patterns
//
// Board: rp2040:rp2040:pimoroni_pico_plus_2w:ipbtstack=ipv4btcble
// Requires: KeyboardBLE (built-in), U8g2

#include <KeyboardBLE.h>
#include <PicoBluetoothBLEHID.h>
#include "config.h"
#include "buttons.h"
#include "actions.h"
#include "display.h"
#include "haptic.h"
#include "led.h"
#include "battery.h"

// --- Separate 8KB stack for core 1 ---
bool core1_separate_stack = true;

// --- Shared state (cross-core, mutex-protected) ---
struct SharedState {
    bool bleConnected;
    uint8_t batteryPercent;
    char lastAction[20];
    bool actionPending;  // Flag for display to pick up new actions
};

auto_init_mutex(stateMutex);
static volatile SharedState shared = {false, 0, "", false};

// --- Core 0 objects ---
static ButtonManager buttons;
static Haptic haptic;

// --- Core 1 objects ---
static Display display;
static StatusLED led;
static Battery battery;

// ============================================================
// Core 0 — BLE + Buttons + Haptic
// ============================================================

void setup() {
    Serial.begin(115200);

    // Start BLE keyboard
    KeyboardBLE.begin("Roam", "Roam");
    Serial.println("core0: BLE keyboard started");

    buttons.begin();
    haptic.begin();
    actionsBegin();
}

void loop() {
    static uint32_t lastPoll = 0;
    uint32_t now = micros();

    // Poll buttons at 100 Hz
    if ((now - lastPoll) < BUTTON_POLL_US) {
        haptic.update();
        return;
    }
    lastPoll = now;

    // Check BLE connection state
    bool connected = PicoBluetoothBLEHID.connected();
    {
        CoreMutex m(&stateMutex);
        if (m) {
            shared.bleConnected = connected;
        }
    }

    // Poll buttons
    ActionType action = ACTION_NONE;
    buttons.poll(action);

    if (action != ACTION_NONE && connected) {
        // Execute the HID action
        executeAction(action);

        // Trigger haptic feedback
        if (action == ACTION_BLE_SWITCH) {
            haptic.play(HAPTIC_DOUBLE_TAP);
        } else {
            haptic.play(HAPTIC_SHORT_BUZZ);
        }

        // Share action name with core 1 for display
        const char* name = ACTION_NAMES[action];
        {
            CoreMutex m(&stateMutex);
            if (m) {
                strncpy((char*)shared.lastAction, name, sizeof(shared.lastAction) - 1);
                ((char*)shared.lastAction)[sizeof(shared.lastAction) - 1] = '\0';
                shared.actionPending = true;
            }
        }

        Serial.printf("action: %s\n", name);
    } else if (action != ACTION_NONE && !connected) {
        // Not connected — error buzz
        haptic.play(HAPTIC_ERROR);
        Serial.println("action: not connected");
    }

    haptic.update();
}

// ============================================================
// Core 1 — Display + Battery + LED
// ============================================================

void setup1() {
    display.begin();
    led.begin();
    battery.begin();

    // Initial battery read
    battery.read();

    {
        CoreMutex m(&stateMutex);
        if (m) {
            shared.batteryPercent = battery.percent();
        }
    }

    display.setBatteryPercent(battery.percent());
    display.setBleStatus("Advertising");
    led.setPattern(LED_SLOW_BLINK);
}

void loop1() {
    static uint32_t lastRender = 0;
    static bool wasConnected = false;
    uint32_t now = millis();

    // --- Read shared state ---
    bool bleConnected;
    bool actionPending;
    char actionName[20];

    {
        CoreMutex m(&stateMutex);
        if (m) {
            bleConnected = shared.bleConnected;
            actionPending = shared.actionPending;
            if (actionPending) {
                strncpy(actionName, (const char*)shared.lastAction, sizeof(actionName));
                actionName[sizeof(actionName) - 1] = '\0';
                shared.actionPending = false;
            }
        }
    }

    // --- BLE status change ---
    if (bleConnected != wasConnected) {
        wasConnected = bleConnected;
        if (bleConnected) {
            display.setBleStatus("Connected");
            led.setPattern(LED_SOLID);
            haptic.play(HAPTIC_CONNECTED);
        } else {
            display.setBleStatus("Advertising");
            led.setPattern(LED_SLOW_BLINK);
        }
    }

    // --- Action display ---
    if (actionPending) {
        display.showAction(actionName);
    }

    // --- Battery ---
    if (battery.shouldRead()) {
        battery.read();
        display.setBatteryPercent(battery.percent());

        {
            CoreMutex m(&stateMutex);
            if (m) {
                shared.batteryPercent = battery.percent();
            }
        }

        // Update BLE battery service
        KeyboardBLE.setBattery(battery.percent());

        // Low battery LED override
        if (battery.isLow() && !bleConnected) {
            led.setPattern(LED_DIM_PULSE);
        }
    }

    // --- LED ---
    led.update();

    // --- Display at 10 Hz ---
    if ((now - lastRender) >= DISPLAY_PERIOD_MS) {
        lastRender = now;
        display.render();
    }
}
