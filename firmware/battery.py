"""Battery voltage monitor for Roam.

Reads VSYS/3 via ADC3 (GPIO29) on the Pico 2 W. The wireless chip shares
GPIO25 with the SPI clock, so we must set it high before reading ADC to
avoid bus contention.

LiPo discharge curve (approximate):
  4.2V = 100%, 3.7V = 50%, 3.3V = 10%, 3.0V = 0%
"""

import machine
import time


class Battery:
    """Monitors LiPo battery voltage via the Pico's VSYS/3 ADC."""

    # LiPo voltage thresholds
    VOLTAGE_FULL = 4.2
    VOLTAGE_NOMINAL = 3.7
    VOLTAGE_LOW = 3.3
    VOLTAGE_EMPTY = 3.0

    # ADC reference voltage and divider ratio
    ADC_VREF = 3.3
    ADC_RESOLUTION = 65535  # 16-bit ADC
    VSYS_DIVIDER = 3.0     # VSYS is divided by 3 before reaching ADC

    def __init__(self, read_interval_s=60):
        self._adc = machine.ADC(29)  # ADC3 on GPIO29
        # GP25 must be driven high to read VSYS on wireless-enabled boards
        self._gp25 = machine.Pin(25, machine.Pin.OUT)
        self._read_interval = read_interval_s
        self._voltage = 0.0
        self._percent = 0
        self._last_read = 0

    @property
    def voltage(self):
        """Last measured battery voltage."""
        return self._voltage

    @property
    def percent(self):
        """Last calculated battery percentage (0-100)."""
        return self._percent

    @property
    def is_low(self):
        """True if battery is below 10%."""
        return self._percent <= 10

    def read(self):
        """Take a single battery voltage reading.

        Sets GP25 high to avoid SPI bus contention with the CYW43439,
        reads ADC, then releases GP25. Averages 3 samples for stability.

        Note: On Pimoroni Pico Plus 2 W, the VSYS divider ratio may differ
        from the standard Pico 2 W. If readings are incorrect, adjust
        VSYS_DIVIDER or use the Pimoroni-specific voltage reading method.
        """
        self._gp25.value(1)
        time.sleep_ms(1)  # Settling time

        # Average 3 samples
        total = 0
        for _ in range(3):
            total += self._adc.read_u16()
            time.sleep_ms(1)
        raw = total // 3

        adc_voltage = (raw / self.ADC_RESOLUTION) * self.ADC_VREF
        self._voltage = adc_voltage * self.VSYS_DIVIDER

        self._gp25.value(0)

        # Sanity check: USB power should read ~5V, LiPo 3.0-4.2V
        # If reading is nonsensical, assume USB power
        if self._voltage < 1.0 or self._voltage > 6.0:
            self._voltage = 5.0  # Assume USB power
            self._percent = 100
        else:
            self._percent = self._voltage_to_percent(self._voltage)

        self._last_read = time.ticks_ms()
        return self._voltage

    def should_read(self):
        """Check if enough time has elapsed for a new reading."""
        if self._last_read == 0:
            return True
        elapsed = time.ticks_diff(time.ticks_ms(), self._last_read)
        return elapsed >= self._read_interval * 1000

    def _voltage_to_percent(self, v):
        """Convert battery voltage to percentage using piecewise linear approximation.

        LiPo curve:
          4.2V -> 100%
          3.7V -> 50%
          3.3V -> 10%
          3.0V -> 0%
        """
        if v >= self.VOLTAGE_FULL:
            return 100
        elif v >= self.VOLTAGE_NOMINAL:
            # 3.7-4.2V maps to 50-100%
            return int(50 + (v - self.VOLTAGE_NOMINAL) / (self.VOLTAGE_FULL - self.VOLTAGE_NOMINAL) * 50)
        elif v >= self.VOLTAGE_LOW:
            # 3.3-3.7V maps to 10-50%
            return int(10 + (v - self.VOLTAGE_LOW) / (self.VOLTAGE_NOMINAL - self.VOLTAGE_LOW) * 40)
        elif v >= self.VOLTAGE_EMPTY:
            # 3.0-3.3V maps to 0-10%
            return int((v - self.VOLTAGE_EMPTY) / (self.VOLTAGE_LOW - self.VOLTAGE_EMPTY) * 10)
        else:
            return 0
