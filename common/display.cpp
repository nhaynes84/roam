// Roam — Display implementation
// OLED via hardware I2C — DISPLAY_TYPE defined in board-specific config.h

#include "display.h"
#include <string.h>

void Display::begin() {
    // Configure Wire pins before U8g2 touches it
#ifdef ARDUINO_ARCH_RP2040
    Wire.setSDA(PIN_SDA);
    Wire.setSCL(PIN_SCL);
#else
    Wire.setPins(PIN_SDA, PIN_SCL);
#endif
    Wire.setClock(I2C_FREQ);
    Wire.begin();

    _u8g2 = new DISPLAY_TYPE(U8G2_R0, U8X8_PIN_NONE);
    _u8g2->setI2CAddress(DISPLAY_I2C_ADDR << 1);
    _u8g2->begin();
    Serial.println("display: OLED initialized (HW I2C)");
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

void Display::showBleText(const char* text) {
    strncpy(_bleText, text, sizeof(_bleText) - 1);
    _bleText[sizeof(_bleText) - 1] = '\0';
    _messageMode = true;
    _dirty = true;
}

void Display::toggleScreen() {
    _messageMode = !_messageMode;
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

    if (_messageMode && _bleText[0] != '\0') {
        // Full-screen message mode — BLE text only
        _u8g2->setFont(u8g2_font_6x10_tr);
        // Word-wrap into lines (21 chars wide at 6px)
        const int lineH = 12;
        const int maxW = 21;
        int y = 12;
        const char* p = _bleText;
        while (*p && y <= 60) {
            // Find line break point
            int len = strlen(p);
            int lineLen = len < maxW ? len : maxW;
            // Try to break at space
            if (len > maxW) {
                int brk = maxW;
                while (brk > 0 && p[brk] != ' ') brk--;
                if (brk > 0) lineLen = brk;
            }
            char line[22];
            memcpy(line, p, lineLen);
            line[lineLen] = '\0';
            _u8g2->drawStr(0, y, line);
            p += lineLen;
            if (*p == ' ') p++;  // skip space at break
            y += lineH;
        }
    } else {
        // Status mode — normal layout
        _u8g2->setFont(u8g2_font_6x10_tr);
        _u8g2->drawStr(0, 10, _mode);
        _u8g2->drawStr(0, 26, _bleStatus);
        _drawBattery();

        if (_lastAction[0] != '\0') {
            _u8g2->drawStr(0, 58, _lastAction);
        }
    }

    _u8g2->sendBuffer();
    _dirty = false;
}
