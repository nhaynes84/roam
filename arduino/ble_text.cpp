// Roam — BLE text service implementation
// Extends PicoBluetoothBLEHID's ATT database with a custom writable characteristic.
// No library fork needed — _attdb and _attdbLen are public members.

#include "ble_text.h"
#include <PicoBluetoothBLEHID.h>

// BTStack includes (same redefinition dance as PicoBluetoothBLEHID.h)
#define HID_REPORT_TYPE_INPUT HID_REPORT_TYPE_INPUT_BT
#define HID_REPORT_TYPE_OUTPUT HID_REPORT_TYPE_OUTPUT_BT
#define HID_REPORT_TYPE_FEATURE HID_REPORT_TYPE_FEATURE_BT
#define hid_report_type_t hid_report_type_t_bt
#include <ble/att_db.h>
#include <ble/att_server.h>
#include <btstack.h>
#undef hid_report_type_t
#undef HID_REPORT_TYPE_FEATURE
#undef HID_REPORT_TYPE_OUTPUT
#undef HID_REPORT_TYPE_INPUT

// --- ATT handle assignments (appended after HID's last handle 0x003E) ---
#define TEXT_SERVICE_HANDLE 0x003F
#define TEXT_CHAR_HANDLE    0x0040
#define TEXT_VALUE_HANDLE   0x0041

// --- ATT DB entries for the text service ---
// Format per entry: [len_lo][len_hi][flags_lo][flags_hi][handle_lo][handle_hi][uuid...][value...]
static const uint8_t attdb_text_service[] = {
    // 0x003F PRIMARY_SERVICE — UUID 0xFF00 (vendor-specific)
    0x0a, 0x00,  // length = 10
    0x02, 0x00,  // flags = READ
    0x3f, 0x00,  // handle
    0x00, 0x28,  // type = Primary Service (0x2800)
    0x00, 0xff,  // service UUID = 0xFF00

    // 0x0040 CHARACTERISTIC declaration — UUID 0xFF01, properties: READ | WRITE | WRITE_WITHOUT_RESPONSE
    0x0d, 0x00,  // length = 13
    0x02, 0x00,  // flags = READ
    0x40, 0x00,  // handle
    0x03, 0x28,  // type = Characteristic (0x2803)
    0x0e,        // properties = READ(0x02) | WRITE_WITHOUT_RESPONSE(0x04) | WRITE(0x08)
    0x41, 0x00,  // value handle
    0x01, 0xff,  // char UUID = 0xFF01

    // 0x0041 VALUE — DYNAMIC | READ | WRITE | WRITE_WITHOUT_RESPONSE
    0x08, 0x00,  // length = 8
    0x0e, 0x01,  // flags = READ(0x02) | WRITE_WITHOUT_RESPONSE(0x04) | WRITE(0x08) | DYNAMIC(0x0100)
    0x41, 0x00,  // handle
    0x01, 0xff,  // type UUID = 0xFF01

    // DB terminator
    0x00, 0x00,
};

// --- Shared state between callbacks and BLETextService ---
static char _sharedTextBuf[BLE_TEXT_MAX_LEN];
static uint16_t _sharedTextLen = 0;
static volatile bool _sharedNewText = false;

// --- ATT read callback ---
static uint16_t text_read_callback(hci_con_handle_t con_handle, uint16_t att_handle,
                                    uint16_t offset, uint8_t *buffer, uint16_t buffer_size) {
    (void)con_handle;
    if (att_handle == TEXT_VALUE_HANDLE) {
        return att_read_callback_handle_blob((const uint8_t *)_sharedTextBuf,
                                             _sharedTextLen, offset, buffer, buffer_size);
    }
    return 0;
}

// --- ATT write callback ---
static int text_write_callback(hci_con_handle_t con_handle, uint16_t att_handle,
                                uint16_t transaction_mode, uint16_t offset,
                                uint8_t *buffer, uint16_t buffer_size) {
    (void)con_handle;
    (void)transaction_mode;
    (void)offset;
    if (att_handle == TEXT_VALUE_HANDLE) {
        uint16_t len = buffer_size < (BLE_TEXT_MAX_LEN - 1) ? buffer_size : (BLE_TEXT_MAX_LEN - 1);
        memcpy(_sharedTextBuf, buffer, len);
        _sharedTextBuf[len] = '\0';
        _sharedTextLen = len;
        _sharedNewText = true;
        return 0;
    }
    return 0;
}

// --- Service handler registration ---
static att_service_handler_t _textServiceHandler;

BLETextService bleText;

void BLETextService::begin() {
    // Extend the ATT DB built by PicoBluetoothBLEHID
    uint8_t *db = PicoBluetoothBLEHID._attdb;
    int dbLen = PicoBluetoothBLEHID._attdbLen;

    if (!db || dbLen < 2) {
        Serial.println("ble_text: ERROR — ATT DB not initialized, call after KeyboardBLE.begin()");
        return;
    }

    // The DB ends with a 2-byte terminator (0x00, 0x00).
    // We'll replace it with our service entries (which include their own terminator).
    int insertPos = dbLen - 2;  // overwrite old terminator
    int extraBytes = sizeof(attdb_text_service) - 2;  // net new bytes (our terminator replaces old)

    // Realloc the buffer with room for our service
    uint8_t *newDb = (uint8_t *)realloc(db, dbLen + extraBytes);
    if (!newDb) {
        Serial.println("ble_text: ERROR — realloc failed");
        return;
    }

    // Copy our service entries (overwriting old terminator, adding new one)
    memcpy(newDb + insertPos, attdb_text_service, sizeof(attdb_text_service));

    // Update PicoBluetoothBLEHID's public members
    PicoBluetoothBLEHID._attdb = newDb;
    PicoBluetoothBLEHID._attdbLen = dbLen + extraBytes;

    // Tell btstack about the (possibly moved) DB pointer
    att_set_db(newDb);

    // Register our service handler (only once — persists across BLE restarts)
    if (!_handlerRegistered) {
        memset(&_textServiceHandler, 0, sizeof(_textServiceHandler));
        _textServiceHandler.start_handle = TEXT_SERVICE_HANDLE;
        _textServiceHandler.end_handle = TEXT_VALUE_HANDLE;
        _textServiceHandler.read_callback = text_read_callback;
        _textServiceHandler.write_callback = text_write_callback;
        att_server_register_service_handler(&_textServiceHandler);
        _handlerRegistered = true;
    }

    Serial.printf("ble_text: service registered (handles 0x%04X-0x%04X, DB %d bytes)\n",
                  TEXT_SERVICE_HANDLE, TEXT_VALUE_HANDLE, PicoBluetoothBLEHID._attdbLen);
}

const char* BLETextService::getText() {
    if (_sharedNewText) {
        memcpy(_textBuf, _sharedTextBuf, BLE_TEXT_MAX_LEN);
        _newText = false;
        _sharedNewText = false;
        return _textBuf;
    }
    return _textBuf;
}

bool BLETextService::hasNewText() const {
    return _sharedNewText;
}
