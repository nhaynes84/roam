// Roam — Display implementation (Wire / HW_I2C for RP2040)
// Unified layout: status bar | content area | scroll indicator
// DISPLAY_TYPE defined in board-specific config.h

#include "display.h"
#include <string.h>

void Display::begin() {
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
    _u8g2->setFont(u8g2_font_6x10_tr);
    _available = true;
    _dirty = true;
    _lastActivity = millis();
    memset(_msgRing, 0, sizeof(_msgRing));
    Serial.println("display: OLED initialized (HW I2C)");
}

// --- Status bar ---

void Display::setBleConnected(bool connected) {
    if (connected != _bleConnected) {
        _bleConnected = connected;
        _dirty = true;
    }
}

void Display::setBatteryPercent(uint8_t pct) {
    if (pct != _batteryPct) {
        _batteryPct = pct;
        _dirty = true;
    }
}

// --- Content ---

void Display::showAction(const char* action) {
    strncpy(_lastAction, action, sizeof(_lastAction) - 1);
    _lastAction[sizeof(_lastAction) - 1] = '\0';
    _actionTime = millis();
    _lastActivity = millis();
    _dirty = true;
}

void Display::pushMessage(const char* text) {
    strncpy(_msgRing[_msgHead], text, MSG_MAX_LEN - 1);
    _msgRing[_msgHead][MSG_MAX_LEN - 1] = '\0';
    _msgHead = (_msgHead + 1) % MSG_RING_SIZE;
    if (_msgCount < MSG_RING_SIZE) _msgCount++;
    _msgViewOffset = 0;  // auto-show newest
    _msgPageOffset = 0;
    wake();              // incoming message wakes screen
    _dirty = true;
}

void Display::scrollFwd() {
    // > / up = advance: next page, then newer message (higher number)
    if (_msgCount == 0) return;

    int idx = _viewedMsgIndex();
    int totalPages = _countMsgPages(_msgRing[idx]);

    if (_msgPageOffset < totalPages - 1) {
        _msgPageOffset++;
    } else if (_msgViewOffset > 0) {
        _msgViewOffset--;
        _msgPageOffset = 0;
    } else {
        return;
    }
    _lastActivity = millis();
    _dirty = true;
}

void Display::scrollBack() {
    // < / down = go back: prev page, then older message (lower number)
    if (_msgCount == 0) return;

    if (_msgPageOffset > 0) {
        _msgPageOffset--;
    } else if (_msgViewOffset < (int8_t)(_msgCount - 1)) {
        _msgViewOffset++;
        int idx = _viewedMsgIndex();
        _msgPageOffset = _countMsgPages(_msgRing[idx]) - 1;
    } else {
        return;
    }
    _lastActivity = millis();
    _dirty = true;
}

int Display::_viewedMsgIndex() const {
    return ((int)_msgHead - 1 - _msgViewOffset + MSG_RING_SIZE * 2) % MSG_RING_SIZE;
}

int Display::_wrapLineLen(const char* p) const {
    int len = strlen(p);
    if (len == 0) return 0;
    const int maxChars = SCREEN_WIDTH / 6;
    if (len <= maxChars) return len;
    int brk = maxChars;
    while (brk > 0 && p[brk] != ' ') brk--;
    return (brk > 0) ? brk : maxChars;
}

int Display::_countMsgPages(const char* msg) const {
    int lines = 0;
    const char* p = msg;
    while (*p) {
        int ll = _wrapLineLen(p);
        if (ll == 0) break;
        p += ll;
        if (*p == ' ') p++;
        lines++;
    }
    return (lines <= 0) ? 1 : (lines + 2) / 3;
}

// --- Power management ---

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
    if (_available && _powered) {
        _u8g2->setPowerSave(1);
        _powered = false;
    }
}

void Display::powerOn() {
    if (_available && !_powered) {
        _u8g2->setPowerSave(0);
        _powered = true;
        _dirty = true;
    }
}

void Display::wake() {
    _lastActivity = millis();
    if (!_powered) powerOn();
    if (_dimmed) brighten();
}

// --- Drawing helpers ---

void Display::_drawStatusBar() {
    // BT connection indicator (left side)
    if (_bleConnected) {
        _u8g2->drawDisc(4, 4, 3);   // filled circle = connected
    } else {
        _u8g2->drawCircle(4, 4, 3); // hollow circle = advertising
    }

    // Battery icon (right-aligned, 18x8 at x=104)
    const int bx = 104, by = 0, bw = 18, bh = 8;
    _u8g2->drawFrame(bx, by, bw, bh);
    _u8g2->drawBox(bx + bw, by + 2, 2, 4);  // terminal nub
    int fillW = (int)((bw - 2) * _batteryPct / 100);
    if (fillW > 0) {
        _u8g2->drawBox(bx + 1, by + 1, fillW, bh - 2);
    }

    // Separator line
    _u8g2->drawHLine(0, 11, SCREEN_WIDTH);
}

void Display::_drawContent() {
    _u8g2->setFont(u8g2_font_6x10_tr);

    // Action confirmation takes priority (centered in content area)
    if (_lastAction[0] != '\0') {
        int w = _u8g2->getStrWidth(_lastAction);
        int x = (SCREEN_WIDTH - w) / 2;
        _u8g2->drawStr(x, 36, _lastAction);
        return;
    }

    // Show viewed message from ring buffer
    if (_msgCount == 0) return;

    int idx = _viewedMsgIndex();
    const char* msg = _msgRing[idx];
    const char* p = msg;

    // Skip lines for current page
    int skipLines = _msgPageOffset * 3;
    for (int i = 0; i < skipLines && *p; i++) {
        int ll = _wrapLineLen(p);
        if (ll == 0) break;
        p += ll;
        if (*p == ' ') p++;
    }

    // Draw up to 3 lines
    const int lineH = 12;
    int y = 24;
    for (int line = 0; line < 3 && *p; line++) {
        int ll = _wrapLineLen(p);
        if (ll == 0) break;

        char buf[22];
        memcpy(buf, p, ll);
        buf[ll] = '\0';
        _u8g2->drawStr(0, y, buf);

        p += ll;
        if (*p == ' ') p++;
        y += lineH;
    }
}

void Display::_drawScrollIndicator() {
    if (_msgCount == 0) return;

    int idx = _viewedMsgIndex();
    int totalPages = _countMsgPages(_msgRing[idx]);

    char buf[12];
    bool canLeft, canRight;

    if (totalPages > 1) {
        // Multi-page message: show page indicator
        snprintf(buf, sizeof(buf), "p%d/%d", _msgPageOffset + 1, totalPages);
        canLeft  = _msgPageOffset > 0 || _msgViewOffset < (int8_t)(_msgCount - 1);
        canRight = _msgPageOffset < totalPages - 1 || _msgViewOffset > 0;
    } else if (_msgCount > 1) {
        // Single-page: show message indicator (chronological: 1=oldest, N=newest)
        snprintf(buf, sizeof(buf), "m%d/%d", _msgCount - _msgViewOffset, _msgCount);
        canLeft  = _msgViewOffset < (int8_t)(_msgCount - 1);
        canRight = _msgViewOffset > 0;
    } else {
        return;  // Single message, single page — nothing to show
    }

    _u8g2->setFont(u8g2_font_6x10_tr);
    int w = _u8g2->getStrWidth(buf);
    int cx = (SCREEN_WIDTH - w) / 2;
    _u8g2->drawStr(cx, 62, buf);

    if (canLeft) {
        _u8g2->drawTriangle(cx - 12, 57, cx - 6, 53, cx - 6, 61);
    }
    if (canRight) {
        int rx = cx + w + 6;
        _u8g2->drawTriangle(rx + 6, 57, rx, 53, rx, 61);
    }
}

// --- Render ---

void Display::render() {
    if (!_available || !_powered) return;

    // Fade action text after timeout
    if (_lastAction[0] != '\0') {
        if ((millis() - _actionTime) >= ACTION_FADE_MS) {
            _lastAction[0] = '\0';
            _dirty = true;
        }
    }

    if (!_dirty) return;

    _u8g2->clearBuffer();
    _drawStatusBar();
    _drawContent();
    _drawScrollIndicator();
    _u8g2->sendBuffer();
    _dirty = false;
}
