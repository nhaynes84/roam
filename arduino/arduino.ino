// Roam — Arduino-pico BLE HID Firmware
// Pimoroni Pico Plus 2 W (RP2350 + CYW43439)
// Single-core build — BLE + buttons + actions + display
// Board: rp2040:rp2040:pimoroni_pico_plus_2w:ipbtstack=ipv4btcble

#include <KeyboardBLE.h>
#include <PicoBluetoothBLEHID.h>
#include "config.h"
#include "buttons.h"
#include "actions.h"
#include "display.h"
#include "battery.h"
#include "ble_text.h"

static ButtonManager buttons;
static Display display;
static Battery battery;

void setup() {
    Serial.begin(115200);
    delay(1000);

    pinMode(ROAM_LED_PIN, OUTPUT);
    pinMode(PIN_MOTOR, OUTPUT);
    digitalWrite(PIN_MOTOR, LOW);

    Serial.println("Starting BLE keyboard...");
    KeyboardBLE.begin("Roam", "Roam");
    Serial.println("BLE started, advertising as 'Roam'");

    // Add custom GATT text service (must be after KeyboardBLE.begin)
    bleText.begin();

    Serial.println("Initializing display...");
    display.begin();
    Serial.println("Display init done");

    display.setBleStatus("Advertising");
    battery.begin();
    buttons.begin();
}

void loop() {
    static uint32_t lastStatus = 0;
    static uint32_t lastRender = 0;
    static bool wasConnected = false;
    bool connected = PicoBluetoothBLEHID.connected();

    // LED: solid when connected, blink when advertising
    static uint32_t lastBlink = 0;
    static bool ledState = false;
    if (connected) {
        digitalWrite(ROAM_LED_PIN, HIGH);
    } else {
        if (millis() - lastBlink > 500) {
            ledState = !ledState;
            digitalWrite(ROAM_LED_PIN, ledState ? HIGH : LOW);
            lastBlink = millis();
        }
    }

    // BLE status change
    if (connected != wasConnected) {
        wasConnected = connected;
        display.setBleStatus(connected ? "Connected" : "Advertising");
    }

    // Print BLE status every 2 seconds
    if (millis() - lastStatus > 2000) {
        Serial.printf("BLE: %s\n", connected ? "CONNECTED" : "advertising...");
        lastStatus = millis();
    }

    // Poll buttons
    ActionType action = ACTION_NONE;
    buttons.poll(action);

    if (action != ACTION_NONE) {
        if (action == ACTION_TOGGLE_SCREEN) {
            // Local action — no HID, no connection required
            display.toggleScreen();
            digitalWrite(PIN_MOTOR, HIGH);
            delay(40);
            digitalWrite(PIN_MOTOR, LOW);
            Serial.printf("action: toggle screen (%s)\n",
                          display.inMessageMode() ? "message" : "status");
        } else if (connected) {
            executeAction(action);

            // Short motor buzz
            digitalWrite(PIN_MOTOR, HIGH);
            delay(80);
            digitalWrite(PIN_MOTOR, LOW);

            display.showAction(ACTION_NAMES[action]);
            Serial.printf("action: %s\n", ACTION_NAMES[action]);
        } else {
            Serial.printf("action: %s (not connected)\n", ACTION_NAMES[action]);
        }
    }

    // Battery monitor (every 60s)
    if (battery.shouldRead()) {
        battery.read();
        display.setBatteryPercent(battery.percent());
        if (battery.voltage() > 4.5f) {
            display.setBleStatus(connected ? "Connected (USB)" : "Charging");
        }
    }

    // Check for BLE text pushes
    if (bleText.hasNewText()) {
        const char* text = bleText.getText();
        display.showBleText(text);
        Serial.printf("ble_text: \"%s\"\n", text);
    }

    // Render display at 10 Hz
    if ((millis() - lastRender) >= DISPLAY_PERIOD_MS) {
        lastRender = millis();
        display.render();
    }

    delay(10);
}
