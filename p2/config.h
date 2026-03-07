// Roam P2 — Pin definitions, button mapping, and timing constants
// Seeed XIAO nRF52840 Sense (nRF52840 + BLE 5.0)

#pragma once

#include <Arduino.h>

// --- I2C (OLED) ---
#define PIN_SDA        D4
#define PIN_SCL        D5
#define I2C_FREQ       400000

// --- Buttons (active low, internal pull-up) ---
#define PIN_BTN_INDEX  D0
#define PIN_BTN_MIDDLE D1
#define PIN_BTN_RING   D2
#define PIN_BTN_PINKY  D3
#define NUM_BUTTONS    4

static const uint8_t BUTTON_PINS[NUM_BUTTONS] = {
    PIN_BTN_INDEX, PIN_BTN_MIDDLE, PIN_BTN_RING, PIN_BTN_PINKY
};

// --- Scroll buttons (thumb, active low, internal pull-up) ---
#define PIN_BTN_SCROLL_FWD  D8
#define PIN_BTN_SCROLL_BACK D9

// --- Display reset ---
// SH1106 module has no reset pin; SSD1309 used D10
#define PIN_DISPLAY_RST     U8X8_PIN_NONE

// --- Haptic motor (NPN via 1kΩ) ---
#define PIN_MOTOR      D6

// --- Status LED ---
#define ROAM_LED_PIN   D7

// --- Battery ---
// XIAO nRF52840 has built-in battery management via JST connector.
// Battery voltage readable via internal ADC channel.
// PIN_VBAT is defined by the Seeed board core — no need to redefine it.
#define VBAT_ENABLE_PIN    -1         // No enable pin needed on XIAO

// --- Timing ---
#define DEBOUNCE_MS       50
#define LONG_PRESS_MS     600
#define DOUBLE_TAP_MS     300
#define BUTTON_POLL_US    10000   // 100 Hz
#define DISPLAY_PERIOD_MS 100     // 10 Hz
#define BATTERY_PERIOD_MS 60000   // Every 60s
#define ACTION_FADE_MS    3000    // Action text display duration
#define SCREEN_DIM_MS     10000   // Dim after 10s inactivity
#define SCREEN_OFF_MS     30000   // Power off after 30s inactivity

// --- Display ---
// 1.3" 128x64 I2C OLED (SH1106)
#define SCREEN_WIDTH      128
#define SCREEN_HEIGHT     64
#define DISPLAY_TYPE      U8G2_SH1106_128X64_NONAME_F_HW_I2C
#define DISPLAY_I2C_ADDR  0x3C

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
    { ACTION_DICTATION,     ACTION_TMUX_PANE,      ACTION_NONE },           // Index
    { ACTION_ENTER,         ACTION_APPROVE_YES,    ACTION_APPROVE_ALWAYS }, // Middle
    { ACTION_REJECT_ESCAPE, ACTION_KILL_PROCESS,   ACTION_NONE },           // Ring
    { ACTION_CYCLE_MODE,    ACTION_BLE_SWITCH,     ACTION_NONE },           // Pinky
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
