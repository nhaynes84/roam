// Roam — OLED status display (U8g2 HW_I2C)
// DISPLAY_TYPE defined in board-specific config.h

#pragma once

#include "config.h"
#include <Wire.h>
#include <U8g2lib.h>

class Display {
public:
    void begin();
    bool isAvailable() const { return _available; }

    // Setters — mark dirty on change
    void setMode(const char* mode);
    void setBleStatus(const char* status);
    void setBatteryPercent(uint8_t pct);
    void showAction(const char* action);
    void showBleText(const char* text);  // Full-screen message (stays until toggled)
    void toggleScreen();                 // Switch between message and status view

    bool inMessageMode() const { return _messageMode; }

    // Render if dirty. Call at ~10 Hz.
    void render();

    void dim();
    void brighten();
    void powerOff();
    void powerOn();

private:
    DISPLAY_TYPE* _u8g2 = nullptr;
    bool _available = false;
    bool _dirty = true;
    bool _dimmed = false;

    char _mode[16] = "Roam";
    char _bleStatus[24] = "Advertising";
    uint8_t _batteryPct = 0;
    char _lastAction[20] = "";
    uint32_t _actionTime = 0;
    char _bleText[128] = "";
    bool _messageMode = false;

    void _drawBattery();
};
