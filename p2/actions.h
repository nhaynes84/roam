// Roam P2 — HID action dispatcher
// Maps ActionType enum to BLEHidAdafruit calls

#pragma once

#include "config.h"
#include <bluefruit.h>

void actionsBegin();
void executeAction(ActionType action);
void bleSwitch();  // Disconnect + reject reconnections from current device
