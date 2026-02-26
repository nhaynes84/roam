"""SH1106 I2C OLED driver for MicroPython.

Handles the SH1106 controller's 132-column buffer (vs 128 visible pixels)
by applying a 2-pixel column offset. Implements the standard MicroPython
FrameBuffer interface for use with the framebuf module.

Based on the community SH1106 driver with cleanup for production use.
"""

import framebuf
import time


# SH1106 commands
_SET_CONTRAST = const(0x81)
_SET_ENTIRE_ON = const(0xA4)
_SET_NORM_INV = const(0xA6)
_SET_DISP = const(0xAE)
_SET_MEM_ADDR = const(0x20)
_SET_COL_ADDR = const(0x21)
_SET_PAGE_ADDR = const(0x22)
_SET_DISP_START_LINE = const(0x40)
_SET_SEG_REMAP = const(0xA0)
_SET_MUX_RATIO = const(0xA8)
_SET_COM_OUT_DIR = const(0xC0)
_SET_DISP_OFFSET = const(0xD3)
_SET_COM_PIN_CFG = const(0xDA)
_SET_DISP_CLK_DIV = const(0xD5)
_SET_PRECHARGE = const(0xD9)
_SET_VCOM_DESEL = const(0xDB)
_SET_CHARGE_PUMP = const(0x8D)
_SET_LOW_COLUMN = const(0x00)
_SET_HIGH_COLUMN = const(0x10)
_SET_PAGE_ADDR_SH1106 = const(0xB0)


class SH1106_I2C:
    """SH1106 OLED display driver over I2C.

    Args:
        width: Display width in pixels (typically 128).
        height: Display height in pixels (typically 64).
        i2c: Initialized machine.I2C instance.
        addr: I2C address (default 0x3C).
        rotate: 180-degree rotation if True.
    """

    def __init__(self, width, height, i2c, addr=0x3C, rotate=False):
        self.width = width
        self.height = height
        self.i2c = i2c
        self.addr = addr
        self.rotate = rotate
        self.pages = height // 8
        self.offset = 2  # SH1106 has 132 columns, offset by 2 for 128-wide display

        # Framebuffer for drawing operations
        self.buffer = bytearray(width * self.pages)
        self.fb = framebuf.FrameBuffer(self.buffer, width, height, framebuf.MONO_VLSB)

        # I2C command/data buffers
        self._cmd_buf = bytearray(2)
        self._cmd_buf[0] = 0x80  # Co=1, D/C#=0 (command)

        self._init_display()

    def _init_display(self):
        """Initialize the SH1106 with standard settings."""
        cmds = [
            _SET_DISP | 0x00,           # Display off
            _SET_DISP_CLK_DIV, 0x80,    # Clock divide ratio/oscillator frequency
            _SET_MUX_RATIO, self.height - 1,
            _SET_DISP_OFFSET, 0x00,     # No display offset
            _SET_DISP_START_LINE | 0x00,
            _SET_CHARGE_PUMP, 0x14,     # Enable charge pump
            _SET_MEM_ADDR, 0x00,        # Horizontal addressing mode
        ]

        if self.rotate:
            cmds += [_SET_SEG_REMAP | 0x00, _SET_COM_OUT_DIR]
        else:
            cmds += [_SET_SEG_REMAP | 0x01, _SET_COM_OUT_DIR | 0x08]

        cmds += [
            _SET_COM_PIN_CFG, 0x12 if self.height > 32 else 0x02,
            _SET_CONTRAST, 0x7F,        # Medium contrast
            _SET_PRECHARGE, 0xF1,       # Pre-charge period
            _SET_VCOM_DESEL, 0x40,      # VCOMH deselect level
            _SET_ENTIRE_ON,             # Output follows RAM
            _SET_NORM_INV,              # Non-inverted display
            _SET_DISP | 0x01,           # Display on
        ]

        for cmd in cmds:
            self._write_cmd(cmd)

    def _write_cmd(self, cmd):
        """Send a single command byte."""
        self._cmd_buf[1] = cmd
        self.i2c.writeto(self.addr, self._cmd_buf)

    def show(self):
        """Write the framebuffer to the display, page by page.

        SH1106 doesn't support horizontal addressing across pages like SSD1306,
        so we must set the page and column address for each page individually.
        """
        for page in range(self.pages):
            self._write_cmd(_SET_PAGE_ADDR_SH1106 | page)
            self._write_cmd(_SET_LOW_COLUMN | (self.offset & 0x0F))
            self._write_cmd(_SET_HIGH_COLUMN | (self.offset >> 4))

            # Data prefix: Co=0, D/C#=1 (data stream)
            start = page * self.width
            data = bytearray(1)
            data[0] = 0x40
            data += self.buffer[start:start + self.width]
            self.i2c.writeto(self.addr, data)

    def fill(self, color):
        """Fill the entire display."""
        self.fb.fill(color)

    def pixel(self, x, y, color=None):
        """Get or set a pixel."""
        if color is None:
            return self.fb.pixel(x, y)
        self.fb.pixel(x, y, color)

    def text(self, string, x, y, color=1):
        """Draw text at position (x, y)."""
        self.fb.text(string, x, y, color)

    def hline(self, x, y, w, color=1):
        """Draw a horizontal line."""
        self.fb.hline(x, y, w, color)

    def vline(self, x, y, h, color=1):
        """Draw a vertical line."""
        self.fb.vline(x, y, h, color)

    def rect(self, x, y, w, h, color=1):
        """Draw a rectangle outline."""
        self.fb.rect(x, y, w, h, color)

    def fill_rect(self, x, y, w, h, color=1):
        """Draw a filled rectangle."""
        self.fb.fill_rect(x, y, w, h, color)

    def scroll(self, dx, dy):
        """Scroll the framebuffer."""
        self.fb.scroll(dx, dy)

    def contrast(self, value):
        """Set display contrast (0-255)."""
        self._write_cmd(_SET_CONTRAST)
        self._write_cmd(value)

    def invert(self, invert):
        """Invert display colors."""
        self._write_cmd(_SET_NORM_INV | (invert & 1))

    def poweroff(self):
        """Turn off the display."""
        self._write_cmd(_SET_DISP | 0x00)

    def poweron(self):
        """Turn on the display."""
        self._write_cmd(_SET_DISP | 0x01)
