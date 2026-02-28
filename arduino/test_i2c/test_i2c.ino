// I2C bus scanner — finds all devices on GP4(SDA)/GP5(SCL)
#include <Wire.h>

void setup() {
    Serial.begin(115200);
    delay(2000);

    Wire.setSDA(4);
    Wire.setSCL(5);
    Wire.setClock(400000);
    Wire.begin();

    Serial.println("I2C Scanner — scanning GP4(SDA) GP5(SCL)...");
}

void loop() {
    int found = 0;
    for (uint8_t addr = 1; addr < 127; addr++) {
        Wire.beginTransmission(addr);
        uint8_t err = Wire.endTransmission();
        if (err == 0) {
            Serial.printf("  Found device at 0x%02X\n", addr);
            found++;
        }
    }

    if (found == 0) {
        Serial.println("  No I2C devices found.");
    } else {
        Serial.printf("  %d device(s) found.\n", found);
    }

    Serial.println("---");
    delay(3000);
}
