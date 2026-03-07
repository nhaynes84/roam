// Roam P2 — OLED display with unified layout
// Status bar (BT + battery icons) | content area | scroll indicator
// Uses TWIM1 direct register access (TWIM0 conflicts with Bluefruit softdevice)
// DISPLAY_TYPE defined in board-specific config.h

#pragma once

#include "config.h"
#include <U8g2lib.h>

#define MSG_RING_SIZE  100
#define MSG_MAX_LEN    128

class Display {
public:
    void begin();
    bool isAvailable() const { return _available; }

    // Status bar
    void setBleConnected(bool connected);
    void setBatteryPercent(uint8_t pct);

    // Content area
    void showAction(const char* action);
    void pushMessage(const char* text);
    void scrollFwd();    // Toward newer messages (> button)
    void scrollBack();   // Toward older messages (< button)

    // Power management
    void dim();
    void brighten();
    void powerOff();
    void powerOn();
    void wake();
    uint32_t lastActivityTime() const { return _lastActivity; }

    // Render at ~10 Hz
    void render();

    // Diagnostics
    void printDiag();

private:
    DISPLAY_TYPE* _u8g2 = nullptr;
    bool _available = false;
    bool _dirty = true;
    bool _dimmed = false;
    bool _powered = true;

    // Status bar
    bool _bleConnected = false;
    bool _usbPowered = false;
    uint8_t _batteryPct = 0;

    // Action confirmation (fades after ACTION_FADE_MS)
    char _lastAction[20] = "";
    uint32_t _actionTime = 0;

    // Message ring buffer
    char _msgRing[MSG_RING_SIZE][MSG_MAX_LEN];
    uint8_t _msgCount = 0;
    uint8_t _msgHead = 0;       // Next write position
    int8_t  _msgViewOffset = 0; // 0 = newest, positive = older
    int8_t  _msgPageOffset = 0; // Page within current message (0 = first)

    // Activity tracking for sleep timer
    uint32_t _lastActivity = 0;

    // Drawing helpers
    void _drawStatusBar();
    void _drawContent();
    void _drawScrollIndicator();
    int  _viewedMsgIndex() const;
    int  _wrapLineLen(const char* p) const;
    int  _countMsgPages(const char* msg) const;
};
