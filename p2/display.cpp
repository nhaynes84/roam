// Roam P2 — Display implementation
// Uses TWIM1 direct register access (TWIM0 conflicts with Bluefruit softdevice)
// Seeed BSP Wire library has infinite spin loops — bypassed entirely
// DISPLAY_TYPE defined in board-specific config.h

#include "display.h"
#include <string.h>

// --- TWIM1 raw driver (bypasses Wire library) ---

static void twim1_init() {
    NRF_TWIM1->ENABLE = 0;
    NRF_P0->PIN_CNF[PIN_SDA] = (GPIO_PIN_CNF_DIR_Input << GPIO_PIN_CNF_DIR_Pos)
                                | (GPIO_PIN_CNF_INPUT_Connect << GPIO_PIN_CNF_INPUT_Pos)
                                | (GPIO_PIN_CNF_PULL_Pullup << GPIO_PIN_CNF_PULL_Pos)
                                | (GPIO_PIN_CNF_DRIVE_S0D1 << GPIO_PIN_CNF_DRIVE_Pos);
    NRF_P0->PIN_CNF[PIN_SCL] = (GPIO_PIN_CNF_DIR_Input << GPIO_PIN_CNF_DIR_Pos)
                                | (GPIO_PIN_CNF_INPUT_Connect << GPIO_PIN_CNF_INPUT_Pos)
                                | (GPIO_PIN_CNF_PULL_Pullup << GPIO_PIN_CNF_PULL_Pos)
                                | (GPIO_PIN_CNF_DRIVE_S0D1 << GPIO_PIN_CNF_DRIVE_Pos);
    NRF_TWIM1->PSEL.SDA = PIN_SDA;
    NRF_TWIM1->PSEL.SCL = PIN_SCL;
    NRF_TWIM1->FREQUENCY = TWIM_FREQUENCY_FREQUENCY_K100;
    NRF_TWIM1->SHORTS = TWIM_SHORTS_LASTTX_STOP_Msk;
    NRF_TWIM1->ENABLE = (TWIM_ENABLE_ENABLE_Enabled << TWIM_ENABLE_ENABLE_Pos);
}

static bool twim1_write(uint8_t addr, uint8_t *data, uint16_t len) {
    NRF_TWIM1->ADDRESS = addr;
    NRF_TWIM1->TXD.PTR = (uint32_t)data;
    NRF_TWIM1->TXD.MAXCNT = len;
    NRF_TWIM1->EVENTS_STOPPED = 0;
    NRF_TWIM1->EVENTS_ERROR = 0;
    NRF_TWIM1->TASKS_STARTTX = 1;
    uint32_t t = 500000;
    while (!NRF_TWIM1->EVENTS_STOPPED && !NRF_TWIM1->EVENTS_ERROR) {
        if (--t == 0) return false;
    }
    if (NRF_TWIM1->EVENTS_ERROR) {
        NRF_TWIM1->EVENTS_ERROR = 0;
        uint32_t err = NRF_TWIM1->ERRORSRC;
        NRF_TWIM1->ERRORSRC = err;
        NRF_TWIM1->TASKS_STOP = 1;
        while (!NRF_TWIM1->EVENTS_STOPPED);
        NRF_TWIM1->EVENTS_STOPPED = 0;
        return false;
    }
    NRF_TWIM1->EVENTS_STOPPED = 0;
    return true;
}

// --- U8g2 custom byte callback for TWIM1 ---

static uint8_t _u8g2_i2c_buf[256];
static uint16_t _u8g2_i2c_len = 0;
static uint8_t _u8g2_i2c_addr = 0x3C;

uint8_t u8x8_byte_twim1(u8x8_t *u8x8, uint8_t msg, uint8_t arg_int, void *arg_ptr) {
    switch (msg) {
        case U8X8_MSG_BYTE_INIT:
            break;
        case U8X8_MSG_BYTE_SET_DC:
            break;
        case U8X8_MSG_BYTE_START_TRANSFER:
            _u8g2_i2c_len = 0;
            _u8g2_i2c_addr = u8x8_GetI2CAddress(u8x8) >> 1;
            break;
        case U8X8_MSG_BYTE_SEND:
            if (_u8g2_i2c_len + arg_int <= sizeof(_u8g2_i2c_buf)) {
                memcpy(_u8g2_i2c_buf + _u8g2_i2c_len, arg_ptr, arg_int);
                _u8g2_i2c_len += arg_int;
            }
            break;
        case U8X8_MSG_BYTE_END_TRANSFER:
            if (_u8g2_i2c_len > 0) {
                if (!twim1_write(_u8g2_i2c_addr, _u8g2_i2c_buf, _u8g2_i2c_len))
                    return 0;
            }
            break;
    }
    return 1;
}

uint8_t u8x8_gpio_and_delay_nrf52(u8x8_t *u8x8, uint8_t msg, uint8_t arg_int, void *arg_ptr) {
    switch (msg) {
        case U8X8_MSG_GPIO_AND_DELAY_INIT:
            break;
        case U8X8_MSG_DELAY_MILLI:
            delay(arg_int);
            break;
        case U8X8_MSG_DELAY_10MICRO:
            delayMicroseconds(arg_int * 10);
            break;
        case U8X8_MSG_DELAY_100NANO:
            delayMicroseconds(1);
            break;
    }
    return 1;
}

// --- Display class ---

void Display::begin() {
    twim1_init();

    _u8g2 = new DISPLAY_TYPE(U8G2_R0, U8X8_PIN_NONE);
    _u8g2->getU8x8()->byte_cb = u8x8_byte_twim1;
    _u8g2->getU8x8()->gpio_and_delay_cb = u8x8_gpio_and_delay_nrf52;
    _u8g2->setI2CAddress(DISPLAY_I2C_ADDR << 1);
    _u8g2->begin();
    _u8g2->setFont(u8g2_font_6x10_tr);
    _available = true;
    _dirty = true;
    _lastActivity = millis();
    memset(_msgRing, 0, sizeof(_msgRing));
    Serial.println("display: OLED initialized (TWIM1)");
}

void Display::printDiag() {
    Serial.printf("display: avail=%d powered=%d dimmed=%d msgs=%d\n",
                  _available, _powered, _dimmed, _msgCount);
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

void Display::setProfileName(const char* name) {
    strncpy(_profileName, name, sizeof(_profileName) - 1);
    _profileName[sizeof(_profileName) - 1] = '\0';
    _dirty = true;
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

    // USB power detection (nRF52840 POWER peripheral)
    _usbPowered = (NRF_POWER->USBREGSTATUS & POWER_USBREGSTATUS_VBUSDETECT_Msk) != 0;

    // Battery icon (right-aligned, 18x8 at x=104)
    const int bx = 104, by = 0, bw = 18, bh = 8;
    _u8g2->drawFrame(bx, by, bw, bh);
    _u8g2->drawBox(bx + bw, by + 2, 2, 4);  // terminal nub
    int fillW = (int)((bw - 2) * _batteryPct / 100);
    if (fillW > 0) {
        _u8g2->drawBox(bx + 1, by + 1, fillW, bh - 2);
    }

    // Lightning bolt overlay when USB powered (charging)
    if (_usbPowered) {
        int cx = bx + bw / 2;  // center of battery body
        // Small 5px-tall bolt: zig-zag line
        _u8g2->setDrawColor(2);  // XOR so it's visible on filled or empty
        _u8g2->drawLine(cx + 1, by + 1, cx - 1, by + 4);
        _u8g2->drawLine(cx - 1, by + 4, cx + 1, by + 4);
        _u8g2->drawLine(cx + 1, by + 4, cx - 1, by + 7);
        _u8g2->setDrawColor(1);
    }

    // Profile name (centered in status bar)
    if (_profileName[0] != '\0') {
        _u8g2->setFont(u8g2_font_6x10_tr);
        int w = _u8g2->getStrWidth(_profileName);
        _u8g2->drawStr((SCREEN_WIDTH - w) / 2, 8, _profileName);
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
