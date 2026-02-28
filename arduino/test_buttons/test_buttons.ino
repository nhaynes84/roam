// Button + BLE debug test
// Prints button events AND BLE connection state to serial
// Sends simple keystrokes to verify HID works
// LED on GP16 lights on button press as visual feedback

#include <KeyboardBLE.h>
#include <PicoBluetoothBLEHID.h>

void setup() {
    Serial.begin(115200);
    delay(1000);

    pinMode(10, INPUT_PULLUP);
    pinMode(11, INPUT_PULLUP);
    pinMode(12, INPUT_PULLUP);
    pinMode(13, INPUT_PULLUP);
    pinMode(16, OUTPUT);

    Serial.println("Starting BLE keyboard...");
    KeyboardBLE.begin("Roam", "Roam");
    Serial.println("BLE started, advertising as 'Roam'");
}

static bool lastBtn[4] = {true, true, true, true};
static uint8_t pins[4] = {10, 11, 12, 13};
static const char keys[4] = {'a', 'b', 'c', 'd'};

void loop() {
    static uint32_t lastStatus = 0;
    bool connected = PicoBluetoothBLEHID.connected();

    // Print BLE status every 2 seconds
    if (millis() - lastStatus > 2000) {
        Serial.printf("BLE: %s\n", connected ? "CONNECTED" : "advertising...");
        lastStatus = millis();
    }

    for (int i = 0; i < 4; i++) {
        bool state = digitalRead(pins[i]);
        if (state != lastBtn[i]) {
            lastBtn[i] = state;
            if (!state) {
                digitalWrite(16, HIGH);
                Serial.printf("GP%d PRESSED  (BLE %s)\n", pins[i],
                    connected ? "CONNECTED" : "NOT CONNECTED");

                if (connected) {
                    KeyboardBLE.press(keys[i]);
                    delay(50);
                    KeyboardBLE.releaseAll();
                    Serial.printf("  -> sent '%c'\n", keys[i]);
                }
            } else {
                digitalWrite(16, LOW);
            }
        }
    }
    delay(10);
}
