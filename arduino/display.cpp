// Roam — Display implementation
// SH1106 128x64 OLED via I2C on GP4/GP5

#include "display.h"
#include <string.h>

void Display::begin() {
    // Set up I2C on GP4/GP5 before U8g2 init
    Wire.setSDA(PIN_SDA);
    Wire.setSCL(PIN_SCL);
    Wire.setClock(I2C_FREQ);

    // Scan for SH1106 at common addresses
    Wire.begin();
    delay(50);  // Let I2C settle
    Wire.beginTransmission(0x3C);
    bool found3C = (Wire.endTransmission() == 0);
    Wire.beginTransmission(0x3D);
    bool found3D = (Wire.endTransmission() == 0);

    if (!found3C && !found3D) {
        Serial.println("display: no OLED found on I2C");
        Wire.end();  // Release I2C bus when no display connected
        return;
    }

    uint8_t addr = found3C ? 0x3C : 0x3D;
    Serial.printf("display: SH1106 found at 0x%02X\n", addr);

    // U8g2 constructor — full framebuffer mode
    _u8g2 = new U8G2_SH1106_128X64_NONAME_F_HW_I2C(U8G2_R0, U8X8_PIN_NONE);
    _u8g2->setI2CAddress(addr << 1);  // U8g2 uses 8-bit address
    _u8g2->begin();
    _u8g2->setFont(u8g2_font_6x10_tr);
    _available = true;
    _dirty = true;
}

void Display::setMode(const char* mode) {
    if (strcmp(_mode, mode) != 0) {
        strncpy(_mode, mode, sizeof(_mode) - 1);
        _mode[sizeof(_mode) - 1] = '\0';
        _dirty = true;
    }
}

void Display::setBleStatus(const char* status) {
    if (strcmp(_bleStatus, status) != 0) {
        strncpy(_bleStatus, status, sizeof(_bleStatus) - 1);
        _bleStatus[sizeof(_bleStatus) - 1] = '\0';
        _dirty = true;
    }
}

void Display::setBatteryPercent(uint8_t pct) {
    if (pct != _batteryPct) {
        _batteryPct = pct;
        _dirty = true;
    }
}

void Display::showAction(const char* action) {
    strncpy(_lastAction, action, sizeof(_lastAction) - 1);
    _lastAction[sizeof(_lastAction) - 1] = '\0';
    _actionTime = millis();
    _dirty = true;
}

void Display::dim() {
    if (_available && !_dimmed) {
        _u8g2->setContrast(10);
        _dimmed = true;
    }
}

void Display::brighten() {
    if (_available && _dimmed) {
        _u8g2->setContrast(0x7F);
        _dimmed = false;
    }
}

void Display::powerOff() {
    if (_available) _u8g2->setPowerSave(1);
}

void Display::powerOn() {
    if (_available) {
        _u8g2->setPowerSave(0);
        _dirty = true;
    }
}

void Display::_drawBattery() {
    // Text
    char buf[16];
    snprintf(buf, sizeof(buf), "Batt:%d%%", _batteryPct);
    _u8g2->drawStr(0, 42, buf);

    // Bar outline at right side
    const int bx = 90, by = 34, bw = 30, bh = 8;
    _u8g2->drawFrame(bx, by, bw, bh);
    // Terminal nub
    _u8g2->drawBox(bx + bw, by + 2, 2, bh - 4);
    // Fill
    int fillW = (int)((bw - 2) * _batteryPct / 100);
    if (fillW > 0) {
        _u8g2->drawBox(bx + 1, by + 1, fillW, bh - 2);
    }
}

void Display::render() {
    if (!_available) return;

    // Check if action text should fade
    if (_lastAction[0] != '\0') {
        if ((millis() - _actionTime) >= ACTION_FADE_MS) {
            _lastAction[0] = '\0';
            _dirty = true;
        }
    }

    if (!_dirty) return;

    _u8g2->clearBuffer();

    // Line 1: Mode name (y=10 for baseline with 6x10 font)
    _u8g2->setFont(u8g2_font_6x10_tr);
    _u8g2->drawStr(0, 10, _mode);

    // Line 2: BLE status
    _u8g2->drawStr(0, 26, _bleStatus);

    // Line 3: Battery bar
    _drawBattery();

    // Line 4: Last action
    if (_lastAction[0] != '\0') {
        _u8g2->drawStr(0, 58, _lastAction);
    }

    _u8g2->sendBuffer();
    _dirty = false;
}
