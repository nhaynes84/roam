// OLED test — U8g2 HW_I2C @ 5V VCC, no BLE
#include <Wire.h>
#include <U8g2lib.h>

U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE);

void setup() {
    Serial.begin(115200);
    delay(2000);
    Serial.println("U8g2 HW_I2C @ 5V");

    Wire.setSDA(4);
    Wire.setSCL(5);
    Wire.setClock(400000);
    Wire.begin();

    u8g2.setI2CAddress(0x3C << 1);
    Serial.println("calling begin...");
    u8g2.begin();
    Serial.println("begin done");

    u8g2.clearBuffer();
    u8g2.setFont(u8g2_font_ncenB14_tr);
    u8g2.drawStr(10, 25, "Roam");
    u8g2.setFont(u8g2_font_6x10_tr);
    u8g2.drawStr(10, 45, "BLE: Connected");
    u8g2.drawStr(10, 60, "Action: Dictation");
    u8g2.sendBuffer();
    Serial.println("rendered");
}

void loop() {
    static uint32_t last = 0;
    if (millis() - last > 2000) {
        Serial.println("alive");
        last = millis();
    }
}
