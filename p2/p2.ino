// Roam P2 — Bluefruit BLE HID Firmware
// Seeed XIAO nRF52840 Sense (nRF52840 + BLE 5.0)
// Board: Seeeduino:nrf52:xiaonRF52840Sense

#include <bluefruit.h>
#include "config.h"
#include "buttons.h"
#include "actions.h"
#include "display.h"
#include "battery.h"
#include "ble_text.h"

BLEHidAdafruit blehid;
BLEDis bledis;   // Device Information Service

static ButtonManager buttons;
static Display display;
static Battery battery;

// --- BLE callbacks ---
void connect_callback(uint16_t conn_handle) {
    (void)conn_handle;
    Serial.println("BLE: CONNECTED");
    display.setBleStatus("Connected");
}

void disconnect_callback(uint16_t conn_handle, uint8_t reason) {
    (void)conn_handle;
    (void)reason;
    Serial.println("BLE: Disconnected, re-advertising");
    display.setBleStatus("Advertising");
}

void setup() {
    Serial.begin(115200);
    delay(1000);

    pinMode(ROAM_LED_PIN, OUTPUT);
    pinMode(PIN_MOTOR, OUTPUT);
    digitalWrite(PIN_MOTOR, LOW);

    // --- BLE Init ---
    Bluefruit.begin();
    Bluefruit.setTxPower(4);
    Bluefruit.setName("Roam2");
    Bluefruit.Periph.setConnectCallback(connect_callback);
    Bluefruit.Periph.setDisconnectCallback(disconnect_callback);

    // Device Information Service
    bledis.setManufacturer("Roam");
    bledis.setModel("P2");
    bledis.begin();

    // HID Keyboard
    blehid.begin();
    Serial.println("BLE HID started");

    // Custom text service (must be after blehid.begin)
    bleText.begin();

    // --- Advertising ---
    Bluefruit.Advertising.addFlags(BLE_GAP_ADV_FLAGS_LE_ONLY_GENERAL_DISC_MODE);
    Bluefruit.Advertising.addTxPower();
    Bluefruit.Advertising.addAppearance(BLE_APPEARANCE_HID_KEYBOARD);
    Bluefruit.Advertising.addService(blehid);
    Bluefruit.Advertising.addName();
    Bluefruit.Advertising.restartOnDisconnect(true);
    Bluefruit.Advertising.setInterval(32, 244);  // in units of 0.625ms
    Bluefruit.Advertising.setFastTimeout(30);     // fast mode for 30 seconds
    Bluefruit.Advertising.start(0);               // advertise forever
    Serial.println("BLE advertising as 'Roam'");

    // --- Peripherals ---
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
    bool connected = Bluefruit.connected();

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
