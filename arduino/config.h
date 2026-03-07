// Roam — Pin definitions, button mapping, and timing constants
// Pimoroni Pico Plus 2 W (RP2350 + CYW43439)

#pragma once

#include <Arduino.h>

// --- I2C (OLED) ---
#define PIN_SDA        4
#define PIN_SCL        5
#define I2C_FREQ       400000

// --- Buttons (active low, internal pull-up) ---
#define PIN_BTN_INDEX  10
#define PIN_BTN_MIDDLE 11
#define PIN_BTN_RING   12
#define PIN_BTN_PINKY  13
#define NUM_BUTTONS    4

static const uint8_t BUTTON_PINS[NUM_BUTTONS] = {
    PIN_BTN_INDEX, PIN_BTN_MIDDLE, PIN_BTN_RING, PIN_BTN_PINKY
};

// --- Haptic motor (NPN via 1kΩ) ---
#define PIN_MOTOR      15

// --- Status LED (via 100Ω) ---
#define ROAM_LED_PIN   16

// --- Battery ADC ---
#define PIN_BATTERY    29   // ADC3 — VSYS/3
#define PIN_GP25       25   // Must be HIGH during ADC read (CYW43 SPI)

// --- Timing ---
#define DEBOUNCE_MS       50
#define LONG_PRESS_MS     600
#define DOUBLE_TAP_MS     300   // Max gap between taps for double-tap
#define BUTTON_POLL_US    10000   // 100 Hz
#define DISPLAY_PERIOD_MS 100     // 10 Hz
#define BATTERY_PERIOD_MS 60000   // Every 60s
#define ACTION_FADE_MS    3000    // Action text display duration
#define SCREEN_DIM_MS     10000   // Dim after 10s inactivity
#define SCREEN_OFF_MS     30000   // Power off after 30s inactivity

// --- Display ---
#define SCREEN_WIDTH   128
#define SCREEN_HEIGHT  64
#define DISPLAY_TYPE      U8G2_SH1106_128X64_NONAME_F_HW_I2C
#define DISPLAY_I2C_ADDR  0x3C
#define PIN_DISPLAY_RST   U8X8_PIN_NONE  // SH1106 — no reset pin wired

// --- Action types ---
enum ActionType : uint8_t {
    ACTION_NONE = 0,
    // Index button
    ACTION_DICTATION,       // Consumer key 0x00CF
    ACTION_TMUX_PANE,       // Ctrl+B, o
    // Middle button
    ACTION_CYCLE_MODE,      // Shift+Tab
    ACTION_BLE_SWITCH,      // Disconnect + re-advertise
    // Ring button
    ACTION_APPROVE_YES,     // y + Enter
    ACTION_APPROVE_ALWAYS,  // Tab + Enter
    // Pinky button
    ACTION_REJECT_ESCAPE,   // Escape
    ACTION_KILL_PROCESS,    // Ctrl+C
    // Double-tap
    ACTION_ENTER,           // Enter only (no y prefix)
    // Scroll (dedicated buttons on P2, mapped to double-tap for P1 testing)
    ACTION_SCROLL_FWD,      // Next line (short) or next page (long)
    ACTION_SCROLL_BACK,     // Prev line (short) or prev page (long)
};

// Button index → short/long action mapping
struct ButtonMapping {
    ActionType shortPress;
    ActionType longPress;
    ActionType doubleTap;
};

static const ButtonMapping BUTTON_MAP[NUM_BUTTONS] = {
    { ACTION_DICTATION,     ACTION_TMUX_PANE,      ACTION_NONE },  // Index
    { ACTION_CYCLE_MODE,    ACTION_BLE_SWITCH,     ACTION_NONE },  // Middle
    { ACTION_ENTER,         ACTION_APPROVE_YES,     ACTION_APPROVE_ALWAYS },  // Ring
    { ACTION_REJECT_ESCAPE, ACTION_KILL_PROCESS,    ACTION_NONE  },  // Pinky
};

// Human-readable action names for display
static const char* ACTION_NAMES[] = {
    "",              // ACTION_NONE
    "Dictation",     // ACTION_DICTATION
    "Tmux Pane",     // ACTION_TMUX_PANE
    "Cycle Mode",    // ACTION_CYCLE_MODE
    "BLE Switch",    // ACTION_BLE_SWITCH
    "Approve",       // ACTION_APPROVE_YES
    "Always",        // ACTION_APPROVE_ALWAYS
    "Escape",        // ACTION_REJECT_ESCAPE
    "Kill",          // ACTION_KILL_PROCESS
    "Enter",         // ACTION_ENTER
    "",              // ACTION_SCROLL_FWD (handled locally)
    "",              // ACTION_SCROLL_BACK (handled locally)
};
