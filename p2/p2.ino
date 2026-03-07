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
#include "imu.h"

BLEHidAdafruit blehid;
BLEDis bledis;   // Device Information Service

static ButtonManager buttons;
static Button scrollFwd;
static Button scrollBack;
static Display display;
static Battery battery;

// Active profile — defaults to Mac, auto-switches on connect
volatile Profile activeProfile = PROFILE_MAC;

// Known device MAC (first 3 bytes = OUI). Set to 0 to match any.
// After pairing your Android phone, replace with its MAC.
// Format: {0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF}
static uint8_t knownMacMAC[6]     = {0};  // Will be learned on first Mac connection
static uint8_t knownAndroidMAC[6] = {0};  // Will be learned on first Android connection
static bool macLearned = false;
static bool androidLearned = false;

// LED state — can be toggled by user, auto-off on sleep
static bool ledEnabled = true;

void bleSwitch() {
    // Remove bond for current peer so it can't auto-reconnect
    if (Bluefruit.connected()) {
        BLEConnection* conn = Bluefruit.Connection(Bluefruit.connHandle());
        conn->removeBondKey();
        Serial.println("BLE Switch: bond removed for current peer");
        Bluefruit.disconnect(Bluefruit.connHandle());
    }
    delay(200);
    Bluefruit.Advertising.start(0);
}

// --- BLE callbacks ---
void connect_callback(uint16_t conn_handle) {
    BLEConnection* conn = Bluefruit.Connection(conn_handle);
    uint8_t addr[6];
    ble_gap_addr_t peer = conn->getPeerAddr();
    memcpy(addr, peer.addr, 6);

    Serial.printf("BLE: CONNECTED [%02X:%02X:%02X:%02X:%02X:%02X]\n",
                  addr[5], addr[4], addr[3], addr[2], addr[1], addr[0]);

    // Auto-detect profile by MAC
    Profile prev = activeProfile;
    if (macLearned && memcmp(addr, knownMacMAC, 6) == 0) {
        activeProfile = PROFILE_MAC;
    } else if (androidLearned && memcmp(addr, knownAndroidMAC, 6) == 0) {
        activeProfile = PROFILE_ANDROID;
    } else if (!macLearned) {
        // First unknown device → assume Mac
        memcpy(knownMacMAC, addr, 6);
        macLearned = true;
        activeProfile = PROFILE_MAC;
        Serial.println("Learned Mac MAC");
    } else if (!androidLearned) {
        // Second unknown device → assume Android
        memcpy(knownAndroidMAC, addr, 6);
        androidLearned = true;
        activeProfile = PROFILE_ANDROID;
        Serial.println("Learned Android MAC");
    }

    display.setBleConnected(true);
    display.setProfileName(PROFILE_NAMES[activeProfile]);
    if (activeProfile != prev || !macLearned) {
        display.showAction(PROFILE_NAMES[activeProfile]);
    }
    Serial.printf("Profile: %s\n", PROFILE_NAMES[activeProfile]);
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
    display.setProfileName(PROFILE_NAMES[activeProfile]);
    imuBegin();  // After display — swaps TWIM1 pins temporarily, then restores
    battery.begin();
    buttons.begin();
    scrollFwd.begin(PIN_BTN_SCROLL_FWD, 0);
    scrollBack.begin(PIN_BTN_SCROLL_BACK, 0);
}

void loop() {
    static uint32_t lastStatus = 0;
    static uint32_t lastRender = 0;
    bool connected = Bluefruit.connected();

    // LED: off when sleeping or disabled, solid when connected, blink when advertising
    static uint32_t lastBlink = 0;
    static bool ledState = false;
    uint32_t idleNow = millis() - display.lastActivityTime();
    bool sleeping = idleNow >= SCREEN_OFF_MS;

    if (!ledEnabled || sleeping) {
        digitalWrite(LED_BUILTIN, HIGH);  // Off (active low)
    } else if (connected) {
        digitalWrite(LED_BUILTIN, LOW);   // Solid on (active low)
    } else {
        if (millis() - lastBlink > 500) {
            ledState = !ledState;
            digitalWrite(LED_BUILTIN, ledState ? LOW : HIGH);
            lastBlink = millis();
        }
    }

    // Print status every 2 seconds
    if (millis() - lastStatus > 2000) {
        display.printDiag();
        Serial.printf("imu_ready=%d\n", imuReady());
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
        } else if (action == ACTION_LED_TOGGLE) {
            // Local action — toggle status LED
            ledEnabled = !ledEnabled;
            display.showAction(ledEnabled ? "LED On" : "LED Off");
            digitalWrite(PIN_MOTOR, HIGH);
            delay(40);
            digitalWrite(PIN_MOTOR, LOW);
            Serial.printf("action: LED %s\n", ledEnabled ? "on" : "off");
        } else if (action == ACTION_PROFILE_TOGGLE) {
            // Local action — no connection required
            executeAction(action);
            display.showAction(PROFILE_NAMES[activeProfile]);
            display.setProfileName(PROFILE_NAMES[activeProfile]);
            digitalWrite(PIN_MOTOR, HIGH);
            delay(60);
            digitalWrite(PIN_MOTOR, LOW);
            Serial.printf("action: profile -> %s\n", PROFILE_NAMES[activeProfile]);
        } else if (connected) {
            executeAction(action);

            // Haptic feedback — quick pulse for pane switch, standard for rest
            digitalWrite(PIN_MOTOR, HIGH);
            delay(action == ACTION_TMUX_PANE ? 25 : 80);
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

    // IMU wake-on-motion — wrist rotation wakes screen
    if (imuWoke()) {
        display.wake();
    }

    // Screen sleep timer (reuse idleNow from LED section)
    if (idleNow >= SCREEN_OFF_MS) {
        display.powerOff();
    } else if (idleNow >= SCREEN_DIM_MS) {
        display.dim();
    }

    // Render display at 10 Hz
    if ((millis() - lastRender) >= DISPLAY_PERIOD_MS) {
        lastRender = millis();
        display.render();
    }

    delay(10);
}
