// I2C probe — LED diagnostics, no serial dependency
// XIAO nRF52840: LED_BUILTIN active LOW, LEDB/LEDG also available
#include <bluefruit.h>
#include <Wire.h>

void blink(int times, int on_ms, int off_ms) {
    for (int i = 0; i < times; i++) {
        digitalWrite(LED_BUILTIN, LOW);   // ON
        delay(on_ms);
        digitalWrite(LED_BUILTIN, HIGH);  // OFF
        delay(off_ms);
    }
}

void i2c_recover(uint8_t sda, uint8_t scl) {
    pinMode(sda, INPUT_PULLUP);
    pinMode(scl, OUTPUT);
    for (int i = 0; i < 9; i++) {
        if (digitalRead(sda)) break;
        digitalWrite(scl, LOW);
        delayMicroseconds(5);
        digitalWrite(scl, HIGH);
        delayMicroseconds(5);
    }
    pinMode(sda, OUTPUT);
    digitalWrite(sda, LOW);
    delayMicroseconds(5);
    digitalWrite(scl, HIGH);
    delayMicroseconds(5);
    digitalWrite(sda, HIGH);
    pinMode(sda, INPUT_PULLUP);
    pinMode(scl, INPUT_PULLUP);
}

void setup() {
    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, HIGH);  // OFF
    delay(1000);

    // Blink 1: alive
    blink(1, 500, 500);

    // Bus recovery
    i2c_recover(D4, D5);
    delay(100);

    // Blink 2: recovery done, about to Wire.begin
    blink(2, 300, 300);

    Wire.begin();

    // Blink 3: Wire.begin survived
    blink(3, 300, 300);

    // Probe 0x3C
    Wire.beginTransmission(0x3C);
    uint8_t err = Wire.endTransmission();

    // Blink 4: probe done
    blink(4, 300, 300);

    delay(1000);

    // Result: fast flicker = FOUND, slow pulse = NOT FOUND
    if (err == 0) {
        while (true) { blink(5, 100, 100); delay(800); }
    } else {
        while (true) { blink(1, 1000, 1000); }
    }
}

void loop() {}
