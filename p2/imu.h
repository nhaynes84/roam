// Roam P2 — IMU wake-on-motion (LSM6DS3TR-C on XIAO Sense internal I2C)

#pragma once
#include <stdint.h>

void imuBegin();
bool imuWoke();      // Returns true if motion wake occurred since last check
bool imuReady();     // Returns true if IMU was detected and configured
uint8_t imuWhoAmI(); // Last WHO_AM_I value read (0x6A = success)
