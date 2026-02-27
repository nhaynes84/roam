// Roam — OLED status display (SH1106 128x64 via I2C)
// U8g2 library, dirty-flag rendering at 10 Hz on core 1

#pragma once

#include "config.h"
#include <U8g2lib.h>
#include <Wire.h>

class Display {
public:
    void begin();
    bool isAvailable() const { return _available; }

    // Setters — mark dirty on change
    void setMode(const char* mode);
    void setBleStatus(const char* status);
    void setBatteryPercent(uint8_t pct);
    void showAction(const char* action);

    // Render if dirty. Call at ~10 Hz.
    void render();

    void dim();
    void brighten();
    void powerOff();
    void powerOn();

private:
    U8G2_SH1106_128X64_NONAME_F_HW_I2C* _u8g2 = nullptr;
    bool _available = false;
    bool _dirty = true;
    bool _dimmed = false;

    char _mode[16] = "Roam";
    char _bleStatus[24] = "Advertising";
    uint8_t _batteryPct = 0;
    char _lastAction[20] = "";
    uint32_t _actionTime = 0;

    void _drawBattery();
};
