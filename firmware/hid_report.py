"""HID Report Map descriptor and keycode constants for Roam BLE keyboard.

Defines a composite HID descriptor with two reports:
  Report ID 1: Standard 6KRO keyboard (8 bytes)
  Report ID 2: Consumer Control (2 bytes, 16-bit usage code)
"""

# --- HID Report Map Descriptor ---
# Composite descriptor: keyboard + consumer control
REPORT_MAP = bytes([
    # ============================================
    # Report ID 1: Keyboard (6KRO)
    # Input: [modifiers(1), reserved(1), keys(6)] = 8 bytes
    # Output: [LEDs(1)] = 1 byte
    # ============================================
    0x05, 0x01,        # Usage Page (Generic Desktop)
    0x09, 0x06,        # Usage (Keyboard)
    0xA1, 0x01,        # Collection (Application)
    0x85, 0x01,        #   Report ID (1)

    # Modifier keys (byte 0): 8 bits for Ctrl/Shift/Alt/GUI L+R
    0x05, 0x07,        #   Usage Page (Key Codes)
    0x19, 0xE0,        #   Usage Minimum (Left Control)
    0x29, 0xE7,        #   Usage Maximum (Right GUI)
    0x15, 0x00,        #   Logical Minimum (0)
    0x25, 0x01,        #   Logical Maximum (1)
    0x75, 0x01,        #   Report Size (1)
    0x95, 0x08,        #   Report Count (8)
    0x81, 0x02,        #   Input (Data, Variable, Absolute)

    # Reserved byte (byte 1)
    0x75, 0x08,        #   Report Size (8)
    0x95, 0x01,        #   Report Count (1)
    0x81, 0x01,        #   Input (Constant)

    # LED output report (caps lock, etc.)
    0x05, 0x08,        #   Usage Page (LEDs)
    0x19, 0x01,        #   Usage Minimum (Num Lock)
    0x29, 0x05,        #   Usage Maximum (Kana)
    0x75, 0x01,        #   Report Size (1)
    0x95, 0x05,        #   Report Count (5)
    0x91, 0x02,        #   Output (Data, Variable, Absolute)
    # LED padding (3 bits)
    0x75, 0x01,        #   Report Size (1)
    0x95, 0x03,        #   Report Count (3)
    0x91, 0x01,        #   Output (Constant)

    # Key array (bytes 2-7): up to 6 simultaneous keys
    0x05, 0x07,        #   Usage Page (Key Codes)
    0x19, 0x00,        #   Usage Minimum (0)
    0x29, 0xFF,        #   Usage Maximum (255)
    0x15, 0x00,        #   Logical Minimum (0)
    0x26, 0xFF, 0x00,  #   Logical Maximum (255)
    0x75, 0x08,        #   Report Size (8)
    0x95, 0x06,        #   Report Count (6)
    0x81, 0x00,        #   Input (Data, Array)

    0xC0,              # End Collection

    # ============================================
    # Report ID 2: Consumer Control
    # Input: [usage_code(2)] = 2 bytes (16-bit)
    # ============================================
    0x05, 0x0C,        # Usage Page (Consumer Devices)
    0x09, 0x01,        # Usage (Consumer Control)
    0xA1, 0x01,        # Collection (Application)
    0x85, 0x02,        #   Report ID (2)

    0x15, 0x00,        #   Logical Minimum (0)
    0x26, 0xFF, 0x0F,  #   Logical Maximum (4095)
    0x19, 0x00,        #   Usage Minimum (0)
    0x2A, 0xFF, 0x0F,  #   Usage Maximum (4095)
    0x75, 0x10,        #   Report Size (16)
    0x95, 0x01,        #   Report Count (1)
    0x81, 0x00,        #   Input (Data, Array)

    0xC0,              # End Collection
])

# Report sizes (excluding Report ID byte, which aioble handles)
KEYBOARD_REPORT_SIZE = 8   # modifiers(1) + reserved(1) + keys(6)
CONSUMER_REPORT_SIZE = 2   # usage_code(2)

# Report IDs
KEYBOARD_REPORT_ID = 1
CONSUMER_REPORT_ID = 2

# --- Modifier key bitmasks (byte 0 of keyboard report) ---
MOD_NONE = 0x00
MOD_LEFT_CTRL = 0x01
MOD_LEFT_SHIFT = 0x02
MOD_LEFT_ALT = 0x04
MOD_LEFT_GUI = 0x08
MOD_RIGHT_CTRL = 0x10
MOD_RIGHT_SHIFT = 0x20
MOD_RIGHT_ALT = 0x40
MOD_RIGHT_GUI = 0x80

# Convenience aliases
MOD_CTRL = MOD_LEFT_CTRL
MOD_SHIFT = MOD_LEFT_SHIFT
MOD_ALT = MOD_LEFT_ALT
MOD_GUI = MOD_LEFT_GUI

# --- HID Keycodes (USB HID Usage Table, Keyboard/Keypad Page 0x07) ---
KEY_NONE = 0x00
KEY_A = 0x04
KEY_B = 0x05
KEY_C = 0x06
KEY_D = 0x07
KEY_E = 0x08
KEY_F = 0x09
KEY_G = 0x0A
KEY_H = 0x0B
KEY_I = 0x0C
KEY_J = 0x0D
KEY_K = 0x0E
KEY_L = 0x0F
KEY_M = 0x10
KEY_N = 0x11
KEY_O = 0x12
KEY_P = 0x13
KEY_Q = 0x14
KEY_R = 0x15
KEY_S = 0x16
KEY_T = 0x17
KEY_U = 0x18
KEY_V = 0x19
KEY_W = 0x1A
KEY_X = 0x1B
KEY_Y = 0x1C
KEY_Z = 0x1D

KEY_1 = 0x1E
KEY_2 = 0x1F
KEY_3 = 0x20
KEY_4 = 0x21
KEY_5 = 0x22
KEY_6 = 0x23
KEY_7 = 0x24
KEY_8 = 0x25
KEY_9 = 0x26
KEY_0 = 0x27

KEY_ENTER = 0x28
KEY_ESCAPE = 0x29
KEY_BACKSPACE = 0x2A
KEY_TAB = 0x2B
KEY_SPACE = 0x2C

KEY_MINUS = 0x2D
KEY_EQUAL = 0x2E
KEY_LEFT_BRACKET = 0x2F
KEY_RIGHT_BRACKET = 0x30
KEY_BACKSLASH = 0x31
KEY_SEMICOLON = 0x33
KEY_QUOTE = 0x34
KEY_GRAVE = 0x35
KEY_COMMA = 0x36
KEY_PERIOD = 0x37
KEY_SLASH = 0x38
KEY_CAPS_LOCK = 0x39

KEY_F1 = 0x3A
KEY_F2 = 0x3B
KEY_F3 = 0x3C
KEY_F4 = 0x3D
KEY_F5 = 0x3E
KEY_F6 = 0x3F
KEY_F7 = 0x40
KEY_F8 = 0x41
KEY_F9 = 0x42
KEY_F10 = 0x43
KEY_F11 = 0x44
KEY_F12 = 0x45

KEY_RIGHT_ARROW = 0x4F
KEY_LEFT_ARROW = 0x50
KEY_DOWN_ARROW = 0x51
KEY_UP_ARROW = 0x52

KEY_DELETE = 0x4C
KEY_HOME = 0x4A
KEY_END = 0x4D
KEY_PAGE_UP = 0x4B
KEY_PAGE_DOWN = 0x4E

# --- Consumer Control Usage IDs (Usage Page 0x0C) ---
CONSUMER_MUTE = 0x00E2
CONSUMER_VOL_UP = 0x00E9
CONSUMER_VOL_DOWN = 0x00EA
CONSUMER_PLAY_PAUSE = 0x00CD
CONSUMER_NEXT_TRACK = 0x00B5
CONSUMER_PREV_TRACK = 0x00B6
CONSUMER_BRIGHTNESS_UP = 0x006F
CONSUMER_BRIGHTNESS_DOWN = 0x0070
CONSUMER_DICTATION = 0x00CF  # macOS dictation key
