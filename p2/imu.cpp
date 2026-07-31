// Roam P2 — LSM6DS3TR-C wake-on-motion
// IMU is on internal I2C (P0.07/P0.27), display is on external I2C (P0.04/P0.05).
// Both share TWIM1 — pin-swap at init, then IMU only uses hardware interrupt.

#include "imu.h"
#include "config.h"
#include <Arduino.h>

// --- IMU I2C pins (raw nRF52840 pin numbers, not Arduino Dx) ---
#define IMU_SDA  7   // P0.07
#define IMU_SCL  27  // P0.27
#define IMU_ADDR 0x6A

// --- LSM6DS3TR-C registers ---
#define REG_WHO_AM_I     0x0F  // Should return 0x6A
#define REG_CTRL1_XL     0x10  // Accel ODR + full-scale
#define REG_CTRL2_G      0x11  // Gyro ODR + full-scale
#define REG_CTRL3_C      0x12  // Control (BDU, IF_INC)
#define REG_WAKE_UP_SRC  0x1B  // Wake-up interrupt source
#define REG_TAP_CFG      0x58  // Interrupt enable + slope filter
#define REG_WAKE_UP_THS  0x5B  // Wake-up threshold
#define REG_WAKE_UP_DUR  0x5C  // Wake-up duration
#define REG_MD1_CFG      0x5E  // INT1 routing

// --- State ---
static volatile bool _wakeFlag = false;
static bool _ready = false;
static uint8_t _lastWhoAmI = 0;

static void imuISR() {
    _wakeFlag = true;
}

// --- TWIM1 pin management ---

static void twim1_setup(uint8_t sda, uint8_t scl) {
    NRF_TWIM1->ENABLE = 0;
    // Explicitly disconnect old pin assignments (nRF52840 errata)
    NRF_TWIM1->PSEL.SDA = 0xFFFFFFFF;
    NRF_TWIM1->PSEL.SCL = 0xFFFFFFFF;
    // Configure new GPIO pins for I2C (open-drain, pull-up)
    NRF_P0->PIN_CNF[sda] = (GPIO_PIN_CNF_DIR_Input << GPIO_PIN_CNF_DIR_Pos)
                          | (GPIO_PIN_CNF_INPUT_Connect << GPIO_PIN_CNF_INPUT_Pos)
                          | (GPIO_PIN_CNF_PULL_Pullup << GPIO_PIN_CNF_PULL_Pos)
                          | (GPIO_PIN_CNF_DRIVE_S0D1 << GPIO_PIN_CNF_DRIVE_Pos);
    NRF_P0->PIN_CNF[scl] = (GPIO_PIN_CNF_DIR_Input << GPIO_PIN_CNF_DIR_Pos)
                          | (GPIO_PIN_CNF_INPUT_Connect << GPIO_PIN_CNF_INPUT_Pos)
                          | (GPIO_PIN_CNF_PULL_Pullup << GPIO_PIN_CNF_PULL_Pos)
                          | (GPIO_PIN_CNF_DRIVE_S0D1 << GPIO_PIN_CNF_DRIVE_Pos);
    // Assign new pins
    NRF_TWIM1->PSEL.SDA = sda;
    NRF_TWIM1->PSEL.SCL = scl;
    NRF_TWIM1->FREQUENCY = TWIM_FREQUENCY_FREQUENCY_K100;
    NRF_TWIM1->SHORTS = TWIM_SHORTS_LASTTX_STOP_Msk;
    NRF_TWIM1->ENABLE = (TWIM_ENABLE_ENABLE_Enabled << TWIM_ENABLE_ENABLE_Pos);
}

static void twim1_force_stop() {
    NRF_TWIM1->EVENTS_ERROR = 0;
    NRF_TWIM1->ERRORSRC = NRF_TWIM1->ERRORSRC;
    NRF_TWIM1->EVENTS_STOPPED = 0;
    NRF_TWIM1->TASKS_STOP = 1;
    for (uint32_t t = 100000; t; t--) {
        if (NRF_TWIM1->EVENTS_STOPPED) break;
    }
    NRF_TWIM1->EVENTS_STOPPED = 0;
}

// --- IMU I2C transactions (static buffers for DMA safety) ---

static uint8_t _tx[2];
static uint8_t _rx[1];

static bool imu_write_reg(uint8_t reg, uint8_t val) {
    _tx[0] = reg;
    _tx[1] = val;
    NRF_TWIM1->ADDRESS = IMU_ADDR;
    NRF_TWIM1->TXD.PTR = (uint32_t)_tx;
    NRF_TWIM1->TXD.MAXCNT = 2;
    NRF_TWIM1->SHORTS = TWIM_SHORTS_LASTTX_STOP_Msk;
    NRF_TWIM1->EVENTS_STOPPED = 0;
    NRF_TWIM1->EVENTS_ERROR = 0;
    NRF_TWIM1->TASKS_STARTTX = 1;

    for (uint32_t t = 500000; t; t--) {
        if (NRF_TWIM1->EVENTS_STOPPED) {
            NRF_TWIM1->EVENTS_STOPPED = 0;
            return true;
        }
        if (NRF_TWIM1->EVENTS_ERROR) {
            twim1_force_stop();
            return false;
        }
    }
    twim1_force_stop();
    return false;
}

static bool imu_read_reg(uint8_t reg, uint8_t* out) {
    _tx[0] = reg;
    NRF_TWIM1->ADDRESS = IMU_ADDR;
    NRF_TWIM1->TXD.PTR = (uint32_t)_tx;
    NRF_TWIM1->TXD.MAXCNT = 1;
    NRF_TWIM1->RXD.PTR = (uint32_t)_rx;
    NRF_TWIM1->RXD.MAXCNT = 1;
    NRF_TWIM1->SHORTS = TWIM_SHORTS_LASTTX_STARTRX_Msk | TWIM_SHORTS_LASTRX_STOP_Msk;
    NRF_TWIM1->EVENTS_STOPPED = 0;
    NRF_TWIM1->EVENTS_ERROR = 0;
    NRF_TWIM1->TASKS_STARTTX = 1;

    for (uint32_t t = 500000; t; t--) {
        if (NRF_TWIM1->EVENTS_STOPPED) {
            NRF_TWIM1->EVENTS_STOPPED = 0;
            NRF_TWIM1->SHORTS = TWIM_SHORTS_LASTTX_STOP_Msk;
            *out = _rx[0];
            return true;
        }
        if (NRF_TWIM1->EVENTS_ERROR) {
            twim1_force_stop();
            NRF_TWIM1->SHORTS = TWIM_SHORTS_LASTTX_STOP_Msk;
            return false;
        }
    }
    twim1_force_stop();
    NRF_TWIM1->SHORTS = TWIM_SHORTS_LASTTX_STOP_Msk;
    return false;
}

// --- Bus conditioning (required before TWIM1 will work) ---

static void bus_condition(uint8_t sda, uint8_t scl) {
    // Strong push-pull config (H0H1) — needed to reliably drive bus after power-on
    static const uint32_t DRIVE_CFG =
        (GPIO_PIN_CNF_DIR_Output << GPIO_PIN_CNF_DIR_Pos)
        | (GPIO_PIN_CNF_INPUT_Connect << GPIO_PIN_CNF_INPUT_Pos)
        | (GPIO_PIN_CNF_PULL_Pullup << GPIO_PIN_CNF_PULL_Pos)
        | (GPIO_PIN_CNF_DRIVE_H0H1 << GPIO_PIN_CNF_DRIVE_Pos);

    // Drive both lines HIGH with strong push-pull, let bus settle
    NRF_P0->PIN_CNF[sda] = DRIVE_CFG;
    NRF_P0->PIN_CNF[scl] = DRIVE_CFG;
    NRF_P0->OUTSET = (1UL << sda) | (1UL << scl);
    delay(10);

    // Bus recovery: toggle SCL 18 times to clear any stuck slave
    for (int i = 0; i < 18; i++) {
        NRF_P0->OUTCLR = (1UL << scl);
        delayMicroseconds(5);
        NRF_P0->OUTSET = (1UL << scl);
        delayMicroseconds(5);
    }

    // STOP condition: SDA LOW→HIGH while SCL HIGH
    NRF_P0->OUTCLR = (1UL << sda);
    delayMicroseconds(5);
    NRF_P0->OUTSET = (1UL << scl);
    delayMicroseconds(5);
    NRF_P0->OUTSET = (1UL << sda);
    delay(5);

    // Reset to floating before TWIM1 takes over
    NRF_P0->PIN_CNF[sda] = 0;
    NRF_P0->PIN_CNF[scl] = 0;
}

// --- Public API ---

void imuBegin() {
    // CRITICAL POWER-ON SEQUENCE:
    // 1. Float I2C pins (no pull-ups — ESD diodes clamp unpowered IMU to GND)
    // 2. Power on, wait 200ms
    // 3. Condition the bus (pull-ups + 9 SCL clocks)
    // 4. THEN enable TWIM1

    // 1. Ensure IMU I2C pins are floating
    NRF_P0->PIN_CNF[IMU_SDA] = 0;
    NRF_P0->PIN_CNF[IMU_SCL] = 0;

    // 2. Power on IMU
    pinMode(PIN_LSM6DS3TR_C_POWER, OUTPUT);
    digitalWrite(PIN_LSM6DS3TR_C_POWER, HIGH);
    delay(200);

    // 3. Condition the bus (pull-ups + recovery clocks)
    bus_condition(IMU_SDA, IMU_SCL);

    // 4. NOW swap TWIM1 to IMU pins
    twim1_setup(IMU_SDA, IMU_SCL);
    delay(5);

    // Verify chip ID (retry up to 3 times)
    uint8_t id = 0;
    bool i2c_ok = false;
    for (int attempt = 0; attempt < 3; attempt++) {
        i2c_ok = imu_read_reg(REG_WHO_AM_I, &id);
        if (i2c_ok && id == 0x6A) break;
        delay(10);
    }
    _lastWhoAmI = id;
    if (!i2c_ok || id != 0x6A) {
        Serial.printf("imu: WHO_AM_I failed (i2c=%d, id=0x%02X), skipping\n", i2c_ok, id);
        twim1_setup(PIN_SDA, PIN_SCL);
        return;
    }
    Serial.println("imu: LSM6DS3TR-C detected");

    // Configure wake-on-motion
    imu_write_reg(REG_CTRL1_XL, 0x20);     // Accel 26 Hz, +/-2g (low-power)
    imu_write_reg(REG_CTRL2_G,  0x00);     // Gyro off (saves power)
    imu_write_reg(REG_CTRL3_C,  0x44);     // BDU=1, IF_INC=1
    imu_write_reg(REG_TAP_CFG,  0x80);     // INTERRUPTS_ENABLE=1, slope filter, LIR=0
    imu_write_reg(REG_WAKE_UP_THS, 0x06);  // Threshold: 6 * FS/64 = 375mg at +/-2g
    imu_write_reg(REG_WAKE_UP_DUR, 0x00);  // Any single sample above threshold
    imu_write_reg(REG_MD1_CFG,  0x20);     // Route wake-up to INT1

    // Clear any pending interrupt
    uint8_t src;
    imu_read_reg(REG_WAKE_UP_SRC, &src);

    // Restore TWIM1 to display pins
    twim1_setup(PIN_SDA, PIN_SCL);

    // Attach hardware interrupt on INT1
    pinMode(PIN_LSM6DS3TR_C_INT1, INPUT_PULLDOWN);
    attachInterrupt(digitalPinToInterrupt(PIN_LSM6DS3TR_C_INT1), imuISR, RISING);

    _ready = true;
    Serial.println("imu: wake-on-motion active (125mg threshold)");
}

bool imuWoke() {
    if (_wakeFlag) {
        _wakeFlag = false;
        return true;
    }
    return false;
}

bool imuReady() { return _ready; }
uint8_t imuWhoAmI() { return _lastWhoAmI; }
