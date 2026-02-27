// Roam — HID action dispatcher
// Maps ActionType enum to KeyboardBLE calls

#pragma once

#include "config.h"
#include <KeyboardBLE.h>

void actionsBegin();
void executeAction(ActionType action);
