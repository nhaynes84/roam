// SSD1309 2.42" OLED — SPI test on XIAO nRF52840
// Wiring:
//   D4 = MOSI (DIN/SDA on module)
//   D5 = SCK  (CLK/SCL on module)
//   D1 = CS   (chip select)
//   D0 = DC   (data/command)
//   D2 = RST  (reset, optional — tie to 3.3V if not using)
//   VCC = 5V (from VUSB pin), GND = GND
//
// If screen stays dark, board is probably configured for I2C — try ssd1309_i2c_test
// Check BS0/BS1 resistors on the back of the module to confirm interface mode

#include <bluefruit.h>
#include <U8g2lib.h>
#include <SPI.h>

#define PIN_CS    1   // D1
#define PIN_DC    0   // D0
#define PIN_RST   2   // D2 (optional — set to U8X8_PIN_NONE if tied high)
#define PIN_MOSI  4   // D4
#define PIN_SCK   5   // D5

// U8g2 SSD1309 128x64 — full buffer, hardware SPI
// Constructor uses: rotation, cs, dc, reset
U8G2_SSD1309_128X64_NONAME2_F_4W_HW_SPI u8g2(U8G2_R0, PIN_CS, PIN_DC, PIN_RST);

void setup() {
    Serial.begin(115200);
    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, HIGH);  // off
    delay(2000);

    Serial.println("=== SSD1309 SPI Test ===");
    Serial.printf("MOSI=D%d  SCK=D%d  CS=D%d  DC=D%d  RST=D%d\n",
                  PIN_MOSI, PIN_SCK, PIN_CS, PIN_DC, PIN_RST);

    Bluefruit.begin();

    u8g2.begin();

    u8g2.clearBuffer();
    u8g2.setFont(u8g2_font_helvB12_tr);
    u8g2.drawStr(8, 20, "SSD1309 SPI");
    u8g2.setFont(u8g2_font_6x10_tr);
    u8g2.drawStr(8, 38, "HW SPI on XIAO nRF52840");
    u8g2.drawStr(8, 52, "128x64");
    u8g2.drawFrame(0, 0, 128, 64);
    u8g2.sendBuffer();

    Serial.println("Display initialized OK");
    digitalWrite(LED_BUILTIN, LOW);  // solid = success
}

void loop() {
    static uint32_t last = 0;
    static uint32_t count = 0;
    if (millis() - last > 1000) {
        last = millis();
        count++;
        u8g2.setFont(u8g2_font_6x10_tr);
        u8g2.setDrawColor(0);
        u8g2.drawBox(80, 55, 48, 10);
        u8g2.setDrawColor(1);
        char buf[16];
        snprintf(buf, sizeof(buf), "%lus", count);
        u8g2.drawStr(80, 63, buf);
        u8g2.sendBuffer();
    }
}
