# Coldcard Mk5 WebAssembly variant — display override.
#
# Replaces shared/display.py for the WASM build. The on-device version
# drives the SSD1306 OLED over SPI; under WASM we emit framebuffer
# bytes to a JS callback (window.coldcardScreenPaint) instead. Same
# 128×64 mono pixel format, packed per upstream ssd1306.py convention
# (8 pixels per byte, vertical column order, page rows 0..7).
#
# Per AD-5: bytes flow JS-ward via this stub; key codes flow Py-ward via
# the numpad override.
import framebuf
import js

WIDTH = 128
HEIGHT = 64

_buf = bytearray(WIDTH * HEIGHT // 8)
_fb = framebuf.FrameBuffer(_buf, WIDTH, HEIGHT, framebuf.MONO_VLSB)


class Display:
    WIDTH = WIDTH
    HEIGHT = HEIGHT

    def __init__(self):
        self.dis = _fb
        self.last_buf = None

    def clear(self):
        _fb.fill(0)

    def show(self):
        # The JS side reads framebuffer bytes directly from MEMFS; the
        # snapshot at /work/screen.bin is the source of truth so the page
        # can repaint on resize without re-running Python.
        try:
            with open('/work/screen.bin', 'wb') as f:
                f.write(bytes(_buf))
        except OSError:
            pass
        if hasattr(js, 'coldcardScreenPaint'):
            js.coldcardScreenPaint(bytes(_buf))

    def text(self, msg, x, y, invert=False, font=None):
        _fb.text(msg, x, y, 0 if invert else 1)

    def fill_rect(self, x, y, w, h, c=1):
        _fb.fill_rect(x, y, w, h, c)

    def hline(self, x, y, w, c=1):
        _fb.hline(x, y, w, c)


def init():
    return Display()
