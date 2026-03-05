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
static Button scrollFwd;
static Button scrollBack;
static Display display;
static Battery battery;

// --- BLE callbacks ---
void connect_callback(uint16_t conn_handle) {
    (void)conn_handle;
    Serial.println("BLE: CONNECTED");
    display.setBleConnected(true);
}

void disconnect_callback(uint16_t conn_handle, uint8_t reason) {
    (void)conn_handle;
    (void)reason;
    Serial.println("BLE: Disconnected, re-advertising");
    display.setBleConnected(false);
}

void setup() {
    Serial.begin(115200);
    delay(500);

    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, HIGH);  // Off (active low)
    pinMode(ROAM_LED_PIN, OUTPUT);
    pinMode(PIN_MOTOR, OUTPUT);
    digitalWrite(PIN_MOTOR, LOW);

    Serial.println("=== Roam P2 boot ===");

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
    display.begin();
    display.setBleConnected(false);
    battery.begin();
    buttons.begin();
    scrollFwd.begin(PIN_BTN_SCROLL_FWD, 0);
    scrollBack.begin(PIN_BTN_SCROLL_BACK, 0);
}

void loop() {
    static uint32_t lastStatus = 0;
    static uint32_t lastRender = 0;
    bool connected = Bluefruit.connected();

    // LED: solid when connected, blink when advertising
    static uint32_t lastBlink = 0;
    static bool ledState = false;
    if (connected) {
        digitalWrite(LED_BUILTIN, LOW);  // Solid on (active low)
    } else {
        if (millis() - lastBlink > 500) {
            ledState = !ledState;
            digitalWrite(LED_BUILTIN, ledState ? LOW : HIGH);  // Active low
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

    // Always poll scroll buttons to keep debounce state current
    ButtonEvent sfEvt = scrollFwd.poll();
    ButtonEvent sbEvt = scrollBack.poll();
    if (action == ACTION_NONE) {
        if (sfEvt == BTN_EVENT_SHORT || sfEvt == BTN_EVENT_LONG)
            action = ACTION_SCROLL_FWD;
        else if (sbEvt == BTN_EVENT_SHORT || sbEvt == BTN_EVENT_LONG)
            action = ACTION_SCROLL_BACK;
    }

    if (action != ACTION_NONE) {
        display.wake();  // Any button press wakes screen
        if (action == ACTION_SCROLL_FWD || action == ACTION_SCROLL_BACK) {
            // Local action — no HID, no connection required
            if (action == ACTION_SCROLL_FWD) display.scrollFwd();
            else display.scrollBack();
            display.wake();
            digitalWrite(PIN_MOTOR, HIGH);
            delay(40);
            digitalWrite(PIN_MOTOR, LOW);
            Serial.printf("action: scroll %s\n",
                          action == ACTION_SCROLL_FWD ? "fwd" : "back");
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
        // USB power detection — battery icon handles visual feedback
    }

    // Check for BLE text pushes
    if (bleText.hasNewText()) {
        const char* text = bleText.getText();
        display.pushMessage(text);
        digitalWrite(PIN_MOTOR, HIGH);
        delay(60);
        digitalWrite(PIN_MOTOR, LOW);
        delay(80);
        digitalWrite(PIN_MOTOR, HIGH);
        delay(60);
        digitalWrite(PIN_MOTOR, LOW);
        Serial.printf("ble_text: \"%s\"\n", text);
    }

    // Screen sleep timer
    uint32_t idle = millis() - display.lastActivityTime();
    if (idle >= SCREEN_OFF_MS) {
        display.powerOff();
    } else if (idle >= SCREEN_DIM_MS) {
        display.dim();
    }

    // Render display at 10 Hz
    if ((millis() - lastRender) >= DISPLAY_PERIOD_MS) {
        lastRender = millis();
        display.render();
    }

    delay(10);
}
