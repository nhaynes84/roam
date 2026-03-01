// Bare minimum LED blink — no I2C, no Wire
#include <bluefruit.h>

void setup() {
    pinMode(LED_BUILTIN, OUTPUT);
}

void loop() {
    digitalWrite(LED_BUILTIN, LOW);   // ON (active low)
    delay(200);
    digitalWrite(LED_BUILTIN, HIGH);  // OFF
    delay(200);
}
