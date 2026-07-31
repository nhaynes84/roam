// Blind SSD1309 init — sends I2C data IGNORING NACKs
// If screen lights up, it's receiving data but not ACKing (D2 issue)
#include <Arduino.h>
#include <bluefruit.h>

#define SDA_PIN D4
#define SCL_PIN D5

void sda_high() { pinMode(SDA_PIN, INPUT_PULLUP); }
void sda_low()  { pinMode(SDA_PIN, OUTPUT); digitalWrite(SDA_PIN, LOW); }
void scl_high() { pinMode(SCL_PIN, INPUT_PULLUP); delayMicroseconds(5); }
void scl_low()  { pinMode(SCL_PIN, OUTPUT); digitalWrite(SCL_PIN, LOW); delayMicroseconds(5); }

void bb_start() {
    sda_high(); scl_high(); delayMicroseconds(5);
    sda_low(); delayMicroseconds(5);
    scl_low();
}

void bb_stop() {
    sda_low(); delayMicroseconds(5);
    scl_high(); delayMicroseconds(5);
    sda_high(); delayMicroseconds(5);
}

void bb_write_byte(uint8_t b) {
    for (int i = 7; i >= 0; i--) {
        if (b & (1 << i)) sda_high(); else sda_low();
        scl_high(); scl_low();
    }
    // ACK clock — don't care about response
    sda_high(); scl_high(); scl_low();
}

void bb_cmd(uint8_t cmd) {
    bb_start();
    bb_write_byte(0x78);  // 0x3C << 1
    bb_write_byte(0x00);  // Co=0, D/C#=0 (command)
    bb_write_byte(cmd);
    bb_stop();
    delayMicroseconds(100);
}

void bb_cmd2(uint8_t cmd, uint8_t arg) {
    bb_start();
    bb_write_byte(0x78);
    bb_write_byte(0x00);
    bb_write_byte(cmd);
    bb_write_byte(arg);
    bb_stop();
    delayMicroseconds(100);
}

// Also check ACK during address phase
int bb_write_byte_ack(uint8_t b) {
    for (int i = 7; i >= 0; i--) {
        if (b & (1 << i)) sda_high(); else sda_low();
        scl_high(); scl_low();
    }
    sda_high(); scl_high();
    int ack = digitalRead(SDA_PIN);  // 0 = ACK
    scl_low();
    return ack == 0;
}

void do_init_and_fill() {
    bb_cmd(0xAE);
    bb_cmd2(0xD5, 0x80);
    bb_cmd2(0xA8, 0x3F);
    bb_cmd2(0xD3, 0x00);
    bb_cmd(0x40);
    bb_cmd2(0x8D, 0x14);
    bb_cmd(0xA1);
    bb_cmd(0xC8);
    bb_cmd2(0xDA, 0x12);
    bb_cmd2(0x81, 0xFF);  // Max contrast
    bb_cmd2(0xD9, 0xF1);
    bb_cmd2(0xDB, 0x40);
    bb_cmd(0xA4);
    bb_cmd(0xA6);

    for (uint8_t page = 0; page < 8; page++) {
        bb_cmd(0xB0 + page);
        bb_cmd(0x00);
        bb_cmd(0x10);
        bb_start();
        bb_write_byte(0x78);
        bb_write_byte(0x40);
        for (int col = 0; col < 128; col++)
            bb_write_byte(0xFF);
        bb_stop();
    }
    bb_cmd(0xAF);
}

void setup() {
    Serial.begin(115200);
    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, HIGH);  // OFF
    delay(3000);
    Serial.println("=== Live I2C scan + blind init (repeating) ===");
}

void loop() {
    // Scan for any device
    Serial.print("scan: ");
    uint8_t found = 0;
    for (uint8_t addr = 0x03; addr <= 0x77; addr++) {
        bb_start();
        int ack = bb_write_byte_ack((addr << 1) | 0);
        bb_stop();
        if (ack) {
            Serial.printf("0x%02X ", addr);
            found++;
        }
    }
    if (found == 0) Serial.print("no devices");
    Serial.println();

    // Check D2 pad voltage proxy — read SDA with no pullup
    pinMode(SDA_PIN, INPUT);
    delayMicroseconds(100);
    int sda_float = digitalRead(SDA_PIN);
    pinMode(SCL_PIN, INPUT);
    delayMicroseconds(100);
    int scl_float = digitalRead(SCL_PIN);
    Serial.printf("float: SDA=%d SCL=%d\n", sda_float, scl_float);

    // Blind init + fill
    do_init_and_fill();
    Serial.println("init sent");

    // LED: ON if found, OFF if not
    digitalWrite(LED_BUILTIN, found > 0 ? LOW : HIGH);

    Serial.println();
    delay(3000);
}
