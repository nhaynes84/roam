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
#include "audio_stream.h"

BLEHidAdafruit blehid;
BLEDis bledis;   // Device Information Service

static ButtonManager buttons;
static Button scrollFwd;
static Button scrollBack;
static Display display;
static Battery battery;

// Active profile. Phone-relay mode keeps Android as the only live BLE peer.
#if ROAM_PHONE_RELAY_MODE
volatile Profile activeProfile = PROFILE_ANDROID;
#else
volatile Profile activeProfile = PROFILE_MAC;
#endif

// Known device MAC (first 3 bytes = OUI). Set to 0 to match any.
// After pairing your Android phone, replace with its MAC.
// Format: {0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF}
static uint8_t knownMacMAC[6]     = {0};  // Will be learned on first Mac connection
static uint8_t knownAndroidMAC[6] = {0};  // Will be learned on first Android connection
static bool macLearned = false;
static bool androidLearned = false;

// LED state — can be toggled by user, auto-off on sleep
static bool ledEnabled = true;
static uint32_t lastAdvertisingCheck = 0;

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

    // Phone-relay mode: Android owns BLE; Mac receives traffic through Android.
    Profile prev = activeProfile;
#if ROAM_PHONE_RELAY_MODE
    activeProfile = PROFILE_ANDROID;
    display.setBleConnected(true);
    display.setProfileName(PROFILE_NAMES[activeProfile]);
    if (activeProfile != prev) {
        display.showAction(PROFILE_NAMES[activeProfile]);
    }
    Serial.println("Profile: Android (phone relay mode)");
    return;
#else
    // Auto-detect profile by MAC.
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
#endif
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
    Bluefruit.configPrphBandwidth(BANDWIDTH_MAX);
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
    if (!bleText.addToAdvertising()) {
        Serial.println("ble_text: WARNING text service not added to advertising");
    }
    Bluefruit.ScanResponse.addName();
    Bluefruit.Advertising.restartOnDisconnect(true);
    Bluefruit.Advertising.setInterval(32, 244);  // in units of 0.625ms
    Bluefruit.Advertising.setFastTimeout(30);     // fast mode for 30 seconds
    Bluefruit.Advertising.start(0);               // advertise forever
    Serial.println("BLE advertising as 'Roam2' with HID + text service");

    // --- Peripherals ---
    display.begin();
    display.setBleConnected(false);
    display.setProfileName(PROFILE_NAMES[activeProfile]);
    imuBegin();  // After display — swaps TWIM1 pins temporarily, then restores
    battery.begin();
    audioStream.begin();
    buttons.begin();
    scrollFwd.begin(PIN_BTN_SCROLL_FWD, 0);
    scrollBack.begin(PIN_BTN_SCROLL_BACK, 0);
}

void loop() {
    static uint32_t lastStatus = 0;
    static uint32_t lastRender = 0;
    bool connected = Bluefruit.connected();

    if (!connected && (millis() - lastAdvertisingCheck) > 1000) {
        lastAdvertisingCheck = millis();
        if (!Bluefruit.Advertising.isRunning()) {
            Bluefruit.Advertising.start(0);
            Serial.println("BLE: Advertising watchdog restarted advertising");
        }
    }

    // LED: off when sleeping or disabled, solid when connected, blink when advertising
    static uint32_t lastBlink = 0;
    static bool ledState = false;
    uint32_t idleNow = millis() - display.lastActivityTime();
    bool sleeping = idleNow >= SCREEN_OFF_MS;

    if (!ledEnabled || sleeping) {
        digitalWrite(LED_BUILTIN, HIGH);       // Off (active low)
        digitalWrite(ROAM_LED_PIN, LOW);       // Off (active high)
    } else if (connected) {
        digitalWrite(LED_BUILTIN, LOW);        // Solid on (active low)
        digitalWrite(ROAM_LED_PIN, HIGH);      // Solid on (active high)
    } else {
        if (millis() - lastBlink > 500) {
            ledState = !ledState;
            digitalWrite(LED_BUILTIN, ledState ? LOW : HIGH);
            digitalWrite(ROAM_LED_PIN, ledState ? HIGH : LOW);
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
        if (sfEvt == BTN_EVENT_LONG)
            action = ACTION_CLEAR_MSGS;
        else if (sfEvt == BTN_EVENT_SHORT)
            action = ACTION_SCROLL_FWD;
        else if (sbEvt == BTN_EVENT_SHORT || sbEvt == BTN_EVENT_LONG)
            action = ACTION_SCROLL_BACK;
    }

    if (action != ACTION_NONE) {
        bleText.notifyEvent(RELAY_EVENT_ACTION, (uint8_t)action, (uint8_t)activeProfile, millis());
        display.wake();  // Any button press wakes screen
        if (action == ACTION_CLEAR_MSGS) {
            display.clearMessages();
            display.showAction("Cleared");
            digitalWrite(PIN_MOTOR, HIGH);
            delay(80);
            digitalWrite(PIN_MOTOR, LOW);
            Serial.println("action: clear messages");
        } else if (action == ACTION_SCROLL_FWD || action == ACTION_SCROLL_BACK) {
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
        }
#if ROAM_PHONE_RELAY_MODE
        else if (action == ACTION_DICTATION_ANDROID) {
            // In phone-relay mode this button notifies Android over FF02; Android
            // starts/stops FF03 mic streaming over FF04.
            display.showAction("Mic Toggle");
            digitalWrite(PIN_MOTOR, HIGH);
            delay(40);
            digitalWrite(PIN_MOTOR, LOW);
            Serial.println("action: relay dictation toggle");
        }
        else if (action == ACTION_BLE_SWITCH) {
            executeAction(action);
            digitalWrite(PIN_MOTOR, HIGH);
            delay(80);
            digitalWrite(PIN_MOTOR, LOW);
            display.showAction(ACTION_NAMES[action]);
            Serial.println("action: BLE switch");
        } else {
            // Phone-relay mode sends Mac commands through Android -> Wi-Fi -> receiver.
            // Do not emit BLE HID to Android for these actions.
            digitalWrite(PIN_MOTOR, HIGH);
            delay(action == ACTION_TMUX_PANE ? 25 : 80);
            digitalWrite(PIN_MOTOR, LOW);
            display.showAction(ACTION_NAMES[action]);
            Serial.printf("action: relay command %s\n", ACTION_NAMES[action]);
        }
#else
        else if (connected) {
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
#endif
    }

    // Battery monitor (every 60s)
    if (battery.shouldRead()) {
        battery.read();
        display.setBatteryPercent(battery.percent());
        // USB power detection — battery icon handles visual feedback
    }

    // Check for BLE text pushes
    if (bleText.hasNewText()) {
        const char* raw = bleText.getText();
        uint8_t pane = MSG_PANE_GLOBAL;
        const char* text = raw;

        // Parse pane prefix: \x01 + pane_byte + text
        if (raw[0] == '\x01' && raw[1] != '\0') {
            pane = (uint8_t)raw[1];
            text = raw + 2;
        }

        // Pane-switch messages set the active filter, stored as global
        if (strncmp(text, "Pane ", 5) == 0) {
            display.setActivePane(pane);
            display.pushMessage(text);  // global
        } else {
            display.pushMessage(text, pane);
        }

        digitalWrite(PIN_MOTOR, HIGH);
        delay(60);
        digitalWrite(PIN_MOTOR, LOW);
        delay(80);
        digitalWrite(PIN_MOTOR, HIGH);
        delay(60);
        digitalWrite(PIN_MOTOR, LOW);
        Serial.printf("ble_text: pane=%d \"%s\"\n", pane, text);
    }

    if (bleText.hasControlCommand()) {
        uint8_t cmd = bleText.getControlCommand();
        if (cmd == RELAY_CONTROL_START_AUDIO) {
            if (audioStream.start()) {
                bleText.notifyEvent(RELAY_EVENT_PTT_START, 0, (uint8_t)activeProfile, millis());
                display.showAction("Mic On");
                display.wake();
            }
        } else if (cmd == RELAY_CONTROL_STOP_AUDIO) {
            audioStream.stop();
            bleText.notifyEvent(RELAY_EVENT_PTT_STOP, 0, (uint8_t)activeProfile, millis());
            display.showAction("Mic Off");
            display.wake();
        } else if (cmd == RELAY_CONTROL_STATUS_REQUEST) {
            bleText.notifyEvent(RELAY_EVENT_STATUS, 0, (uint8_t)activeProfile, millis());
        }
        Serial.printf("ble_relay: control=%u\n", cmd);
    }

    audioStream.poll(bleText);

    // IMU wake-on-motion — wrist rotation wakes screen
    if (imuWoke()) {
        display.wake();
    }

    // Screen sleep timer — recompute idle after all wake sources
    idleNow = millis() - display.lastActivityTime();
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
