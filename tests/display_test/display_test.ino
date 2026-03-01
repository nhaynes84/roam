// SH1106 — U8g2 with custom TWIM1 byte callback + Bluefruit
#include <bluefruit.h>
#include <U8g2lib.h>

#define OLED_ADDR 0x3C
#define SDA_PIN   4
#define SCL_PIN   5

// --- Raw TWIM1 driver ---

void twim_init() {
    NRF_TWIM1->ENABLE = 0;
    NRF_P0->PIN_CNF[SDA_PIN] = (GPIO_PIN_CNF_DIR_Input << GPIO_PIN_CNF_DIR_Pos)
                                | (GPIO_PIN_CNF_INPUT_Connect << GPIO_PIN_CNF_INPUT_Pos)
                                | (GPIO_PIN_CNF_PULL_Pullup << GPIO_PIN_CNF_PULL_Pos)
                                | (GPIO_PIN_CNF_DRIVE_S0D1 << GPIO_PIN_CNF_DRIVE_Pos);
    NRF_P0->PIN_CNF[SCL_PIN] = (GPIO_PIN_CNF_DIR_Input << GPIO_PIN_CNF_DIR_Pos)
                                | (GPIO_PIN_CNF_INPUT_Connect << GPIO_PIN_CNF_INPUT_Pos)
                                | (GPIO_PIN_CNF_PULL_Pullup << GPIO_PIN_CNF_PULL_Pos)
                                | (GPIO_PIN_CNF_DRIVE_S0D1 << GPIO_PIN_CNF_DRIVE_Pos);
    NRF_TWIM1->PSEL.SDA = SDA_PIN;
    NRF_TWIM1->PSEL.SCL = SCL_PIN;
    NRF_TWIM1->FREQUENCY = TWIM_FREQUENCY_FREQUENCY_K100;
    NRF_TWIM1->SHORTS = TWIM_SHORTS_LASTTX_STOP_Msk;
    NRF_TWIM1->ENABLE = (TWIM_ENABLE_ENABLE_Enabled << TWIM_ENABLE_ENABLE_Pos);
}

bool twim_write(uint8_t *data, uint16_t len) {
    NRF_TWIM1->ADDRESS = OLED_ADDR;
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

// --- U8g2 custom byte callback ---
// U8g2 calls this to send I2C data. We accumulate into a buffer
// and flush on U8X8_MSG_BYTE_END_TRANSFER.

static uint8_t u8g2_buf[256];
static uint16_t u8g2_buf_len = 0;

uint8_t u8x8_byte_twim1(u8x8_t *u8x8, uint8_t msg, uint8_t arg_int, void *arg_ptr) {
    switch (msg) {
        case U8X8_MSG_BYTE_INIT:
            break;
        case U8X8_MSG_BYTE_SET_DC:
            break;
        case U8X8_MSG_BYTE_START_TRANSFER:
            u8g2_buf_len = 0;
            break;
        case U8X8_MSG_BYTE_SEND:
            if (u8g2_buf_len + arg_int <= sizeof(u8g2_buf)) {
                memcpy(u8g2_buf + u8g2_buf_len, arg_ptr, arg_int);
                u8g2_buf_len += arg_int;
            }
            break;
        case U8X8_MSG_BYTE_END_TRANSFER:
            if (u8g2_buf_len > 0) {
                // Send in chunks of 32 to avoid TWIM issues
                uint16_t pos = 0;
                while (pos < u8g2_buf_len) {
                    uint16_t chunk = u8g2_buf_len - pos;
                    if (chunk > 32) chunk = 32;
                    if (!twim_write(u8g2_buf + pos, chunk)) return 0;
                    pos += chunk;
                    delayMicroseconds(50);
                }
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

// Use raw U8g2 constructor with our custom callbacks
U8G2_SH1106_128X64_NONAME_F_2ND_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE);

void setup() {
    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, HIGH);
    delay(2000);

    Bluefruit.begin();
    Bluefruit.setName("Roam2");

    twim_init();

    // Override U8g2's byte and GPIO callbacks with our custom ones
    u8g2.getU8x8()->byte_cb = u8x8_byte_twim1;
    u8g2.getU8x8()->gpio_and_delay_cb = u8x8_gpio_and_delay_nrf52;
    u8g2.setI2CAddress(OLED_ADDR << 1);
    u8g2.begin();

    u8g2.clearBuffer();
    u8g2.setFont(u8g2_font_6x10_tr);
    u8g2.drawStr(10, 20, "Hello Roam P2!");
    u8g2.drawStr(10, 40, "TWIM1 + Bluefruit");
    u8g2.drawFrame(0, 0, 128, 64);
    u8g2.sendBuffer();

    // Solid LED = done
    digitalWrite(LED_BUILTIN, LOW);
}

void loop() {}
