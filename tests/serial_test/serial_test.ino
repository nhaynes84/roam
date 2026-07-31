#include <bluefruit.h>

void setup() {
    Serial.begin(115200);
    while (!Serial) delay(10);
    Serial.println("XIAO serial OK");
}

void loop() {
    Serial.println("ping");
    delay(2000);
}
